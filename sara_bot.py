"""
Sara JobHunter — Telegram bot.

Sara is Ganna's personal job search assistant. She hunts for creative IT
product roles across Europe twice a day and messages Ganna directly on Telegram.
"""

import os
import time
import logging
import schedule
import requests
from datetime import datetime
from dotenv import load_dotenv
from job_searcher import fetch_new_jobs

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sara.log"),
    ],
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ── Telegram helpers ──────────────────────────────────────────────────────────

def send_message(text: str, parse_mode: str = "HTML", disable_preview: bool = True) -> bool:
    try:
        resp = requests.post(
            f"{BASE_URL}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_preview,
            },
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return False


def get_my_chat_id():
    """Poll for the first message and return the sender's chat ID."""
    try:
        resp = requests.get(f"{BASE_URL}/getUpdates", timeout=10)
        updates = resp.json().get("result", [])
        if updates:
            return str(updates[-1]["message"]["chat"]["id"])
    except Exception:
        pass
    return None


# ── Message builders ──────────────────────────────────────────────────────────

SCORE_STARS = {0: "", 1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "🌟🌟", 5: "🔥"}

def _stars(score: int) -> str:
    bracket = min(score // 3, 5)
    return SCORE_STARS.get(bracket, "🔥")


def format_job_card(job: dict, index: int) -> str:
    stars = _stars(job.get("score", 0))
    loc = job.get("location", "")
    remote_tag = "🏠 Remote" if any(w in loc.lower() for w in ["remote", "anywhere", "worldwide"]) else f"📍 {loc}"
    posted = job.get("posted", "")
    posted_str = f" · {posted}" if posted else ""
    desc = job.get("description", "").strip()
    desc_preview = (desc[:180] + "…") if len(desc) > 180 else desc

    lines = [
        f"<b>{index}. {job['title']}</b> {stars}",
        f"🏢 {job.get('company', 'Unknown')}",
        f"{remote_tag}{posted_str}",
        f"🔗 <a href=\"{job['url']}\">View & Apply</a>",
    ]
    if desc_preview:
        lines.append(f"\n<i>{desc_preview}</i>")

    return "\n".join(lines)


def send_job_batch(jobs: list[dict]) -> None:
    """Send jobs in batches of 5 so messages stay readable."""
    batch_size = 5
    total = len(jobs)

    for start in range(0, total, batch_size):
        batch = jobs[start:start + batch_size]
        parts = []
        for i, job in enumerate(batch, start=start + 1):
            parts.append(format_job_card(job, i))
        send_message("\n\n─────────────────\n\n".join(parts))
        time.sleep(1)


# ── Sara's personality messages ───────────────────────────────────────────────

def send_intro(count: int, is_first: bool = False) -> None:
    now = datetime.now()
    greeting = "Good morning ☀️" if now.hour < 13 else "Hey there 👋"

    if is_first:
        msg = (
            f"Hi Ganna! I'm <b>Sara</b>, your personal job hunting assistant 🎯\n\n"
            f"I'll search twice a day for creative IT product roles across Europe "
            f"that match your background in SaaS, fintech, sports tech, and AI products.\n\n"
            f"I found <b>{count} new roles</b> to kick things off — let's go! 🚀"
        )
    else:
        templates = [
            f"{greeting} Ganna! I found <b>{count} new role{'s' if count > 1 else ''}</b> that look like a great fit 👇",
            f"{greeting}! Sara here 🕵️‍♀️ — just finished my job hunt and found <b>{count} interesting position{'s' if count > 1 else ''}</b> for you:",
            f"Fresh picks for you, Ganna! ✨ I spotted <b>{count} role{'s' if count > 1 else ''}</b> worth checking out today:",
        ]
        from random import choice
        msg = choice(templates)

    send_message(msg)


def send_no_new_jobs() -> None:
    msgs = [
        "Hey Ganna! 👋 Sara checked everywhere — nothing new and exciting yet. I'll ping you the moment something good shows up. Stay creative! 🎨",
        "Hi! It's Sara 🕵️‍♀️ — quiet day on the job boards. I'm keeping watch and will message you as soon as something cool lands. Hang tight!",
    ]
    from random import choice
    send_message(choice(msgs))


def send_outro(count: int) -> None:
    if count <= 3:
        msg = "That's all for now! I'll be back with more soon 💌 — Sara"
    elif count <= 8:
        msg = f"That's your {count} picks for today! Remember: you're looking for the creative, feature-driven role 🎯 Good luck! — Sara"
    else:
        msg = f"Wow, {count} roles today! Quality over quantity — I sorted them by match score, so start from the top ⬆️ — Sara"
    send_message(msg)


# ── Main search run ───────────────────────────────────────────────────────────

_is_first_run = True

def run_search() -> None:
    global _is_first_run
    log.info("=== Sara starting job search run ===")

    jobs = fetch_new_jobs()

    if not jobs:
        send_no_new_jobs()
        _is_first_run = False
        return

    send_intro(len(jobs), is_first=_is_first_run)
    time.sleep(1)
    send_job_batch(jobs)
    time.sleep(1)
    send_outro(len(jobs))

    _is_first_run = False
    log.info("Sara sent %d jobs to Ganna", len(jobs))


# ── Command listener (basic /start, /search, /help) ──────────────────────────

def listen_for_commands() -> None:
    """Simple long-poll listener for user commands."""
    offset = None
    log.info("Sara is listening for Telegram commands…")

    while True:
        try:
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            resp = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=35)
            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "").strip().lower()
                chat_id = str(msg.get("chat", {}).get("id", ""))

                if chat_id != CHAT_ID:
                    continue

                if text in ["/start", "/help"]:
                    send_message(
                        "Hi! I'm <b>Sara</b> 👋 your personal PM job hunter.\n\n"
                        "<b>Commands:</b>\n"
                        "/search — search for new jobs right now\n"
                        "/help — show this message\n\n"
                        "I automatically search twice a day (9am &amp; 6pm) and message you when I find something good 🎯"
                    )
                elif text == "/search":
                    send_message("On it! 🔍 Let me check the job boards for you…")
                    run_search()

        except Exception as e:
            log.error("Command listener error: %s", e)
            time.sleep(5)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import threading

    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    if not CHAT_ID:
        print("⚠️  TELEGRAM_CHAT_ID not set. Waiting for you to send /start to the bot…")
        print("   Open Telegram, find your bot, send any message, then run:")
        print("   python3 sara_bot.py --get-chat-id")

    if "--get-chat-id" in sys.argv:
        cid = get_my_chat_id()
        if cid:
            print(f"✅ Your chat ID is: {cid}")
            print(f"   Add this to .env:  TELEGRAM_CHAT_ID={cid}")
        else:
            print("❌ No messages found. Send /start to your bot on Telegram first.")
        sys.exit(0)

    print("🤖 Sara JobHunter is online!")
    print("   Searching at 9:00 and 18:00 every day.")
    print("   Type /search in Telegram to trigger an immediate search.\n")

    # Run once immediately on start
    run_search()

    # Schedule twice daily
    schedule.every().day.at("09:00").do(run_search)
    schedule.every().day.at("18:00").do(run_search)

    # Run command listener in background thread
    t = threading.Thread(target=listen_for_commands, daemon=True)
    t.start()

    while True:
        schedule.run_pending()
        time.sleep(30)
