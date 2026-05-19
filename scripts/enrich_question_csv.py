"""
Enrich question_ids.csv with subject, chapter, concept, difficulty from Acadza API.
Produces data/question_ids_enriched.csv with columns:
  question_id, subject, chapter, concepts, sub_concepts, difficulty, level, question_type
"""
import csv
import json
import os
import sys
import time

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), ".env"))

import requests

# ── config ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INPUT_CSV  = os.path.join(BASE_DIR, "data", "question_ids.csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "data", "question_ids_enriched.csv")

ACADZA_API_URL = os.getenv("ACADZA_API_URL", "https://api.acadza.in/question/details")

try:
    import certifi
    CERT_PATH = certifi.where()
except ImportError:
    CERT_PATH = True

raw_verify = os.getenv("ACADZA_VERIFY", "true").strip().lower()
VERIFY_SSL = CERT_PATH if raw_verify not in {"0", "false", "no"} else False


def _build_headers():
    course = os.getenv("ACADZA_COURSE", "JEE").strip()
    auth   = os.getenv("ACADZA_AUTH", "").strip()
    apikey = os.getenv("ACADZA_API_KEY", "postmanrulz").strip()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.acadza.com",
        "Referer": "https://www.acadza.com/",
        "User-Agent": os.getenv(
            "ACADZA_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        ),
        "api-key": apikey,
        "course": course,
    }
    if auth:
        headers["Authorization"] = auth
    return headers


def fetch_question(qid: str) -> dict | None:
    headers = _build_headers()
    headers["questionId"] = qid
    try:
        resp = requests.post(ACADZA_API_URL, json={}, headers=headers,
                             timeout=15, verify=VERIFY_SSL)
        if resp.status_code == 200:
            return resp.json()
        print(f"  [WARN] {qid}: HTTP {resp.status_code}")
        return None
    except Exception as exc:
        print(f"  [ERR] {qid}: {exc}")
        return None


def extract_concepts(raw: dict) -> list[str]:
    """Extract concept names from various tag formats."""
    out = []
    for key in ("tagConcept", "tagConcepts", "concepts"):
        items = raw.get(key) or []
        if isinstance(items, dict):
            items = [items]
        for item in items:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                for vk in ("concept", "conceptName", "name", "title"):
                    v = item.get(vk)
                    if isinstance(v, str) and v.strip():
                        out.append(v.strip())
                        break
    return list(dict.fromkeys(out))  # dedupe preserve order


def extract_subconcepts(raw: dict) -> list[str]:
    out = []
    for key in ("tagSubConcept", "tagSubConcepts", "subConcepts"):
        items = raw.get(key) or []
        if isinstance(items, dict):
            items = [items]
        for item in items:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                for vk in ("subConcept", "subconcept", "subConceptName", "name"):
                    v = item.get(vk)
                    if isinstance(v, str) and v.strip():
                        out.append(v.strip())
                        break
    return list(dict.fromkeys(out))


def main():
    # Load input IDs
    if not os.path.isfile(INPUT_CSV):
        print(f"Input CSV not found: {INPUT_CSV}")
        sys.exit(1)

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        ids = [row["question_id"].strip() for row in reader if row.get("question_id", "").strip()]

    print(f"Found {len(ids)} question IDs in {INPUT_CSV}")
    print(f"API: {ACADZA_API_URL}")
    print()

    rows = []
    for i, qid in enumerate(ids):
        print(f"[{i+1}/{len(ids)}] Fetching {qid}...", end=" ")
        raw = fetch_question(qid)
        if not raw:
            print("FAILED")
            rows.append({
                "question_id": qid,
                "subject": "",
                "chapter": "",
                "concepts": "",
                "sub_concepts": "",
                "difficulty": "",
                "level": "",
                "question_type": "",
            })
            continue

        subject  = (raw.get("subject") or "").strip()
        chapter  = (raw.get("chapter") or "").strip()
        concepts = extract_concepts(raw)
        subconcepts = extract_subconcepts(raw)
        difficulty = str(raw.get("difficulty") or "").strip()
        level    = str(raw.get("level") or "").strip()
        qtype    = (raw.get("questionType") or "scq").strip()

        print(f"[OK] {subject} / {chapter} / {difficulty} / {qtype}")

        rows.append({
            "question_id": qid,
            "subject": subject,
            "chapter": chapter,
            "concepts": "|".join(concepts),
            "sub_concepts": "|".join(subconcepts),
            "difficulty": difficulty,
            "level": level,
            "question_type": qtype,
        })

        time.sleep(0.3)  # be polite to API

    # Write enriched CSV
    fieldnames = ["question_id", "subject", "chapter", "concepts", "sub_concepts",
                  "difficulty", "level", "question_type"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[DONE] Enriched CSV written to {OUTPUT_CSV}")
    print(f"   {len(rows)} entries, {sum(1 for r in rows if r['subject'])} with data")

    # Summary
    subjects = {}
    for r in rows:
        s = r["subject"]
        if s:
            subjects.setdefault(s, []).append(r)
    print("\nBreakdown:")
    for s, qs in sorted(subjects.items()):
        difficulties = {}
        for q in qs:
            d = q["difficulty"] or "Unknown"
            difficulties[d] = difficulties.get(d, 0) + 1
        diff_str = ", ".join(f"{d}={c}" for d, c in sorted(difficulties.items()))
        print(f"  {s}: {len(qs)} questions ({diff_str})")


if __name__ == "__main__":
    main()
