#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import feedparser
import json
import os
import logging
import time
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from contextlib import asynccontextmanager

from scraper import NewsScraper
from content_extractor import extract_content
from telegram_sender import send_telegram_message, escape_markdown_v2
from summarizer import summarize_with_gemini

# Cấu hình logging với rotation để tránh file log quá lớn
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
MAX_ARTICLES_PER_SOURCE = 10
MESSAGE_LIMIT = 4000
DATA_DIR = 'data'
PROCESSED_LINKS_FILE = os.path.join(DATA_DIR, 'processed_links.json')
RSS_CONFIG_FILE = os.path.join(DATA_DIR, 'rss_sources.json')
RETRY_DELAY = 1
MAX_CONCURRENT_REQUESTS = 5

@dataclass
class Article:
    """Cấu trúc dữ liệu cho bài báo."""
    title: str
    link: str
    content: Optional[str] = None

class ConfigManager:
    """Quản lý cấu hình RSS từ file hoặc mặc định."""
    
    @staticmethod
    def load_rss_sources() -> Dict[str, str]:
        """Tải các nguồn RSS từ file cấu hình hoặc trả về mặc định."""
        if os.path.exists(RSS_CONFIG_FILE):
            try:
                with open(RSS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                logger.warning(f"Không thể đọc file cấu hình RSS. Sử dụng cấu hình mặc định.")
        
        # Cấu hình mặc định
        default_sources = {
            'VnExpress Mới nhất': 'https://vnexpress.net/rss/tin-moi-nhat.rss',
            'VnExpress Kinh doanh': 'https://vnexpress.net/rss/kinh-doanh.rss',
            'Vietstock Chứng khoán': 'https://vietstock.vn/rss/chung-khoan.rss',
            'Lao Động': 'https://laodong.vn/rss/tin-moi-nhat.rss'
        }
        
        # Tạo file cấu hình mặc định
        ConfigManager._save_default_config(default_sources)
        return default_sources
    
    @staticmethod
    def _save_default_config(sources: Dict[str, str]) -> None:
        """Lưu cấu hình mặc định ra file."""
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(RSS_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(sources, f, ensure_ascii=False, indent=2)

class ProcessedLinksManager:
    """Quản lý danh sách các link đã xử lý."""
    
    def __init__(self):
        self.processed_links: Set[str] = set()
    
    def load(self) -> Set[str]:
        """Tải danh sách các link đã được xử lý."""
        if os.path.exists(PROCESSED_LINKS_FILE):
            try:
                with open(PROCESSED_LINKS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.processed_links = set(data) if isinstance(data, list) else set()
                    return self.processed_links
            except (json.JSONDecodeError, FileNotFoundError):
                logger.warning(f"Lỗi đọc file {PROCESSED_LINKS_FILE}. Bắt đầu với danh sách rỗng.")
        
        self.processed_links = set()
        return self.processed_links
    
    def save(self) -> None:
        """Lưu danh sách các link đã xử lý."""
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(PROCESSED_LINKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.processed_links), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Lỗi khi lưu processed links: {e}")
    
    def add(self, link: str) -> None:
        """Thêm link vào danh sách đã xử lý."""
        self.processed_links.add(link)
    
    def contains(self, link: str) -> bool:
        """Kiểm tra link đã được xử lý chưa."""
        return link in self.processed_links

class MessageSplitter:
    """Chia tin nhắn thành các phần nhỏ hơn giới hạn."""
    
    @staticmethod
    def split_message(text: str, limit: int = MESSAGE_LIMIT) -> List[str]:
        """Chia một đoạn văn bản dài thành nhiều phần nhỏ hơn giới hạn."""
        if len(text) <= limit:
            return [text]
        
        parts = []
        remaining_text = text
        
        while remaining_text:
            if len(remaining_text) <= limit:
                parts.append(remaining_text)
                break
            
            # Tìm vị trí ngắt dòng gần nhất
            split_pos = remaining_text.rfind('\n', 0, limit)
            if split_pos == -1:
                split_pos = limit
            
            parts.append(remaining_text[:split_pos])
            remaining_text = remaining_text[split_pos:].lstrip()
        
        return parts

class RSSFetcher:
    """Lấy tin tức từ các nguồn RSS."""
    
    def __init__(self, processed_links_manager: ProcessedLinksManager):
        self.processed_links_manager = processed_links_manager
    
    def fetch_new_articles(self, rss_sources: Dict[str, str]) -> List[Article]:
        """Lấy các bài báo mới từ tất cả nguồn RSS."""
        new_articles = []
        
        for source_name, rss_url in rss_sources.items():
            logger.info(f"-> Đang lấy từ: {source_name}")
            try:
                feed = feedparser.parse(rss_url)
                if feed.bozo:
                    logger.warning(f"Lỗi parsing RSS từ {source_name}: {feed.bozo_exception}")
                    continue
                
                for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
                    if not self.processed_links_manager.contains(entry.link):
                        new_articles.append(Article(
                            title=entry.title,
                            link=entry.link
                        ))
            except Exception as e:
                logger.error(f"Lỗi khi lấy RSS từ {source_name}: {e}")
                continue
        
        return new_articles

class ContentProcessor:
    """Xử lý nội dung bài báo."""
    
    def __init__(self, scraper: NewsScraper, processed_links_manager: ProcessedLinksManager):
        self.scraper = scraper
        self.processed_links_manager = processed_links_manager
    
    def process_articles_concurrent(self, articles: List[Article]) -> List[Article]:
        """Xử lý nhiều bài báo song song để tăng tốc độ."""
        successful_articles = []
        
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            # Tạo future cho mỗi bài báo
            future_to_article = {
                executor.submit(self._process_single_article, article): article 
                for article in articles
            }
            
            # Xử lý kết quả
            for future in as_completed(future_to_article):
                article = future_to_article[future]
                try:
                    processed_article = future.result()
                    if processed_article and processed_article.content:
                        successful_articles.append(processed_article)
                        self.processed_links_manager.add(processed_article.link)
                except Exception as e:
                    logger.error(f"Lỗi xử lý bài báo {article.link}: {e}")
        
        return successful_articles
    
    def _process_single_article(self, article: Article) -> Optional[Article]:
        """Xử lý một bài báo duy nhất."""
        try:
            response = self.scraper.get_content_with_retry(article.link)
            if response and response.status_code == 200:
                content = extract_content(response.text, article.link)
                if content:
                    article.content = f"TIÊU ĐỀ: {article.title}\nNỘI DUNG:\n{content}"
                    return article
        except Exception as e:
            logger.error(f"Lỗi khi xử lý bài báo {article.link}: {e}")
        
        return None

class TelegramMessageSender:
    """Gửi tin nhắn Telegram."""
    
    def __init__(self):
        self.message_splitter = MessageSplitter()
    
    def send_summary(self, summary: str) -> None:
        """Gửi tóm tắt tin tức qua Telegram."""
        try:
            # Xử lý ký tự đặc biệt cho nội dung AI
            escaped_content = escape_markdown_v2(summary)
            
            # Thêm tiêu đề
            full_message = f"📰 *BẢN TIN TỔNG HỢP HÔM NAY*\n\n{escaped_content}"
            
            # Chia tin nhắn thành các phần nhỏ
            message_chunks = self.message_splitter.split_message(full_message)
            
            for i, chunk in enumerate(message_chunks):
                message_to_send = chunk
                
                # Thêm ghi chú phần nếu có nhiều hơn 1 phần
                if len(message_chunks) > 1:
                    note = escape_markdown_v2(f"\n\n(Phần {i+1}/{len(message_chunks)})")
                    message_to_send += note
                
                send_telegram_message(message_to_send)
                time.sleep(RETRY_DELAY)
                
        except Exception as e:
            logger.error(f"Lỗi khi gửi tin nhắn Telegram: {e}")

class NewsBot:
    """Bot tóm tắt tin tức chính."""
    
    def __init__(self):
        self.scraper = NewsScraper()
        self.processed_links_manager = ProcessedLinksManager()
        self.rss_fetcher = RSSFetcher(self.processed_links_manager)
        self.content_processor = ContentProcessor(self.scraper, self.processed_links_manager)
        self.telegram_sender = TelegramMessageSender()
    
    def run(self) -> None:
        """Chạy quy trình xử lý tin tức chính."""
        logger.info("--- Bot tóm tắt tin tức bắt đầu chạy ---")
        
        try:
            # Tải danh sách link đã xử lý
            self.processed_links_manager.load()
            
            # Tải cấu hình RSS
            rss_sources = ConfigManager.load_rss_sources()
            logger.info("Đang kiểm tra tin tức từ tất cả các nguồn RSS...")
            
            # Lấy bài báo mới
            new_articles = self.rss_fetcher.fetch_new_articles(rss_sources)
            
            if not new_articles:
                logger.info("Không có bài báo mới.")
                return
            
            logger.info(f"Phát hiện {len(new_articles)} bài báo mới. Bắt đầu thu thập nội dung...")
            
            # Xử lý nội dung bài báo song song
            processed_articles = self.content_processor.process_articles_concurrent(new_articles)
            
            if not processed_articles:
                logger.warning("Không thu thập được nội dung từ bất kỳ bài báo mới nào.")
                return
            
            logger.info(f"Đã thu thập {len(processed_articles)} bài báo. Tạo tóm tắt...")
            
            # Gộp nội dung và tóm tắt
            combined_text = "\n\n---HẾT BÀI BÁO---\n\n".join(
                article.content for article in processed_articles
            )
            
            final_summary = summarize_with_gemini(combined_text)
            
            logger.info("Đã nhận tóm tắt từ AI. Gửi tin nhắn...")
            
            # Gửi tin nhắn
            self.telegram_sender.send_summary(final_summary)
            
        except Exception as e:
            logger.error(f"Lỗi trong quá trình xử lý: {e}")
        
        finally:
            # Lưu danh sách link đã xử lý
            self.processed_links_manager.save()
            self.scraper.close()
            logger.info("--- Hoàn tất chu kỳ. ---")

def main():
    """Hàm chính."""
    try:
        bot = NewsBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot bị dừng bởi người dùng.")
    except Exception as e:
        logger.error(f"Lỗi không mong muốn: {e}")

if __name__ == "__main__":
    main()
