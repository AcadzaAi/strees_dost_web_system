"""Domain schema and priority definitions."""
from __future__ import annotations

SLOT_SCHEMA = {
    "distractions": [
        "phone_app",
        "app_activity",
        "reel_type",
        "friend_name",
        "gaming_app",
        "gaming_time",
    ],
    "academic_confidence": [
        "weak_subject",
        "favorite_subject",
        "concept_confidence",
        "last_test_experience",
    ],
    "time_pressure": [
        "exam_time_left",
        "study_hours_per_day",
        "timetable_breaker",
    ],
    "social_comparison": [
        "comparison_person",
        "comparison_gap",
    ],
    "family_pressure": [
        "family_member",
        "expectation_type",
    ],
    "motivation": [
        "motivation_reason",
        "demotivation_reason",
    ],
    "backlog_stress": [
        "backlog_subject",
        "backlog_deadline",
    ],
}

PRIORITY_ORDER = [
    "time_pressure",
    "academic_confidence",
    "distractions",
    "backlog_stress",
    "family_pressure",
    "social_comparison",
    "motivation",
]


# Question-level trigger system for Focus Zones test
QUESTION_TRIGGERS = [
    "TORCHLIGHT_SPOTLIGHT",
    "HARD_FOG",
    "SCREEN_FLIP",
    "ACCURACY_TEST",
    "READING_TEST",
    "HARD_PEER_DOUBT",
    "BILLIARD_BALL",
]

# Trigger metadata: difficulty and characteristics
QUESTION_TRIGGER_META = {
    "TORCHLIGHT_SPOTLIGHT": {
        "difficulty": "medium",
        "intensity": "mild",
        "description": "Torchlight spotlight effect that tests visual focus",
        "order": 1,
        "frontend_trigger": "torchlightSpotlight",
        "delay_ms": 6000,
    },
    "HARD_FOG": {
        "difficulty": "medium",  # Despite name, used as medium trigger at Q2
        "intensity": "strong",
        "description": "Fog overlay with pre-sequence (difficulty check, warning, stress timer)",
        "order": 2,
        "is_meta_question": True,
        "frontend_trigger": "hardFog",
        "delay_ms": 6000,
        "pre_sequence": ["difficultyCheckPrompt", "hardQuestionWarning", "stressTimer"],
    },
    "SCREEN_FLIP": {
        "difficulty": "hard",
        "intensity": "strong",
        "description": "Screen flip cycle (5 flips, final state permanent)",
        "order": 3,
        "frontend_trigger": "screenFlip",
        "delay_ms": 5000,
        "flip_cycles": 5,
    },
    "ACCURACY_TEST": {
        "difficulty": "medium",
        "intensity": "moderate",
        "description": "Shaking screen accuracy test with explain trap",
        "order": 4,
        "frontend_trigger": "accuracyTest",
        "delay_ms": 1000,
        "wait_for_screen_free": True,
    },
    "READING_TEST": {
        "difficulty": "medium",
        "intensity": "moderate",
        "description": "Reading test with hand signal, clear time, and blur gate",
        "order": 5,
        "frontend_trigger": "readingTest",
        "delay_ms": 3000,
        "sequence": ["focusHandSignal", "clearReading", "focusReadGate"],
    },
    "HARD_PEER_DOUBT": {
        "difficulty": "hard",
        "intensity": "strong",
        "description": "Peer comparison with pre-sequence and submission interception",
        "order": 6,
        "is_meta_question": True,
        "frontend_trigger": "hardPeerDoubt",
        "delay_ms": 6000,
        "pre_sequence": ["difficultyCheckPrompt", "hardQuestionWarning", "stressTimer"],
        "interception_enabled": True,
        "max_interceptions": 2,
    },
    "BILLIARD_BALL": {
        "difficulty": "medium",
        "intensity": "moderate",
        "description": "Bouncing question with pre-taunt",
        "order": 7,
        "frontend_trigger": "billiardBall",
        "delay_ms": 1500,
        "sequence": ["premiumImagePopup", "bouncingQuestion"],
    },
}

# New user sequence (fixed order, mild to strong)
# Q2 and Q6 are hard questions for new users
NEW_USER_TRIGGER_SEQUENCE = [
    "TORCHLIGHT_SPOTLIGHT", # Q1 (medium)
    "HARD_FOG",            # Q2 (hard) ⚠️
    "SCREEN_FLIP",         # Q3 (medium)
    "ACCURACY_TEST",       # Q4 (medium)
    "READING_TEST",        # Q5 (medium)
    "HARD_PEER_DOUBT",     # Q6 (hard) ⚠️
    "BILLIARD_BALL",       # Q7 (medium)
]

# Hard triggers (can only appear Q2-Q6 for returning users)
HARD_QUESTION_TRIGGERS = ["HARD_FOG", "HARD_PEER_DOUBT"]

# Medium triggers (can appear anywhere for returning users)
MEDIUM_QUESTION_TRIGGERS = [
    "TORCHLIGHT_SPOTLIGHT",
    "SCREEN_FLIP",
    "ACCURACY_TEST",
    "READING_TEST",
    "BILLIARD_BALL",
]


__all__ = [
    "SLOT_SCHEMA",
    "PRIORITY_ORDER",
    "QUESTION_TRIGGERS",
    "QUESTION_TRIGGER_META",
    "NEW_USER_TRIGGER_SEQUENCE",
    "HARD_QUESTION_TRIGGERS",
    "MEDIUM_QUESTION_TRIGGERS",
]
