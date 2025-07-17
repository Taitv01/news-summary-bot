# telegram_sender.py
import os
import requests
import logging

logger = logging.getLogger(__name__)

def send_telegram_message(message_text):
    """Gửi tin nhắn văn bản đến một chat Telegram cụ thể."""
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID chưa được thiết lập.")
        return

    # Sử dụng MarkdownV2 để định dạng link đẹp hơn
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message_text,
        'parse_mode': 'MarkdownV2'
    }

    try:
        response = requests.post(api_url, json=payload, timeout=10)
        response_data = response.json()
        if response.status_code == 200 and response_data.get('ok'):
            logger.info("Đã gửi tin nhắn tóm tắt đến Telegram thành công.")
        else:
            logger.error(f"Lỗi khi gửi tin đến Telegram: {response_data.get('description', response.text)}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi kết nối khi gửi tin đến Telegram: {e}")
