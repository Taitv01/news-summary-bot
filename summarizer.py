# summarizer.py
import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def summarize_with_gemini(combined_articles_text: str) -> str:
    """
    Sử dụng Gemini API để tóm tắt một chuỗi lớn chứa nhiều bài báo.
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY chưa được thiết lập.")
        return "Lỗi: Không tìm thấy API Key của Gemini."

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        prompt = f"""Bạn là một biên tập viên báo chí xuất sắc. Dưới đây là nội dung của nhiều bài báo khác nhau, được phân tách bởi '---HẾT BÀI BÁO---'.
Hãy đọc tất cả và tạo ra một bản tin tổng hợp. Với mỗi bài báo, hãy rút ra tiêu đề và viết một đoạn tóm tắt ngắn gọn khoảng 2-3 câu về nội dung chính.
Trình bày rõ ràng, chuyên nghiệp.

NỘI DUNG CÁC BÀI BÁO:
---
{combined_articles_text}
---

BẢN TIN TỔNG HỢP:"""

        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        logger.error(f"Lỗi khi gọi Gemini API: {e}")
        # Trả về lỗi để bot có thể gửi thông báo lỗi này lên Telegram
        return f"Lỗi trong quá trình tóm tắt: {e}"
