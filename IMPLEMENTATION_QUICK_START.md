# Question Trigger Decision Layer - Quick Start Guide (go below for commands and stuff)

## 🎯 What This Does

Implements an AI decision layer that manages trigger selection for the 7-question Focus Zones test:
- **New users**: Fixed sequence (mild → strong) with Q3 and Q6 as hard questions
- **Returning users**: Randomized sequence with Q1 always medium, 2 hard questions total

## 🚀 Quick Start

### 1. Test the Implementation
```bash
python test_question_trigger_decision.py
```

Expected: ✅ ALL TESTS PASSED

### 2. Start the Server
```bash
python wsgi.py
```

### 3. Test API Endpoints

#### Check User Type
```bash
curl -X POST http://localhost:5000/api/questions/check-user-type \
  -H "Content-Type: application/json" \
  -d '{"user_profile": {"name": "", "test_count": 0}}'
```

Response:
```json
{
  "status": "success",
  "is_new_user": true,
  "should_ask_name": true,
  "message": "New user detected"
}
```

#### Generate Test Plan
```bash
curl -X POST http://localhost:5000/api/questions/trigger-plan \
  -H "Content-Type: application/json" \
  -d '{"user_profile": {"name": "John", "test_count": 5}}'
```

Response:
```json
{
  "status": "success",
  "is_new_user": false,
  "user_type": "returning",
  "total_questions": 7,
  "medium_count": 5,
  "hard_count": 2,
  "sequence": [
    {
      "question_number": 1,
      "trigger_name": "SPOTLIGHT_HUNT",
      "difficulty": "medium",
      "intensity": "mild",
      "is_hard": false
    },
    // ... 6 more questions
  ]
}
```

#### Get Specific Question Trigger
```bash
curl -X POST http://localhost:5000/api/questions/trigger/3 \
  -H "Content-Type: application/json" \
  -d '{"user_profile": {"name": "John", "test_count": 5}}'
```

## 📋 Trigger List

### Medium Triggers (5)
1. **SPOTLIGHT_HUNT** - Spotlight effect testing visual focus
2. **HARD_FOG** - Fog overlay with meta-question (despite name, used as medium)
3. **ACCURACY_TEST** - Precision-based accuracy challenge
4. **READING_TEST** - Reading comprehension under pressure
5. **BILLIARD_BALL** - Moving target tracking challenge

### Hard Triggers (2)
6. **FLIP_CYCLE** - Screen flip cycle testing spatial orientation
7. **HARD_PEER_DOUBT** - Peer comparison with meta-question

## 🔄 User Flow

### New User Flow
```
1. App Launch
   ↓
2. Check user type → is_new_user = true
   ↓
3. Ask for name → Save to SharedPreferences
   ↓
4. Generate test plan → Fixed sequence
   ↓
5. Fetch questions (2 API calls: 5 medium + 2 hard)
   ↓
6. Render questions with triggers
   ↓
7. Save results (test_count++, previous_triggers)
```

### Returning User Flow
```
1. App Launch
   ↓
2. Check user type → is_new_user = false
   ↓
3. Skip name prompt (already saved)
   ↓
4. Generate test plan → Randomized sequence
   ↓
5. Fetch questions (2 API calls: 5 medium + 2 hard)
   ↓
6. Render questions with triggers
   ↓
7. Save results (test_count++, previous_triggers)
```

## 📊 Trigger Sequences

### New User (Fixed)
```
Q1 → SPOTLIGHT_HUNT      (medium, mild)
Q2 → HARD_FOG            (medium, strong)
Q3 → FLIP_CYCLE          (hard, strong) ⚠️
Q4 → ACCURACY_TEST       (medium, moderate)
Q5 → READING_TEST        (medium, moderate)
Q6 → HARD_PEER_DOUBT     (hard, strong) ⚠️
Q7 → BILLIARD_BALL       (medium, moderate)
```

### Returning User (Example)
```
Q1 → READING_TEST        (medium) ✓ Never hard
Q2 → HARD_FOG            (medium) ✓
Q3 → FLIP_CYCLE          (hard) ⚠️
Q4 → SPOTLIGHT_HUNT      (medium) ✓
Q5 → HARD_PEER_DOUBT     (hard) ⚠️
Q6 → ACCURACY_TEST       (medium) ✓
Q7 → BILLIARD_BALL       (medium) ✓
```

## 🎨 Frontend Integration

### User Profile Structure
```javascript
{
  name: "John Doe",              // Empty for new user
  test_count: 3,                 // 0 for new user
  last_test_date: "2026-05-01",
  previous_triggers: [           // From last test
    "SPOTLIGHT_HUNT",
    "HARD_FOG",
    "FLIP_CYCLE",
    "ACCURACY_TEST",
    "READING_TEST",
    "HARD_PEER_DOUBT",
    "BILLIARD_BALL"
  ]
}
```

### Basic Integration
```javascript
// 1. Check user type
const userProfile = loadFromStorage();
const typeResponse = await fetch('/api/questions/check-user-type', {
  method: 'POST',
  body: JSON.stringify({ user_profile: userProfile })
});
const { is_new_user, should_ask_name } = await typeResponse.json();

if (should_ask_name) {
  const name = await promptForName();
  userProfile.name = name;
  saveToStorage(userProfile);
}

// 2. Generate test plan
const planResponse = await fetch('/api/questions/trigger-plan', {
  method: 'POST',
  body: JSON.stringify({ user_profile: userProfile })
});
const testPlan = await planResponse.json();

// 3. Fetch questions (2 separate calls)
const mediumQuestions = await fetchQuestions('medium', 5);
const hardQuestions = await fetchQuestions('hard', 2);

// 4. Render with triggers
testPlan.sequence.forEach((trigger, index) => {
  const question = trigger.is_hard 
    ? hardQuestions.shift()
    : mediumQuestions.shift();
  renderQuestionWithTrigger(question, trigger);
});

// 5. Save results
userProfile.test_count++;
userProfile.previous_triggers = testPlan.sequence.map(t => t.trigger_name);
saveToStorage(userProfile);
```

## 📁 Files Created/Modified

### Created
- `app/services/question_trigger_decision.py` - Decision engine
- `docs/question-trigger-decision-layer.md` - Full documentation
- `test_question_trigger_decision.py` - Test suite
- `QUESTION_TRIGGER_IMPLEMENTATION.md` - Implementation details
- `IMPLEMENTATION_QUICK_START.md` - This file

### Modified
- `app/constants.py` - Added trigger constants
- `app/api/question_routes.py` - Added 3 API endpoints

## ✅ Validation Rules

1. Total questions: Exactly 7
2. Q1 constraint: Never hard (always medium)
3. Hard count: Exactly 2 hard questions
4. Medium count: Exactly 5 medium questions
5. No duplicates: Each trigger appears once
6. Hard positions: Q2-Q7 only (returning users)
7. Repetition avoidance: Deprioritize last trigger

## 🧪 Test Coverage

- ✅ New user detection
- ✅ New user sequence (fixed order)
- ✅ Returning user sequence (randomized)
- ✅ Full test plan generation
- ✅ Specific question triggers
- ✅ Sequence validation
- ✅ Previous trigger avoidance
- ✅ Trigger metadata

## 📚 Documentation

- **Full Documentation**: `docs/question-trigger-decision-layer.md`
- **Implementation Details**: `QUESTION_TRIGGER_IMPLEMENTATION.md`
- **This Quick Start**: `IMPLEMENTATION_QUICK_START.md`

## 🎯 Next Steps

### Backend (Complete ✅)
- ✅ Decision engine
- ✅ API endpoints
- ✅ Tests
- ✅ Documentation

### Frontend (To Do)
1. User profile management (SharedPreferences/LocalStorage)
2. Trigger plan API integration
3. Trigger visual effects (7 implementations)
4. Meta-question handling
5. Test result saving
6. End-to-end testing

## 🆘 Troubleshooting

### Tests Fail
```bash
# Check Python version (3.8+)
python --version

# Reinstall dependencies
pip install -r requirements.txt

# Run tests with verbose output
python test_question_trigger_decision.py -v
```

### API Errors
```bash
# Check server is running
curl http://localhost:5000/api/questions/stats

# Check logs
tail -f logs/app.log
```

### Import Errors
```bash
# Ensure app is in Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

## 📞 Support

For questions or issues:
1. Check `docs/question-trigger-decision-layer.md` for detailed documentation
2. Review `QUESTION_TRIGGER_IMPLEMENTATION.md` for implementation details
3. Run tests to verify setup: `python test_question_trigger_decision.py`

## 🎉 Status

**Backend Implementation**: 🟢 **COMPLETE AND TESTED**

Ready for frontend integration!

---TEST---

Terminal 1 (Server):

.\venv\Scripts\Activate.ps1
python test_question_trigger_decision.py  # Run tests first
python wsgi.py 
                            # Start server
Terminal 2 (Testing):
.\venv\Scripts\Activate.ps1
python test_api.py   

=== Test 1: Check New User ===
{
  "is_new_user": true,
  "message": "New user detected",
  "should_ask_name": true,
  "status": "success"
}

=== Test 2: New User Test Plan ===
User Type: new
Total Questions: 7
Medium: 5, Hard: 2

Sequence:
  Q1: SPOTLIGHT_HUNT (MEDIUM, mild)
  Q2: HARD_FOG (MEDIUM, strong)
  Q3: FLIP_CYCLE (⚠️ HARD, strong)
  Q4: ACCURACY_TEST (MEDIUM, moderate)
  Q5: READING_TEST (MEDIUM, moderate)
  Q6: HARD_PEER_DOUBT (⚠️ HARD, strong)
  Q7: BILLIARD_BALL (MEDIUM, moderate)

=== Test 3: Returning User Test Plan ===
User Type: returning

Sequence:
  Q1: SPOTLIGHT_HUNT (MEDIUM, mild)
  Q2: ACCURACY_TEST (MEDIUM, moderate)
  Q3: HARD_FOG (MEDIUM, strong)
  Q4: BILLIARD_BALL (MEDIUM, moderate)
  Q5: HARD_PEER_DOUBT (⚠️ HARD, strong)
  Q6: FLIP_CYCLE (⚠️ HARD, strong)
  Q7: READING_TEST (MEDIUM, moderate)

✅ All tests completed!