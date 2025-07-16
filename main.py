import os
import requests
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import random

# --- CẤU HÌNH ---
PROCESSED_LINKS_FILE = 'processed_links.txt'

# Lấy thông tin nhạy cảm từ GitHub Secrets (sẽ được truyền vào dưới dạng biến môi trường)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Danh sách các nguồn cấp RSS tin tức
RSS_FEEDS = [
    {'name': 'VnExpress Mới nhất', 'url': 'https://vnexpress.net/rss/tin-moi-nhat.rss'},
    {'name': 'VnExpress Kinh doanh', 'url': 'https://vnexpress.net/rss/kinh-doanh.rss'},
    {'name': 'Vietstock Chứng khoán', 'url': 'https://vietstock.vn/830/chung-khoan/co-phieu.rss'},
    {'name': 'Lao Động', 'url': 'https://laodong.vn/rss/tin-moi-nhat.rss'}
]
MAX_ARTICLES_PER_DIGEST = 10

# **FIX:** Danh sách các User-Agent để xoay vòng, giả dạng nhiều trình duyệt khác nhau
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
]

# --- CÁC HÀM LƯU TRỮ (Đọc/ghi file cục bộ) ---

def load_processed_links():
    if not os.path.exists(PROCESSED_LINKS_FILE):
        return set()
    with open(PROCESSED_LINKS_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)

def save_processed_links(links_set):
    with open(PROCESSED_LINKS_FILE, 'w', encoding='utf-8') as f:
        for link in sorted(list(links_set)):
            f.write(link + '\n')

# --- CÁC HÀM CHỨC NĂNG ---

def get_all_news_from_rss(feeds):
    print("Đang kiểm tra tin tức từ tất cả các nguồn RSS...")
    all_articles = []
    for feed_info in feeds:
        try:
            print(f"  -> Đang lấy từ: {feed_info['name']}")
            # Sử dụng một User-Agent ngẫu nhiên khi lấy RSS feed
            feed = feedparser.parse(feed_info['url'], agent=random.choice(USER_AGENTS))
            for entry in feed.entries[:10]:
                all_articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'source': feed_info['name']
                })
        except Exception as e:
            print(f"Lỗi khi lấy tin từ {feed_info['name']}: {e}")
    return all_articles


def scrape_article_content(url):
    print(f"Đang lấy nội dung từ: {url}")
    try:
        # **FIX:** Nâng cấp bộ headers và xoay vòng User-Agent
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1'
        }
        
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # **FIX:** Bổ sung thêm nhiều selector hơn nữa để tìm nội dung
        selectors = [
            "article.fck_detail",           # VnExpress (cấu trúc cũ)
            "div.sidebar-1",                # VnExpress (cấu trúc mới)
            "div#article-content",          # Vietstock
            "div.content-detail",           # Vietstock (cấu trúc khác)
            "div.post-content",             # Cấu trúc blog chung
            "div.entry-content",            # Cấu trúc blog chung
            "div.td-post-content",          # Cấu trúc báo chí
            "div.article-content",          # Cấu trúc chung
            "div.singular-content",         # Lao Động
            "div[data-testid='article-body']", # US News
            "main article"                  # Cấu trúc HTML5 chung
        ]
        article_body = None
        for selector in selectors:
            article_body = soup.select_one(selector)
            if article_body: 
                print(f"  -> Tìm thấy nội dung với selector: '{selector}'")
                break
        
        if article_body:
            # Loại bỏ các thẻ không mong muốn
            for unwanted_tag in article_body.select('div, figure, table, script, style, aside, .ad-placeholder, .related-news'):
                unwanted_tag.decompose()
            
            paragraphs = article_body.find_all('p')
            
            # Nếu không tìm thấy thẻ <p>, thử lấy toàn bộ text
            if not paragraphs:
                content_text = article_body.get_text(separator='\n', strip=True)
                return content_text
            
            return "\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            
        print(f"  [CẢNH BÁO] Không tìm thấy selector phù hợp cho trang: {url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Lỗi kết nối hoặc timeout khi lấy nội dung: {e}")
        return None
    except Exception as e:
        print(f"Lỗi không xác định khi lấy nội dung: {e}")
        return None

def generate_digest_with_gemini(all_articles_content):
    if not all_articles_content: return None
    print("Đang gửi nội dung tổng hợp đến Gemini để tạo bản tin...")
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Bạn là một biên tập viên báo chí chuyên nghiệp, có nhiệm vụ tạo ra một bản tin tổng hợp cho kênh Telegram từ nhiều nguồn tin tức tiếng Việt và tiếng Anh.

        **Nhiệm vụ:**
        1.  Đọc và phân tích tất cả các bài báo được cung cấp.
        2.  **QUAN TRỌNG: Nếu một bài báo được viết bằng tiếng Anh, hãy dịch những ý chính sang tiếng Việt trước khi tóm tắt.**
        3.  Chọn ra khoảng 3 đến 5 tin tức quan trọng, nổi bật và đáng chú ý nhất từ TẤT CẢ các nguồn.
        4.  Với MỖI tin tức đã chọn, hãy tóm tắt lại bằng tiếng Việt theo ĐÚNG cấu trúc sau (bao gồm cả tên nguồn):
            `<b>🔥 [Viết một tiêu đề tin tức thật hấp dẫn bằng tiếng Việt]</b>\n<i>[Tóm tắt súc tích nội dung chính bằng tiếng Việt trong 2-3 câu]</i>\n(Nguồn: [Tên nguồn của bài báo đó])`
        5.  Sắp xếp các tin đã tóm tắt theo mức độ quan trọng giảm dần (tin nóng nhất, quan trọng nhất lên đầu).
        6.  Kết hợp tất cả thành một tin nhắn duy nhất cho Telegram. Bắt đầu tin nhắn bằng tiêu đề chính: `☀️ BẢN TIN TỔNG HỢP ☀️`.
        7.  Phân tách mỗi mục tin tức bằng một dòng `---`.

        **Yêu cầu đầu ra:**
        - Toàn bộ đầu ra phải bằng tiếng Việt.
        - Chỉ trả về DUY NHẤT tin nhắn đã được định dạng hoàn chỉnh cho Telegram.
        - Không thêm bất kỳ lời chào hỏi, lời giải thích, hay ghi chú nào khác.

        **NỘI DUNG CÁC BÀI BÁO CẦN XỬ LÝ:**
        ---
        {all_articles_content}
        ---
        """
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Lỗi khi gọi Gemini API: {e}")
        return None

def send_message_to_telegram(message):
    print("Đang gửi bản tin tổng hợp đến Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, data=payload, timeout=20)
        if response.status_code == 200:
            print("Gửi bản tin thành công!")
        else:
            print(f"Gửi bản tin thất bại. Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Lỗi khi gửi tin nhắn Telegram: {e}")


# --- HÀM CHÍNH ---
def main():
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY]):
        print("LỖI: Thiếu một trong các secrets cần thiết.")
        return
        
    print("--- Bot tóm tắt tin tức bắt đầu chạy ---")
    processed_links = load_processed_links()
    print(f"Đã tải {len(processed_links)} links đã xử lý.")
    
    articles = get_all_news_from_rss(RSS_FEEDS)
    new_articles = [article for article in articles if article['link'] not in processed_links]

    if not new_articles:
        print("Không có bài báo nào mới.")
    else:
        print(f"Phát hiện {len(new_articles)} bài báo mới. Bắt đầu xử lý...")
        random.shuffle(new_articles)
        articles_to_process = new_articles[:MAX_ARTICLES_PER_DIGEST]
        full_content_for_digest = ""
        links_in_this_batch = []
        for article in articles_to_process:
            content = scrape_article_content(article['link'])
            if content:
                full_content_for_digest += f"--- NGUỒN: {article['source']} ---\nBÀI BÁO: {article['title']}\nLINK: {article['link']}\nNỘI DUNG:\n{content}\n\n"
                links_in_this_batch.append(article['link'])
        if full_content_for_digest:
            digest_message = generate_digest_with_gemini(full_content_for_digest)
            if digest_message:
                send_message_to_telegram(digest_message)
                processed_links.update(links_in_this_batch)
                save_processed_links(processed_links)
                print("Lưu lại file processed_links.txt")
        else:
            print("Không lấy được nội dung từ các bài báo mới.")

    print("--- Hoàn tất chu kỳ. ---")

if __name__ == "__main__":
    main()
