# scraper.py

import requests
import time
import random
import logging

logger = logging.getLogger(__name__)

class NewsScraper:
    def __init__(self):
        """
        Khởi tạo Scraper với một session và bộ headers giả lập trình duyệt.
        Sử dụng Session giúp duy trì các thiết lập (như headers) cho tất cả các request.
        """
        self.session = requests.Session()
        
        # Bộ headers đầy đủ để giả lập trình duyệt, tránh bị chặn (lỗi 406)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        self.session.headers.update(headers)

    def get_content_with_retry(self, url, retries=3):
        """
        Thử lấy nội dung từ một URL, với cơ chế thử lại (retry).
        Sử dụng session đã được cấu hình sẵn headers.
        """
        logger.info(f"Đang lấy nội dung từ: {url}")
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=15)
                
                if response.status_code == 200:
                    return response
                
                # Ghi log cụ thể hơn cho các lỗi thường gặp
                elif response.status_code == 406:
                    logger.warning(f"Lỗi 406 Not Acceptable. Máy chủ không chấp nhận headers.")
                elif response.status_code == 403:
                    logger.warning(f"Lỗi 403 Forbidden. Bị từ chối truy cập.")
                else:
                    logger.warning(f"Lỗi HTTP {response.status_code} khi truy cập {url}")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Lỗi kết nối khi truy cập {url}: {e}")
            
            # Nếu chưa phải lần thử cuối, đợi một chút rồi thử lại
            if attempt < retries - 1:
                wait_time = round(random.uniform(2.5, 5.0), 1)
                logger.info(f"Chờ {wait_time} giây trước khi thử lại...")
                time.sleep(wait_time)
        
        logger.error(f"Không thể lấy nội dung từ {url} sau {retries} lần thử")
        return None
