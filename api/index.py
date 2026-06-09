"""
api/index.py — JobMatch Flask API for Vercel serverless.
CV data travels through browser sessionStorage — no server-side sessions.
"""
import os
import sys
import requests as http_requests
from flask import Flask, request, jsonify, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cv_parser import extract_cv_keywords, rank_jobs
from services.job_fetcher import fetch_all_jobs

app = Flask(__name__)

PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify/{}"
PAYSTACK_LINK = os.getenv("PAYSTACK_LINK", "https://paystack.shop/pay/1awi14rss-")


# ── CORS ──
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


# ── Paystack helper ──
def _verify_paystack(reference: str) -> bool:
    secret_key = os.getenv("PAYSTACK_SECRET_KEY", "")
    if not secret_key:
        return False
    try:
        resp = http_requests.get(
            PAYSTACK_VERIFY_URL.format(reference),
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=15,
        )
        result = resp.json()
        return result.get("data", {}).get("status") == "success"
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# POST /api/parse
# Accepts CV text, returns extracted keywords + Paystack URL.
# ─────────────────────────────────────────────────────────
@app.route("/api/parse", methods=["POST", "OPTIONS"])
def parse_cv():
    if request.method == "OPTIONS":
        return Response(status=200)

    data = request.get_json(silent=True) or {}
    cv_text = (data.get("cv_text") or "").strip()

    if not cv_text:
        return jsonify({"error": "Please paste your CV text."}), 400
    if len(cv_text) < 100:
        return jsonify({"error": "CV text is too short. Please paste your full CV."}), 400

    try:
        keywords = extract_cv_keywords(cv_text)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    # Fetch and rank jobs now — return preview (no links) + total count
    try:
        all_jobs = fetch_all_jobs([])
        try:
            ranked = rank_jobs(cv_text, all_jobs)
        except Exception:
            ranked = all_jobs[:15]

        total = len(ranked)

        # Preview — 3 jobs, links removed
        preview = []
        for job in ranked[:3]:
            preview.append({
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "source": job.get("source", ""),
                "posted": job.get("posted", "Date unknown"),
                "match_reason": job.get("match_reason", ""),
            })

    except Exception:
        total = 0
        preview = []

    return jsonify({
        "keywords": keywords,
        "total": total,
        "preview": preview,
        "paystack_url": PAYSTACK_LINK
    })


# ─────────────────────────────────────────────────────────
# POST /api/match
# Verifies payment, fetches + ranks jobs, returns results.
# Body: { reference, cv_text, keywords }
# ─────────────────────────────────────────────────────────
@app.route("/api/match", methods=["POST", "OPTIONS"])
def match_jobs():
    if request.method == "OPTIONS":
        return Response(status=200)

    data = request.get_json(silent=True) or {}
    reference = (data.get("reference") or "").strip()
    cv_text   = (data.get("cv_text") or "").strip()
    keywords  = data.get("keywords") or {}

    if not reference:
        return jsonify({"error": "Missing payment reference."}), 400
    if not cv_text:
        return jsonify({"error": "CV data missing. Please go back and start again."}), 400

    # Verify payment
    if not _verify_paystack(reference):
        return jsonify({"error": "Payment not confirmed. If you were charged contact support."}), 402

    # Get search keywords
    search_terms = keywords.get("search_keywords", []) + keywords.get("job_titles", [])
    if not search_terms:
        try:
            extracted = extract_cv_keywords(cv_text)
            search_terms = extracted.get("search_keywords", []) + extracted.get("job_titles", [])
        except Exception:
            search_terms = ["kenya jobs"]

    # Fetch jobs from feeds
    jobs = fetch_all_jobs(search_terms)

    if not jobs:
        return jsonify({
            "jobs": [],
            "keywords": keywords,
            "message": "No matching jobs found right now. Try again tomorrow as new jobs are posted daily."
        })

    # AI ranking
    try:
        ranked = rank_jobs(cv_text, jobs)
    except Exception:
        ranked = jobs[:15]

    return jsonify({
        "jobs": ranked,
        "keywords": keywords,
        "total_found": len(jobs),
        "message": f"Found {len(jobs)} matching jobs. Showing your top {len(ranked)} matches."
    })
