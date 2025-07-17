# scraper.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import logging
import random

logger = logging.getLogger(__name__)

class NewsScraper:
    def __init__(self):
        """
        Khởi tạo Scraper sử dụng Selenium với trình duyệt Chrome.
        """
        logger.info("Đang khởi tạo trình duyệt ảo (Selenium)...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy ở chế độ không có giao diện
        chrome_options.add_argument("--no-sandbox") # Bắt buộc khi chạy trên Linux/Github Actions
        chrome_options.add_argument("--disable-dev-shm-usage") # Bắt buộc khi chạy trên Linux/Github Actions
        chrome_options.add_argument("--window-size=1920,1080") # Giả lập kích thước màn hình
        
        # User-Agent để trông giống trình duyệt thật
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        chrome_options.add_argument(f'user-agent={user_agent}')

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Trình duyệt ảo đã sẵn sàng.")
        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo Selenium WebDriver: {e}")
            self.driver = None

    def get_content_with_retry(self, url, retries=2):
        """
        Lấy nội dung trang bằng Selenium, có thử lại.
        """
        if not self.driver:
            logger.error("WebDriver không được khởi tạo, không thể lấy nội dung.")
            return None
            
        logger.info(f"Đang lấy nội dung từ: {url}")
        for attempt in range(retries):
            try:
                self.driver.get(url)
                # Đợi một chút để trang tải xong JavaScript (nếu có)
                time.sleep(random.uniform(2, 4)) 
                
                # Trả về đối tượng Response giả lập để tương thích với code cũ
                class FakeResponse:
                    def __init__(self, content, status_code):
                        self.text = content
                        self.status_code = status_code
                
                return FakeResponse(self.driver.page_source, 200)

            except Exception as e:
                logger.warning(f"Lỗi khi dùng Selenium để lấy {url}: {e}")
                if attempt < retries - 1:
                    wait_time = round(random.uniform(3, 6), 1)
                    logger.info(f"Chờ {wait_time} giây trước khi thử lại...")
                    time.sleep(wait_time)
        
        logger.error(f"Không thể lấy nội dung từ {url} sau {retries} lần thử")
        return None

    def close(self):
        """Đóng trình duyệt để giải phóng tài nguyên."""
        if self.driver:
            logger.info("Đang đóng trình duyệt ảo...")
            self.driver.quit()
            logger.info("Đã đóng trình duyệt.")
