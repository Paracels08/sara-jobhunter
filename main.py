#!/usr/bin/env python3
"""
Job Search Bot — entry point.

Usage:
  python3 main.py          # run once right now
  python3 main.py --watch  # run on a recurring schedule (every CHECK_INTERVAL_HOURS hours)
  python3 main.py --test   # send a test email with fake data to verify setup
"""

import os
import sys
import time
import logging
import schedule
from dotenv import load_dotenv

from job_searcher import fetch_new_jobs
from email_sender import send_job_digest

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("job_search.log"),
    ],
)
log = logging.getLogger(__name__)


def run():
    log.info("=== Starting job search run ===")
    jobs = fetch_new_jobs()

    if not jobs:
        log.info("No new relevant jobs found this run — no email sent")
        return

    log.info("Found %d new jobs — sending digest", len(jobs))
    send_job_digest(jobs)


def run_test():
    """Send a test email with one fake job to verify Gmail credentials."""
    fake = [{
        "source": "Test",
        "title": "Senior Product Manager — Test Entry",
        "company": "Acme Corp",
        "location": "Remote (Europe)",
        "url": "https://example.com",
        "posted": "2026-06-27",
        "description": "This is a test entry to verify your email setup is working correctly.",
        "tags": "remote saas roadmap agile",
        "score": 5,
    }]
    ok = send_job_digest(fake)
    if ok:
        print("✅ Test email sent — check your inbox at", os.getenv("RECIPIENT_EMAIL"))
    else:
        print("❌ Failed to send — check .env credentials (see README.md)")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--test" in args:
        run_test()

    elif "--watch" in args:
        interval = int(os.getenv("CHECK_INTERVAL_HOURS", "12"))
        log.info("Watch mode: checking every %d hours", interval)
        run()  # run immediately on start
        schedule.every(interval).hours.do(run)
        while True:
            schedule.run_pending()
            time.sleep(60)

    else:
        run()
