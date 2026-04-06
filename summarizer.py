import os
import json
import glob
from openai import OpenAI
from datetime import datetime
import config

class RedditSummarizer:
    def __init__(self):
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL
        )
        self.model = config.OPENAI_MODEL_NAME

    def _describe_image(self, image_url):
        print(f"Bắt đầu phân tích hình ảnh: {image_url}")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Bạn là chuyên gia phân tích hình ảnh kỹ thuật. Nhiệm vụ của bạn là trích xuất văn bản (OCR) và mô tả ngắn gọn nội dung kỹ thuật. KHÔNG chào hỏi, KHÔNG giải thích dông dài, KHÔNG nói 'Tôi đã thấy' hay 'Tôi không thấy'. Chỉ trả về nội dung phân tích."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Trích xuất văn bản và mô tả kỹ thuật từ ảnh này (tiếng Việt):"},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                max_tokens=600
            )
            desc = response.choices[0].message.content
            print(f"Kết quả phân tích ảnh: {desc[:100]}...")
            
            # Nếu model trả về thông điệp báo không thấy ảnh (hallucination)
            bad_keywords = ["không thấy hình ảnh", "chưa thấy hình ảnh", "tải hình ảnh lên", "không có ảnh"]
            if any(k in desc.lower() for k in bad_keywords) and len(desc) > 200:
                return "[Không thể phân tích ảnh - Model hallucination]"
                
            return desc
        except Exception as e:
            return "[Lỗi trích xuất ảnh]"

    def _summarize_thread(self, thread_data):
        post_obj = thread_data['data'][0]['data']['children'][0]['data']
        comments_obj = thread_data['data'][1]['data']['children']
        thread_info = thread_data.get('thread_info', {})
        
        image_context = ""
        if thread_info.get("image_url"):
            desc = self._describe_image(thread_info['image_url'])
            image_context = f"\n[Thông tin từ hình ảnh: {desc}]\n"

        full_text = f"Tiêu đề: {post_obj['title']}\n"
        full_text += f"Nội dung: {post_obj.get('selftext', 'Trống')}\n"
        full_text += image_context
        full_text += "\nCác thảo luận hàng đầu:\n"
        
        for comment in comments_obj[:10]:
            body = comment.get('data', {}).get('body', '')
            if body:
                full_text += f"- {body}\n"
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "Bạn là Robot tóm tắt tin thảo luận Reddit. Hãy tóm tắt cực kỳ ngắn gọn, KHÔNG có các câu dẫn thừa như 'Dưới đây là tóm tắt' hay 'Bài đăng thảo luận về'. Đi thẳng vào nội dung chính. Trình bày dùng các bullet points. Trả lời bằng tiếng Việt."
                    },
                    {"role": "user", "content": full_text}
                ],
                max_tokens=800
            )
            summary_content = response.choices[0].message.content
            thread_url = f"https://www.reddit.com{post_obj['permalink']}"
            
            # Escape Markdown characters in title to avoid breaking [link](url)
            safe_title = post_obj['title'].replace('[', '(').replace(']', ')').replace('*', '').replace('_', ' ')
            
            return f"📌 *[{safe_title}]({thread_url})*\n\n{summary_content}"
        except:
            safe_title = post_obj['title'].replace('[', '(').replace(']', ')').replace('*', '').replace('_', ' ')
            return f"📌 *{safe_title}*\n[Lỗi tóm tắt]"

    def summarize_run(self):
        tracking_file = config.TRACKING_FILE
        posts_dir = config.POSTS_DIR
        
        if not os.path.exists(tracking_file):
            return ""

        with open(tracking_file, 'r', encoding='utf-8') as f:
            tracking = json.load(f)

        if not tracking:
            print("[Summarizer] Không có bài đăng nào trong hàng chờ để tóm tắt.")
            return ""

        print(f"[Summarizer] Bắt đầu tóm tắt {len(tracking)} bài đăng...")

        # Sắp xếp bài viết theo thời gian phát hiện (mới nhất lên đầu)
        sorted_tids = sorted(
            tracking.keys(), 
            key=lambda tid: tracking[tid].get('first_seen', 0), 
            reverse=True
        )

        thread_summaries = []
        updated_tracking = False
        
        for tid in sorted_tids:
            info = tracking[tid]
            
            # Chỉ xử lý các bài đăng đang 'active'
            if info.get('status') != 'active':
                continue

            file_path = os.path.join(posts_dir, f"{tid}.json")
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    thread_data = json.load(f)
                    
                    # Nếu đã có summary cũ trong tracking, ta vẫn có thể tóm tắt lại để cập nhật
                    # hoặc dùng lại nếu muốn tiết kiệm API. Ở đây ta tóm tắt lại để có tin mới nhất.
                    summary = self._summarize_thread(thread_data)
                    thread_summaries.append(summary)
                    
                    # Lưu summary vào tracking để dùng sau này (khi chuyển sang temporary)
                    tracking[tid]['last_summary'] = summary
                    updated_tracking = True

        # Nếu có cập nhật summary, lưu lại vào tracking.json
        if updated_tracking:
            with open(tracking_file, 'w', encoding='utf-8') as f:
                json.dump(tracking, f, indent=4, ensure_ascii=False)

        if not thread_summaries:
            print("[Summarizer] Không tạo được bản tóm tắt nào từ dữ liệu hiện có.")
            return ""

        print(f"[Summarizer] Đã tóm tắt thành công {len(thread_summaries)} bài viết.")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        final_report = f"🔥 *BÁO CÁO REDDIT r/LocalLLaMA* ({datetime.now().strftime('%H:%M %d/%m')})\n"
        final_report += "━━━━━━━━━━━━━━━━━━━━\n\n"
        final_report += "\n\n────────────────\n\n".join(thread_summaries)

        summary_path = os.path.join(config.SUMMARIES_DIR, f"report_{timestamp}.md")
        latest_path = os.path.join(config.SUMMARIES_DIR, "latest_summary.md")
        
        for path in [summary_path, latest_path]:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(final_report)
        
        return final_report
