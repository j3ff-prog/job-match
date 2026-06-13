import requests
import feedparser
from datetime import datetime, timezone
from dateutil import parser as dateparser
import os

ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID", "37f1173d")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "94bac5cd4e13949bebadd4b8ccacf95e")


RSS_FEEDS = [
    {"source": "JobWebKenya", "url": "https://www.jobwebkenya.com/feed/"},
    {"source": "Corporate Staffing", "url": "https://www.corporatestaffing.co.ke/feed/"},
]

DEFAULT_TERMS = ["kenya jobs", "nairobi jobs", "customer service kenya", "accountant kenya", "engineer kenya"]


def _clean_html(text):
    import re
    clean = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", clean).strip()[:400]


def _parse_date(s):
    if not s:
        return None
    try:
        return dateparser.parse(s)
    except Exception:
        return None


def _is_expired(date_str):
    d = _parse_date(date_str)
    if not d:
        return False
    now = datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (now - d).days > 30


def _fetch_rss(feed_info):
    try:
        feed = feedparser.parse(feed_info["url"])
        jobs = []
        for item in feed.entries:
            if _is_expired(getattr(item, "published", "")):
                continue
            title = (getattr(item, "title", "") or "").strip()
            link = (getattr(item, "link", "") or "").strip()
            if not title or not link:
                continue
            pub_date = _parse_date(getattr(item, "published", ""))
            jobs.append({
                "title": title,
                "company": (getattr(item, "author", "") or "").strip(),
                "link": link,
                "summary": _clean_html(getattr(item, "summary", "") or ""),
                "source": feed_info["source"],
                "posted": pub_date.strftime("%d %b %Y") if pub_date else "Date unknown",
                "posted_raw": pub_date.isoformat() if pub_date else "",
                "match_reason": ""
            })
        return jobs
    except Exception:
        return []


def _fetch_adzuna(keyword, country="za", results=10):
    try:
        resp = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
            params={
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": keyword,
                "results_per_page": results,
                "sort_by": "date",
            },
            timeout=8
        )
        data = resp.json()
        jobs = []
        for item in data.get("results", []):
            pub_date = _parse_date(item.get("created", ""))
            jobs.append({
                "title": item.get("title", "").strip(),
                "company": item.get("company", {}).get("display_name", ""),
                "link": item.get("redirect_url", ""),
                "summary": _clean_html(item.get("description", "")),
                "source": "Adzuna",
                "posted": pub_date.strftime("%d %b %Y") if pub_date else "Date unknown",
                "posted_raw": pub_date.isoformat() if pub_date else "",
                "match_reason": ""
            })
        return jobs
    except Exception:
        return []


def fetch_all_jobs(keywords=None):
    """
    keywords: list of search terms extracted from CV.
    Falls back to DEFAULT_TERMS if none provided.
    """
    all_jobs = []

    # RSS feeds — get everything, AI ranks later
    for feed in RSS_FEEDS:
        all_jobs.extend(_fetch_rss(feed))

    # Adzuna — use CV keywords if available, else defaults
    search_terms = keywords if keywords else DEFAULT_TERMS
    # Use top 5 keywords only to avoid quota burn
    for term in search_terms[:5]:
        all_jobs.extend(_fetch_adzuna(term, country="za", results=5))

    # Deduplicate
    seen = set()
    unique = []
    for job in all_jobs:
        if job["link"] and job["link"] not in seen:
            seen.add(job["link"])
            unique.append(job)

    # Sort newest first
    def sort_key(job):
        try:
            d = dateparser.parse(job.get("posted", ""))
            return d or datetime.min.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    unique.sort(key=sort_key, reverse=True)
    return unique
