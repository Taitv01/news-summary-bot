#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ... các dòng import khác ...
from content_extractor import extract_content
from telegram_sender import send_telegram_message
from summarizer import summarize_with_gemini # <-- THÊM DÒNG NÀY

# ... các hàm khác giữ nguyên ...

def process_news():
    # ... phần đầu hàm giữ nguyên ...
    
    try:
        # ... logic lấy tin tức giữ nguyên ...
        
        for article in successful_articles:
            # Lấy nội dung
            response = scraper.get_content_with_retry(article['link'])
            
            if response and response.status_code == 200:
                content = extract_content(response.text, article['link'])
                
                if content:
                    # GỌI GEMINI ĐỂ TÓM TẮT
                    logger.info(f"Đang tóm tắt bài báo: {article['title'][:30]}...")
                    summary = summarize_with_gemini(content)
                    
                    article['summary'] = summary # Lưu lại nội dung tóm tắt
                    
                    successful_articles.append(article)
                    processed_links.add(article['link'])
                    logger.info(f"[THÀNH CÔNG] Đã xử lý và tóm tắt: {article['title'][:50]}...")
                # ...
        
        # ...

        if successful_articles:
            # GỬI TIN NHẮN TÓM TẮT NÂNG CAO ĐẾN TELEGRAM
            for article in successful_articles:
                # Định dạng MarkdownV2
                title = article['title'].replace('-', r'\-').replace('.', r'\.').replace('!', r'\!').replace('(', r'\(').replace(')', r'\)')
                link = article['link'].replace('-', r'\-').replace('.', r'\.')
                summary_text = article.get('summary', 'Không có tóm tắt').replace('-', r'\-').replace('.', r'\.').replace('!', r'\!').replace('(', r'\(').replace(')', r'\)')
                
                message = f"📰 *{title}*\n\n"
                message += f"{summary_text}\n\n"
                message += f"[Đọc bài viết đầy đủ]({link})"
                
                send_telegram_message(message)
                time.sleep(1) # Thêm độ trễ 1 giây giữa các tin nhắn
        # ...

    finally:
        scraper.close()
    
    # ...
