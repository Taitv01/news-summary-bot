import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def scrape_article_content(url):
    """
    Scrape nội dung bài báo với cơ chế bypass bot detection
    """
    print(f"Đang lấy nội dung từ: {url}")
    
    # Tạo session với retry strategy
    session = requests.Session()
    
    # Cấu hình retry cho các lỗi tạm thời
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,  # Tăng thời gian chờ giữa các lần retry
        status_forcelist=[429, 500, 502, 503, 504, 403, 406],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Headers mô phỏng trình duyệt Chrome thật
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'DNT': '1',
        'Pragma': 'no-cache'
    }
    
    try:
        # Thêm delay ngẫu nhiên để tránh rate limiting
        time.sleep(random.uniform(2, 5))
        
        # Thêm referer cho các trang Vietnamese
        if 'vnexpress.net' in url:
            headers['Referer'] = 'https://vnexpress.net/'
        elif 'vietstock.vn' in url:
            headers['Referer'] = 'https://vietstock.vn/'
        elif 'laodong.vn' in url:
            headers['Referer'] = 'https://laodong.vn/'
        
        response = session.get(
            url, 
            headers=headers, 
            timeout=30, 
            allow_redirects=True,
            verify=True
        )
        
        # Xử lý các status code cụ thể
        if response.status_code == 406:
            print(f"  [CẢNH BÁO] Website từ chối yêu cầu (406): {url}")
            return None
        elif response.status_code == 403:
            print(f"  [CẢNH BÁO] Bị chặn truy cập (403): {url}")
            return None
        elif response.status_code == 429:
            print(f"  [CẢNH BÁO] Rate limit exceeded (429): {url}")
            time.sleep(10)  # Chờ 10 giây trước khi tiếp tục
            return None
        
        response.raise_for_status()
        
        # Kiểm tra content type
        content_type = response.headers.get('content-type', '')
        if 'text/html' not in content_type:
            print(f"  [CẢNH BÁO] Không phải HTML content: {url}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Selectors được tối ưu cho các trang Vietnamese
        selectors = [
            # VnExpress
            "article.fck_detail .Normal",
            "article.fck_detail",
            "div.fck_detail",
            
            # VietStock
            "div.content-news-detail",
            "div.content-detail",
            "div.news-content",
            
            # Lao Dong
            "div.content-news-detail-new",
            "div.post-content",
            "div.entry-content",
            
            # Generic selectors
            "div.article-content",
            "div#article-content",
            "div.singular-content",
            "div[data-testid='article-body']",
            "article",
            "div.content",
            "main"
        ]
        
        article_body = None
        for selector in selectors:
            article_body = soup.select_one(selector)
            if article_body:
                print(f"  [THÀNH CÔNG] Tìm thấy nội dung với selector: {selector}")
                break
        
        if article_body:
            # Xóa các thẻ không cần thiết
            unwanted_selectors = [
                'div.advertisement', 'div.ads', 'div.ad', 'div.banner',
                'script', 'style', 'nav', 'footer', 'header', 'aside',
                'div.related-articles', 'div.social-share', 'div.tags',
                'div.author-info', 'div.comment', 'div.fb-comments',
                'iframe', 'video', 'audio', 'embed', 'object'
            ]
            
            for selector in unwanted_selectors:
                for element in article_body.select(selector):
                    element.decompose()
            
            # Lấy text từ các thẻ p
            paragraphs = article_body.find_all('p')
            if not paragraphs:
                # Fallback: lấy text từ div nếu không có p
                paragraphs = article_body.find_all('div')
            
            content_parts = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 20:  # Chỉ lấy đoạn có ít nhất 20 ký tự
                    content_parts.append(text)
            
            final_content = "\n".join(content_parts)
            
            if len(final_content) > 200:  # Chỉ trả về nếu có nội dung đủ dài
                print(f"  [THÀNH CÔNG] Lấy được {len(final_content)} ký tự từ {url}")
                return final_content
            else:
                print(f"  [CẢNH BÁO] Nội dung quá ngắn ({len(final_content)} ký tự): {url}")
                return None
        else:
            print(f"  [CẢNH BÁO] Không tìm thấy selector phù hợp cho trang: {url}")
            # Debug: In ra một phần HTML để kiểm tra
            print(f"  [DEBUG] HTML structure: {soup.title.get_text() if soup.title else 'No title'}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"  [LỖI] Timeout khi truy cập: {url}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"  [LỖI] Lỗi kết nối: {url}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"  [LỖI] HTTP Error {e.response.status_code}: {url}")
        return None
    except Exception as e:
        print(f"  [LỖI] Lỗi không xác định: {e}")
        return None
