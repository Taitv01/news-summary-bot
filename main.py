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
    """Tải các nguồn RSS từ cấu hình."""
    return {
        'VnExpress Mới nhất': 'https://vnexpress.net/rss/tin-moi-nhat.rss',
        'VnExpress Kinh doanh': 'https://vnexpress.net/rss/kinh-doanh.rss',
        'Vietstock Chứng khoán': 'https://vietstock.vn/rss/chung-khoan.rss',
        'Lao Động': 'https://laodong.vn/rss/tin-moi-nhat.rss'
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
    """Quy trình xử lý tin tức chính."""
    logger.info("--- Bot tóm tắt tin tức bắt đầu chạy ---")
    scraper = NewsScraper()
    
    try:
        processed_links = load_processed_links()
        rss_sources = load_rss_sources()
        logger.info("Đang kiểm tra tin tức từ tất cả các nguồn RSS...")
        
        # Lấy bài báo mới
        new_articles = []
        for source_name, rss_url in rss_sources.items():
            logger.info(f"-> Đang lấy từ: {source_name}")
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
                    if entry.link not in processed_links:
                        new_articles.append(Article(title=entry.title, link=entry.link))
            except Exception as e:
                logger.error(f"Lỗi khi lấy RSS từ {source_name}: {e}")
                continue
        
        if not new_articles:
            logger.info("Không có bài báo mới.")
            return

        logger.info(f"Phát hiện {len(new_articles)} bài báo mới. Bắt đầu thu thập nội dung...")
        
        # Xử lý song song với ThreadPoolExecutor
        successful_articles = []
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            future_to_article = {
                executor.submit(process_single_article, article, scraper): article 
                for article in new_articles
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

        logger.info(f"Đã thu thập {len(successful_articles)} bài báo. Tạo tóm tắt...")
        
        # Gộp nội dung và tóm tắt
        combined_text = "\n\n---HẾT BÀI BÁO---\n\n".join(
            article.content for article in successful_articles
        )
        
        final_summary = summarize_with_gemini(combined_text)
        
        logger.info("Đã nhận tóm tắt từ AI. Chuẩn bị gửi tin nhắn...")
        
        # Xử lý và gửi tin nhắn
        escaped_content = escape_markdown_v2(final_summary)
        full_message_body = f"📰 *BẢN TIN TỔNG HỢP HÔM NAY*\n\n{escaped_content}"
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
