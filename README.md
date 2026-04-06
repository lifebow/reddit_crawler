# 🤖 Reddit Crawler & Telegram Summary Bot

An automated service that crawls hot threads from a Reddit subreddit, generates AI-powered Vietnamese summaries, and delivers periodic reports to subscribers via a Telegram bot.

## ✨ Features

- **Reddit Hot Thread Crawler** — Fetches trending posts from any subreddit (default: `r/LocalLLaMA`) using Reddit's public JSON API with proxy support.
- **AI-Powered Summarization** — Summarizes threads and their top comments into concise Vietnamese bullet-points using an OpenAI-compatible LLM.
- **Image Analysis** — Extracts text (OCR) and describes images attached to posts via a vision-capable model.
- **Telegram Bot Interface** — Delivers formatted reports to approved subscribers with admin management, scheduling, and inline controls.
- **Post Lifecycle Management** — Automatically tracks, archives, and cleans up posts across a 3-stage lifecycle (Active → Temporary → Deleted).
- **Scheduled Reporting** — Crawls every hour on the hour (:00) and summarizes/sends reports at :05. Subscribers can customize which hours they receive reports.
- **Docker-Ready** — Comes with `Dockerfile` and `docker-compose.yml` for one-command deployment.

## 🏗️ Architecture

```
main.py                 # Entry point — orchestrates crawler, summarizer, and bot
├── crawler.py          # RedditCrawler — fetches hot threads & comments from Reddit
├── summarizer.py       # RedditSummarizer — generates AI summaries via OpenAI API
├── telegram_bot.py     # TelegramBot — handles commands, subscriptions & delivery
└── config.py           # Centralized configuration from environment variables
```

### Data Flow

```
Reddit JSON API
      │
      ▼
  ┌────────────┐     ┌──────────────┐     ┌──────────────┐
  │  Crawler    │────▶│  Summarizer  │────▶│ Telegram Bot │
  │ (hourly)   │     │  (LLM + OCR) │     │  (delivery)  │
  └────────────┘     └──────────────┘     └──────────────┘
      │                     │                     │
      ▼                     ▼                     ▼
  data/posts/          data/summaries/       subscribers.json
  tracking.json        latest_summary.md
```

### Post Lifecycle

| Stage | Duration | Behavior |
|---|---|---|
| 🟢 **Active** | 0 – 24h | Full crawling & comment updates every hour |
| 🟡 **Temporary** | 24h – 72h | Retained in tracking with last summary, no longer updated |
| 🔴 **Deleted** | > 72h | Removed from tracking and all data files |

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A Telegram Bot token (from [@BotFather](https://t.me/BotFather))
- An OpenAI-compatible API key
- _(Optional)_ A proxy URL if Reddit is blocked in your region

### 1. Clone & Install

```bash
git clone <repository-url>
cd reddit-crawler_new

python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example env file and fill in your credentials:

```bash
cp .env-example .env
```

Edit `.env`:

```env
# LLM Settings
OPENAI_API_KEY=xxx
OPENAI_BASE_URL=xxx
OPENAI_MODEL_NAME=gpt-5.3-codex
OPENAI_VISION_MODEL_NAME=gpt-5.3-codex

# Telegram Settings
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_ADMIN_ID=xxx

# Optional Constraints (Optional)
SUBREDDIT=LocalLLaMA

# VPN Settings (for NordVPN via Gluetun)
# Get token from: https://my.nordvpn.com/dashboard/nordvpn/
PROXY_URL=xxx
```

### 3. Run

```bash
python main.py
```

On startup the bot will:
1. Run an initial crawl cycle
2. Generate and send a summary report to all subscribers
3. Switch to scheduled mode (crawl at :00, summarize at :05 each hour)

## 🐳 Docker Deployment

```bash
docker compose up -d --build
```

The `docker-compose.yml` mounts `./data` so crawled data persists across container restarts. The timezone is set to `Asia/Ho_Chi_Minh` (GMT+7).

## 📱 Telegram Commands

### User Commands

| Command | Description |
|---|---|
| `/start` | Subscribe to receive periodic reports (requires admin approval) |
| `/latest` | Get the most recent summary report immediately |
| `/schedule <hours>` | Set custom report hours, e.g. `/schedule 8, 12, 20` |

### Admin Commands

| Command | Description |
|---|---|
| `/list` | View all tracked posts with status and remaining time |
| `/force_report` | Manually trigger a summarize + send cycle |
| `/approve <ID>` | Approve a pending subscriber **or** renew a post for another 24h |
| `/remove <ID>` | Mark a post for removal at next crawl cycle |
| `/blacklist <ID>` | Permanently block a post from being tracked |
| `/unblacklist <ID>` | Remove a post from the permanent blacklist |

> **Note:** The admin is identified by `TELEGRAM_ADMIN_ID` in `.env`. Subscription requests trigger an inline approval prompt sent directly to the admin.

## ⚙️ Configuration Reference

All configuration lives in `config.py` and is driven by environment variables:

| Variable | Default | Description |
|---|---|---|
| `SUBREDDIT` | `LocalLLaMA` | Target subreddit to crawl |
| `OPENAI_API_KEY` | — | API key for the LLM provider |
| `OPENAI_BASE_URL` | — | Base URL for the OpenAI-compatible API |
| `OPENAI_MODEL_NAME` | `gpt-4o-mini` | Model used for summarization & image analysis |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_ADMIN_ID` | — | Telegram user ID of the admin |
| `PROXY_URL` | `None` | HTTP/SOCKS proxy for Reddit requests |

Internal constants (in `config.py`):

| Constant | Value | Description |
|---|---|---|
| `REDDIT_FETCH_LIMIT` | `15` | Max hot threads fetched per cycle |
| `REPORT_HOURS` | `[10, 22]` | Default subscriber report hours (GMT+7) |

## 📂 Project Structure

```
reddit-crawler_new/
├── .env-example            # Template for environment variables
├── .gitignore
├── Dockerfile              # Python 3.10-slim container
├── docker-compose.yml      # Production deployment config
├── requirements.txt        # Python dependencies
├── config.py               # Centralized settings & path management
├── main.py                 # Entry point — scheduler & lifecycle
├── crawler.py              # Reddit data fetching
├── summarizer.py           # LLM-powered thread summarization
├── telegram_bot.py         # Telegram bot handlers & delivery
├── blacklist.json/         # Per-subreddit blacklist storage
└── data/                   # Runtime data (gitignored)
    ├── posts/              # Raw thread JSON files
    ├── summaries/          # Generated report files
    ├── tracking.json       # Post lifecycle state
    ├── subscribers.json    # User subscriptions & schedules
    └── blacklist.json      # Blacklisted post IDs
```

## 🔧 Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP client for Reddit API |
| `python-telegram-bot` | Telegram Bot API framework |
| `openai` | OpenAI-compatible LLM client |
| `python-dotenv` | Load `.env` into environment |
| `httpx` | Async HTTP transport |
| `pysocks` | SOCKS proxy support |

## 📄 License

This project is provided as-is for personal use.
