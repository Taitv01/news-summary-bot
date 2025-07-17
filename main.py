#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import feedparser
import json
import os
import logging
import time
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
    file_path = 'data/processed_links.json'
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except json.JSONDecodeError:
            logger.warning(f"Lỗi đọc file {file_path}. Bắt đầu với danh sách rỗng.")
            return set()
    return set()

def save_processed_links(links):
    """Lưu danh sách các link đã xử lý."""
    os.makedirs('data', exist_ok=True)
    with open('data/processed_links.json', 'w', encoding='utf-8') as f:
        json.dump(list(links), f, ensure_ascii=False, indent=2)

def split_message(text: str, limit: int = 4000) -> list[str]:
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

def process_news():
    """Quy trình xử lý tin tức chính."""
    logger.info("--- Bot tóm tắt tin tức bắt đầu chạy ---")
    scraper = NewsScraper()
    
    try:
        processed_links = load_processed_links()
        logger.info(f"Đã tải {len(processed_links)} links đã xử lý.")
        
        rss_sources = load_rss_sources()
        logger.info("Đang kiểm tra tin tức từ tất cả các nguồn RSS...")
        
        new_articles = []
        for source_name, rss_url in rss_sources.items():
            logger.info(f"-> Đang lấy từ: {source_name}")
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                if entry.link not in processed_links:
                    new_articles.append({'title': entry.title, 'link': entry.link})
        
        if not new_articles:
            logger.info("Không có bài báo mới.")
            return

        logger.info(f"Phát hiện {len(new_articles)} bài báo mới. Bắt đầu thu thập nội dung...")
        
        all_articles_content = []
        for article in new_articles:
            response = scraper.get_content_with_retry(article['link'])
            if response and response.status_code == 200:
                content = extract_content(response.text, article['link'])
                if content:
                    full_content = f"TIÊU ĐỀ: {article['title']}\nNỘI DUNG:\n{content}"
                    all_articles_content.append(full_content)
                    processed_links.add(article['link'])

        if not all_articles_content:
            logger.warning("Không thu thập được nội dung từ bất kỳ bài báo mới nào.")
            return

        logger.info(f"Đã thu thập {len(all_articles_content)} bài báo. Gộp lại và gửi đi tóm tắt...")
        combined_text = "\n\n---HẾT BÀI BÁO---\n\n".join(all_articles_content)
        
        final_summary = summarize_with_gemini(combined_text)
        
        logger.info("Đã nhận tóm tắt từ AI. Chuẩn bị chia và gửi tin nhắn...")
        
        # Thêm tiêu đề chung cho bản tin
        final_summary_with_header = f"📰 *BẢN TIN TỔNG HỢP HÔM NAY*\n\n{final_summary}"
        escaped_summary = escape_markdown_v2(final_summary_with_header)
        
        message_chunks = split_message(escaped_summary, 4000)
        
        for i, chunk in enumerate(message_chunks):
            # Nếu có nhiều phần, thêm ghi chú phần
            if len(message_chunks) > 1:
                chunk_to_send = f"*(Phần {i+1}/{len(message_chunks)})*\n\n{chunk}"
            else:
                chunk_to_send = chunk
            
            send_telegram_message(chunk_to_send)
            time.sleep(1)

    finally:
        save_processed_links(processed_links)
        scraper.close()
        logger.info("--- Hoàn tất chu kỳ. ---")

if __name__ == "__main__":
    process_news()
