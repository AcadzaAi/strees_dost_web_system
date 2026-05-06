# Question Trigger Decision Layer - Focus Zones Test

## Overview

The Question Trigger Decision Layer is an AI-powered system that manages trigger selection for the 7-question Focus Zones test. It implements different trigger sequences for new vs. returning users to test focus and accuracy under various conditions.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React/JS)                       │
│  - User profile management (SharedPreferences)               │
│  - Question rendering with triggers                          │
│  - Trigger execution (visual effects, meta-questions)        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              API Layer (Flask Routes)                        │
│  POST /api/questions/trigger-plan                            │
│  POST /api/questions/trigger/<question_number>               │
│  POST /api/questions/check-user-type                         │
│  POST /api/questions/load-test-questions                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│        Decision Engine (Python Service)                      │
│  - QuestionTriggerDecisionEngine                             │
│  - New user: Fixed sequence (mild → strong)                  │
│  - Returning user: Randomized with constraints               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Question Fetching (Acadza API)                  │
│  - Fetch 5 medium questions (separate API call)              │
│  - Fetch 2 hard questions (separate API call)                │
└─────────────────────────────────────────────────────────────┘
```

## Core Concepts

### User Types

#### New User
- **Definition**: No saved name OR test_count = 0
- **Name Prompt**: YES (asked initially, saved to SharedPreferences)
- **Trigger Sequence**: Fixed order (mild → strong)
- **Purpose**: Gradual introduction to stress triggers

#### Returning User
- **Definition**: Has saved name AND test_count > 0
- **Name Prompt**: NO (already saved)
- **Trigger Sequence**: Randomized with constraints
- **Purpose**: Unpredictable testing environment

### Question Structure

**Total Questions**: 7
- **Medium Questions**: 5
- **Hard Questions**: 2

**API Calls Required**: 2
1. Call 1: Fetch 5 medium difficulty questions
2. Call 2: Fetch 2 hard difficulty questions

### Trigger Types

#### Medium Triggers (5 total)
1. **SPOTLIGHT_HUNT** - Spotlight effect testing visual focus
2. **ACCURACY_TEST** - Precision-based accuracy challenge
3. **READING_TEST** - Reading comprehension under pressure
4. **BILLIARD_BALL** - Moving target tracking challenge

#### Hard Triggers (2 total)
5. **HARD_FOG** - Fog overlay with meta-question
6. **FLIP_CYCLE** - Screen flip cycle testing spatial orientation
7. **HARD_PEER_DOUBT** - Peer comparison with meta-question

**Note**: Hard triggers often include meta-questions like "How was the last question? Was it medium?"

## Trigger Sequences

### New User Sequence (Fixed Order)

```
Q1 → SPOTLIGHT_HUNT      (medium, mild)
Q2 → HARD_FOG            (hard, strong) ⚠️
Q3 → FLIP_CYCLE          (hard, strong) ⚠️
Q4 → ACCURACY_TEST       (medium, moderate)
Q5 → READING_TEST        (medium, moderate)
Q6 → HARD_PEER_DOUBT     (hard, strong) ⚠️
Q7 → BILLIARD_BALL       (medium, moderate)
```

**Characteristics**:
- Progression from mild (Q1) to strong (Q3-Q4)
- Hard questions at Q3 and Q6 (fixed positions)
- Predictable for first-time users

### Returning User Sequence (Randomized)

**Constraints**:
- ✅ Q1: **NEVER hard** (only medium triggers allowed)
- ✅ Q2-Q7: **Completely random** (hard can appear on Q2, Q3, Q4, Q5, or Q6)
- ✅ Exactly **2 hard** questions total
- ✅ Exactly **5 medium** questions total
- ✅ **No duplicate** triggers in same test
- ✅ Avoid immediate repetition from previous test (if possible)

**Example Sequences**:

```
Example 1:
Q1 → SPOTLIGHT_HUNT      (medium) ✓
Q2 → HARD_FOG            (hard) ✓
Q3 → ACCURACY_TEST       (medium) ✓
Q4 → FLIP_CYCLE          (hard) ✓
Q5 → READING_TEST        (medium) ✓
Q6 → BILLIARD_BALL       (medium) ✓
Q7 → (one more medium)   (medium) ✓

Example 2:
Q1 → READING_TEST        (medium) ✓
Q2 → ACCURACY_TEST       (medium) ✓
Q3 → HARD_PEER_DOUBT     (hard) ✓
Q4 → SPOTLIGHT_HUNT      (medium) ✓
Q5 → HARD_FOG            (hard) ✓
Q6 → BILLIARD_BALL       (medium) ✓
Q7 → (one more medium)   (medium) ✓
```

## API Endpoints

### 1. Generate Full Test Plan

**Endpoint**: `POST /api/questions/trigger-plan`

**Purpose**: Generate complete trigger sequence for all 7 questions

**Request**:
```json
{
  "user_profile": {
    "name": "John Doe",           // Empty string if new user
    "test_count": 3,              // 0 for new user
    "last_test_date": "2026-05-01",
    "previous_triggers": [        // Optional: from last test
      "SPOTLIGHT_HUNT",
      "HARD_FOG",
      "FLIP_CYCLE",
      "ACCURACY_TEST",
      "READING_TEST",
      "HARD_PEER_DOUBT",
      "BILLIARD_BALL"
    ]
  }
}
```

**Response**:
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
      "description": "Spotlight effect that tests visual focus",
      "is_hard": false,
      "is_meta_question": false
    },
    {
      "question_number": 2,
      "trigger_name": "HARD_FOG",
      "difficulty": "hard",
      "intensity": "strong",
      "description": "Fog overlay with meta-question about previous question",
      "is_hard": true,
      "is_meta_question": true
    },
    // ... 5 more questions
  ],
  "medium_questions": [
    // 5 medium trigger configs
  ],
  "hard_questions": [
    // 2 hard trigger configs
  ]
}
```

### 2. Get Trigger for Specific Question

**Endpoint**: `POST /api/questions/trigger/<question_number>`

**Purpose**: Get trigger config for a single question (1-7)

**Request**:
```json
{
  "user_profile": {
    "name": "John Doe",
    "test_count": 3,
    "previous_triggers": [...]
  }
}
```

**Response**:
```json
{
  "status": "success",
  "question_number": 3,
  "trigger_name": "FLIP_CYCLE",
  "difficulty": "hard",
  "intensity": "strong",
  "description": "Screen flip cycle that tests spatial orientation",
  "is_hard": true,
  "is_meta_question": false
}
```

### 3. Check User Type

**Endpoint**: `POST /api/questions/check-user-type`

**Purpose**: Determine if user is new or returning

**Request**:
```json
{
  "user_profile": {
    "name": "",           // Empty for new user
    "test_count": 0       // 0 for new user
  }
}
```

**Response**:
```json
{
  "status": "success",
  "is_new_user": true,
  "should_ask_name": true,
  "message": "New user detected"
}
```

### 4. Load Test Questions (Enhanced)

**Endpoint**: `POST /api/questions/load-test-questions`

**Purpose**: Fetch 7 questions from Acadza API (5 medium + 2 hard)

**Request**:
```json
{
  "subject": "Physics",
  "topics": ["Kinematics", "Newton's Laws"]
}
```

**Response**:
```json
{
  "status": "success",
  "questions": [
    // 7 formatted questions (5 medium + 2 hard)
  ],
  "total_questions": 7,
  "fallback": false,
  "timestamp": "2026-05-06T10:30:00Z"
}
```

## Implementation Details

### Decision Engine Logic

**File**: `app/services/question_trigger_decision.py`

**Key Class**: `QuestionTriggerDecisionEngine`

**Methods**:

1. **`is_new_user(user_profile)`**
   - Checks if name is empty OR test_count = 0
   - Returns: `bool`

2. **`get_trigger_sequence_for_new_user()`**
   - Returns fixed sequence (NEW_USER_TRIGGER_SEQUENCE)
   - Order: mild → strong
   - Returns: `List[Dict]`

3. **`get_trigger_sequence_for_returning_user(previous_triggers)`**
   - Randomizes triggers with constraints
   - Q1: Always medium
   - Q2-Q7: Random (2 hard, 5 medium total)
   - Avoids immediate repetition
   - Returns: `List[Dict]`

4. **`get_full_test_plan(user_profile, previous_triggers)`**
   - Generates complete test plan
   - Splits into medium_questions and hard_questions
   - Returns: `Dict`

5. **`validate_trigger_sequence(sequence)`**
   - Validates sequence meets all constraints
   - Returns: `(is_valid, errors)`

### Constants

**File**: `app/constants.py`

```python
QUESTION_TRIGGERS = [
    "SPOTLIGHT_HUNT",
    "HARD_FOG",
    "FLIP_CYCLE",
    "ACCURACY_TEST",
    "READING_TEST",
    "HARD_PEER_DOUBT",
    "BILLIARD_BALL",
]

NEW_USER_TRIGGER_SEQUENCE = [
    "SPOTLIGHT_HUNT",      # Q1
    "HARD_FOG",            # Q2
    "FLIP_CYCLE",          # Q3 (hard)
    "ACCURACY_TEST",       # Q4
    "READING_TEST",        # Q5
    "HARD_PEER_DOUBT",     # Q6 (hard)
    "BILLIARD_BALL",       # Q7
]

HARD_QUESTION_TRIGGERS = ["HARD_FOG", "FLIP_CYCLE", "HARD_PEER_DOUBT"]
MEDIUM_QUESTION_TRIGGERS = ["SPOTLIGHT_HUNT", "ACCURACY_TEST", "READING_TEST", "BILLIARD_BALL"]
```

## Frontend Integration

### User Profile Management

**Storage**: SharedPreferences (Android) / LocalStorage (Web)

**Profile Structure**:
```javascript
{
  name: "John Doe",              // Empty string for new user
  test_count: 3,                 // 0 for new user
  last_test_date: "2026-05-01",
  previous_triggers: [           // Array of trigger names from last test
    "SPOTLIGHT_HUNT",
    "HARD_FOG",
    // ...
  ]
}
```

### Workflow

#### 1. App Launch
```javascript
// Check if user is new or returning
const userProfile = loadFromSharedPreferences();

const response = await fetch('/api/questions/check-user-type', {
  method: 'POST',
  body: JSON.stringify({ user_profile: userProfile })
});

const { is_new_user, should_ask_name } = await response.json();

if (should_ask_name) {
  // Show name input screen
  const name = await promptForName();
  userProfile.name = name;
  saveToSharedPreferences(userProfile);
}
```

#### 2. Generate Test Plan
```javascript
// Get full trigger sequence
const response = await fetch('/api/questions/trigger-plan', {
  method: 'POST',
  body: JSON.stringify({ user_profile: userProfile })
});

const testPlan = await response.json();
// testPlan.sequence contains all 7 trigger configs
```

#### 3. Fetch Questions
```javascript
// Make 2 separate API calls
const mediumResponse = await fetch('/api/questions/load-test-questions', {
  method: 'POST',
  body: JSON.stringify({
    subject: selectedSubject,
    topics: selectedTopics,
    difficulty: 'medium',
    count: 5
  })
});

const hardResponse = await fetch('/api/questions/load-test-questions', {
  method: 'POST',
  body: JSON.stringify({
    subject: selectedSubject,
    topics: selectedTopics,
    difficulty: 'hard',
    count: 2
  })
});

const mediumQuestions = await mediumResponse.json();
const hardQuestions = await hardResponse.json();
```

#### 4. Render Questions with Triggers
```javascript
testPlan.sequence.forEach((triggerConfig, index) => {
  const questionNumber = triggerConfig.question_number;
  const triggerName = triggerConfig.trigger_name;
  const isHard = triggerConfig.is_hard;
  
  // Select question from appropriate pool
  const question = isHard 
    ? hardQuestions[hardIndex++]
    : mediumQuestions[mediumIndex++];
  
  // Apply trigger to question
  renderQuestionWithTrigger(question, triggerConfig);
});
```

#### 5. Save Test Results
```javascript
// After test completion
userProfile.test_count += 1;
userProfile.last_test_date = new Date().toISOString();
userProfile.previous_triggers = testPlan.sequence.map(t => t.trigger_name);

saveToSharedPreferences(userProfile);
```

### Trigger Implementation Examples

#### SPOTLIGHT_HUNT (Medium)
```javascript
function applySpotlightHunt(questionElement) {
  // Create spotlight effect
  const spotlight = document.createElement('div');
  spotlight.className = 'spotlight-overlay';
  spotlight.style.background = 'radial-gradient(circle at var(--mouse-x) var(--mouse-y), transparent 100px, rgba(0,0,0,0.8) 200px)';
  
  // Track mouse movement
  document.addEventListener('mousemove', (e) => {
    spotlight.style.setProperty('--mouse-x', e.clientX + 'px');
    spotlight.style.setProperty('--mouse-y', e.clientY + 'px');
  });
  
  questionElement.appendChild(spotlight);
}
```

#### HARD_FOG (Hard with Meta-Question)
```javascript
function applyHardFog(questionElement, previousQuestion) {
  // Apply fog overlay
  const fog = document.createElement('div');
  fog.className = 'fog-overlay';
  fog.style.background = 'rgba(255, 255, 255, 0.7)';
  fog.style.backdropFilter = 'blur(3px)';
  questionElement.appendChild(fog);
  
  // Add meta-question
  const metaQuestion = document.createElement('div');
  metaQuestion.className = 'meta-question';
  metaQuestion.textContent = `Before answering: Was the last question (Q${previousQuestion.number}) medium difficulty?`;
  
  questionElement.insertBefore(metaQuestion, questionElement.firstChild);
}
```

#### FLIP_CYCLE (Hard)
```javascript
function applyFlipCycle(questionElement) {
  let flipCount = 0;
  const maxFlips = 3;
  
  const flipInterval = setInterval(() => {
    questionElement.style.transform = 'rotateY(180deg)';
    
    setTimeout(() => {
      questionElement.style.transform = 'rotateY(0deg)';
      flipCount++;
      
      if (flipCount >= maxFlips) {
        clearInterval(flipInterval);
      }
    }, 1000);
  }, 3000);
}
```

## Testing

### Unit Tests

**File**: `tests/test_question_trigger_decision.py`

```python
def test_new_user_sequence():
    engine = QuestionTriggerDecisionEngine()
    user_profile = {"name": "", "test_count": 0}
    
    sequence = engine.get_trigger_sequence_for_new_user()
    
    assert len(sequence) == 7
    assert sequence[0]["trigger_name"] == "SPOTLIGHT_HUNT"
    assert sequence[2]["trigger_name"] == "FLIP_CYCLE"
    assert sequence[2]["is_hard"] == True

def test_returning_user_q1_never_hard():
    engine = QuestionTriggerDecisionEngine()
    user_profile = {"name": "John", "test_count": 5}
    
    for _ in range(100):  # Test randomization
        sequence = engine.get_trigger_sequence_for_returning_user()
        assert sequence[0]["is_hard"] == False

def test_returning_user_exactly_2_hard():
    engine = QuestionTriggerDecisionEngine()
    user_profile = {"name": "John", "test_count": 5}
    
    sequence = engine.get_trigger_sequence_for_returning_user()
    hard_count = sum(1 for t in sequence if t["is_hard"])
    
    assert hard_count == 2
```

### Integration Tests

```bash
# Test trigger plan endpoint
curl -X POST http://localhost:5000/api/questions/trigger-plan \
  -H "Content-Type: application/json" \
  -d '{
    "user_profile": {
      "name": "",
      "test_count": 0
    }
  }'

# Test specific question trigger
curl -X POST http://localhost:5000/api/questions/trigger/3 \
  -H "Content-Type: application/json" \
  -d '{
    "user_profile": {
      "name": "John",
      "test_count": 5
    }
  }'
```

## Validation Rules

The system validates trigger sequences against these rules:

1. ✅ **Total Questions**: Exactly 7 questions
2. ✅ **Q1 Constraint**: Q1 is never hard
3. ✅ **Hard Count**: Exactly 2 hard questions
4. ✅ **Medium Count**: Exactly 5 medium questions
5. ✅ **Valid Triggers**: All trigger names are in QUESTION_TRIGGERS
6. ✅ **No Duplicates**: No trigger appears twice in same test
7. ✅ **Hard Positions**: Hard questions only on Q2-Q7 (returning users)

## Error Handling

### Invalid Question Number
```json
{
  "status": "error",
  "message": "Invalid question_number. Must be 1-7."
}
```

### Missing User Profile
```json
{
  "status": "error",
  "message": "user_profile is required"
}
```

### Validation Failure
```json
{
  "status": "error",
  "message": "Trigger sequence validation failed",
  "errors": [
    "Q1 cannot be a hard question",
    "Must have exactly 2 hard questions, got 3"
  ]
}
```

## Performance Considerations

1. **Caching**: User profiles cached in SharedPreferences/LocalStorage
2. **API Calls**: 2 separate calls for medium/hard questions (Acadza limitation)
3. **Randomization**: O(n) complexity for returning user sequence generation
4. **Validation**: O(n) complexity for sequence validation

## Future Enhancements

1. **Adaptive Difficulty**: Adjust trigger intensity based on user performance
2. **Trigger Analytics**: Track effectiveness of each trigger type
3. **Custom Sequences**: Allow admins to define custom trigger sequences
4. **A/B Testing**: Test different trigger orders for optimization
5. **Machine Learning**: Use ML to predict optimal trigger sequences

## References

- [AI Feedback Workflow Diagram](./ai-feedback-workflow-diagram.md)
- [Decision Feedback Layer Rules](./decision-feedback-layer-rules.md)
- [Implementation Summary](../IMPLEMENTATION_SUMMARY.md)

## Support

For questions or issues, contact the development team or file an issue in the project repository.
