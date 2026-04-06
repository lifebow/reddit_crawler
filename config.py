import os
from dotenv import load_dotenv

load_dotenv()

# Reddit Settings
SUBREDDIT = os.getenv("SUBREDDIT", "LocalLLaMA")
REDDIT_FETCH_LIMIT = 15

# OpenAI / LLM Settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
PROXY_URL = os.getenv("PROXY_URL") # Example: http://user:pass@host:port or socks5://...

# Telegram Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
# GMT+7 Reporting Hours (Default: 10:05 AM and 10:05 PM)
REPORT_HOURS = [10, 22] 

# Path Settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
POSTS_DIR = os.path.join(DATA_DIR, "posts")
SUMMARIES_DIR = os.path.join(DATA_DIR, "summaries")
TRACKING_FILE = os.path.join(DATA_DIR, "tracking.json")
SUBSCRIBERS_FILE = os.path.join(DATA_DIR, "subscribers.json")
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist.json")

# Ensure directories exist
for d in [DATA_DIR, POSTS_DIR, SUMMARIES_DIR]:
    os.makedirs(d, exist_ok=True)
