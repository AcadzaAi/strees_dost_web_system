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
    "SPOTLIGHT_HUNT",
    "HARD_FOG",
    "FLIP_CYCLE",
    "ACCURACY_TEST",
    "READING_TEST",
    "HARD_PEER_DOUBT",
    "BILLIARD_BALL",
]

# Trigger metadata: difficulty and characteristics
QUESTION_TRIGGER_META = {
    "SPOTLIGHT_HUNT": {
        "difficulty": "medium",
        "intensity": "mild",
        "description": "Spotlight effect that tests visual focus",
        "order": 1,
    },
    "HARD_FOG": {
        "difficulty": "medium",  # Despite name, used as medium trigger at Q2
        "intensity": "strong",
        "description": "Fog overlay with meta-question about previous question",
        "order": 2,
        "is_meta_question": True,
    },
    "FLIP_CYCLE": {
        "difficulty": "hard",
        "intensity": "strong",
        "description": "Screen flip cycle that tests spatial orientation",
        "order": 3,
    },
    "ACCURACY_TEST": {
        "difficulty": "medium",
        "intensity": "moderate",
        "description": "Precision-based accuracy challenge",
        "order": 4,
    },
    "READING_TEST": {
        "difficulty": "medium",
        "intensity": "moderate",
        "description": "Reading comprehension under pressure",
        "order": 5,
    },
    "HARD_PEER_DOUBT": {
        "difficulty": "hard",
        "intensity": "strong",
        "description": "Peer comparison with meta-question",
        "order": 6,
        "is_meta_question": True,
    },
    "BILLIARD_BALL": {
        "difficulty": "medium",
        "intensity": "moderate",
        "description": "Moving target tracking challenge",
        "order": 7,
    },
}

# New user sequence (fixed order, mild to strong)
# Q3 and Q6 are hard questions for new users
NEW_USER_TRIGGER_SEQUENCE = [
    "SPOTLIGHT_HUNT",      # Q1 (medium)
    "HARD_FOG",            # Q2 (medium - despite name)
    "FLIP_CYCLE",          # Q3 (hard) ⚠️
    "ACCURACY_TEST",       # Q4 (medium)
    "READING_TEST",        # Q5 (medium)
    "HARD_PEER_DOUBT",     # Q6 (hard) ⚠️
    "BILLIARD_BALL",       # Q7 (medium)
]

# Hard triggers (can only appear Q2-Q6 for returning users)
HARD_QUESTION_TRIGGERS = ["FLIP_CYCLE", "HARD_PEER_DOUBT"]

# Medium triggers (can appear anywhere for returning users)
MEDIUM_QUESTION_TRIGGERS = [
    "SPOTLIGHT_HUNT",
    "HARD_FOG",  # Despite name, used as medium difficulty
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
