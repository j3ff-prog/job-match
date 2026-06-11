"""
job_fetcher.py — Fetches jobs via Adzuna API + RSS2JSON proxy.
"""
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser
import os

ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

# Search terms relevant to Kenyan job seekers
SEARCH_TERMS = [
    "customer service",
    "sales",
    "accountant",
    "software developer",
    "nurse",
    "teacher",
    "engineer",
    "admin",
    "NGO",
    "finance",
]

RSS2JSON = "https://api.rss2json.com/v1/api.json"
RSS_FEEDS = [
    {"source": "JobWebKenya",      "url": "https://www.jobwebkenya.com/feed/"},
    {"source": "Corporate Staffing","url": "https://www.corporatestaffing.co.ke/feed/"},
]


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


def _fetch_adzuna(keyword, country="za", results=10):
    """Fetch from Adzuna API. Uses South Africa (za) as closest African market."""
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return []
    try:
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        params = {
            "app_id": ADZUNA_APP_ID,
            "app_key": ADZUNA_APP_KEY,
            "what": keyword,
            "results_per_page": results,
            "sort_by": "date",
        }
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()
        jobs = []
        for item in data.get("results", []):
            created = item.get("created", "")
            pub_date = _parse_date(created)
            jobs.append({
                "title": item.get("title", "").strip(),
                "company": item.get("company", {}).get("display_name", ""),
                "link": item.get("redirect_url", ""),
                "summary": _clean_html(item.get("description", "")),
                "source": "Adzuna",
                "posted": pub_date.strftime("%d %b %Y") if pub_date else "Date unknown",
                "posted_raw": pub_date.isoformat() if pub_date else "",
                "match_reason": "",
            })
        return jobs
    except Exception:
        return []


def _fetch_rss(feed_info):
    """Fetch via RSS2JSON proxy."""
    try:
        resp = requests.get(
            RSS2JSON,
            params={"rss_url": feed_info["url"], "count": 30},
            timeout=10
        )
        data = resp.json()
        if data.get("status") != "ok":
            return []
        jobs = []
        for item in data.get("items", []):
            pub_date_str = item.get("pubDate", "")
            if _is_expired(pub_date_str):
                continue
            title = (item.get("title") or "").strip()
            link = (item.get("link") or "").strip()
            if not title or not link:
                continue
            pub_date = _parse_date(pub_date_str)
            jobs.append({
                "title": title,
                "company": (item.get("author") or "").strip(),
                "link": link,
                "summary": _clean_html(item.get("description") or ""),
                "source": feed_info["source"],
                "posted": pub_date.strftime("%d %b %Y") if pub_date else "Date unknown",
                "posted_raw": pub_date.isoformat() if pub_date else "",
                "match_reason": "",
            })
        return jobs
    except Exception:
        return []


def fetch_all_jobs():
    all_jobs = []

    # Fetch from RSS feeds first
    for feed in RSS_FEEDS:
        all_jobs.extend(_fetch_rss(feed))

    # Fetch from Adzuna for top 3 search terms
    for term in SEARCH_TERMS[:3]:
        all_jobs.extend(_fetch_adzuna(term, country="za", results=5))

    # Deduplicate by link
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