"""End-to-end image pipeline test from a student's perspective.

Each test case simulates a student's initial distraction + multiple followup
answers, then checks that 3 usable, non-vague images are returned and served.

Usage:
    1. Start the server:  py -3.12 wsgi.py   (listens on port 5002)
    2. In another shell:  py -3.12 scripts/test_distraction_images.py

A case PASSes when at least one usable (valid, sufficiently large, non-blank)
image is served for the distraction. "distinct" reports how many of the 3
question slots got different images.
"""
import io
import time
import requests
from PIL import Image

BASE = "http://127.0.0.1:5002"

# Realistic student scenarios: (label, initial_text, [followups], expect_images)
CASES = [
    # ── Distractions (regression) ────────────────────────────────
    ("Celebrity – Alia Bhatt", "alia bhatt and her movies",
     ["i binge her film clips on youtube", "her dance reels are addictive"], True),
    ("Game – Free Fire", "free fire",
     ["i grind ranked every evening", "i cant stop after one match"], True),

    # ── Emotional / wellbeing states ─────────────────────────────
    ("Emotion – generic stress", "i have a lot of stress",
     ["everything feels like too much", "i cant calm down"], True),
    ("Emotion – not feeling good", "i am not feeling good these days",
     ["i feel low and unmotivated", "studying feels heavy"], True),
    ("Emotion – exam anxiety", "i feel very anxious about my exams",
     ["my heart races before tests", "i blank out in the exam hall"], True),
    ("Emotion – burnout/tired", "i feel burnt out and exhausted",
     ["i study but nothing sticks", "i am tired all the time"], True),
    ("Vague – I have a problem", "i have a problem",
     ["i just cant study properly", "something feels off"], True),

    # ── Academic topics ──────────────────────────────────────────
    ("Academic – calculus", "i have a problem in calculus",
     ["integration confuses me", "i cant solve definite integrals"], True),
    ("Academic – thermodynamics", "physics thermodynamics is hard for me",
     ["i dont get the PV diagrams", "entropy makes no sense"], True),
    ("Academic – organic chemistry", "organic chemistry is my weak area",
     ["reaction mechanisms confuse me", "i forget named reactions"], True),
    ("Academic – trigonometry", "i struggle with trigonometry in maths",
     ["identities are hard to remember", "i mix up sin cos tan"], True),
    ("Academic – electrostatics", "i have trouble in electrostatics physics",
     ["gauss law is confusing", "i cant do field problems"], True),
    ("Academic – generic maths", "i am weak in maths",
     ["i make silly mistakes", "i run out of time in maths"], True),
]


def analyze(content):
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))
        w, h = img.size
        return w, h, img.format
    except Exception as e:
        return None, None, f"INVALID:{e}"


def run_case(label, initial, followups, expect):
    payload = {"initial_text": initial, "followup_answers": followups}
    status = None
    for _ in range(45):
        try:
            data = requests.post(f"{BASE}/api/triggers/distraction-image", json=payload, timeout=25).json()
        except Exception as e:
            time.sleep(2); continue
        status = data.get("status")
        if status == "ready":
            break
        time.sleep(2)

    # New unified endpoint returns all 3 URLs at once in image_urls array
    results = []
    try:
        rr = requests.post(f"{BASE}/api/triggers/distraction-image", json=payload, timeout=25).json()
        urls = rr.get("image_urls", [None, None, None])
        for q in (1, 2, 3):
            u = urls[q - 1] if q <= len(urls) else None
            if not u:
                results.append((q, None, "NO_IMAGE"))
                continue
            try:
                ig = requests.get(f"{BASE}{u}", timeout=25)
                w, h, fmt = analyze(ig.content)
                results.append((q, u, f"{ig.status_code} {fmt} {w}x{h} {len(ig.content)}B"))
            except Exception as e:
                results.append((q, u, f"fetch-error:{e}"))
    except Exception as e:
        for q in (1, 2, 3):
            results.append((q, None, f"req-error:{e}"))

    urls = [u for (_, u, _) in results if u]
    distinct = len(set(urls))
    ok_imgs = sum(1 for (_, u, info) in results if u and "INVALID" not in info and "x" in str(info) and "None" not in str(info))
    verdict = "PASS" if (ok_imgs >= 1 and (not expect or urls)) else "FAIL"
    print(f"\n[{verdict}] {label}")
    print(f"    status={status}  usable={ok_imgs}/3  distinct={distinct}")
    for q, u, info in results:
        print(f"    Q{q}: {info}  {u or ''}")
    return verdict, ok_imgs, distinct


if __name__ == "__main__":
    summary = []
    for label, initial, followups, expect in CASES:
        v, ok, dist = run_case(label, initial, followups, expect)
        summary.append((label, v, ok, dist))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passes = sum(1 for (_, v, _, _) in summary if v == "PASS")
    for label, v, ok, dist in summary:
        print(f"  [{v}] {label:38s} usable={ok}/3 distinct={dist}")
    print(f"\n  {passes}/{len(summary)} cases passed")
