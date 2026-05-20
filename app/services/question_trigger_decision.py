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
            user_profile: Dict with keys like 'name', 'test_count', 'completed_sessions', 'last_test_date'
            
        Returns:
            True if new user, False if returning user
        """
        if not user_profile:
            logger.info("is_new_user: No user_profile provided → NEW USER")
            return True
        
        # Check if name is saved
        name = user_profile.get("name", "").strip()
        if not name:
            logger.info("is_new_user: No name saved → NEW USER")
            return True
        
        # Check if user has taken test before (check both test_count and completed_sessions)
        test_count = user_profile.get("test_count", 0)
        completed_sessions = user_profile.get("completed_sessions", 0)
        
        logger.info(
            "is_new_user: name='%s', test_count=%d, completed_sessions=%d",
            name, test_count, completed_sessions
        )
        
        # User is new if both are 0
        if test_count == 0 and completed_sessions == 0:
            logger.info("is_new_user: Both counts are 0 → NEW USER")
            return True
        
        logger.info("is_new_user: Has previous sessions → RETURNING USER")
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
        question_difficulties: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Get randomized trigger sequence for returning users.
        
        For returning users:
        - Q1: Always Medium (never hard)
        - Q2-Q7: Random mix of 2 hard + 4 medium questions
        - Hard questions get Q2 or Q6 trigger definitions randomly
        - Medium questions get other trigger definitions randomly
        - Each question maintains its complete trigger cycle
        
        Args:
            previous_triggers: List of trigger names from user's last test
            question_difficulties: List of difficulty levels for each question (HARD/MEDIUM)
            
        Returns:
            List of 7 trigger configs in randomized order
        """
        # Prepare pools
        available_hard_triggers = self.hard_triggers.copy()
        available_medium_triggers = self.medium_triggers.copy()
        
        # Avoid immediate repetition if possible
        if previous_triggers:
            last_trigger = previous_triggers[-1] if previous_triggers else None
            if last_trigger in available_hard_triggers and len(available_hard_triggers) > 1:
                # Deprioritize last hard trigger
                available_hard_triggers = [t for t in available_hard_triggers if t != last_trigger]
                available_hard_triggers.append(last_trigger)  # Add to end
            if last_trigger in available_medium_triggers and len(available_medium_triggers) > 1:
                # Deprioritize last medium trigger
                available_medium_triggers = [t for t in available_medium_triggers if t != last_trigger]
                available_medium_triggers.append(last_trigger)  # Add to end
        
        # Shuffle pools
        random.shuffle(available_hard_triggers)
        random.shuffle(available_medium_triggers)
        
        # Build sequence
        sequence = []
        hard_trigger_idx = 0
        medium_trigger_idx = 0
        
        # If question_difficulties provided, use them to determine which questions are hard
        if question_difficulties and len(question_difficulties) == 7:
            logger.info("Using provided question difficulties: %s", question_difficulties)
            for q_num in range(1, 8):
                is_hard_question = question_difficulties[q_num - 1].upper() == "HARD"
                
                # Q1 should never be hard
                if q_num == 1 and is_hard_question:
                    logger.warning("Q1 marked as HARD but forcing to MEDIUM")
                    is_hard_question = False
                
                if is_hard_question:
                    # Hard question gets a hard trigger (Q2 or Q6 trigger definition)
                    trigger_name = available_hard_triggers[hard_trigger_idx % len(available_hard_triggers)]
                    hard_trigger_idx += 1
                else:
                    # Medium question gets a medium trigger
                    trigger_name = available_medium_triggers[medium_trigger_idx % len(available_medium_triggers)]
                    medium_trigger_idx += 1
                
                meta = QUESTION_TRIGGER_META[trigger_name]
                sequence.append({
                    "question_number": q_num,
                    "trigger_name": trigger_name,
                    "difficulty": meta["difficulty"],
                    "intensity": meta["intensity"],
                    "description": meta["description"],
                    "is_hard": is_hard_question,
                    "is_meta_question": meta.get("is_meta_question", False),
                })
        else:
            # Fallback: Random positioning (old logic)
            logger.info("No question difficulties provided, using random positioning")
            # Q1: Always medium (never hard)
            q1_trigger = available_medium_triggers[0]
            remaining_medium = available_medium_triggers[1:]
            
            # Select 2 hard questions for Q2-Q7
            hard_positions = random.sample(range(2, 8), 2)  # Pick 2 positions from [2,3,4,5,6,7]
            hard_positions.sort()
            
            hard_idx = 0
            medium_idx = 0
            
            for q_num in range(1, 8):
                if q_num == 1:
                    # Q1: Always medium
                    trigger_name = q1_trigger
                    is_hard = False
                elif q_num in hard_positions:
                    # Q2-Q7: Hard question
                    trigger_name = available_hard_triggers[hard_idx]
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
            "Generated returning user sequence: triggers=%s",
            [f"Q{t['question_number']}:{t['trigger_name']}({'H' if t['is_hard'] else 'M'})" for t in sequence],
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
        
        force_new = bool(user_profile.get("force_new_user"))
        is_new = force_new or self.is_new_user(user_profile)
        
        if is_new:
            sequence = self.get_trigger_sequence_for_new_user()
        else:
            sequence = self.get_trigger_sequence_for_returning_user(previous_triggers)
        
        return sequence[question_number - 1]

    def get_full_test_plan(
        self,
        user_profile: Dict,
        previous_triggers: Optional[List[str]] = None,
        question_difficulties: Optional[List[str]] = None,
    ) -> Dict:
        """Generate complete test plan with all 7 triggers.
        
        Args:
            user_profile: User profile dict
            previous_triggers: List of trigger names from user's last test
            question_difficulties: List of difficulty levels for each question (HARD/MEDIUM)
            
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
        force_new = bool(user_profile.get("force_new_user"))
        is_new = force_new or self.is_new_user(user_profile)
        
        if is_new:
            sequence = self.get_trigger_sequence_for_new_user()
        else:
            sequence = self.get_trigger_sequence_for_returning_user(previous_triggers, question_difficulties)
        
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
    question_difficulties: Optional[List[str]] = None,
) -> Dict:
    """Generate complete test plan with all 7 triggers.
    
    Args:
        user_profile: User profile dict
        previous_triggers: List of trigger names from user's last test
        question_difficulties: List of difficulty levels for each question (HARD/MEDIUM)
        
    Returns:
        Dict with complete test plan
    """
    return _decision_engine.get_full_test_plan(user_profile, previous_triggers, question_difficulties)


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
