#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import feedparser
import json
import os
import logging
from scraper import NewsScraper
from content_extractor import extract_content
from telegram_sender import send_telegram_message  # <-- THÊM DÒNG NÀY

# (Các hàm cấu hình logging, load_rss_sources, ... giữ nguyên)
# ...
# ...

def process_news():
    """Xử lý tin tức chính"""
    logger.info("--- Bot tóm tắt tin tức bắt đầu chạy ---")
    
    scraper = NewsScraper()
    
    try:
        # (Phần code lấy tin tức, ... giữ nguyên)
        # ...
        # ...

        if successful_articles:
            logger.info(f"\nĐã xử lý thành công {len(successful_articles)} bài báo.")
            
            # TẠO TIN NHẮN TÓM TẮT VÀ GỬI ĐẾN TELEGRAM
            summary_message = f"*📰 Tin tức tổng hợp mới nhất ({len(successful_articles)} tin)*\n\n"
            for article in successful_articles:
                # Định dạng MarkdownV2 yêu cầu thoát các ký tự đặc biệt
                title = article['title'].replace('-', r'\-').replace('.', r'\.').replace('!', r'\!').replace('(', r'\(').replace(')', r'\)')
                link = article['link'].replace('-', r'\-').replace('.', r'\.')
                summary_message += f"▪️ [{title}]({link})\n"
            
            send_telegram_message(summary_message) # <-- GỌI HÀM GỬI TIN
            
        else:
            logger.warning("Không lấy được nội dung từ bất kỳ bài báo mới nào.")

    finally:
        scraper.close()
    
    logger.info("--- Hoàn tất chu kỳ. ---")

if __name__ == "__main__":
    process_news()
