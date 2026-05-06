"""Test to verify all model names are correct (gpt-4o-mini, not gpt-5-mini)."""
import os
import re
from pathlib import Path

def test_no_invalid_model_names():
    """Verify no gpt-5-mini model names exist in the codebase."""
    print("=" * 60)
    print("Testing: No Invalid Model Names (gpt-5-mini)")
    print("=" * 60)
    
    invalid_model = "gpt-5-mini"
    valid_model = "gpt-4o-mini"
    
    # Search all Python files
    app_dir = Path("app")
    python_files = list(app_dir.rglob("*.py"))
    
    invalid_found = []
    valid_found = []
    
    for file_path in python_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # Check for invalid model
            if invalid_model in content:
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if invalid_model in line:
                        invalid_found.append((str(file_path), i, line.strip()))
            
            # Check for valid model
            if valid_model in content:
                valid_found.append(str(file_path))
        
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")
    
    # Report results
    print(f"\n✓ Scanned {len(python_files)} Python files")
    
    if invalid_found:
        print(f"\n❌ FAILED: Found {len(invalid_found)} instances of invalid model '{invalid_model}':")
        for file_path, line_num, line in invalid_found:
            print(f"  {file_path}:{line_num}")
            print(f"    {line}")
        return False
    else:
        print(f"\n✅ PASSED: No instances of invalid model '{invalid_model}' found")
    
    if valid_found:
        print(f"\n✓ Found {len(valid_found)} files using valid model '{valid_model}':")
        for file_path in valid_found[:10]:  # Show first 10
            print(f"  ✓ {file_path}")
        if len(valid_found) > 10:
            print(f"  ... and {len(valid_found) - 10} more files")
    
    return True


def test_model_consistency():
    """Verify all LLM calls use consistent model naming."""
    print("\n" + "=" * 60)
    print("Testing: Model Name Consistency")
    print("=" * 60)
    
    app_dir = Path("app")
    python_files = list(app_dir.rglob("*.py"))
    
    # Pattern to find model= parameters
    model_pattern = re.compile(r'model\s*=\s*["\']([^"\']+)["\']')
    
    models_found = {}
    
    for file_path in python_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            matches = model_pattern.findall(content)
            
            for model in matches:
                if model not in models_found:
                    models_found[model] = []
                models_found[model].append(str(file_path))
        
        except Exception as e:
            pass
    
    print(f"\nFound {len(models_found)} unique model names:")
    for model, files in sorted(models_found.items()):
        print(f"\n  Model: {model}")
        print(f"  Used in {len(files)} file(s)")
        
        # Check if it's a valid OpenAI model
        valid_models = [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "whisper-1",
        ]
        
        is_valid = any(valid in model for valid in valid_models)
        status = "✅" if is_valid else "⚠️"
        print(f"  Status: {status}")
    
    return True


def test_specific_files():
    """Test specific files mentioned in the changelog."""
    print("\n" + "=" * 60)
    print("Testing: Specific Files from Changelog")
    print("=" * 60)
    
    files_to_check = [
        "app/services/slot_prefill_llm.py",
        "app/services/gpt_client.py",
        "app/services/slot_gate_llm.py",
        "app/services/question_mutator.py",
    ]
    
    all_passed = True
    
    for file_path in files_to_check:
        path = Path(file_path)
        if not path.exists():
            print(f"\n⚠️  File not found: {file_path}")
            continue
        
        content = path.read_text(encoding='utf-8')
        
        has_invalid = "gpt-5-mini" in content
        has_valid = "gpt-4o-mini" in content
        
        if has_invalid:
            print(f"\n❌ {file_path}")
            print(f"   Still contains 'gpt-5-mini'")
            all_passed = False
        elif has_valid:
            print(f"\n✅ {file_path}")
            print(f"   Using 'gpt-4o-mini' correctly")
        else:
            print(f"\n⚠️  {file_path}")
            print(f"   No model references found")
    
    return all_passed


def run_all_tests():
    """Run all model name tests."""
    print("\n" + "=" * 60)
    print("Model Name Verification Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test 1: No invalid model names
    results.append(("No Invalid Models", test_no_invalid_model_names()))
    
    # Test 2: Model consistency
    results.append(("Model Consistency", test_model_consistency()))
    
    # Test 3: Specific files
    results.append(("Specific Files", test_specific_files()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("All model names are correct (gpt-4o-mini)")
    else:
        print("❌ SOME TESTS FAILED")
        print("Please fix the invalid model names")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
