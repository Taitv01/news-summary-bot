import requests

# THAY THẾ CÁC GIÁ TRỊ CỦA BẠN VÀO ĐÂY
BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
CHAT_ID = "123456789"

# Đừng thay đổi các dòng dưới
message = "Tin nhắn thử nghiệm từ script Python."
url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": message
}

try:
    response = requests.post(url, json=payload)
    print("Phản hồi từ server Telegram:")
    print(response.json())
except Exception as e:
    print(f"Đã xảy ra lỗi: {e}")
