""" 
api/index.py — JobMatch Flask API for Vercel serverless.
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

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

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


@app.route("/api/debug", methods=["GET"])
def debug_feeds():
    import requests as req
    results = {}
    feeds = [
        ("JobWebKenya", "https://www.jobwebkenya.com/feed/"),
        ("Corporate Staffing", "https://www.corporatestaffing.co.ke/feed/"),
        ("OYK", "https://opportunitiesforyoungkenyans.co.ke/feed/"),
    ]
    for name, rss_url in feeds:
        try:
            resp = req.get(
                "https://api.rss2json.com/v1/api.json",
                params={"rss_url": rss_url, "count": 5},
                timeout=10
            )
            data = resp.json()
            status = data.get("status")
            count = len(data.get("items", []))
            results[name] = f"{status} — {count} items"
        except Exception as e:
            results[name] = f"FAILED — {str(e)}"
    return jsonify(results)


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

    # Extract keywords using Gemini
    try:
        keywords = extract_cv_keywords(cv_text)
    except Exception:
        keywords = {}

    return jsonify({"keywords": keywords, "paystack_url": PAYSTACK_LINK})


@app.route("/api/preview", methods=["POST", "OPTIONS"])
def preview_jobs():
    if request.method == "OPTIONS":
        return Response(status=200)
    data = request.get_json(silent=True) or {}
    cv_text  = (data.get("cv_text") or "").strip()
    keywords = data.get("keywords") or {}
    if not cv_text:
        return jsonify({"error": "CV text missing."}), 400
    try:
        search_terms = keywords.get("search_keywords", []) + keywords.get("job_titles", [])
        all_jobs = fetch_all_jobs(keywords=search_terms if search_terms else None)
        total = len(all_jobs)
        preview = []
        for job in all_jobs[:3]:
            preview.append({
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "source": job.get("source", ""),
                "posted": job.get("posted", "Date unknown"),
                "match_reason": "",
            })
        return jsonify({"total": total, "preview": preview})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

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
    if not _verify_paystack(reference):
        return jsonify({"error": "Payment not confirmed. If you were charged contact support."}), 402

    search_terms = keywords.get("search_keywords", []) + keywords.get("job_titles", [])
    jobs = fetch_all_jobs(keywords=search_terms if search_terms else None)

    if not jobs:
        return jsonify({
            "jobs": [],
            "keywords": keywords,
            "message": "No matching jobs found right now. Try again tomorrow as new jobs are posted daily."
        })

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
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
