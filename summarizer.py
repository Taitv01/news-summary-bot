# summarizer.py
import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def summarize_with_gemini(article_text: str) -> str:
    """
    Sử dụng Gemini API để tóm tắt nội dung một bài báo.
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY chưa được thiết lập.")
        return "Lỗi: Không tìm thấy API Key của Gemini."

    try:
        genai.configure(api_key=api_key)
        
        # Sử dụng model Flash, nhanh và hiệu quả cho việc tóm tắt
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        prompt = f"""Bạn là một biên tập viên báo chí chuyên nghiệp và giàu kinh nghiệm. Hãy đọc và tóm tắt nội dung bài báo sau đây thành 3 gạch đầu dòng súc tích, dễ hiểu bằng tiếng Việt. Giữ giọng văn trung lập, chỉ tập trung vào các thông tin quan trọng nhất.

BÀI BÁO:
---
{article_text}
---

TÓM TẮT:"""

        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        logger.error(f"Lỗi khi gọi Gemini API: {e}")
        return f"Lỗi trong quá trình tóm tắt: {e}"
