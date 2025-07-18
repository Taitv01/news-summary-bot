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

# Constants
MAX_ARTICLES_PER_SOURCE = 10
MESSAGE_LIMIT = 4000
DATA_DIR = 'data'
PROCESSED_LINKS_FILE = os.path.join(DATA_DIR, 'processed_links.json')
MAX_CONCURRENT_REQUESTS = 3

@dataclass
class Article:
    """Cấu trúc dữ liệu cho bài báo."""
    title: str
    link: str
    content: Optional[str] = None

def load_rss_sources():
    """Tải các nguồn RSS từ cấu hình với nhiều nguồn tin đáng tin cậy."""
    return {
        # Báo chí chính thống
        'VnExpress Mới nhất': 'https://vnexpress.net/rss/tin-moi-nhat.rss',
        'VnExpress Kinh doanh': 'https://vnexpress.net/rss/kinh-doanh.rss',
        'VnExpress Thể thao': 'https://vnexpress.net/rss/the-thao.rss',
        'Tuổi Trẻ': 'https://tuoitre.vn/rss/tin-moi-nhat.rss',
        'Thanh Niên': 'https://thanhnien.vn/rss/home.rss',
        'Dân Trí': 'https://dantri.com.vn/rss/trangchu.rss',
        'Vietnamnet': 'https://vietnamnet.vn/rss/tin-moi-nhat.rss',
        
        # Kinh tế - Tài chính
        'Vietstock': 'https://vietstock.vn/rss/chung-khoan.rss',
        'CafeF': 'https://cafef.vn/rss/trang-chu.rss',
        'Đầu tư Online': 'https://baodautu.vn/rss/tin-moi-nhat.rss',
        'Thời báo Kinh tế': 'https://thesaigontimes.vn/rss/home.rss',
        
        # Tin tức xã hội
        'Lao Động': 'https://laodong.vn/rss/tin-moi-nhat.rss',
        'Pháp luật TP.HCM': 'https://plo.vn/rss/home.rss',
        'Công An Nhân Dân': 'https://cand.com.vn/rss/home.rss',
        
        # Công nghệ
        'Genk': 'https://genk.vn/rss/trang-chu.rss',
        'ICTnews': 'https://ictnews.vn/rss/home.rss',
        'VnReview': 'https://vnreview.vn/rss/home.rss',
        
        # Giải trí & Lifestyle
        'Zing News': 'https://zingnews.vn/rss/home.rss',
        'Kenh14': 'https://kenh14.vn/rss/home.rss',
        'Eva': 'https://eva.vn/rss/home.rss',
        
        # Quốc tế
        'BBC Tiếng Việt': 'https://www.bbc.com/vietnamese/rss.xml',
        'VOV': 'https://vov.vn/rss/tin-moi-nhat.rss',
        'VOA Tiếng Việt': 'https://www.voatiengviet.com/rss/rss.xml'
    }

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

def fetch_rss_with_fallback(source_name: str, rss_url: str, max_retries: int = 3) -> List[Article]:
    """Lấy RSS với cơ chế retry và fallback."""
    for attempt in range(max_retries):
        try:
            logger.info(f"-> Đang lấy từ: {source_name} (lần thử {attempt + 1})")
            
            # Thêm headers để tránh bị block
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Parse RSS với timeout
            feed = feedparser.parse(rss_url, request_headers=headers)
            
            if feed.bozo:
                logger.warning(f"Lỗi parsing RSS từ {source_name}: {feed.bozo_exception}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    return []
            
            articles = []
            for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
                if hasattr(entry, 'link') and hasattr(entry, 'title'):
                    articles.append(Article(
                        title=entry.title,
                        link=entry.link
                    ))
            
            if articles:
                logger.info(f"✓ Lấy thành công {len(articles)} bài từ {source_name}")
            else:
                logger.warning(f"Không có bài báo từ {source_name}")
                
            return articles
            
        except Exception as e:
            logger.error(f"Lỗi khi lấy RSS từ {source_name} (lần {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                logger.error(f"Không thể lấy RSS từ {source_name} sau {max_retries} lần thử")
    
    return []

def process_single_article(article: Article, scraper: NewsScraper) -> Optional[Article]:
    """Xử lý một bài báo."""
    try:
        response = scraper.get_content_with_retry(article.link)
        if response and response.status_code == 200:
            content = extract_content(response.text, article.link)
            if content:
                article.content = f"TIÊU ĐỀ: {article.title}\nNỘI DUNG:\n{content}"
                return article
    except Exception as e:
        logger.error(f"Lỗi khi xử lý bài báo {article.link}: {e}")
    return None

def process_news():
    """Quy trình xử lý tin tức chính với xử lý RSS cải tiến."""
    logger.info("--- Bot tóm tắt tin tức bắt đầu chạy ---")
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
                executor.submit(fetch_rss_with_fallback, source_name, rss_url): source_name
                for source_name, rss_url in rss_sources.items()
            }
            
            for future in as_completed(future_to_source):
                source_name = future_to_source[future]
                try:
                    articles = future.result()
                    if articles:
                        # Lọc bài báo chưa xử lý
                        new_articles = [
                            article for article in articles 
                            if article.link not in processed_links
                        ]
                        all_new_articles.extend(new_articles)
                        successful_sources.append(source_name)
                        logger.info(f"✓ {source_name}: {len(new_articles)} bài mới")
                    else:
                        failed_sources.append(source_name)
                except Exception as e:
                    failed_sources.append(source_name)
                    logger.error(f"Lỗi xử lý nguồn {source_name}: {e}")
        
        # Báo cáo kết quả
        logger.info(f"Kết quả thu thập:")
        logger.info(f"  - Thành công: {len(successful_sources)} nguồn")
        logger.info(f"  - Thất bại: {len(failed_sources)} nguồn")
        if failed_sources:
            logger.warning(f"  - Các nguồn thất bại: {', '.join(failed_sources)}")
        
        logger.info(f"Tổng cộng: {len(all_new_articles)} bài báo mới")
        
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
                    result = future.result()
                    if result and result.content:
                        successful_articles.append(result)
                        processed_links.add(result.link)
                except Exception as e:
                    logger.error(f"Lỗi xử lý bài báo {article.link}: {e}")

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
        
        # Thêm thông tin nguồn vào tóm tắt
        source_info = f"\n\n📊 *Thống kê nguồn tin:*\n✅ {len(successful_sources)} nguồn thành công\n📰 {len(successful_articles)} bài báo được xử lý"
        
        logger.info("Gửi tin nhắn...")
        
        # Xử lý và gửi tin nhắn
        escaped_content = escape_markdown_v2(final_summary)
        escaped_source_info = escape_markdown_v2(source_info)
        full_message_body = f"📰 *BẢN TIN TỔNG HỢP HÔM NAY*\n\n{escaped_content}{escaped_source_info}"
        
        message_chunks = split_message(full_message_body, MESSAGE_LIMIT)
        
        for i, chunk in enumerate(message_chunks):
            message_to_send = chunk
            if len(message_chunks) > 1:
                note = escape_markdown_v2(f"\n\n(Phần {i+1}/{len(message_chunks)})")
                message_to_send += note

            send_telegram_message(message_to_send)
            time.sleep(1)

    except Exception as e:
        logger.error(f"Lỗi trong quá trình xử lý: {e}")
    finally:
        save_processed_links(processed_links)
        scraper.close()
        logger.info("--- Hoàn tất chu kỳ. ---")

if __name__ == "__main__":
    process_news()
