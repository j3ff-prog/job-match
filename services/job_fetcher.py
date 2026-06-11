"""
job_fetcher.py — Fetches Kenyan jobs via RSS2JSON proxy service.
RSS2JSON fetches feeds on our behalf — bypasses Vercel outbound restrictions.
"""
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser

RSS2JSON_URL = "https://api.rss2json.com/v1/api.json"

FEEDS = [
    {
        "source": "JobWebKenya",
        "rss_url": "https://www.jobwebkenya.com/feed/"
    },
    {
        "source": "Corporate Staffing",
        "rss_url": "https://www.corporatestaffing.co.ke/feed/"
    },
    {
        "source": "Opportunities for Young Kenyans",
        "rss_url": "https://opportunitiesforyoungkenyans.co.ke/feed/"
    },
    {
        "source": "Kenya Job",
        "rss_url": "https://www.kenyajob.com/rss.xml"
    },
]


def _clean_html(text):
    import re
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:400]


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return dateparser.parse(date_str)
    except Exception:
        return None


def _is_expired(date_str):
    pub_date = _parse_date(date_str)
    if not pub_date:
        return False
    now = datetime.now(timezone.utc)
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    return (now - pub_date).days > 30


def fetch_feed_via_proxy(rss_url):
    """Fetch a feed through RSS2JSON proxy — avoids Vercel outbound blocking."""
    try:
        resp = requests.get(
            RSS2JSON_URL,
            params={"rss_url": rss_url, "count": 50},
            timeout=10
        )
        data = resp.json()
        if data.get("status") != "ok":
            return []
        return data.get("items", [])
    except Exception:
        return []


def fetch_all_jobs():
    all_jobs = []

    for feed_info in FEEDS:
        items = fetch_feed_via_proxy(feed_info["rss_url"])
        for item in items:
            pub_date_str = item.get("pubDate", "")
            if _is_expired(pub_date_str):
                continue

            title = (item.get("title") or "").strip()
            link = (item.get("link") or "").strip()
            summary = _clean_html(item.get("description") or item.get("content") or "")
            company = (item.get("author") or "").strip()
            pub_date = _parse_date(pub_date_str)

            if not title or not link:
                continue

            all_jobs.append({
                "title": title,
                "company": company,
                "link": link,
                "summary": summary,
                "source": feed_info["source"],
                "posted": pub_date.strftime("%d %b %Y") if pub_date else "Date unknown",
                "posted_raw": pub_date.isoformat() if pub_date else "",
                "match_reason": ""
            })

    # Deduplicate
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        if job["link"] not in seen:
            seen.add(job["link"])
            unique_jobs.append(job)

    # Sort newest first
    def sort_key(job):
        try:
            d = dateparser.parse(job.get("posted", ""))
            return d or datetime.min.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    unique_jobs.sort(key=sort_key, reverse=True)
    return unique_jobs