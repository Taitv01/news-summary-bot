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

        logger.info(f"Phát hiện {len(new_articles)} bài báo mới. Bắt đầu xử lý...")
        
        # VÒNG LẶP 1: THU THẬP VÀ TÓM TẮT
        articles_to_send = []
        for article in new_articles:
            logger.info(f"Đang xử lý: {article['title'][:40]}...")
            response = scraper.get_content_with_retry(article['link'])
            
            if response and response.status_code == 200:
                content = extract_content(response.text, article['link'])
                if content:
                    logger.info("-> Lấy nội dung thành công, đang gửi đi tóm tắt...")
                    summary = summarize_with_gemini(content)
                    article['summary'] = summary
                    articles_to_send.append(article)
                    processed_links.add(article['link'])
                else:
                    logger.warning("-> Không trích xuất được nội dung.")
            else:
                logger.warning("-> Không tải được trang.")

        # VÒNG LẶP 2: GỬI KẾT QUẢ TỚI TELEGRAM
        if articles_to_send:
            logger.info(f"Đã xử lý xong. Chuẩn bị gửi {len(articles_to_send)} tin nhắn đến Telegram.")
            for article in articles_to_send:
                # Sử dụng hàm escape chuyên dụng để xử lý các ký tự đặc biệt
                title = escape_markdown_v2(article['title'])
                summary_text = escape_markdown_v2(article.get('summary', 'Không có tóm tắt'))
                link = article['link'] # Link không cần escape

                message = f"📰 *{title}*\n\n{summary_text}\n\n[Đọc bài viết đầy đủ]({link})"
                send_telegram_message(message)
                time.sleep(1) # Chờ 1 giây để tránh spam Telegram
        else:
            logger.warning("Không có bài báo nào được xử lý thành công.")

    finally:
        save_processed_links(processed_links)
        scraper.close()
        logger.info("--- Hoàn tất chu kỳ. ---")

if __name__ == "__main__":
    process_news()
