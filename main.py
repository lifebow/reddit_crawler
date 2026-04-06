import time
import asyncio
import os
import logging
from datetime import datetime, timedelta
import config
from crawler import RedditCrawler
from summarizer import RedditSummarizer
from telegram_bot import TelegramBot

# Setup basic logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("MainService")

async def run_crawler_cycle(bot_instance):
    """Thực hiện một chu kỳ crawl và thông báo thay đổi trạng thái."""
    logger.info("=" * 40)
    logger.info("[START] Bắt đầu chu kỳ quét Reddit...")
    try:
        crawler = RedditCrawler()
        # Chạy crawler.run() trong thread riêng để không block event loop
        archived, deleted = await asyncio.to_thread(crawler.run)
        
        if archived or deleted:
            logger.info(f"[Crawler] Phát hiện thay đổi: {len(archived)} archived, {len(deleted)} deleted.")
            await bot_instance.notify_status_change(archived, deleted)
        
        logger.info("[SUCCESS] Hoàn tất chu kỳ quét Reddit.")
    except Exception as e:
        logger.error(f"[ERROR] Lỗi trong chu kỳ quét: {e}", exc_info=True)
    logger.info("=" * 40)

async def run_notification_cycle(bot_instance, force_all=False):
    """Thực hiện một chu kỳ tóm tắt và gửi báo cáo."""
    logger.info("=" * 40)
    logger.info("[START] Bắt đầu chu kỳ tóm tắt và thông báo...")
    try:
        summarizer = RedditSummarizer()
        # Tạo báo cáo
        report = await asyncio.to_thread(summarizer.summarize_run)
        
        if report:
            # Xác định giờ mục tiêu (None = gửi cho tất cả nếu là startup)
            target_hour = None if force_all else datetime.now().hour
            if force_all:
                logger.info("[Notifier] Chế độ startup: Gửi báo cáo cho toàn bộ subscribers.")
            else:
                logger.info(f"[Notifier] Kiểm tra lịch nhận tin cho khung giờ {target_hour}h...")
            
            await bot_instance.send_report(report, target_hour=target_hour)
            logger.info("[SUCCESS] Đã xử lý xong chu kỳ gửi báo cáo.")
        else:
            logger.warning("[SKIP] Không có nội dung tóm tắt để gửi.")
            
    except Exception as e:
        logger.error(f"[ERROR] Lỗi trong chu kỳ tóm tắt: {e}", exc_info=True)
    logger.info("=" * 40)

async def crawler_loop(bot_instance):
    """Vòng lặp chạy crawler vào đúng phút 00 của mỗi giờ."""
    while True:
        try:
            now = datetime.now()
            next_run = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            sleep_seconds = (next_run - now).total_seconds()
            logger.info(f"[Schedule] Đợi đến lượt Crawl tiếp theo: {next_run.strftime('%H:%M:%S')} (Chờ {int(sleep_seconds)}s)")
            await asyncio.sleep(sleep_seconds)
            
            await run_crawler_cycle(bot_instance)
            await asyncio.sleep(60) # Chặn lặp lại trong cùng 1 phút
                
        except Exception as e:
            logger.error(f"[Crawler Loop] Lỗi vòng lặp: {e}")
            await asyncio.sleep(60)

async def notification_loop(bot_instance):
    """Vòng lặp chạy tóm tắt vào đúng phút 05 của mỗi giờ."""
    while True:
        try:
            now = datetime.now()
            next_run = now.replace(minute=5, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(hours=1)
            
            sleep_seconds = (next_run - now).total_seconds()
            logger.info(f"[Schedule] Đợi đến lượt Notifier tiếp theo: {next_run.strftime('%H:%M:%S')} (Chờ {int(sleep_seconds)}s)")
            await asyncio.sleep(sleep_seconds)

            await run_notification_cycle(bot_instance)
            await asyncio.sleep(60)
                
        except Exception as e:
            logger.error(f"[Notifier Loop] Lỗi vòng lặp: {e}")
            await asyncio.sleep(60)

async def main():
    bot = TelegramBot()
    app = await bot.create_app()
    if not app:
        logger.error("Dịch vụ không thể khởi động: Thiếu TELEGRAM_BOT_TOKEN.")
        return

    logger.info("🚀 Dịch vụ Reddit Bot đang khởi động...")
    
    async with app:
        await app.initialize()
        
        # Đợi 1 chút sau khi init để Telegram API sẵn sàng
        await asyncio.sleep(1)
        await bot.register_commands(app)
        
        await app.start()
        await app.updater.start_polling()
        
        # --- QUY TRÌNH CHẠY LẦN ĐẦU (STARTUP) ---
        logger.info(">>> [KHỞI ĐỘNG] Chạy đợt quét & tóm tắt đầu tiên...")
        
        # 1. Quét dữ liệu
        await run_crawler_cycle(bot)
        
        # 2. Tóm tắt và gửi ngay cho Admin/Subscribers
        await run_notification_cycle(bot, force_all=True)
        
        logger.info(">>> [HOÀN TẤT KHỞI ĐỘNG] Chuyển sang chế độ chạy theo lịch.")

        # Chạy song song 2 vòng lặp schedule
        tasks = [
            asyncio.create_task(crawler_loop(bot)),
            asyncio.create_task(notification_loop(bot))
        ]
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            for task in tasks: task.cancel()
            if app.updater.running: await app.updater.stop()
            if app.running: await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Dịch vụ đang dừng...")
    except Exception as e:
        logger.error(f"Lỗi hệ thống nghiêm trọng: {e}")
