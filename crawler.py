import requests
import json
import os
import time
from datetime import datetime
import config

class RedditCrawler:
    def __init__(self, subreddit=config.SUBREDDIT):
        self.subreddit = subreddit
        self.posts_dir = config.POSTS_DIR
        self.tracking_file = config.TRACKING_FILE
        self.blacklist_file = config.BLACKLIST_FILE
        self.base_url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.reddit.com/",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
        self.proxies = {
            "http": config.PROXY_URL,
            "https": config.PROXY_URL
        } if config.PROXY_URL else None

    def _load_json(self, path, default={}):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return default
        return default

    def _save_json(self, path, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _request_with_retry(self, url, params=None, max_retries=3):
        """Helper to perform requests with retries and exponential backoff."""
        for attempt in range(max_retries):
            try:
                if params is None:
                    params = {}
                # Add timestamp to bypass cache if not already present
                if 't' not in params:
                    params['t'] = int(time.time())

                response = requests.get(
                    url, 
                    headers=self.headers, 
                    params=params, 
                    proxies=self.proxies, 
                    timeout=20
                )
                
                if response.status_code == 200:
                    return response
                
                print(f"Lỗi HTTP {response.status_code} khi truy cập {url}. Thử lại {attempt + 1}/{max_retries}...")
            except Exception as e:
                print(f"Lỗi kết nối ({e}) khi truy cập {url}. Thử lại {attempt + 1}/{max_retries}...")
            
            if attempt < max_retries - 1:
                sleep_time = 2 ** (attempt + 1)
                time.sleep(sleep_time)
        
        return None

    def fetch_hot_threads(self, limit=config.REDDIT_FETCH_LIMIT):
        blacklist = self._load_json(self.blacklist_file, [])
        print(f"[{datetime.now().strftime('%H:%M')}] Đang tải các bài đăng mới nhất từ r/{self.subreddit}...")
        
        response = self._request_with_retry(self.base_url, params={"limit": limit})
        if not response:
            print("Thất bại khi tải threads sau nhiều lần thử.")
            return []

        try:
            # Kiểm tra xem có phải JSON không
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                print(f"Lỗi: Reddit không trả về JSON (Content-Type: {content_type}). Có thể bị chặn hoặc redirect.")
                return []

            data = response.json()
            threads = []
            for post in data['data']['children'][:limit]:
                post_data = post['data']
                tid = post_data['id']
                
                if tid in blacklist:
                    continue

                image_url = None
                if post_data.get('post_hint') == 'image':
                    image_url = post_data.get('url')
                elif 'url' in post_data and any(post_data['url'].endswith(ext) for ext in ['.jpg', '.png', '.gif', '.jpeg']):
                    image_url = post_data['url']
                elif 'preview' in post_data and 'images' in post_data['preview']:
                    source = post_data['preview']['images'][0]['source']
                    image_url = source['url'].replace('&amp;', '&')
                
                threads.append({
                    'id': tid,
                    'title': post_data['title'],
                    'url': post_data['url'],
                    'image_url': image_url,
                    'permalink': post_data['permalink'],
                    'created_utc': post_data['created_utc']
                })
            return threads
        except Exception as e:
            print(f"Lỗi xử lý dữ liệu Reddit: {e}")
            return []

    def fetch_comments(self, thread_id):
        url = f"https://www.reddit.com/r/{self.subreddit}/comments/{thread_id}.json"
        response = self._request_with_retry(url)
        if response:
            try:
                return response.json()
            except:
                return None
        return None

    def run(self):
        tracking = self._load_json(self.tracking_file, {})
        blacklist = self._load_json(self.blacklist_file, [])
        now = time.time()
        deleted_posts = []
        archived_posts = []
        
        # 1. Fetch current hot threads
        hot_threads = self.fetch_hot_threads()
        new_count = 0
        for thread in hot_threads:
            tid = thread['id']
            if tid not in tracking and tid not in blacklist:
                print(f"Phát hiện bài mới: {thread['title'][:50]}...")
                tracking[tid] = {
                    'title': thread['title'],
                    'first_seen': now,
                    'last_updated': 0,
                    'image_url': thread['image_url'],
                    'permalink': thread['permalink'],
                    'status': 'active'
                }
                new_count += 1
            elif tid in tracking:
                # Cập nhật metadata nếu có thay đổi
                if not tracking[tid].get('image_url') and thread['image_url']:
                    tracking[tid]['image_url'] = thread['image_url']
                if tracking[tid].get('title') != thread['title']:
                    tracking[tid]['title'] = thread['title']
        
        if new_count > 0:
            print(f"Đã thêm {new_count} bài đăng mới vào hàng chờ theo dõi.")

        # 2. Lifecycle management
        active_tracking = {}
        for tid, info in tracking.items():
            age = now - info['first_seen']
            
            # Check for manual removal FLAG
            if info.get('manual_remove') or tid in blacklist:
                deleted_posts.append({'id': tid, 'title': info['title'], 'reason': 'Manual/Blacklist'})
                file_path = os.path.join(self.posts_dir, f"{tid}.json")
                if os.path.exists(file_path):
                    os.remove(file_path)
                continue

            if info.get('status') == 'active' and age < 24 * 3600:
                active_tracking[tid] = info
            elif info.get('status') == 'active' and age >= 24 * 3600:
                info['status'] = 'temporary'
                archived_posts.append({'id': tid, 'title': info['title']})
                active_tracking[tid] = info
                # Xóa file JSON chi tiết khi chuyển sang temporary để tiết kiệm bộ nhớ
                file_path = os.path.join(self.posts_dir, f"{tid}.json")
                if os.path.exists(file_path):
                    os.remove(file_path)
            elif info.get('status') == 'temporary' and age < 72 * 3600:
                active_tracking[tid] = info
            else:
                deleted_posts.append({'id': tid, 'title': info['title'], 'reason': 'Expired (72h)'})
                file_path = os.path.join(self.posts_dir, f"{tid}.json")
                if os.path.exists(file_path):
                    os.remove(file_path)

        # 3. Update only ACTIVE threads (Temporary threads are skipped for updates)
        updated_count = 0
        for tid, info in active_tracking.items():
            if info.get('status') == 'active':
                content = self.fetch_comments(tid)
                if content:
                    file_path = os.path.join(self.posts_dir, f"{tid}.json")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump({'thread_info': info, 'data': content}, f, indent=4, ensure_ascii=False)
                    active_tracking[tid]['last_updated'] = now
                    updated_count += 1
        
        print(f"Hoàn tất: Đã cập nhật nội dung cho {updated_count} bài đăng đang active.")

        self._save_json(self.tracking_file, active_tracking)
        return archived_posts, deleted_posts

if __name__ == "__main__":
    crawler = RedditCrawler()
    crawler.run()
