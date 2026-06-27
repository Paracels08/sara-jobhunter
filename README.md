# Sara JobHunter 🤖

Sara is Ganna's personal Telegram job-hunting assistant. She searches for creative IT product roles across Europe twice a day and messages you directly.

## What Sara looks for

| Location | Job types | Remote? |
|---|---|---|
| Slovenia | PM, PO, Project Manager (IT only) | Optional |
| Rest of Europe | PM, PO | Remote only |
| Rest of Europe | Project Manager | Remote + must be IT company |

**Boosted for:** creative roles, feature development, product discovery, SaaS, fintech, sports tech, AI/LLM, UX-focused companies, senior-level positions.

**Filtered out:** construction, logistics, non-IT, purely administrative PM roles.

## Setup (5 minutes)

### Step 1 — Create Sara's Telegram bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Name: **Sara JobHunter**
4. Username: e.g. `SaraJobHunterBot`
5. Copy the token BotFather gives you

### Step 2 — Configure .env

```bash
cp .env.example .env
```

Edit `.env`:
```
TELEGRAM_BOT_TOKEN=1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 3 — Get your chat ID

```bash
# Start your bot: open Telegram, find your bot, send /start
# Then run:
python3 sara_bot.py --get-chat-id
```

Copy the chat ID into `.env`:
```
TELEGRAM_CHAT_ID=123456789
```

### Step 4 — Install dependencies & run

```bash
pip3 install requests beautifulsoup4 python-dotenv schedule
python3 sara_bot.py
```

Sara will search immediately on launch, then every day at **9:00** and **18:00**.

## Telegram commands

| Command | What Sara does |
|---|---|
| `/search` | Search right now |
| `/help` | Show help |

## Auto-start on Mac

To keep Sara running in the background, add a cron job:
```bash
crontab -e
```
```
@reboot sleep 30 && python3 "/Users/miso/Documents/Claude for everyone/job-search-app/sara_bot.py" >> /tmp/sara.log 2>&1
```
