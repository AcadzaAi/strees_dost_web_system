import requests
import json

BASE_URL = "http://localhost:5002"

print("=== Test 1: Check New User ===")
response = requests.post(
    f"{BASE_URL}/api/questions/check-user-type",
    json={"user_profile": {"name": "", "test_count": 0}}
)
print(json.dumps(response.json(), indent=2))

print("\n=== Test 2: New User Test Plan ===")
response = requests.post(
    f"{BASE_URL}/api/questions/trigger-plan",
    json={"user_profile": {"name": "", "test_count": 0}}
)
plan = response.json()
print(f"User Type: {plan['user_type']}")
print(f"Total Questions: {plan['total_questions']}")
print(f"Medium: {plan['medium_count']}, Hard: {plan['hard_count']}")
print("\nSequence:")
for trigger in plan['sequence']:
    hard_marker = "⚠️ HARD" if trigger['is_hard'] else "MEDIUM"
    print(f"  Q{trigger['question_number']}: {trigger['trigger_name']} ({hard_marker}, {trigger['intensity']})")

print("\n=== Test 3: Returning User Test Plan ===")
response = requests.post(
    f"{BASE_URL}/api/questions/trigger-plan",
    json={"user_profile": {"name": "John", "test_count": 5}}
)
plan = response.json()
print(f"User Type: {plan['user_type']}")
print("\nSequence:")
for trigger in plan['sequence']:
    hard_marker = "⚠️ HARD" if trigger['is_hard'] else "MEDIUM"
    print(f"  Q{trigger['question_number']}: {trigger['trigger_name']} ({hard_marker}, {trigger['intensity']})")

print("\n✅ All tests completed!")
