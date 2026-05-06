"""AI Decision Layer for Question-Level Triggers in Focus Zones Test.

This module implements the trigger decision logic for the 7-question Focus Zones test.
It handles both new user (fixed sequence) and returning user (randomized) flows.

Key Features:
- New users: Fixed trigger sequence (mild → strong)
- Returning users: Randomized triggers with constraints
- Hard questions only on Q2-Q7 (never Q1)
- Exactly 1 trigger per question
- Separate API calls for medium (5) and hard (2) questions
"""
from __future__ import annotations

import logging
import random
from typing import Dict, List, Optional, Tuple

from ..constants import (
    HARD_QUESTION_TRIGGERS,
    MEDIUM_QUESTION_TRIGGERS,
    NEW_USER_TRIGGER_SEQUENCE,
    QUESTION_TRIGGER_META,
    QUESTION_TRIGGERS,
)

logger = logging.getLogger(__name__)


class QuestionTriggerDecisionEngine:
    """Manages trigger decisions for Focus Zones test questions."""

    def __init__(self):
        self.hard_triggers = HARD_QUESTION_TRIGGERS.copy()
        self.medium_triggers = MEDIUM_QUESTION_TRIGGERS.copy()
        self.all_triggers = QUESTION_TRIGGERS.copy()

    def is_new_user(self, user_profile: Dict) -> bool:
        """Determine if user is new based on profile.
        
        New user = no saved name or first time taking test.
        
        Args:
            user_profile: Dict with keys like 'name', 'test_count', 'last_test_date'
            
        Returns:
            True if new user, False if returning user
        """
        if not user_profile:
            return True
        
        # Check if name is saved
        name = user_profile.get("name", "").strip()
        if not name:
            return True
        
        # Check if user has taken test before
        test_count = user_profile.get("test_count", 0)
        if test_count == 0:
            return True
        
        return False

    def get_trigger_sequence_for_new_user(self) -> List[Dict]:
        """Get fixed trigger sequence for new users.
        
        Returns:
            List of 7 trigger configs in fixed order (mild → strong)
        """
        sequence = []
        for idx, trigger_name in enumerate(NEW_USER_TRIGGER_SEQUENCE, start=1):
            meta = QUESTION_TRIGGER_META[trigger_name]
            sequence.append({
                "question_number": idx,
                "trigger_name": trigger_name,
                "difficulty": meta["difficulty"],
                "intensity": meta["intensity"],
                "description": meta["description"],
                "is_hard": trigger_name in self.hard_triggers,
                "is_meta_question": meta.get("is_meta_question", False),
            })
        return sequence

    def get_trigger_sequence_for_returning_user(
        self,
        previous_triggers: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Get randomized trigger sequence for returning users.
        
        Constraints:
        - Q1: Never hard (only medium triggers)
        - Q2-Q7: Completely random (hard can appear on Q2, Q3, Q4, Q5, Q6)
        - Exactly 2 hard questions total
        - Exactly 5 medium questions total
        - Avoid immediate repetition from previous test if possible
        
        Args:
            previous_triggers: List of trigger names from user's last test
            
        Returns:
            List of 7 trigger configs in randomized order
        """
        # Prepare pools
        available_hard = self.hard_triggers.copy()
        available_medium = self.medium_triggers.copy()
        
        # Avoid immediate repetition if possible
        if previous_triggers:
            last_trigger = previous_triggers[-1] if previous_triggers else None
            if last_trigger in available_hard and len(available_hard) > 1:
                # Deprioritize last hard trigger
                available_hard = [t for t in available_hard if t != last_trigger]
                available_hard.append(last_trigger)  # Add to end
            if last_trigger in available_medium and len(available_medium) > 1:
                # Deprioritize last medium trigger
                available_medium = [t for t in available_medium if t != last_trigger]
                available_medium.append(last_trigger)  # Add to end
        
        # Shuffle pools
        random.shuffle(available_hard)
        random.shuffle(available_medium)
        
        # Q1: Always medium (never hard)
        q1_trigger = available_medium[0]
        remaining_medium = available_medium[1:]
        
        # Select 2 hard questions for Q2-Q7
        hard_positions = random.sample(range(2, 8), 2)  # Pick 2 positions from [2,3,4,5,6,7]
        hard_positions.sort()
        
        # Build sequence
        sequence = []
        hard_idx = 0
        medium_idx = 0
        
        for q_num in range(1, 8):
            if q_num == 1:
                # Q1: Always medium
                trigger_name = q1_trigger
                is_hard = False
            elif q_num in hard_positions:
                # Q2-Q7: Hard question
                trigger_name = available_hard[hard_idx]
                hard_idx += 1
                is_hard = True
            else:
                # Q2-Q7: Medium question
                trigger_name = remaining_medium[medium_idx]
                medium_idx += 1
                is_hard = False
            
            meta = QUESTION_TRIGGER_META[trigger_name]
            sequence.append({
                "question_number": q_num,
                "trigger_name": trigger_name,
                "difficulty": meta["difficulty"],
                "intensity": meta["intensity"],
                "description": meta["description"],
                "is_hard": is_hard,
                "is_meta_question": meta.get("is_meta_question", False),
            })
        
        logger.info(
            "Generated returning user sequence: hard_positions=%s triggers=%s",
            hard_positions,
            [t["trigger_name"] for t in sequence],
        )
        
        return sequence

    def get_question_difficulty_split(self) -> Tuple[int, int]:
        """Get the split of medium vs hard questions.
        
        Returns:
            Tuple of (medium_count, hard_count)
        """
        return (5, 2)

    def get_trigger_for_question(
        self,
        question_number: int,
        user_profile: Dict,
        previous_triggers: Optional[List[str]] = None,
    ) -> Dict:
        """Get trigger config for a specific question number.
        
        Args:
            question_number: Question number (1-7)
            user_profile: User profile dict
            previous_triggers: List of trigger names from user's last test
            
        Returns:
            Trigger config dict for the question
        """
        if not 1 <= question_number <= 7:
            raise ValueError(f"Invalid question_number: {question_number}. Must be 1-7.")
        
        is_new = self.is_new_user(user_profile)
        
        if is_new:
            sequence = self.get_trigger_sequence_for_new_user()
        else:
            sequence = self.get_trigger_sequence_for_returning_user(previous_triggers)
        
        return sequence[question_number - 1]

    def get_full_test_plan(
        self,
        user_profile: Dict,
        previous_triggers: Optional[List[str]] = None,
    ) -> Dict:
        """Generate complete test plan with all 7 triggers.
        
        Args:
            user_profile: User profile dict
            previous_triggers: List of trigger names from user's last test
            
        Returns:
            Dict with test plan including:
            - is_new_user: bool
            - total_questions: int
            - medium_count: int
            - hard_count: int
            - sequence: List of trigger configs
            - medium_questions: List of medium trigger configs
            - hard_questions: List of hard trigger configs
        """
        is_new = self.is_new_user(user_profile)
        
        if is_new:
            sequence = self.get_trigger_sequence_for_new_user()
        else:
            sequence = self.get_trigger_sequence_for_returning_user(previous_triggers)
        
        # Split into medium and hard
        medium_questions = [t for t in sequence if not t["is_hard"]]
        hard_questions = [t for t in sequence if t["is_hard"]]
        
        return {
            "is_new_user": is_new,
            "total_questions": 7,
            "medium_count": len(medium_questions),
            "hard_count": len(hard_questions),
            "sequence": sequence,
            "medium_questions": medium_questions,
            "hard_questions": hard_questions,
            "user_type": "new" if is_new else "returning",
        }

    def validate_trigger_sequence(self, sequence: List[Dict]) -> Tuple[bool, List[str]]:
        """Validate a trigger sequence meets all constraints.
        
        Args:
            sequence: List of trigger configs
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check length
        if len(sequence) != 7:
            errors.append(f"Sequence must have 7 questions, got {len(sequence)}")
        
        # Check Q1 is never hard
        if sequence and sequence[0]["is_hard"]:
            errors.append("Q1 cannot be a hard question")
        
        # Check exactly 2 hard and 5 medium
        hard_count = sum(1 for t in sequence if t["is_hard"])
        medium_count = sum(1 for t in sequence if not t["is_hard"])
        
        if hard_count != 2:
            errors.append(f"Must have exactly 2 hard questions, got {hard_count}")
        
        if medium_count != 5:
            errors.append(f"Must have exactly 5 medium questions, got {medium_count}")
        
        # Check all triggers are valid
        for t in sequence:
            if t["trigger_name"] not in self.all_triggers:
                errors.append(f"Invalid trigger name: {t['trigger_name']}")
        
        # Check no duplicate triggers
        trigger_names = [t["trigger_name"] for t in sequence]
        if len(trigger_names) != len(set(trigger_names)):
            errors.append("Duplicate triggers found in sequence")
        
        return (len(errors) == 0, errors)


# Global instance
_decision_engine = QuestionTriggerDecisionEngine()


def get_trigger_for_question(
    question_number: int,
    user_profile: Dict,
    previous_triggers: Optional[List[str]] = None,
) -> Dict:
    """Get trigger config for a specific question number.
    
    Args:
        question_number: Question number (1-7)
        user_profile: User profile dict
        previous_triggers: List of trigger names from user's last test
        
    Returns:
        Trigger config dict for the question
    """
    return _decision_engine.get_trigger_for_question(
        question_number, user_profile, previous_triggers
    )


def get_full_test_plan(
    user_profile: Dict,
    previous_triggers: Optional[List[str]] = None,
) -> Dict:
    """Generate complete test plan with all 7 triggers.
    
    Args:
        user_profile: User profile dict
        previous_triggers: List of trigger names from user's last test
        
    Returns:
        Dict with complete test plan
    """
    return _decision_engine.get_full_test_plan(user_profile, previous_triggers)


def is_new_user(user_profile: Dict) -> bool:
    """Check if user is new (no saved name or first test).
    
    Args:
        user_profile: User profile dict
        
    Returns:
        True if new user, False if returning
    """
    return _decision_engine.is_new_user(user_profile)


__all__ = [
    "QuestionTriggerDecisionEngine",
    "get_trigger_for_question",
    "get_full_test_plan",
    "is_new_user",
]
