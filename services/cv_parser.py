"""
cv_parser.py — Uses Gemini to extract job search keywords from a CV.
Returns structured data used to query job feeds.
"""
import os
import json
from google import genai

MODEL = "gemini-2.5-flash-lite"
_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set.")
        _client = genai.Client(api_key=key)
    return _client


def extract_cv_keywords(cv_text: str) -> dict:
    """
    Extracts structured job search data from a CV.
    Returns dict with: job_titles, skills, location, experience_level, education_level
    """
    prompt = f"""You are a CV analysis expert. Extract job search keywords from this CV.

Return ONLY this JSON — no markdown, no preamble:
{{
  "job_titles": ["list of 3-5 job titles this person is suitable for, from most to least specific"],
  "skills": ["list of 8-12 key skills from the CV"],
  "location": "city or county in Kenya if mentioned, otherwise 'Kenya'",
  "experience_level": "entry / mid / senior",
  "education_level": "certificate / diploma / degree / masters / phd",
  "search_keywords": ["5-8 short keywords to search job boards with, e.g. 'customer service', 'Python developer'"]
}}

CV:
{cv_text}

Return ONLY valid JSON."""

    response = _get_client().models.generate_content(model=MODEL, contents=prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("`").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse CV keywords: {e}")


def rank_jobs(cv_text: str, jobs: list) -> list:
    """
    Takes a list of job dicts and ranks them by relevance to the CV.
    Returns the top 20 most relevant jobs with a match_reason.
    """
    if not jobs:
        return []

    # Prepare a compact job list for Gemini
    jobs_summary = []
    for i, job in enumerate(jobs[:50]):  # max 50 to stay within token limits
        jobs_summary.append({
            "index": i,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "summary": job.get("summary", "")[:200]
        })

    prompt = f"""You are a job matching expert. Given this CV and list of jobs, return the indexes of the TOP 15 most relevant jobs ranked from best to worst match.

CV SUMMARY (first 800 chars):
{cv_text[:800]}

JOBS:
{json.dumps(jobs_summary, indent=2)}

Return ONLY this JSON — no markdown, no preamble:
{{
  "ranked_indexes": [0, 5, 12, ...],
  "match_reasons": {{
    "0": "one sentence why this matches",
    "5": "one sentence why this matches"
  }}
}}"""

    try:
        response = _get_client().models.generate_content(model=MODEL, contents=prompt)
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip().rstrip("`").strip()
        ranking = json.loads(raw)

        ranked = []
        for idx in ranking.get("ranked_indexes", []):
            if idx < len(jobs):
                job = jobs[idx].copy()
                job["match_reason"] = ranking.get("match_reasons", {}).get(str(idx), "")
                ranked.append(job)
        return ranked
    except Exception:
        # If ranking fails, just return first 15 jobs unranked
        return jobs[:15]
