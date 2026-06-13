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
    {"source": "OYK", "url": "https://opportunitiesforyoungkenyans.co.ke/feed/"},
]

DEFAULT_TERMS = ["kenya jobs", "nairobi jobs", "customer service kenya", "accountant kenya", "engineer kenya"]

BLOG_KEYWORDS = [
    "how to", "tips", "habits", "methods", "ways to", "guide", "advice",
    "prepare for", "effective", "want to", "top 10", "top 5", "reasons why",
    "mistakes", "skills you need", "what is", "why you should", "career advice",
    "salary", "interview tips", "cv tips", "resume tips", "job search tips"
]

REMOTE_KEYWORDS = ["remote", "work from home", "wfh", "virtual", "online", "anywhere"]


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


def _is_blog_post(title):
    title_lower = title.lower()
    return any(kw in title_lower for kw in BLOG_KEYWORDS)


def _is_remote(title, summary):
    combined = (title + " " + summary).lower()
    return any(kw in combined for kw in REMOTE_KEYWORDS)


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
            if _is_blog_post(title):
                continue
            pub_date = _parse_date(getattr(item, "published", ""))
            summary = _clean_html(getattr(item, "summary", "") or "")
            jobs.append({
                "title": title,
                "company": (getattr(item, "author", "") or "").strip(),
                "link": link,
                "summary": summary,
                "source": feed_info["source"],
                "posted": pub_date.strftime("%d %b %Y") if pub_date else "Date unknown",
                "posted_raw": pub_date.isoformat() if pub_date else "",
                "match_reason": ""
            })
        return jobs
    except Exception:
        return []


def _fetch_adzuna(keyword, results=10):
    """Fetch remote-only jobs from Adzuna using GB market which has most remote listings."""
    try:
        resp = requests.get(
            "https://api.adzuna.com/v1/api/jobs/gb/search/1",
            params={
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": keyword + " remote",
                "results_per_page": results,
                "sort_by": "date",
            },
            timeout=8
        )
        data = resp.json()
        jobs = []
        for item in data.get("results", []):
            title = item.get("title", "").strip()
            summary = _clean_html(item.get("description", ""))
            # Only include if truly remote
            if not _is_remote(title, summary):
                continue
            pub_date = _parse_date(item.get("created", ""))
            jobs.append({
                "title": title,
                "company": item.get("company", {}).get("display_name", ""),
                "link": item.get("redirect_url", ""),
                "summary": summary,
                "source": "Adzuna (Remote)",
                "posted": pub_date.strftime("%d %b %Y") if pub_date else "Date unknown",
                "posted_raw": pub_date.isoformat() if pub_date else "",
                "match_reason": ""
            })
        return jobs
    except Exception:
        return []


def fetch_all_jobs(keywords=None):
    all_jobs = []

    # RSS feeds — Kenyan job boards
    for feed in RSS_FEEDS:
        all_jobs.extend(_fetch_rss(feed))

    # Adzuna — remote only
    search_terms = keywords if keywords else DEFAULT_TERMS
    for term in search_terms[:5]:
        all_jobs.extend(_fetch_adzuna(term, results=5))

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
