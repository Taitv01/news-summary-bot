# telegram_sender.py
import os
import requests
import logging

logger = logging.getLogger(__name__)

def escape_markdown_v2(text: str) -> str:
    """Thoát các ký tự đặc biệt cho định dạng MarkdownV2 của Telegram."""
    # Danh sách các ký tự cần được thoát
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Thêm một dấu \ vào trước mỗi ký tự đặc biệt
    return "".join(f"\\{char}" if char in escape_chars else char for char in text)

def send_telegram_message(message_text):
    """Gửi tin nhắn văn bản đến một chat Telegram cụ thể."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID chưa được thiết lập.")
        return

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Chúng ta không cần escape toàn bộ message nữa, chỉ cần escape các phần cần thiết trong main.py
    payload = {
        'chat_id': chat_id,
        'text': message_text,
        'parse_mode': 'MarkdownV2'
    }

    try:
        response = requests.post(api_url, json=payload, timeout=10)
        response_data = response.json()
        if response.status_code == 200 and response_data.get('ok'):
            logger.info("Đã gửi tin nhắn đến Telegram thành công.")
        else:
            # Ghi log lỗi chi tiết từ Telegram
            error_description = response_data.get('description', response.text)
            logger.error(f"Lỗi khi gửi tin đến Telegram: {error_description}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi kết nối khi gửi tin đến Telegram: {e}")
