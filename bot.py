import os
import logging
import asyncio
from datetime import datetime
import pytz
import aiohttp
from telegram import Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ── Configuration ──────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "YOUR_FINNHUB_API_KEY_HERE")
CHANNEL_ID = os.getenv("CHANNEL_ID", "YOUR_CHANNEL_OR_CHAT_ID_HERE")

# Timezones
TZ_NY     = pytz.timezone("America/New_York")
TZ_LONDON = pytz.timezone("Europe/London")
TZ_TOKYO  = pytz.timezone("Asia/Tokyo")
TZ_UTC    = pytz.utc

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Market Sessions ────────────────────────────────────────────────────────────
MARKETS = {
    "tokyo": {
        "name": "🇯🇵 Tokyo (Asia)",
        "open":  "09:00",
        "close": "15:30",
        "tz":    TZ_TOKYO,
        "flag":  "🌏",
    },
    "london": {
        "name": "🇬🇧 London",
        "open":  "08:00",
        "close": "16:30",
        "tz":    TZ_LONDON,
        "flag":  "🌍",
    },
    "newyork": {
        "name": "🇺🇸 New York (NYSE/NASDAQ)",
        "open":  "09:30",
        "close": "16:00",
        "tz":    TZ_NY,
        "flag":  "🌎",
    },
}

# Key forex/index symbols to check for bullish/bearish
SYMBOLS = ["AAPL", "SPY", "QQQ", "EURUSD", "GBPUSD", "USDJPY"]


# ── Helpers ────────────────────────────────────────────────────────────────────
async def send_message(bot: Bot, text: str):
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="Markdown"
        )
        logger.info(f"Sent: {text[:60]}...")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


async def fetch_quote(session: aiohttp.ClientSession, symbol: str) -> dict:
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    async with session.get(url) as resp:
        return await resp.json()


async def fetch_news(session: aiohttp.ClientSession) -> list:
    url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
    async with session.get(url) as resp:
        data = await resp.json()
        return data[:5] if isinstance(data, list) else []


# ── Scheduled Jobs ─────────────────────────────────────────────────────────────

async def good_morning(bot: Bot):
    now = datetime.now(TZ_NY)
    date_str = now.strftime("%A, %B %d %Y")
    msg = (
        f"🌅 *Good Morning — AZZAM & Co Team!*\n\n"
        f"📅 {date_str}\n\n"
        f"Today's market sessions:\n"
        f"🌏 Tokyo:    09:00 – 15:30 JST\n"
        f"🌍 London:   08:00 – 16:30 GMT\n"
        f"🌎 New York: 09:30 – 16:00 EST\n\n"
        f"Stay focused, trade smart. Let's have a great day! 💼📈"
    )
    await send_message(bot, msg)


async def market_open_alert(bot: Bot, market_key: str):
    m = MARKETS[market_key]
    msg = (
        f"{m['flag']} *MARKET OPEN — {m['name']}*\n\n"
        f"🟢 The {m['name']} session has just opened!\n"
        f"🕐 Local time: {datetime.now(m['tz']).strftime('%H:%M %Z')}\n\n"
        f"Watch for early momentum and liquidity. Good luck traders! 📊"
    )
    await send_message(bot, msg)


async def market_close_alert(bot: Bot, market_key: str):
    m = MARKETS[market_key]
    msg = (
        f"{m['flag']} *MARKET CLOSE — {m['name']}*\n\n"
        f"🔴 The {m['name']} session has closed.\n"
        f"🕐 Local time: {datetime.now(m['tz']).strftime('%H:%M %Z')}\n\n"
        f"Review your trades and prepare for the next session. 📋"
    )
    await send_message(bot, msg)


async def bullish_bearish_signal(bot: Bot):
    try:
        async with aiohttp.ClientSession() as session:
            results = []
            for symbol in ["SPY", "QQQ", "EURUSD"]:
                try:
                    quote = await fetch_quote(session, symbol)
                    if quote and "c" in quote and "pc" in quote:
                        current = quote["c"]
                        prev_close = quote["pc"]
                        if prev_close and prev_close > 0:
                            change_pct = ((current - prev_close) / prev_close) * 100
                            emoji = "📈 BULLISH" if change_pct > 0 else "📉 BEARISH"
                            arrow = "▲" if change_pct > 0 else "▼"
                            results.append(
                                f"• *{symbol}*: {emoji} {arrow} {abs(change_pct):.2f}%"
                            )
                except Exception:
                    continue

            if results:
                msg = (
                    f"📊 *AZZAM & Co — Market Signal Update*\n"
                    f"🕐 {datetime.now(TZ_NY).strftime('%H:%M EST')}\n\n"
                    + "\n".join(results)
                    + "\n\n_Based on latest price vs previous close._"
                )
                await send_message(bot, msg)
    except Exception as e:
        logger.error(f"Signal error: {e}")


async def breaking_news(bot: Bot):
    try:
        async with aiohttp.ClientSession() as session:
            news = await fetch_news(session)
            if not news:
                return

            msg = "📰 *AZZAM & Co — Breaking Financial News*\n\n"
            for item in news[:4]:
                headline = item.get("headline", "")
                source = item.get("source", "")
                url = item.get("url", "")
                if headline:
                    msg += f"• {headline}\n  _— {source}_\n\n"

            await send_message(bot, msg)
    except Exception as e:
        logger.error(f"News error: {e}")


async def high_impact_events(bot: Bot):
    # High impact economic events reminder (static schedule of key weekly events)
    now = datetime.now(TZ_NY)
    day = now.strftime("%A")

    events = {
        "Monday":    "• USD: Fed Member Speeches\n• EUR: Eurozone Sentix Index",
        "Tuesday":   "• USD: Consumer Confidence\n• GBP: UK Claimant Count",
        "Wednesday": "• USD: ADP Employment + Fed Minutes\n• EUR: CPI Flash Estimate",
        "Thursday":  "• USD: Initial Jobless Claims\n• EUR: ECB Meeting (if scheduled)",
        "Friday":    "• USD: Non-Farm Payrolls (NFP) 🔥\n• USD: Unemployment Rate",
    }

    if day in events:
        msg = (
            f"⚠️ *High Impact Events Today — {day}*\n\n"
            f"{events[day]}\n\n"
            f"_Stay alert — these can cause high volatility!_ 📉📈"
        )
        await send_message(bot, msg)


# ── Bot Commands ───────────────────────────────────────────────────────────────
async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *AZZAM & Co Trading Bot is active!*\n\n"
        "You will receive:\n"
        "🌅 Daily Good Morning at 6:00 AM\n"
        "🟢 Market Open alerts\n"
        "🔴 Market Close alerts\n"
        "📊 Bullish/Bearish signals\n"
        "📰 Breaking financial news\n"
        "⚠️ High impact event reminders\n\n"
        "Use /status to check current market sessions.",
        parse_mode="Markdown"
    )


async def status(update, context: ContextTypes.DEFAULT_TYPE):
    now_utc = datetime.now(TZ_UTC)
    msg = "📊 *Current Market Status*\n\n"

    for key, m in MARKETS.items():
        local_time = now_utc.astimezone(m["tz"])
        open_h, open_m = map(int, m["open"].split(":"))
        close_h, close_m = map(int, m["close"].split(":"))
        is_open = (
            local_time.weekday() < 5 and
            (local_time.hour > open_h or (local_time.hour == open_h and local_time.minute >= open_m)) and
            (local_time.hour < close_h or (local_time.hour == close_h and local_time.minute < close_m))
        )
        status_emoji = "🟢 OPEN" if is_open else "🔴 CLOSED"
        msg += f"{m['flag']} *{m['name']}*: {status_emoji}\n"
        msg += f"   Local: {local_time.strftime('%H:%M %Z')}\n\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


# ── Scheduler Setup ────────────────────────────────────────────────────────────
def setup_scheduler(scheduler: AsyncIOScheduler, bot: Bot):

    # Good Morning — 6:00 AM New York time
    scheduler.add_job(good_morning, "cron", hour=6, minute=0,
                      timezone=TZ_NY, args=[bot])

    # Tokyo open/close (JST)
    scheduler.add_job(market_open_alert,  "cron", hour=9,  minute=0,  timezone=TZ_TOKYO,  args=[bot, "tokyo"])
    scheduler.add_job(market_close_alert, "cron", hour=15, minute=30, timezone=TZ_TOKYO,  args=[bot, "tokyo"])

    # London open/close (GMT)
    scheduler.add_job(market_open_alert,  "cron", hour=8,  minute=0,  timezone=TZ_LONDON, args=[bot, "london"])
    scheduler.add_job(market_close_alert, "cron", hour=16, minute=30, timezone=TZ_LONDON, args=[bot, "london"])

    # New York open/close (EST)
    scheduler.add_job(market_open_alert,  "cron", hour=9,  minute=30, timezone=TZ_NY,     args=[bot, "newyork"])
    scheduler.add_job(market_close_alert, "cron", hour=16, minute=0,  timezone=TZ_NY,     args=[bot, "newyork"])

    # Bullish/Bearish signals — every 2 hours during NY trading hours
    scheduler.add_job(bullish_bearish_signal, "cron", hour="10,12,14,16",
                      minute=0, timezone=TZ_NY, args=[bot])

    # Breaking news — every 3 hours
    scheduler.add_job(breaking_news, "cron", hour="7,10,13,16",
                      minute=0, timezone=TZ_NY, args=[bot])

    # High impact events reminder — every weekday at 8:00 AM NY
    scheduler.add_job(high_impact_events, "cron", hour=8, minute=0,
                      day_of_week="mon-fri", timezone=TZ_NY, args=[bot])


# ── Main ───────────────────────────────────────────────────────────────────────
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot = app.bot

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))

    scheduler = AsyncIOScheduler()
    setup_scheduler(scheduler, bot)
    scheduler.start()

    logger.info("🚀 AZZAM & Co Trading Bot is running!")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
