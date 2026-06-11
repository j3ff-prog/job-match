import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser
import os

ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID", "37f1173d")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "94bac5cd4e13949bebadd4b8ccacf95e")

RSS2JSON = "https://api.rss2json.com/v1/api.json"

RSS_FEEDS = [
    {"source": "JobWebKenya", "url": "https://www.jobwebkenya.com/feed/"},
    {"source": "Corporate Staffing", "url": "https://www.corporatestaffing.co.ke/feed/"},
]

ADZUNA_TERMS = ["customer service", "accountant", "software developer", "nurse", "engineer"]


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
            if _is_expired(item.get("pubDate", "")):
                continue
            title = (item.get("title") or "").strip()
            link = (item.get("link") or "").strip()
            if not title or not link:
                continue
            pub_date = _parse_date(item.get("pubDate", ""))
            jobs.append({
                "title": title,
                "company": (item.get("author") or "").strip(),
                "link": link,
                "summary": _clean_html(item.get("description") or ""),
                "source": feed_info["source"],
                "posted": pub_date.strftime("%d %b %Y") if pub_date else "Date unknown",
                "posted_raw": pub_date.isoformat() if pub_date else "",
                "match_reason": ""
            })
        return jobs
    except Exception:
        return []


def _fetch_adzuna(keyword):
    try:
        resp = requests.get(
            "https://api.adzuna.com/v1/api/jobs/za/search/1",
            params={
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": keyword,
                "results_per_page": 5,
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


def fetch_all_jobs():
    all_jobs = []

    for feed in RSS_FEEDS:
        all_jobs.extend(_fetch_rss(feed))

    for term in ADZUNA_TERMS[:3]:
        all_jobs.extend(_fetch_adzuna(term))

    seen = set()
    unique = []
    for job in all_jobs:
        if job["link"] and job["link"] not in seen:
            seen.add(job["link"])
            unique.append(job)

    def sort_key(job):
        try:
            d = dateparser.parse(job.get("posted", ""))
            return d or datetime.min.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    unique.sort(key=sort_key, reverse=True)
    return unique
