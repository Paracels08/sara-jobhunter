"""
Job search engine for Sara JobHunter Telegram bot.

Search rules:
- Slovenia: PM / PO / Project Manager in IT, remote OR onsite
- Rest of Europe: PM / PO remote only; Project Manager only at strong IT companies
"""

import os
import re
import time
import json
import hashlib
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SEEN_JOBS_FILE = "seen_jobs.json"

# ── Search keyword sets ───────────────────────────────────────────────────────

PM_KEYWORDS = ["product manager", "product owner", "senior product manager", "head of product"]
PROJECT_MANAGER_KEYWORDS = ["it project manager", "technical project manager"]
BA_KEYWORDS = ["product analyst"]

# ── Scoring: what makes a job a great fit for Ganna ──────────────────────────

STRONG_POSITIVE = [
    # Creative / feature-building signal
    "creative", "innovation", "feature", "product discovery", "ideation",
    "user experience", "ux", "design thinking", "product vision", "product strategy",
    # Domain experience
    "saas", "b2b saas", "consumer", "fintech", "payments", "banking",
    "sports", "media", "entertainment", "ad tech", "creative platform",
    "fan engagement", "gaming", "edtech", "healthtech",
    # Tech signal
    "ai", "machine learning", "llm", "data", "real-time", "api",
    "frontend", "mobile", "platform",
    # Process
    "roadmap", "backlog", "agile", "scrum", "discovery", "stakeholder",
    "user research", "a/b test", "metrics", "okr",
]

# Weak positive — small boost
WEAK_POSITIVE = [
    "startup", "scale-up", "growth", "series", "venture",
    "cross-functional", "launch", "0 to 1", "greenfield",
    "english", "international",
]

# These signal a NON-IT / non-creative PM role — penalise hard
NEGATIVE_KEYWORDS = [
    "construction", "real estate", "property", "civil", "infrastructure",
    "manufacturing", "logistics", "supply chain", "procurement",
    "retail store", "restaurant", "hospitality", "hotel",
    "event management", "wedding", "marketing agency",
    "pmo", "programme manager", "programme office",
    "non-profit", "ngo", "government", "public sector",
    "warehouse", "field operations",
]

# IT-company signal for Project Manager roles (only include PM roles at these)
IT_COMPANY_SIGNALS = [
    "software", "tech", "technology", "platform", "saas", "cloud",
    "digital", "app", "mobile", "data", "ai", "ml", "fintech",
    "startup", "scale-up", "engineering", "developer", "product",
    "iot", "cybersecurity", "devops", "api", "microservices",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Seen-jobs cache ───────────────────────────────────────────────────────────

def _load_seen() -> set:
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE) as f:
            return set(json.load(f))
    return set()


def _save_seen(seen: set) -> None:
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen), f)


def _job_id(job: dict) -> str:
    key = f"{job.get('title', '')}|{job.get('company', '')}|{job.get('url', '')}"
    return hashlib.md5(key.encode()).hexdigest()


# ── Relevance scoring ─────────────────────────────────────────────────────────

def score_job(job: dict) -> int:
    text = (
        (job.get("title") or "") + " " +
        (job.get("description") or "") + " " +
        (job.get("company") or "") + " " +
        (job.get("tags") or "")
    ).lower()

    # Hard disqualify if non-IT negative keywords found
    neg_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if neg_hits >= 2:
        return -1

    score = 0
    for kw in STRONG_POSITIVE:
        if kw in text:
            score += 2
    for kw in WEAK_POSITIVE:
        if kw in text:
            score += 1

    # Seniority match boost (Ganna has 5 yrs exp)
    if any(w in text for w in ["senior", "lead", "principal", "head of", "staff"]):
        score += 3

    # Project Manager roles need an IT company signal
    title_lower = (job.get("title") or "").lower()
    is_project_manager = "project manager" in title_lower and "product" not in title_lower
    if is_project_manager:
        it_hits = sum(1 for s in IT_COMPANY_SIGNALS if s in text)
        if it_hits == 0:
            return -1  # Project Manager at non-IT company → skip
        score += it_hits  # bonus for strong IT signal

    return score


ALLOWED_TITLE_PATTERNS = [
    "product manager",
    "product owner",
    "head of product",
    "vp of product",
    "vp product",
    "director of product",
    "project manager",
    "it project manager",
    "technical project manager",
    "product analyst",
]

def _title_is_allowed(title: str) -> bool:
    """Return True only if the job title matches one of our target roles."""
    t = title.lower()
    return any(p in t for p in ALLOWED_TITLE_PATTERNS)


def is_creative_it_fit(job: dict) -> bool:
    """Final gate: must have at least some positive signal."""
    return score_job(job) >= 3


# ── LinkedIn scraper ──────────────────────────────────────────────────────────

def _linkedin_search(keyword: str, location: str, remote: bool) -> list[dict]:
    base = "https://www.linkedin.com/jobs/search/"
    params = {
        "keywords": keyword,
        "location": location,
        "f_TPR": "r604800",  # last 7 days
        "start": "0",
    }
    if remote:
        params["f_WT"] = "2"

    try:
        resp = requests.get(base, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log.warning("LinkedIn '%s' @ %s failed: %s", keyword, location, e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []
    for card in soup.select("div.base-card"):
        try:
            title = card.select_one("h3.base-search-card__title")
            company = card.select_one("h4.base-search-card__subtitle")
            loc = card.select_one("span.job-search-card__location")
            link = card.select_one("a.base-card__full-link")
            date = card.select_one("time")
            if title and link:
                jobs.append({
                    "source": "LinkedIn",
                    "title": title.get_text(strip=True),
                    "company": company.get_text(strip=True) if company else "",
                    "location": loc.get_text(strip=True) if loc else location,
                    "url": link["href"].split("?")[0],
                    "posted": date.get("datetime", "") if date else "",
                    "description": "",
                    "tags": "",
                })
        except Exception:
            continue

    log.info("LinkedIn '%s' @ %s (remote=%s): %d listings", keyword, location, remote, len(jobs))
    return jobs


# EU countries to search on LinkedIn (by name LinkedIn recognises)
EU_LINKEDIN_LOCATIONS = [
    "Germany", "Netherlands", "France", "Spain", "Poland",
    "Sweden", "Austria", "Belgium", "Portugal", "Czech Republic",
    "Denmark", "Finland", "Ireland", "Romania", "Hungary",
    "Italy", "Greece", "Croatia",
]


def scrape_linkedin() -> list[dict]:
    results = []

    # Slovenia — remote not required
    for kw in PM_KEYWORDS + PROJECT_MANAGER_KEYWORDS + BA_KEYWORDS:
        results.extend(_linkedin_search(kw, "Slovenia", remote=False))
        time.sleep(1.5)

    # EU countries — remote only
    for location in EU_LINKEDIN_LOCATIONS:
        for kw in PM_KEYWORDS + PROJECT_MANAGER_KEYWORDS + BA_KEYWORDS:
            results.extend(_linkedin_search(kw, location, remote=True))
            time.sleep(1.2)

    return results


# ── Remotive (remote-only API) ────────────────────────────────────────────────

def scrape_remotive() -> list[dict]:
    jobs = []
    one_week_ago = datetime.utcnow() - timedelta(days=7)

    for category in ["product", "management-finance"]:
        try:
            resp = requests.get(
                "https://remotive.com/api/remote-jobs",
                params={"category": category, "limit": 50},
                timeout=15,
            )
            resp.raise_for_status()
            for item in resp.json().get("jobs", []):
                pub = item.get("publication_date", "")
                try:
                    if datetime.strptime(pub[:19], "%Y-%m-%dT%H:%M:%S") < one_week_ago:
                        continue
                except Exception:
                    pass

                # Accept only EU/worldwide remote jobs
                region = (item.get("candidate_required_location") or "").lower()
                if region and not any(r in region for r in [
                    "europe", "eu", "worldwide", "anywhere", "global", "emea", "remote"
                ]):
                    continue

                jobs.append({
                    "source": "Remotive",
                    "title": item.get("title", ""),
                    "company": item.get("company_name", ""),
                    "location": item.get("candidate_required_location", "Remote"),
                    "url": item.get("url", ""),
                    "posted": pub[:10],
                    "description": BeautifulSoup(
                        item.get("description", ""), "html.parser"
                    ).get_text()[:600],
                    "tags": " ".join(item.get("tags", [])),
                })
        except Exception as e:
            log.warning("Remotive category %s failed: %s", category, e)

    log.info("Remotive: %d Europe/worldwide listings", len(jobs))
    return jobs


# ── Adzuna (multi-country) ────────────────────────────────────────────────────

# EU member states with Adzuna coverage (no UK, no CH, no NO)
ADZUNA_COUNTRIES = ["de", "nl", "fr", "es", "pl", "se", "at", "it"]

def scrape_adzuna() -> list[dict]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return []

    jobs = []
    for country in ADZUNA_COUNTRIES:
        for query in ["product manager remote", "product owner remote"]:
            try:
                resp = requests.get(
                    f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                    params={
                        "app_id": app_id,
                        "app_key": app_key,
                        "what": query,
                        "results_per_page": 15,
                        "max_days_old": 7,
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                for item in resp.json().get("results", []):
                    jobs.append({
                        "source": f"Adzuna ({country.upper()})",
                        "title": item.get("title", ""),
                        "company": item.get("company", {}).get("display_name", ""),
                        "location": item.get("location", {}).get("display_name", ""),
                        "url": item.get("redirect_url", ""),
                        "posted": item.get("created", "")[:10],
                        "description": item.get("description", "")[:600],
                        "tags": "",
                    })
            except Exception as e:
                log.warning("Adzuna %s / %s failed: %s", country, query, e)
            time.sleep(0.4)

    log.info("Adzuna: %d listings", len(jobs))
    return jobs


# ── Main: fetch, deduplicate, score, return new jobs ─────────────────────────

def fetch_new_jobs() -> list[dict]:
    seen = _load_seen()

    raw = []
    raw.extend(scrape_remotive())
    raw.extend(scrape_linkedin())
    raw.extend(scrape_adzuna())

    # Deduplicate by job id
    seen_this_run = {}
    for job in raw:
        jid = _job_id(job)
        if jid not in seen_this_run:
            seen_this_run[jid] = job

    new_jobs = []
    for jid, job in seen_this_run.items():
        if jid in seen:
            continue
        seen.add(jid)
        # Hard filter: title must be a target role
        if not _title_is_allowed(job.get("title", "")):
            continue
        job["score"] = score_job(job)
        if job["score"] >= 3:
            new_jobs.append(job)

    new_jobs.sort(key=lambda j: j["score"], reverse=True)
    _save_seen(seen)

    log.info("New qualifying jobs this run: %d (from %d raw)", len(new_jobs), len(raw))
    return new_jobs
