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

# (Các hàm cấu hình logging, load_rss_sources, etc. giữ nguyên như cũ)
# ...
# ... (Giữ nguyên các hàm từ load_rss_sources đến save_processed_links)

def split_message(text: str, limit: int = 4000) -> list[str]:
    """Chia một đoạn văn bản dài thành nhiều phần nhỏ hơn giới hạn."""
    if len(text) <= limit:
        return [text]

    parts = []
    while len(text) > 0:
        if len(text) <= limit:
            parts.append(text)
            break
        
        # Tìm vị trí ngắt dòng gần nhất từ cuối
        split_pos = text.rfind('\n', 0, limit)
        if split_pos == -1: # Không tìm thấy ngắt dòng, cắt tại giới hạn
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
        # ... (Phần code lấy new_articles từ RSS giữ nguyên)

        if not new_articles:
            logger.info("Không có bài báo mới.")
            return

        logger.info(f"Phát hiện {len(new_articles)} bài báo mới. Bắt đầu thu thập nội dung...")
        
        # --- BƯỚC 1: THU THẬP TẤT CẢ NỘI DUNG ---
        all_articles_content = []
        for article in new_articles:
            response = scraper.get_content_with_retry(article['link'])
            if response and response.status_code == 200:
                content = extract_content(response.text, article['link'])
                if content:
                    # Gộp tiêu đề và nội dung lại
                    full_content = f"TIÊU ĐỀ: {article['title']}\nNỘI DUNG:\n{content}"
                    all_articles_content.append(full_content)
                    processed_links.add(article['link'])

        if not all_articles_content:
            logger.warning("Không thu thập được nội dung từ bất kỳ bài báo mới nào.")
            return

        # --- BƯỚC 2: GỘP VÀ TÓM TẮT TRONG 1 LẦN GỌI API ---
        logger.info(f"Đã thu thập {len(all_articles_content)} bài báo. Gộp lại và gửi đi tóm tắt...")
        combined_text = "\n\n---HẾT BÀI BÁO---\n\n".join(all_articles_content)
        
        final_summary = summarize_with_gemini(combined_text)
        
        # --- BƯỚC 3: CHIA TIN NHẮN VÀ GỬI ĐẾN TELEGRAM ---
        logger.info("Đã nhận tóm tắt từ AI. Chuẩn bị chia và gửi tin nhắn...")
        
        # Escape toàn bộ bản tóm tắt một lần
        escaped_summary = escape_markdown_v2(final_summary)
        
        message_chunks = split_message(escaped_summary, 4000)
        
        for i, chunk in enumerate(message_chunks):
            # Thêm tiêu đề cho các phần tin nhắn
            header = f"📰 *BẢN TIN TỔNG HỢP (Phần {i+1}/{len(message_chunks)})*\n\n"
            full_message = header + chunk
            
            send_telegram_message(full_message)
            time.sleep(1)

    finally:
        save_processed_links(processed_links)
        scraper.close()
        logger.info("--- Hoàn tất chu kỳ. ---")

if __name__ == "__main__":
    process_news()
