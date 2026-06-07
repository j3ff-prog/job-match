"""
job_fetcher.py — Fetches jobs from Kenyan job board RSS feeds.
Filters out expired jobs. Returns clean list of job dicts.
"""
import feedparser
from datetime import datetime, timezone
from dateutil import parser as dateparser

# ── RSS Feed Sources ──
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
        "source": "Google IT Jobs Kenya",
        "url": "https://news.google.com/rss/search?q=IT+jobs+kenya+apply+now&hl=en-KE&gl=KE&ceid=KE:en"
    },
    {
        "source": "Google Jobs Kenya",
        "url": "https://news.google.com/rss/search?q=jobs+kenya+vacancy&hl=en-KE&gl=KE&ceid=KE:en"
    },
    {
        "source": "Google NGO Jobs",
        "url": "https://news.google.com/rss/search?q=NGO+jobs+kenya+apply&hl=en-KE&gl=KE&ceid=KE:en"
    },
    {
        "source": "Google Graduate Jobs",
        "url": "https://news.google.com/rss/search?q=graduate+trainee+jobs+kenya&hl=en-KE&gl=KE&ceid=KE:en"
    },
]

def _parse_date(entry) -> datetime | None:
    """Try to extract a published date from a feed entry."""
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


def _is_expired(entry) -> bool:
    """Returns True if the job was posted more than 30 days ago."""
    pub_date = _parse_date(entry)
    if not pub_date:
        return False  # if no date, assume still valid
    now = datetime.now(timezone.utc)
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    age_days = (now - pub_date).days
    return age_days > 30


def _clean_html(text: str) -> str:
    """Remove basic HTML tags from summary text."""
    import re
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:400]


def fetch_all_jobs(keywords: list) -> list:
    """
    Fetches jobs from all RSS feeds.
    Filters out expired jobs.
    Does basic keyword matching to pre-filter before AI ranking.
    Returns list of job dicts.
    """
    all_jobs = []
    keywords_lower = [k.lower() for k in keywords]

    for feed_info in FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
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

                # Basic keyword pre-filter — job must match at least one keyword
                searchable = (title + " " + summary).lower()
                matches = any(kw in searchable for kw in keywords_lower)
                if not matches:
                    continue

                all_jobs.append({
                    "title": title,
                    "company": company,
                    "link": link,
                    "summary": summary,
                    "source": feed_info["source"],
                    "posted": pub_date.strftime("%d %b %Y") if pub_date else "Recently",
                    "match_reason": ""
                })
        except Exception:
            # If one feed fails, continue with others
            continue

    # Deduplicate by link
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        if job["link"] not in seen:
            seen.add(job["link"])
            unique_jobs.append(job)

    return unique_jobs
