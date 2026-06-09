import feedparser
import urllib.request
from datetime import datetime, timezone
from dateutil import parser as dateparser

FEEDS = [
    {
        "source": "JobWebKenya",
        "url": "https://www.jobwebkenya.com/feed/"
    },
    {
        "source": "Corporate Staffing",
        "url": "https://www.corporatestaffing.co.ke/feed/"
    },
    {
        "source": "Opportunities for Young Kenyans",
        "url": "https://opportunitiesforyoungkenyans.co.ke/feed/"
    },
]


def _fetch_feed_with_timeout(url, timeout=8):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JobMatchBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()
        return feedparser.parse(content)
    except Exception:
        return None


def _parse_date(entry):
    for attr in ("published", "updated", "created"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return dateparser.parse(val)
            except Exception:
                continue
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _is_expired(entry):
    pub_date = _parse_date(entry)
    if not pub_date:
        return False
    now = datetime.now(timezone.utc)
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    return (now - pub_date).days > 30


def _clean_html(text):
    import re
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:400]


def fetch_all_jobs():
    all_jobs = []

    for feed_info in FEEDS:
        try:
            feed = _fetch_feed_with_timeout(feed_info["url"], timeout=8)
            if not feed or not feed.entries:
                continue
            for entry in feed.entries:
                if _is_expired(entry):
                    continue
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = _clean_html(entry.get("summary", "") or entry.get("description", ""))
                company = entry.get("author", "") or entry.get("dc_creator", "") or ""
                pub_date = _parse_date(entry)
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
        except Exception:
            continue

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
            return dateparser.parse(job.get("posted", "")) or datetime.min.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    unique_jobs.sort(key=sort_key, reverse=True)
    return unique_jobs