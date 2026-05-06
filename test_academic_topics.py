#!/usr/bin/env python3
"""Test script for academic topics extraction endpoint."""

import json
import requests

def test_extract_endpoint():
    """Test the /api/extract/academic-topics endpoint."""
    
    # Test data
    test_cases = [
        {
            "name": "Physics conversation",
            "text": "I'm struggling with kinematics and Newton's laws of motion",
            "conversation_history": [
                {"role": "assistant", "text": "What subjects are you finding difficult?"},
                {"role": "user", "text": "Physics is giving me trouble"}
            ]
        },
        {
            "name": "Math with single word reply",
            "text": "circle",
            "conversation_history": [
                {"role": "assistant", "text": "What geometry topic are you working on?"},
                {"role": "user", "text": "circle"}
            ]
        },
        {
            "name": "Chemistry topics",
            "text": "organic chemistry reaction mechanisms are confusing",
            "conversation_history": []
        },
        {
            "name": "Non-academic",
            "text": "I'm feeling stressed about exams",
            "conversation_history": []
        }
    ]
    
    base_url = "http://localhost:5000"
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {test_case['name']} ---")
        
        try:
            response = requests.post(
                f"{base_url}/api/extract/academic-topics",
                json={
                    "text": test_case["text"],
                    "conversation_history": test_case["conversation_history"]
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {})
                
                print(f"Academic Talk Detected: {result.get('academic_talk_detected', False)}")
                print(f"Subjects: {result.get('subjects', [])}")
                print(f"Chapters: {result.get('chapters', [])}")
                print(f"Concepts: {result.get('concepts', [])}")
                print(f"Sub-concepts: {result.get('sub_concepts', [])}")
                
                # Test autoPickedSubject logic
                subjects = result.get('subjects', [])
                auto_picked_subject = subjects[0] if subjects else None
                print(f"Auto Picked Subject: {auto_picked_subject}")
                
                # Test autoPickedTopics logic
                topics = (result.get('sub_concepts', []) or 
                          result.get('concepts', []) or 
                          result.get('chapters', []))
                auto_picked_topics = topics if auto_picked_subject and topics else None
                print(f"Auto Picked Topics: {auto_picked_topics}")
                
            else:
                print(f"Error: {response.text}")
                
        except Exception as e:
            print(f"Request failed: {e}")
    
    print("\n--- Subject Normalization Test ---")
    test_subjects = ["phy", "chem", "math", "bio", "physics", "chemistry", "unknown"]
    
    for subject in test_subjects:
        response = requests.post(
            f"{base_url}/api/extract/academic-topics",
            json={
                "text": f"I need help with {subject}",
                "conversation_history": []
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            result = data.get("result", {})
            normalized = result.get('subjects', [])
            print(f"'{subject}' -> {normalized}")

if __name__ == "__main__":
    test_extract_endpoint()
