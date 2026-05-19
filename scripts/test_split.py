import re, requests, os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def split(html):
    first_a = re.search(r'\(A\)', html)
    if not first_a:
        return html, []
    stem = html[:first_a.start()].strip()
    options_part = html[first_a.start():]
    pattern = r'\(([A-D])\)\s*(.*?)(?=\([A-D]\)|$)'
    matches = re.findall(pattern, options_part, re.DOTALL)
    opts = [{"label": l, "text": c.strip()} for l, c in matches if c.strip()]
    return stem, opts

# Test with a real question
h = {
    "Authorization": os.getenv("ACADZA_AUTH"),
    "Content-Type": "application/json",
    "api-key": "postmanrulz",
    "course": "JEE",
    "questionId": "68e8701b42c06737d6e5619e",
}
data = requests.post("https://api.acadza.in/question/details", json={}, headers=h).json()
qhtml = data["scq"]["question"]
stem, opts = split(qhtml)

print("STEM length:", len(stem))
print("STEM preview:", repr(stem[:120]))
print()
for o in opts:
    label = o["label"]
    text = o["text"]
    has_math = "math" in text.lower()
    has_img = "img" in text.lower()
    print(f"  ({label}) len={len(text)}, math={has_math}, img={has_img}")
    print(f"       preview: {repr(text[:120])}")
print()
print(f"Total options: {len(opts)}")
