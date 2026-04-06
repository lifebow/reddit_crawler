import os
import json
import logging
import time
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.admin_id = config.TELEGRAM_ADMIN_ID
        self.subscribers_file = config.SUBSCRIBERS_FILE
        self.tracking_file = config.TRACKING_FILE
        self.blacklist_file = config.BLACKLIST_FILE
        self.latest_summary_file = os.path.join(config.SUMMARIES_DIR, "latest_summary.md")
        self.application = None

    def _load_json(self, path, default):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading JSON {path}: {e}")
                return default
        return default

    def _save_json(self, path, data):
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving JSON {path}: {e}")

    def _get_approved_subs(self, data):
        # Handle both legacy list and new dict formats
        approved = data.get("approved", {})
        if isinstance(approved, list):
            # Migrate to dict format: {user_id: [default_hours]}
            migrated = {uid: config.REPORT_HOURS for uid in approved}
            data["approved"] = migrated
            self._save_json(self.subscribers_file, data)
            logger.info("Migrated subscribers.json to new format.")
            return migrated
        return approved

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        username = update.effective_user.username or update.effective_user.first_name
        data = self._load_json(self.subscribers_file, {"approved": {}, "pending": []})
        approved = self._get_approved_subs(data)

        if user_id in approved:
            await update.message.reply_text("✅ Bạn đã đăng ký nhận bản tin rồi!")
            return

        if user_id in data.get("pending", []):
            await update.message.reply_text("⏳ Yêu cầu của bạn đang chờ Admin phê duyệt.")
            return

        if "pending" not in data: data["pending"] = []
        data["pending"].append(user_id)
        self._save_json(self.subscribers_file, data)
        await update.message.reply_text("📩 Yêu cầu của bạn đã được gửi tới Admin.")
        
        if self.admin_id:
            keyboard = [[
                InlineKeyboardButton("Phê duyệt ✅", callback_data=f"sub_approve_{user_id}"),
                InlineKeyboardButton("Từ chối ❌", callback_data=f"sub_reject_{user_id}")
            ]]
            await context.bot.send_message(
                chat_id=self.admin_id,
                text=f"🔔 Yêu cầu đăng ký mới:\n- User: {username}\n- ID: {user_id}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def list_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != self.admin_id:
            return

        tracking = self._load_json(self.tracking_file, {})
        blacklist = self._load_json(self.blacklist_file, [])
        
        # Filter out blacklisted or manually removed items
        active_items = {
            tid: info for tid, info in tracking.items() 
            if tid not in blacklist and not info.get('manual_remove')
        }

        if not active_items:
            await update.message.reply_text("Hiện không có bài đăng nào đang được theo dõi.")
            return

        now = time.time()
        text = "📋 **Danh sách bài đăng đang theo dõi:**\n\n"
        
        for tid, info in active_items.items():
            age = now - info['first_seen']
            status_icon = "🟢" if info['status'] == 'active' else "🟡"
            
            if info['status'] == 'active':
                remaining = max(0, int((24 * 3600 - age) / 60))
                time_str = f"Hết hạn sau: {remaining} phút"
                if remaining > 60:
                    time_str = f"Hết hạn sau: {remaining // 60}h {remaining % 60}m"
            else:
                remaining_temp = max(0, int((72 * 3600 - age) / 60))
                time_str = f"Xóa sau: {remaining_temp // 60}h {remaining_temp % 60}m (Temporary)"

            text += f"{status_icon} **{info['title'][:60]}...**\n"
            text += f"└ ID: `{tid}` | {time_str}\n\n"

        text += "💡 *Lệnh quản trị:*\n"
        text += "- Gia hạn: `/approve <ID>`\n"
        text += "- Gỡ sớm: `/remove <ID>`\n"
        text += "- Chặn vĩnh viễn: `/blacklist <ID>`"
        try:
            await update.message.reply_text(text, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception:
            await update.message.reply_text(text, disable_web_page_preview=True)

    async def blacklist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != self.admin_id: return
        if not context.args:
            await update.message.reply_text("Vui lòng nhập ID cần chặn: `/blacklist <ID>`")
            return
        
        target_id = context.args[0]
        blacklist = self._load_json(self.blacklist_file, [])
        if target_id not in blacklist:
            blacklist.append(target_id)
            self._save_json(self.blacklist_file, blacklist)
            await update.message.reply_text(f"🚫 Đã thêm `{target_id}` vào blacklist. Bot sẽ bỏ qua bài viết này mãi mãi.")
        else:
            await update.message.reply_text("ID này đã có trong blacklist.")

    async def unblacklist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != self.admin_id: return
        if not context.args:
            await update.message.reply_text("Vui lòng nhập ID cần bỏ chặn: `/unblacklist <ID>`")
            return
        
        target_id = context.args[0]
        blacklist = self._load_json(self.blacklist_file, [])
        if target_id in blacklist:
            blacklist.remove(target_id)
            self._save_json(self.blacklist_file, blacklist)
            await update.message.reply_text(f"✅ Đã gỡ `{target_id}` khỏi blacklist.")
        else:
            await update.message.reply_text("ID này không có trong blacklist.")

    async def remove_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != self.admin_id: return
        if not context.args:
            await update.message.reply_text("Vui lòng nhập ID cần gỡ: `/remove <ID>`")
            return
        
        target_id = context.args[0]
        tracking = self._load_json(self.tracking_file, {})
        if target_id in tracking:
            tracking[target_id]['manual_remove'] = True
            self._save_json(self.tracking_file, tracking)
            await update.message.reply_text(f"🗑️ Đã đánh dấu gỡ bỏ bài đăng `{target_id}`. Dữ liệu sẽ được xóa ở lần crawl tiếp theo.")
        else:
            await update.message.reply_text("ID này không có trong danh sách theo dõi.")

    async def approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != self.admin_id:
            return

        if not context.args:
            await update.message.reply_text("Vui lòng cung cấp ID: `/approve <ID>`")
            return

        target_id = context.args[0]
        
        subs = self._load_json(self.subscribers_file, {"approved": {}, "pending": []})
        if target_id in subs.get("pending", []):
            subs["pending"].remove(target_id)
            approved = self._get_approved_subs(subs)
            approved[target_id] = config.REPORT_HOURS
            subs["approved"] = approved
            self._save_json(self.subscribers_file, subs)
            await update.message.reply_text(f"✅ Đã phê duyệt người dùng {target_id}.")
            try: await context.bot.send_message(chat_id=target_id, text="🚀 Bạn đã được phê duyệt! Giờ nhận tin mặc định của bạn là 9:00 và 21:00. Dùng `/schedule` để thay đổi.")
            except Exception as e: logger.error(f"Error sending approval: {e}")
            return

        tracking = self._load_json(self.tracking_file, {})
        if target_id in tracking:
            tracking[target_id]['status'] = 'active'
            tracking[target_id]['first_seen'] = time.time()
            tracking[target_id].pop('manual_remove', None)
            self._save_json(self.tracking_file, tracking)
            await update.message.reply_text(f"💎 Đã gia hạn thành công bài đăng `{target_id}` thêm 24h cập nhật!")
            return

        await update.message.reply_text("❌ ID không hợp lệ hoặc không có trong danh sách chờ.")

    async def get_latest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        subs = self._load_json(self.subscribers_file, {"approved": {}, "pending": []})
        approved = self._get_approved_subs(subs)
        if user_id not in approved and user_id != self.admin_id: return

        if not os.path.exists(self.latest_summary_file):
            await update.message.reply_text("📭 Hiện chưa có bản tóm tắt nào.")
            return

        try:
            with open(self.latest_summary_file, 'r', encoding='utf-8') as f:
                report_text = f.read()
            if not report_text:
                await update.message.reply_text("📭 Bản tóm tắt hiện đang trống.")
                return
            
            await self.send_text_in_chunks(update.message.chat_id, report_text)
        except Exception as e:
            logger.error(f"Error in get_latest: {e}")

    async def force_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin command to manually trigger summarizer and send to all approved users."""
        if str(update.effective_user.id) != self.admin_id: return
        
        from summarizer import RedditSummarizer
        await update.message.reply_text("⏳ Đang tạo báo cáo mới và gửi cho mọi người...")
        
        try:
            summarizer = RedditSummarizer()
            report = await asyncio.to_thread(summarizer.summarize_run)
            if report:
                await self.send_report(report)
                await update.message.reply_text("✅ Đã gửi báo cáo thành công!")
            else:
                await update.message.reply_text("📭 Không có dữ liệu để tạo báo cáo.")
        except Exception as e:
            logger.error(f"Error in force_report: {e}")
            await update.message.reply_text(f"❌ Lỗi: {e}")

    async def send_text_in_chunks(self, chat_id, text):
        """Helper to send long text in chunks."""
        bot = self.application.bot if self.application else None
        if not bot:
            from telegram import Bot
            bot = Bot(token=self.token)

        chunks = text.split("\n\n────────────────\n\n")
        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            msg = chunk
            if i < len(chunks) - 1:
                msg += "\n\n────────────────"
            try:
                try:
                    await bot.send_message(chat_id=chat_id, text=msg, parse_mode='MarkdownV2', disable_web_page_preview=True)
                except Exception:
                    await bot.send_message(chat_id=chat_id, text=msg, disable_web_page_preview=True)
            except Exception as e:
                logger.error(f"Error sending chunk to {chat_id}: {e}")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if str(update.effective_user.id) != self.admin_id: return

        data_parts = query.data.split("_")
        prefix, action, target_id = data_parts[0], data_parts[1], data_parts[2]

        if prefix == "sub":
            subs = self._load_json(self.subscribers_file, {"approved": {}, "pending": []})
            if action == "approve":
                if target_id in subs.get("pending", []):
                    subs["pending"].remove(target_id)
                    approved = self._get_approved_subs(subs)
                    approved[target_id] = config.REPORT_HOURS
                    subs["approved"] = approved
                    self._save_json(self.subscribers_file, subs)
                    await query.edit_message_text(f"✅ Đã phê duyệt {target_id}.")
                    try: await context.bot.send_message(chat_id=target_id, text="🚀 Bạn đã được phê duyệt! Giờ nhận tin mặc định của bạn là 9:00 và 21:00. Dùng `/schedule` để thay đổi.")
                    except: pass
            elif action == "reject":
                if target_id in subs.get("pending", []):
                    subs["pending"].remove(target_id)
                    self._save_json(self.subscribers_file, subs)
                    await query.edit_message_text(f"❌ Đã từ chối {target_id}.")

    async def notify_status_change(self, archived, deleted):
        if not self.admin_id or (not archived and not deleted): return
        bot = self.application.bot if self.application else None
        if not bot:
            from telegram import Bot
            bot = Bot(token=self.token)

        text = ""
        if archived:
            text += "🟡 **Chuyển sang Temporary:**\n"
            for p in archived: text += f"- {p['title'][:50]}... ID: `{p['id']}`\n"
        if deleted:
            text += "\n🗑️ **Đã xóa vĩnh viễn/Gỡ bỏ:**\n"
            for p in deleted: text += f"- {p['title'][:50]}...\n"
        
        try: 
            await bot.send_message(chat_id=self.admin_id, text=text, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception:
            try: await bot.send_message(chat_id=self.admin_id, text=text, disable_web_page_preview=True)
            except Exception as e: logger.error(f"Error notifying: {e}")

    async def send_report(self, report_text, target_hour=None):
        if not self.token: return
        
        data = self._load_json(self.subscribers_file, {"approved": {}, "pending": []})
        approved = self._get_approved_subs(data)
        
        for user_id, hours in approved.items():
            if target_hour is not None and target_hour not in hours:
                continue
            
            await self.send_text_in_chunks(user_id, report_text)

    async def schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        data = self._load_json(self.subscribers_file, {"approved": {}, "pending": []})
        approved = self._get_approved_subs(data)

        if user_id not in approved and user_id != self.admin_id:
            await update.message.reply_text("🚫 Bạn cần được phê duyệt trước khi cài đặt giờ nhận tin.")
            return

        if not context.args:
            current = approved.get(user_id, config.REPORT_HOURS)
            await update.message.reply_text(
                f"⏰ Giờ nhận tin hiện tại của bạn: `{current}`\n\n"
                "Sử dụng: `/schedule <giờ1>, <giờ2>, ...` (từ 0 đến 23).\n"
                "Ví dụ: `/schedule 8, 12, 20`",
                parse_mode='Markdown'
            )
            return

        try:
            # Parse hours from args (handle comma separated or space separated)
            input_text = " ".join(context.args).replace(",", " ")
            new_hours = sorted(list(set([int(h.strip()) for h in input_text.split() if h.strip()])))
            
            # Validate
            if any(h < 0 or h > 23 for h in new_hours):
                await update.message.reply_text("❌ Giờ không hợp lệ! Vui lòng chọn từ 0 đến 23.")
                return

            approved[user_id] = new_hours
            data["approved"] = approved
            self._save_json(self.subscribers_file, data)
            await update.message.reply_text(f"✅ Đã cập nhật giờ nhận tin của bạn: `{new_hours}`", parse_mode='Markdown')
        except ValueError:
            await update.message.reply_text("❌ Định dạng không hợp lệ! Ví dụ: `/schedule 9, 21`")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
        if self.admin_id:
            try: await context.bot.send_message(chat_id=self.admin_id, text=f"⚠️ **Bot Error:**\n`{str(context.error)[:3000]}`", parse_mode='Markdown')
            except: pass

    async def register_commands(self, application=None):
        bot = application.bot if application else self.application.bot
        
        logger.info("🛠️ Đang đăng ký danh sách lệnh với Telegram...")
        commands = [
            BotCommand("start", "Đăng ký nhận báo cáo định kỳ"),
            BotCommand("latest", "Nhận bản tóm tắt mới nhất ngay lập tức"),
            BotCommand("schedule", "Cài đặt giờ nhận tin cá nhân"),
            BotCommand("list", "Xem danh sách bài đăng & Quản trị (Admin)"),
            BotCommand("force_report", "Ép chạy tóm tắt & gửi ngay (Admin)"),
            BotCommand("approve", "Gia hạn bài đăng hoặc Phê duyệt user (Admin)"),
            BotCommand("remove", "Ngừng theo dõi bài đăng sớm (Admin)"),
            BotCommand("blacklist", "Chặn vĩnh viễn bài đăng theo ID (Admin)"),
            BotCommand("unblacklist", "Gỡ chặn bài đăng (Admin)")
        ]
        try:
            await bot.set_my_commands(commands)
            logger.info("✅ Đăng ký lệnh thành công với Telegram API!")
        except Exception as e:
            logger.error(f"❌ Lỗi đăng ký lệnh: {e}")

    async def create_app(self):
        if not self.token: return None
        app = ApplicationBuilder().token(self.token).post_init(self.register_commands).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("latest", self.get_latest))
        app.add_handler(CommandHandler("schedule", self.schedule))
        app.add_handler(CommandHandler("list", self.list_tracking))
        app.add_handler(CommandHandler("approve", self.approve))
        app.add_handler(CommandHandler("remove", self.remove_tracking))
        app.add_handler(CommandHandler("blacklist", self.blacklist))
        app.add_handler(CommandHandler("unblacklist", self.unblacklist))
        app.add_handler(CommandHandler("force_report", self.force_report))
        app.add_handler(CallbackQueryHandler(self.button_handler))
        app.add_error_handler(self.error_handler)
        self.application = app
        return app

if __name__ == "__main__":
    import asyncio
    bot = TelegramBot()
    app = asyncio.run(bot.create_app())
    if app: app.run_polling()
