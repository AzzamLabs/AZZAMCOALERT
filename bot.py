import os
import logging
import asyncio
from datetime import datetime
import pytz
import aiohttp
from telegram import Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# ── Configuration ──────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "YOUR_FINNHUB_API_KEY_HERE")
CHANNEL_ID = os.getenv("CHANNEL_ID", "YOUR_CHANNEL_OR_CHAT_ID_HERE")

# Timezones
TZ_NY     = pytz.timezone("America/New_York")
TZ_LONDON = pytz.timezone("Europe/London")
TZ_TOKYO  = pytz.timezone("Asia/Tokyo")
TZ_UTC    = pytz.utc

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

MARKETS = {
    "tokyo":   {"name": "🇯🇵 Tokyo (Asia)",        "open": "09:00", "close": "15:30", "tz": TZ_TOKYO,  "flag": "🌏"},
    "london":  {"name": "🇬🇧 London",              "open": "08:00", "close": "16:30", "tz": TZ_LONDON, "flag": "🌍"},
    "newyork": {"name": "🇺🇸 New York (NYSE/NASDAQ)", "open": "09:30", "close": "16:00", "tz": TZ_NY,    "flag": "🌎"},
}

# Global bot reference
_bot: Bot = None


def get_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def send(text: str):
    """Send a message synchronously from the background scheduler."""
    async def _send():
        await _bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
    try:
        loop = get_loop()
        loop.run_until_complete(_send())
        logger.info(f"Sent: {text[:60]}")
    except Exception as e:
        logger.error(f"Send error: {e}")


# ── Scheduled Jobs (synchronous — called by BackgroundScheduler) ───────────────

def job_good_morning():
    now = datetime.now(TZ_NY)
    send(
        f"🌅 *Good Morning — AZZAM & Co Team!*\n\n"
        f"📅 {now.strftime('%A, %B %d %Y')}\n\n"
        f"Today's market sessions:\n"
        f"🌏 Tokyo:    09:00 – 15:30 JST\n"
        f"🌍 London:   08:00 – 16:30 GMT\n"
        f"🌎 New York: 09:30 – 16:00 EST\n\n"
        f"Stay focused, trade smart. Let's have a great day! 💼📈"
    )


def job_market_open(market_key: str):
    m = MARKETS[market_key]
    send(
        f"{m['flag']} *MARKET OPEN — {m['name']}*\n\n"
        f"🟢 The {m['name']} session has just opened!\n"
        f"🕐 Local time: {datetime.now(m['tz']).strftime('%H:%M %Z')}\n\n"
        f"Watch for early momentum and liquidity. Good luck traders! 📊"
    )


def job_market_close(market_key: str):
    m = MARKETS[market_key]
    send(
        f"{m['flag']} *MARKET CLOSE — {m['name']}*\n\n"
        f"🔴 The {m['name']} session has closed.\n"
        f"🕐 Local time: {datetime.now(m['tz']).strftime('%H:%M %Z')}\n\n"
        f"Review your trades and prepare for the next session. 📋"
    )


def job_signals():
    async def _fetch():
        results = []
        async with aiohttp.ClientSession() as session:
            for symbol in ["SPY", "QQQ", "EURUSD"]:
                try:
                    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                        q = await r.json()
                    if q and q.get("c") and q.get("pc"):
                        pct = ((q["c"] - q["pc"]) / q["pc"]) * 100
                        emoji = "📈 BULLISH" if pct > 0 else "📉 BEARISH"
                        arrow = "▲" if pct > 0 else "▼"
                        results.append(f"• *{symbol}*: {emoji} {arrow} {abs(pct):.2f}%")
                except Exception:
                    pass
        return results

    try:
        loop = get_loop()
        results = loop.run_until_complete(_fetch())
        if results:
            send(
                f"📊 *AZZAM & Co — Market Signal Update*\n"
                f"🕐 {datetime.now(TZ_NY).strftime('%H:%M EST')}\n\n"
                + "\n".join(results)
                + "\n\n_Based on latest price vs previous close._"
            )
    except Exception as e:
        logger.error(f"Signals error: {e}")


def job_news():
    async def _fetch():
        async with aiohttp.ClientSession() as session:
            url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
        return data[:4] if isinstance(data, list) else []

    try:
        loop = get_loop()
        news = loop.run_until_complete(_fetch())
        if news:
            msg = "📰 *AZZAM & Co — Breaking Financial News*\n\n"
            for item in news:
                h = item.get("headline", "")
                s = item.get("source", "")
                if h:
                    msg += f"• {h}\n  _— {s}_\n\n"
            send(msg)
    except Exception as e:
        logger.error(f"News error: {e}")


def job_events():
    day = datetime.now(TZ_NY).strftime("%A")
    events = {
        "Monday":    "• USD: Fed Member Speeches\n• EUR: Eurozone Sentix Index",
        "Tuesday":   "• USD: Consumer Confidence\n• GBP: UK Claimant Count",
        "Wednesday": "• USD: ADP Employment + Fed Minutes\n• EUR: CPI Flash Estimate",
        "Thursday":  "• USD: Initial Jobless Claims\n• EUR: ECB Meeting (if scheduled)",
        "Friday":    "• USD: Non-Farm Payrolls (NFP) 🔥\n• USD: Unemployment Rate",
    }
    if day in events:
        send(
            f"⚠️ *High Impact Events Today — {day}*\n\n"
            f"{events[day]}\n\n"
            f"_Stay alert — these can cause high volatility!_ 📉📈"
        )


# ── Telegram Commands ──────────────────────────────────────────────────────────

async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *AZZAM & Co Trading Bot is active!*\n\n"
        "You will receive:\n"
        "🌅 Daily Good Morning at 6:00 AM\n"
        "🟢 Market Open alerts\n"
        "🔴 Market Close alerts\n"
        "📊 Bullish/Bearish signals every 2hrs\n"
        "📰 Breaking financial news\n"
        "⚠️ High impact event reminders\n\n"
        "Use /status to check current markets.",
        parse_mode="Markdown"
    )


async def cmd_status(update, context: ContextTypes.DEFAULT_TYPE):
    now_utc = datetime.now(TZ_UTC)
    msg = "📊 *Current Market Status*\n\n"
    for key, m in MARKETS.items():
        local = now_utc.astimezone(m["tz"])
        oh, om = map(int, m["open"].split(":"))
        ch, cm = map(int, m["close"].split(":"))
        is_open = (
            local.weekday() < 5 and
            (local.hour > oh or (local.hour == oh and local.minute >= om)) and
            (local.hour < ch or (local.hour == ch and local.minute < cm))
        )
        status = "🟢 OPEN" if is_open else "🔴 CLOSED"
        msg += f"{m['flag']} *{m['name']}*: {status}\n"
        msg += f"   Local: {local.strftime('%H:%M %Z')}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global _bot

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    _bot = app.bot

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))

    # Use BackgroundScheduler (no asyncio conflict)
    scheduler = BackgroundScheduler(timezone=TZ_UTC)

    # Good Morning 6AM NY
    scheduler.add_job(job_good_morning, "cron", hour=11, minute=0)  # 6AM NY = 11AM UTC

    # Tokyo
    scheduler.add_job(job_market_open,  "cron", hour=0,  minute=0,  args=["tokyo"])   # 9AM JST = 0AM UTC
    scheduler.add_job(job_market_close, "cron", hour=6,  minute=30, args=["tokyo"])   # 3:30PM JST = 6:30AM UTC

    # London
    scheduler.add_job(job_market_open,  "cron", hour=8,  minute=0,  args=["london"])  # 8AM GMT = 8AM UTC
    scheduler.add_job(job_market_close, "cron", hour=16, minute=30, args=["london"])  # 4:30PM GMT = 4:30PM UTC

    # New York
    scheduler.add_job(job_market_open,  "cron", hour=14, minute=30, args=["newyork"]) # 9:30AM EST = 2:30PM UTC
    scheduler.add_job(job_market_close, "cron", hour=21, minute=0,  args=["newyork"]) # 4PM EST = 9PM UTC

    # Signals every 2 hours during NY trading
    scheduler.add_job(job_signals, "cron", hour="15,17,19,21", minute=0)

    # News every 3 hours
    scheduler.add_job(job_news, "cron", hour="8,11,14,17", minute=0)

    # Events weekdays 8AM NY = 1PM UTC
    scheduler.add_job(job_events, "cron", day_of_week="mon-fri", hour=13, minute=0)

    scheduler.start()
    logger.info("🚀 AZZAM & Co Trading Bot is running!")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
