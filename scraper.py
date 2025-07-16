#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web scraper với retry logic và anti-detection
"""

import requests
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

logger = logging.getLogger(__name__)

class NewsScraper:
    def __init__(self):
        self.session = requests.Session()
        
        # Cấu hình headers giả lập trình duyệt
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        self.session.headers.update(self.headers)
        
        # Cấu hình retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def get_content_with_retry(self, url, max_retries=3):
        """Lấy nội dung với retry logic"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Đang lấy nội dung từ: {url}")
                
                # Thêm delay ngẫu nhiên để tránh bị chặn
                time.sleep(random.uniform(1, 3))
                
                response = self.session.get(url, timeout=15)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 406:
                    logger.warning(f"Lỗi 406: Thay đổi User-Agent và thử lại...")
                    self.rotate_user_agent()
                elif response.status_code == 429:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limit: Chờ {wait_time} giây...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"HTTP {response.status_code}: {response.reason}")
                    
            except requests.exceptions.Timeout:
                logger.error(f"Timeout lần {attempt + 1}")
            except requests.exceptions.ConnectionError:
                logger.error(f"Lỗi kết nối lần {attempt + 1}")
            except Exception as e:
                logger.error(f"Lỗi khác lần {attempt + 1}: {e}")
            
            if attempt < max_retries - 1:
                wait_time = random.uniform(2, 5)
                logger.info(f"Chờ {wait_time:.1f} giây trước khi thử lại...")
                time.sleep(wait_time)
        
        logger.error(f"Không thể lấy nội dung từ {url} sau {max_retries} lần thử")
        return None
    
    def rotate_user_agent(self):
        """Thay đổi User-Agent ngẫu nhiên"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
        ]
        
        new_ua = random.choice(user_agents)
        self.session.headers.update({'User-Agent': new_ua})
        logger.info(f"Đã thay đổi User-Agent")
