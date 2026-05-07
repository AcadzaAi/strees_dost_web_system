"""Test suite for Question Trigger Decision Layer."""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.question_trigger_decision import (
    QuestionTriggerDecisionEngine,
    get_full_test_plan,
    get_trigger_for_question,
    is_new_user,
)
from app.constants import (
    HARD_QUESTION_TRIGGERS,
    MEDIUM_QUESTION_TRIGGERS,
    NEW_USER_TRIGGER_SEQUENCE,
)


def test_new_user_detection():
    """Test new user detection logic."""
    print("\n=== Test: New User Detection ===")
    
    # Empty profile
    assert is_new_user({}) == True
    print("✓ Empty profile detected as new user")
    
    # No name
    assert is_new_user({"name": "", "test_count": 0}) == True
    print("✓ Empty name detected as new user")
    
    # Zero test count
    assert is_new_user({"name": "John", "test_count": 0}) == True
    print("✓ Zero test count detected as new user")
    
    # Returning user
    assert is_new_user({"name": "John", "test_count": 5}) == False
    print("✓ User with name and test_count > 0 detected as returning user")


def test_new_user_sequence():
    """Test fixed sequence for new users."""
    print("\n=== Test: New User Sequence ===")
    
    engine = QuestionTriggerDecisionEngine()
    sequence = engine.get_trigger_sequence_for_new_user()
    
    # Check length
    assert len(sequence) == 7, f"Expected 7 questions, got {len(sequence)}"
    print(f"✓ Sequence has 7 questions")
    
    # Check order matches NEW_USER_TRIGGER_SEQUENCE
    for idx, expected_trigger in enumerate(NEW_USER_TRIGGER_SEQUENCE):
        actual_trigger = sequence[idx]["trigger_name"]
        assert actual_trigger == expected_trigger, \
            f"Q{idx+1}: Expected {expected_trigger}, got {actual_trigger}"
    print("✓ Sequence matches NEW_USER_TRIGGER_SEQUENCE")
    
    # Check Q3 and Q6 are hard
    assert sequence[2]["is_hard"] == True, "Q3 should be hard"
    assert sequence[5]["is_hard"] == True, "Q6 should be hard"
    print("✓ Q3 and Q6 are hard questions")
    
    # Check exactly 2 hard and 5 medium
    hard_count = sum(1 for t in sequence if t["is_hard"])
    medium_count = sum(1 for t in sequence if not t["is_hard"])
    assert hard_count == 2, f"Expected 2 hard, got {hard_count}"
    assert medium_count == 5, f"Expected 5 medium, got {medium_count}"
    print(f"✓ Exactly 2 hard and 5 medium questions")
    
    # Print sequence
    print("\nNew User Sequence:")
    for t in sequence:
        hard_marker = "⚠️ HARD" if t["is_hard"] else "MEDIUM"
        print(f"  Q{t['question_number']}: {t['trigger_name']} ({hard_marker}, {t['intensity']})")


def test_returning_user_sequence():
    """Test randomized sequence for returning users."""
    print("\n=== Test: Returning User Sequence ===")
    
    engine = QuestionTriggerDecisionEngine()
    
    # Run multiple times to test randomization
    sequences = []
    for i in range(10):
        sequence = engine.get_trigger_sequence_for_returning_user()
        sequences.append(sequence)
        
        # Validate each sequence
        is_valid, errors = engine.validate_trigger_sequence(sequence)
        assert is_valid, f"Sequence {i+1} validation failed: {errors}"
    
    print(f"✓ Generated and validated 10 random sequences")
    
    # Check Q1 is never hard in any sequence
    for idx, sequence in enumerate(sequences):
        assert sequence[0]["is_hard"] == False, \
            f"Sequence {idx+1}: Q1 should never be hard"
    print("✓ Q1 is never hard in any sequence")
    
    # Check all sequences have exactly 2 hard and 5 medium
    for idx, sequence in enumerate(sequences):
        hard_count = sum(1 for t in sequence if t["is_hard"])
        medium_count = sum(1 for t in sequence if not t["is_hard"])
        assert hard_count == 2, f"Sequence {idx+1}: Expected 2 hard, got {hard_count}"
        assert medium_count == 5, f"Sequence {idx+1}: Expected 5 medium, got {medium_count}"
    print("✓ All sequences have exactly 2 hard and 5 medium")
    
    # Check sequences are different (randomization works)
    trigger_lists = [
        tuple(t["trigger_name"] for t in seq)
        for seq in sequences
    ]
    unique_sequences = len(set(trigger_lists))
    print(f"✓ Generated {unique_sequences} unique sequences out of 10")
    
    # Print first sequence as example
    print("\nExample Returning User Sequence:")
    for t in sequences[0]:
        hard_marker = "⚠️ HARD" if t["is_hard"] else "MEDIUM"
        print(f"  Q{t['question_number']}: {t['trigger_name']} ({hard_marker}, {t['intensity']})")


def test_full_test_plan():
    """Test full test plan generation."""
    print("\n=== Test: Full Test Plan ===")
    
    # New user plan
    new_user_profile = {"name": "", "test_count": 0}
    new_plan = get_full_test_plan(new_user_profile)
    
    assert new_plan["is_new_user"] == True
    assert new_plan["user_type"] == "new"
    assert new_plan["total_questions"] == 7
    assert new_plan["medium_count"] == 5
    assert new_plan["hard_count"] == 2
    assert len(new_plan["sequence"]) == 7
    assert len(new_plan["medium_questions"]) == 5
    assert len(new_plan["hard_questions"]) == 2
    print("✓ New user plan generated correctly")
    
    # Returning user plan
    returning_user_profile = {"name": "John", "test_count": 5}
    returning_plan = get_full_test_plan(returning_user_profile)
    
    assert returning_plan["is_new_user"] == False
    assert returning_plan["user_type"] == "returning"
    assert returning_plan["total_questions"] == 7
    assert returning_plan["medium_count"] == 5
    assert returning_plan["hard_count"] == 2
    print("✓ Returning user plan generated correctly")


def test_specific_question_trigger():
    """Test getting trigger for specific question number."""
    print("\n=== Test: Specific Question Trigger ===")
    
    new_user_profile = {"name": "", "test_count": 0}
    
    # Test Q1 for new user
    q1_trigger = get_trigger_for_question(1, new_user_profile)
    assert q1_trigger["question_number"] == 1
    assert q1_trigger["trigger_name"] == "TORCHLIGHT_SPOTLIGHT"
    assert q1_trigger["is_hard"] == False
    print("✓ Q1 trigger for new user: TORCHLIGHT_SPOTLIGHT (medium)")
    
    # Test Q3 for new user (should be hard)
    q3_trigger = get_trigger_for_question(3, new_user_profile)
    assert q3_trigger["question_number"] == 3
    assert q3_trigger["trigger_name"] == "SCREEN_FLIP"
    assert q3_trigger["is_hard"] == True
    print("✓ Q3 trigger for new user: SCREEN_FLIP (hard)")
    
    # Test Q1 for returning user (should never be hard)
    returning_user_profile = {"name": "John", "test_count": 5}
    for i in range(10):
        q1_trigger = get_trigger_for_question(1, returning_user_profile)
        assert q1_trigger["is_hard"] == False, f"Iteration {i+1}: Q1 should never be hard"
    print("✓ Q1 for returning user is never hard (tested 10 times)")


def test_validation():
    """Test sequence validation."""
    print("\n=== Test: Sequence Validation ===")
    
    engine = QuestionTriggerDecisionEngine()
    
    # Valid sequence
    valid_sequence = engine.get_trigger_sequence_for_new_user()
    is_valid, errors = engine.validate_trigger_sequence(valid_sequence)
    assert is_valid == True
    assert len(errors) == 0
    print("✓ Valid sequence passes validation")
    
    # Invalid: Q1 is hard
    invalid_q1_hard = valid_sequence.copy()
    invalid_q1_hard[0] = dict(invalid_q1_hard[0])
    invalid_q1_hard[0]["is_hard"] = True
    is_valid, errors = engine.validate_trigger_sequence(invalid_q1_hard)
    assert is_valid == False
    assert any("Q1 cannot be a hard question" in e for e in errors)
    print("✓ Invalid sequence (Q1 hard) fails validation")
    
    # Invalid: Wrong number of questions
    invalid_length = valid_sequence[:5]
    is_valid, errors = engine.validate_trigger_sequence(invalid_length)
    assert is_valid == False
    assert any("must have 7 questions" in e.lower() for e in errors)
    print("✓ Invalid sequence (wrong length) fails validation")


def test_previous_trigger_avoidance():
    """Test that returning users avoid immediate repetition."""
    print("\n=== Test: Previous Trigger Avoidance ===")
    
    engine = QuestionTriggerDecisionEngine()
    
    # Simulate previous test ending with TORCHLIGHT_SPOTLIGHT
    previous_triggers = [
        "ACCURACY_TEST",
        "HARD_FOG",
        "READING_TEST",
        "SCREEN_FLIP",
        "BILLIARD_BALL",
        "HARD_PEER_DOUBT",
        "TORCHLIGHT_SPOTLIGHT",  # Last trigger
    ]
    
    # Generate new sequence multiple times
    first_triggers = []
    for _ in range(20):
        sequence = engine.get_trigger_sequence_for_returning_user(previous_triggers)
        first_triggers.append(sequence[0]["trigger_name"])
    
    # Check that TORCHLIGHT_SPOTLIGHT is less likely to appear first
    spotlight_count = first_triggers.count("TORCHLIGHT_SPOTLIGHT")
    total_count = len(first_triggers)
    
    print(f"✓ TORCHLIGHT_SPOTLIGHT appeared {spotlight_count}/{total_count} times as Q1")
    print(f"  (Should be less frequent due to deprioritization)")


def test_trigger_metadata():
    """Test trigger metadata is correct."""
    print("\n=== Test: Trigger Metadata ===")
    
    engine = QuestionTriggerDecisionEngine()
    sequence = engine.get_trigger_sequence_for_new_user()
    
    for trigger_config in sequence:
        trigger_name = trigger_config["trigger_name"]
        
        # Check all required fields exist
        assert "question_number" in trigger_config
        assert "trigger_name" in trigger_config
        assert "difficulty" in trigger_config
        assert "intensity" in trigger_config
        assert "description" in trigger_config
        assert "is_hard" in trigger_config
        assert "is_meta_question" in trigger_config
        
        # Check difficulty matches is_hard
        if trigger_name in HARD_QUESTION_TRIGGERS:
            assert trigger_config["difficulty"] == "hard"
        else:
            assert trigger_config["difficulty"] == "medium"
    
    print("✓ All trigger configs have required fields")
    print("✓ Difficulty matches trigger type")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Question Trigger Decision Layer - Test Suite")
    print("=" * 60)
    
    try:
        test_new_user_detection()
        test_new_user_sequence()
        test_returning_user_sequence()
        test_full_test_plan()
        test_specific_question_trigger()
        test_validation()
        test_previous_trigger_avoidance()
        test_trigger_metadata()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return True
    
    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        return False
    
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
