"""
Sends a nicely formatted HTML email digest of new job listings.
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)


def _build_html(jobs: list[dict]) -> str:
    now = datetime.now().strftime("%d %b %Y")

    cards = ""
    for job in jobs:
        score_dots = "●" * min(job.get("score", 0), 10)
        desc = job.get("description", "")
        desc_html = f'<p style="color:#555;font-size:14px;margin:8px 0 0">{desc[:300]}{"…" if len(desc) > 300 else ""}</p>' if desc else ""
        tags = job.get("tags", "")
        tags_html = ""
        if tags:
            tag_list = [t.strip() for t in tags.split() if t.strip()][:6]
            tags_html = "".join(
                f'<span style="background:#e8f4fd;color:#1a73e8;padding:2px 8px;border-radius:12px;font-size:12px;margin:2px 2px 0 0;display:inline-block">{t}</span>'
                for t in tag_list
            )
            tags_html = f'<div style="margin-top:8px">{tags_html}</div>'

        cards += f"""
        <div style="background:#fff;border:1px solid #e0e0e0;border-radius:10px;padding:20px;margin-bottom:16px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <a href="{job['url']}" style="font-size:17px;font-weight:600;color:#1a73e8;text-decoration:none">{job['title']}</a>
              <div style="margin-top:4px;color:#333;font-size:15px">{job['company']}</div>
              <div style="color:#777;font-size:13px;margin-top:2px">📍 {job['location']} &nbsp;·&nbsp; 📅 {job.get('posted','') or 'recent'} &nbsp;·&nbsp; 🔗 {job['source']}</div>
            </div>
            <div style="text-align:right;font-size:13px;color:#e67e22;white-space:nowrap;margin-left:16px" title="Relevance score">
              {score_dots}<br><span style="color:#999">{job.get('score',0)} match pts</span>
            </div>
          </div>
          {desc_html}
          {tags_html}
          <div style="margin-top:12px">
            <a href="{job['url']}" style="background:#1a73e8;color:#fff;padding:8px 18px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:500">Apply →</a>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <div style="max-width:680px;margin:32px auto;padding:0 16px">

    <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);border-radius:12px;padding:28px 32px;margin-bottom:24px;color:#fff">
      <div style="font-size:24px;font-weight:700">🔍 New PM Jobs Found</div>
      <div style="opacity:0.85;margin-top:6px">{now} &nbsp;·&nbsp; {len(jobs)} new remote positions in Europe</div>
      <div style="opacity:0.7;font-size:13px;margin-top:4px">Curated for Ganna Kogoj · Product Manager</div>
    </div>

    {cards}

    <div style="text-align:center;color:#aaa;font-size:12px;margin-top:24px;padding-bottom:32px">
      This digest is auto-generated based on your CV keywords.<br>
      Jobs are sorted by relevance to your experience in SaaS, fintech, sports tech, and AI products.
    </div>
  </div>
</body>
</html>"""


def send_job_digest(jobs: list[dict]) -> bool:
    sender = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_APP_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL", "akyrmyza@gmail.com")

    if not sender or not password:
        log.error("SENDER_EMAIL / SENDER_APP_PASSWORD not set in .env")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔍 {len(jobs)} new remote PM jobs in Europe — {datetime.now().strftime('%d %b')}"
    msg["From"] = f"Job Alert <{sender}>"
    msg["To"] = recipient

    plain = "\n\n".join(
        f"{j['title']} @ {j['company']} ({j['location']})\n{j['url']}"
        for j in jobs
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(_build_html(jobs), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        log.info("Email sent to %s (%d jobs)", recipient, len(jobs))
        return True
    except Exception as e:
        log.error("Failed to send email: %s", e)
        return False
