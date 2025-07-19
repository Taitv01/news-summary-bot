#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import feedparser
import json
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Optional
from dataclasses import dataclass

# Imports cho connection handling cải tiến
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scraper import NewsScraper
from content_extractor import extract_content
from telegram_sender import send_telegram_message, escape_markdown_v2
from summarizer import summarize_with_gemini

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants tối ưu
MAX_ARTICLES_PER_SOURCE = 8  # Giảm từ 10 xuống 8
MESSAGE_LIMIT = 4000
DATA_DIR = 'data'
PROCESSED_LINKS_FILE = os.path.join(DATA_DIR, 'processed_links.json')
MAX_CONCURRENT_REQUESTS = 2  # Giảm từ 3 xuống 2

@dataclass
class Article:
    """Cấu trúc dữ liệu cho bài báo."""
    title: str
    link: str
    content: Optional[str] = None

def load_rss_sources():
    """Tải các nguồn RSS đã được kiểm tra và cập nhật."""
    return {
        # Báo chí chính thống - Nguồn ổn định
        'VnExpress Mới nhất': 'https://vnexpress.net/rss/tin-moi-nhat.rss',
        'VnExpress Kinh doanh': 'https://vnexpress.net/rss/kinh-doanh.rss',
        'VnExpress Thể thao': 'https://vnexpress.net/rss/the-thao.rss',
        'Tuổi Trẻ': 'https://tuoitre.vn/rss/tin-moi-nhat.rss',
        'Thanh Niên': 'https://thanhnien.vn/rss/home.rss',
        'Pháp luật TP.HCM': 'https://plo.vn/rss/home.rss', # Nguồn này vẫn ổn định
        
        # Các nguồn đã được cập nhật URL
        'Zing News (Thời sự)': 'https://znews.vn/rss/thoi-su.rss',
        'Lao Động': 'https://laodong.vn/rss/trang-chu.rss',
        'ICTnews (Công nghệ)': 'https://ictnews.vietnamnet.vn/rss/cong-nghe.rss',
        'BBC Tiếng Việt': 'http://feeds.bbci.co.uk/vietnamese/rss.xml',
        'VOV (Tin 24h)': 'https://vov.vn/rss/tin-24h-298.rss',
        'Vietnamplus': 'https://www.vietnamplus.vn/rss/trangchu.rss',
        'Báo Chính phủ': 'https://baochinhphu.vn/rss/chinh-sach-moi.rss',
        'Nhân Dân': 'https://nhandan.vn/api/rss/trang-chu'
    }
def create_robust_session():
    """Tạo session HTTP với retry và pool management."""
    session = requests.Session()
    
    # Cấu hình retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=20,
        pool_block=False
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

def load_processed_links():
    """Tải danh sách các link đã được xử lý."""
    if os.path.exists(PROCESSED_LINKS_FILE):
        try:
            with open(PROCESSED_LINKS_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except json.JSONDecodeError:
            logger.warning(f"Lỗi đọc file {PROCESSED_LINKS_FILE}. Bắt đầu với danh sách rỗng.")
            return set()
    return set()

def save_processed_links(links):
    """Lưu danh sách các link đã xử lý."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROCESSED_LINKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(links), f, ensure_ascii=False, indent=2)

def split_message(text: str, limit: int = MESSAGE_LIMIT) -> List[str]:
    """Chia một đoạn văn bản dài thành nhiều phần nhỏ hơn giới hạn."""
    if len(text) <= limit:
        return [text]
    
    parts = []
    while len(text) > 0:
        if len(text) <= limit:
            parts.append(text)
            break
        split_pos = text.rfind('\n', 0, limit)
        if split_pos == -1:
            split_pos = limit
        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    return parts

def fetch_rss_with_fallback(source_name: str, rss_url: str, session: requests.Session, max_retries: int = 3) -> List[Article]:
    """RSS parser mạnh mẽ với error handling cải tiến."""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache'
    }
    
    for attempt in range(max_retries):
        try:
            logger.info(f"-> Đang lấy từ: {source_name} (lần thử {attempt + 1})")
            
            # Bước 1: Tải RSS với session
            try:
                response = session.get(rss_url, headers=headers, timeout=15)
                response.raise_for_status()
                
                # Kiểm tra content type
                content_type = response.headers.get('content-type', '').lower()
                if 'html' in content_type and 'xml' not in content_type:
                    logger.warning(f"⚠️ {source_name} trả về HTML thay vì RSS")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    else:
                        return []
                        
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Lỗi tải RSS từ {source_name}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    return []
            
            # Bước 2: Parse RSS với feedparser
            try:
                # Làm sạch content trước khi parse
                content = response.text
                
                # Xử lý encoding nếu cần
                if response.encoding:
                    content = content.encode(response.encoding).decode('utf-8', errors='ignore')
                
                # Parse với feedparser
                feed = feedparser.parse(content)
                
                # Kiểm tra lỗi parse
                if feed.bozo:
                    logger.warning(f"⚠️ RSS parsing warning từ {source_name}: {feed.bozo_exception}")
                    
                    # Vẫn tiếp tục nếu có entries
                    if not feed.entries:
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        else:
                            return []
                
            except Exception as e:
                logger.error(f"❌ Lỗi parse RSS từ {source_name}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    return []
            
            # Bước 3: Trích xuất articles
            articles = []
            entries = feed.entries[:MAX_ARTICLES_PER_SOURCE]
            
            for entry in entries:
                try:
                    # Kiểm tra required fields
                    if not (hasattr(entry, 'link') and hasattr(entry, 'title')):
                        continue
                    
                    # Clean title và link
                    title = entry.title.strip()
                    link = entry.link.strip()
                    
                    # Validate URL
                    if not link.startswith(('http://', 'https://')):
                        continue
                    
                    # Loại bỏ các ký tự đặc biệt trong title
                    title = title.replace('\n', ' ').replace('\r', ' ')
                    while '  ' in title:
                        title = title.replace('  ', ' ')
                    
                    articles.append(Article(title=title, link=link))
                    
                except Exception as e:
                    logger.warning(f"⚠️ Lỗi xử lý entry từ {source_name}: {e}")
                    continue
            
            if articles:
                logger.info(f"✅ Lấy thành công {len(articles)} bài từ {source_name}")
                return articles
            else:
                logger.warning(f"⚠️ Không có bài báo hợp lệ từ {source_name}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Lỗi không mong muốn từ {source_name} (lần {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return []
    
    return []

def process_single_article(article: Article, scraper: NewsScraper) -> Optional[Article]:
    """Xử lý một bài báo với error handling cải tiến."""
    try:
        response = scraper.get_content_with_retry(article.link)
        if response and response.status_code == 200:
            content = extract_content(response.text, article.link)
            if content:
                # Làm sạch content
                content = content.strip()
                if len(content) > 10:  # Chỉ lấy nội dung có ý nghĩa
                    article.content = f"TIÊU ĐỀ: {article.title}\nNỘI DUNG:\n{content}"
                    return article
    except Exception as e:
        logger.error(f"❌ Lỗi khi xử lý bài báo {article.link}: {e}")
    return None

def send_health_report(successful_sources, failed_sources, total_articles):
    """Gửi báo cáo tình trạng hệ thống."""
    try:
        if not successful_sources and not failed_sources:
            return
            
        total_sources = len(successful_sources) + len(failed_sources)
        success_rate = len(successful_sources) / total_sources * 100 if total_sources > 0 else 0
        
        # Chỉ gửi báo cáo khi có vấn đề hoặc tỷ lệ thành công thấp
        if failed_sources or success_rate < 70:
            status_emoji = "✅" if success_rate >= 70 else "⚠️" if success_rate >= 50 else "❌"
            
            report = f"""{status_emoji} **Báo cáo News Bot**

📊 **Thống kê:**
• Tỷ lệ thành công: {success_rate:.1f}% ({len(successful_sources)}/{total_sources})
• Bài báo thu thập: {total_articles}
• Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}

✅ **Nguồn thành công:**
{', '.join(successful_sources[:5])}{'...' if len(successful_sources) > 5 else ''}

❌ **Nguồn thất bại:**
{', '.join(failed_sources[:5])}{'...' if len(failed_sources) > 5 else ''}"""
            
            send_telegram_message(report)
            
    except Exception as e:
        logger.error(f"❌ Lỗi gửi báo cáo: {e}")

def process_news():
    """Quy trình xử lý tin tức chính với error handling cải tiến."""
    logger.info("--- Bot tóm tắt tin tức bắt đầu chạy ---")
    
    # Tạo session chung cho RSS
    http_session = create_robust_session()
    scraper = NewsScraper()
    
    try:
        processed_links = load_processed_links()
        rss_sources = load_rss_sources()
        logger.info(f"Đang kiểm tra tin tức từ {len(rss_sources)} nguồn RSS...")
        
        # Lấy bài báo mới với xử lý song song
        all_new_articles = []
        successful_sources = []
        failed_sources = []
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_source = {
                executor.submit(fetch_rss_with_fallback, source_name, rss_url, http_session): source_name
                for source_name, rss_url in rss_sources.items()
            }
            
            for future in as_completed(future_to_source):
                source_name = future_to_source[future]
                try:
                    articles = future.result(timeout=30)  # Timeout cho mỗi source
                    if articles:
                        # Lọc bài báo chưa xử lý
                        new_articles = [
                            article for article in articles 
                            if article.link not in processed_links
                        ]
                        all_new_articles.extend(new_articles)
                        successful_sources.append(source_name)
                        logger.info(f"✅ {source_name}: {len(new_articles)} bài mới")
                    else:
                        failed_sources.append(source_name)
                        logger.warning(f"⚠️ {source_name}: Không có bài báo")
                except Exception as e:
                    failed_sources.append(source_name)
                    logger.error(f"❌ Lỗi xử lý nguồn {source_name}: {e}")
        
        # Báo cáo chi tiết
        total_sources = len(rss_sources)
        success_rate = len(successful_sources) / total_sources * 100
        
        logger.info(f"📊 Kết quả thu thập RSS:")
        logger.info(f"  ✅ Thành công: {len(successful_sources)}/{total_sources} nguồn ({success_rate:.1f}%)")
        logger.info(f"  ❌ Thất bại: {len(failed_sources)} nguồn")
        logger.info(f"  📰 Tổng bài báo mới: {len(all_new_articles)}")
        
        if failed_sources:
            logger.warning(f"  🔸 Nguồn thất bại: {', '.join(failed_sources)}")
        
        # Gửi báo cáo health
        send_health_report(successful_sources, failed_sources, len(all_new_articles))
        
        if not all_new_articles:
            logger.info("Không có bài báo mới.")
            return

        # Xử lý nội dung bài báo
        logger.info("Bắt đầu thu thập nội dung...")
        
        successful_articles = []
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            future_to_article = {
                executor.submit(process_single_article, article, scraper): article 
                for article in all_new_articles
            }
            
            for future in as_completed(future_to_article):
                article = future_to_article[future]
                try:
                    result = future.result(timeout=60)  # Timeout cho mỗi article
                    if result and result.content:
                        successful_articles.append(result)
                        processed_links.add(result.link)
                except Exception as e:
                    logger.error(f"❌ Lỗi xử lý bài báo {article.link}: {e}")

        if not successful_articles:
            logger.warning("Không thu thập được nội dung từ bất kỳ bài báo mới nào.")
            return

        logger.info(f"Đã thu thập thành công {len(successful_articles)} bài báo")
        
        # Tạo tóm tắt cân bằng từ nhiều nguồn
        combined_text = "\n\n---HẾT BÀI BÁO---\n\n".join(
            article.content for article in successful_articles
        )
        
        logger.info("Đang tạo tóm tắt với AI...")
        final_summary = summarize_with_gemini(combined_text)
        
        # Thêm thông tin thống kê vào tóm tắt
        source_info = f"\n\n📊 **Thống kê nguồn tin:**\n✅ {len(successful_sources)} nguồn thành công\n📰 {len(successful_articles)} bài báo được xử lý\n🕐 {time.strftime('%H:%M %d/%m/%Y')}"
        
        logger.info("Gửi tin nhắn...")
        
        # Xử lý và gửi tin nhắn
        escaped_content = escape_markdown_v2(final_summary)
        escaped_source_info = escape_markdown_v2(source_info)
        full_message_body = f"📰 **BẢN TIN TỔNG HỢP HÔM NAY**\n\n{escaped_content}{escaped_source_info}"
        
        message_chunks = split_message(full_message_body, MESSAGE_LIMIT)
        
        for i, chunk in enumerate(message_chunks):
            message_to_send = chunk
            if len(message_chunks) > 1:
                note = escape_markdown_v2(f"\n\n(Phần {i+1}/{len(message_chunks)})")
                message_to_send += note

            send_telegram_message(message_to_send)
            time.sleep(1)

    except Exception as e:
        logger.error(f"❌ Lỗi chính trong quá trình xử lý: {e}")
        # Gửi thông báo lỗi
        try:
            error_msg = f"🚨 **LỖI BOT TIN TỨC**\n\n{str(e)[:500]}..."
            send_telegram_message(error_msg)
        except:
            pass
    finally:
        # Cleanup resources
        try:
            if 'http_session' in locals():
                http_session.close()
            if 'scraper' in locals():
                scraper.close()
        except:
            pass
        
        save_processed_links(processed_links)
        logger.info("--- Hoàn tất chu kỳ. ---")

if __name__ == "__main__":
    process_news()
