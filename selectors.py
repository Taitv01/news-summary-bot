#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSS selectors cho các website tin tức
"""

from bs4 import BeautifulSoup
import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SITE_SELECTORS = {
    'vnexpress.net': [
        'article.fck_detail',
        'div.fck_detail',
        'div.Normal',
        'div.content_detail'
    ],
    'vietstock.vn': [
        'div.article-content',
        'div.content-news',
        'div.news-content',
        'div.detail-content',
        'div.content-detail',
        'div.entry-content',
        'article'
    ],
    'laodong.vn': [
        'div.article-content',
        'div.content-detail',
        'div.news-content',
        'article'
    ]
}

def get_selectors_for_domain(url):
    """Lấy danh sách selector cho domain"""
    domain = urlparse(url).netloc
    
    # Loại bỏ www. nếu có
    if domain.startswith('www.'):
        domain = domain[4:]
    
    return SITE_SELECTORS.get(domain, ['article', 'div.content', 'div.main-content'])

def extract_content(html, url):
    """Trích xuất nội dung từ HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Xóa các thẻ không cần thiết
    for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
        element.decompose()
    
    # Lấy selector phù hợp cho domain
    selectors = get_selectors_for_domain(url)
    
    content = None
    successful_selector = None
    
    for selector in selectors:
        try:
            content = soup.select_one(selector)
            if content and content.get_text(strip=True):
                successful_selector = selector
                logger.info(f"[THÀNH CÔNG] Sử dụng selector: {selector}")
                break
        except Exception as e:
            logger.error(f"[LỖI] Selector {selector}: {e}")
            continue
    
    if not content:
        logger.warning(f"[CẢNH BÁO] Không tìm thấy selector phù hợp cho: {url}")
        # Fallback: lấy toàn bộ text từ body
        content = soup.find('body')
        if content:
            logger.info(f"[FALLBACK] Sử dụng toàn bộ nội dung body")
    
    if content:
        # Làm sạch nội dung
        text = content.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)  # Xóa khoảng trắng thừa
        text = text.strip()
        
        # Kiểm tra độ dài tối thiểu
        if len(text) < 100:
            logger.warning(f"[CẢNH BÁO] Nội dung quá ngắn ({len(text)} ký tự)")
            return None
            
        return text
    
    return None
