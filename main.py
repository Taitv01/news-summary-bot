#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
News Summarizer Bot
Tự động lấy và tóm tắt tin tức từ các nguồn RSS
"""

import feedparser
import json
import os
from datetime import datetime
import time
import logging
from scraper import NewsScraper
from selectors import extract_content

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
    """Load RSS sources từ file config"""
    return {
        'VnExpress Mới nhất': 'https://vnexpress.net/rss/tin-moi-nhat.rss',
        'VnExpress Kinh doanh': 'https://vnexpress.net/rss/kinh-doanh.rss',
        'Vietstock Chứng khoán': 'https://vietstock.vn/rss/chung-khoan.rss',
        'Lao Động': 'https://laodong.vn/rss/tin-moi-nhat.rss'
    }

def load_processed_links():
    """Load danh sách links đã xử lý"""
    file_path = 'data/processed_links.json'
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_processed_links(links):
    """Lưu danh sách links đã xử lý"""
    os.makedirs('data', exist_ok=True)
    with open('data/processed_links.json', 'w', encoding='utf-8') as f:
        json.dump(list(links), f, ensure_ascii=False, indent=2)

def process_news():
    """Xử lý tin tức chính"""
    logger.info("--- Bot tóm tắt tin tức bắt đầu chạy ---")
    
    # Khởi tạo scraper
    scraper = NewsScraper()
    
    # Load processed links
    processed_links = load_processed_links()
    logger.info(f"Đã tải {len(processed_links)} links đã xử lý.")
    
    # Load RSS sources
    rss_sources = load_rss_sources()
    
    logger.info("Đang kiểm tra tin tức từ tất cả các nguồn RSS...")
    
    new_articles = []
    
    for source_name, rss_url in rss_sources.items():
        logger.info(f"  -> Đang lấy từ: {source_name}")
        
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries:
                if entry.link not in processed_links:
                    new_articles.append({
                        'title': entry.title,
                        'link': entry.link,
                        'source': source_name,
                        'published': getattr(entry, 'published', '')
                    })
                    
        except Exception as e:
            logger.error(f"Không thể lấy từ {source_name}: {e}")
    
    if not new_articles:
        logger.info("Không có bài báo mới.")
        return
    
    logger.info(f"Phát hiện {len(new_articles)} bài báo mới. Bắt đầu xử lý...")
    
    successful_articles = []
    
    for article in new_articles:
        # Lấy nội dung
        response = scraper.get_content_with_retry(article['link'])
        
        if response and response.status_code == 200:
            content = extract_content(response.text, article['link'])
            
            if content:
                article['content'] = content
                successful_articles.append(article)
                processed_links.add(article['link'])
                
                logger.info(f"[THÀNH CÔNG] Đã xử lý: {article['title'][:50]}...")
            else:
                logger.warning(f"[THẤT BẠI] Không lấy được nội dung: {article['title'][:50]}...")
        else:
            logger.warning(f"[THẤT BẠI] Không tải được trang: {article['title'][:50]}...")
    
    # Lưu processed links
    save_processed_links(processed_links)
    
    if successful_articles:
        logger.info(f"\nĐã xử lý thành công {len(successful_articles)} bài báo:")
        for article in successful_articles:
            logger.info(f"- {article['title']}")
            logger.info(f"  Nguồn: {article['source']}")
            logger.info(f"  Độ dài: {len(article['content'])} ký tự")
    else:
        logger.warning("Không lấy được nội dung từ các bài báo mới.")
    
    logger.info("--- Hoàn tất chu kỳ. ---")

if __name__ == "__main__":
    process_news()
