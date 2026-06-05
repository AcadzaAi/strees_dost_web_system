"""Quick smoke test for distraction images - tests key scenarios."""
import io
import time
import requests
from PIL import Image

BASE = "http://127.0.0.1:5002"

# Key test cases: celebrity, emotion, academic
CASES = [
    ("Celebrity", "alia bhatt", ["i watch her movies", "her reels are addictive"]),
    ("Emotion", "i have stress", ["everything feels overwhelming", "i cant focus"]),
    ("Academic", "problem in calculus", ["integration confuses me", "i cant solve integrals"]),
    ("Game", "free fire", ["i play ranked every day", "cant stop after one match"]),
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


def test_case(label, initial, followups):
    print(f"\n[TEST] {label}: '{initial}'")
    payload = {"initial_text": initial, "followup_answers": followups}
    
    # Poll until ready
    for attempt in range(30):
        try:
            data = requests.post(f"{BASE}/api/triggers/distraction-image", json=payload, timeout=15).json()
            status = data.get("status")
            if status == "ready":
                break
            print(f"  attempt {attempt + 1}: {status}")
            time.sleep(2)
        except Exception as e:
            print(f"  attempt {attempt + 1}: error {e}")
            time.sleep(2)
    
    # Get images
    try:
        rr = requests.post(f"{BASE}/api/triggers/distraction-image", json=payload, timeout=15).json()
        images = rr.get("images", [])
        
        if not images or all(img is None for img in images):
            print(f"  ❌ FAIL: No images returned")
            return False
        
        valid_count = 0
        for q, img in enumerate(images, 1):
            if not img or not img.get("data"):
                print(f"  Q{q}: NO_IMAGE")
                continue
            try:
                import base64
                img_bytes = base64.b64decode(img["data"])
                w, h, fmt = analyze(img_bytes)
                if w and h:
                    print(f"  Q{q}: ✓ {img['content_type']} {fmt} {w}x{h} ({len(img_bytes)} bytes)")
                    valid_count += 1
                else:
                    print(f"  Q{q}: ✗ Invalid image")
            except Exception as e:
                print(f"  Q{q}: ✗ Error: {e}")
        
        if valid_count >= 1:
            print(f"  ✅ PASS: {valid_count}/3 valid images")
            return True
        else:
            print(f"  ❌ FAIL: No valid images")
            return False
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("QUICK IMAGE GENERATION TEST")
    print("=" * 60)
    
    results = []
    for label, initial, followups in CASES:
        passed = test_case(label, initial, followups)
        results.append((label, passed))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, p in results if p)
    for label, p in results:
        status = "✅ PASS" if p else "❌ FAIL"
        print(f"  {status}: {label}")
    print(f"\n  {passed}/{len(results)} tests passed")
