"""Routes for generating personalized focus prompts based on selected challenges."""
from __future__ import annotations

import logging
import json
from flask import Blueprint, request, jsonify
from app.services.openai_client import client

logger = logging.getLogger(__name__)
bp = Blueprint("focus_prompts", __name__, url_prefix="/api/focus-prompts")

# Personalized prompt templates for each category
CATEGORY_CONTEXTS = {
    "phone-addiction": {
        "context": "phone usage and smartphone distraction",
        "examples": ["checking notifications", "scrolling endlessly", "social apps"]
    },
    "social-media": {
        "context": "social media and content consumption",
        "examples": ["Instagram reels", "TikTok videos", "YouTube shorts"]
    },
    "entertainment": {
        "context": "entertainment and streaming content",
        "examples": ["Netflix binges", "web series", "movies"]
    },
    "sports-gaming": {
        "context": "gaming and sports activities",
        "examples": ["video games", "online gaming", "sports watching"]
    },
    "exam-stress": {
        "context": "exam anxiety and test pressure",
        "examples": ["panic before exams", "fear of failure", "performance anxiety"]
    },
    "overthinking": {
        "context": "overthinking and mental rumination",
        "examples": ["analyzing everything", "worrying about outcomes", "can't shut mind off"]
    },
    "low-motivation": {
        "context": "low motivation and lack of energy",
        "examples": ["no drive to study", "feeling lazy", "can't start tasks"]
    },
    "consistency": {
        "context": "lack of consistency and discipline",
        "examples": ["starting but not finishing", "irregular study patterns", "breaking routines"]
    },
    "time-management": {
        "context": "time management and planning issues",
        "examples": ["procrastinating", "poor scheduling", "wasting time"]
    },
    "sleep-issues": {
        "context": "sleep problems and fatigue",
        "examples": ["not sleeping enough", "staying up late", "feeling tired"]
    },
    "understanding": {
        "context": "difficulty understanding concepts",
        "examples": ["topics don't make sense", "forgetting what I learned", "confused by lessons"]
    },
    "confidence": {
        "context": "low confidence and self-doubt",
        "examples": ["doubting my abilities", "comparing to others", "feeling not good enough"]
    },
    "family-pressure": {
        "context": "family pressure and expectations",
        "examples": ["parents expectations", "family stress", "pressure to perform"]
    },
    "burnout": {
        "context": "study burnout and exhaustion",
        "examples": ["feeling drained", "mentally exhausted", "can't study anymore"]
    },
    "concentration": {
        "context": "poor concentration and focus issues",
        "examples": ["mind wandering", "can't pay attention", "easily distracted"]
    },
    "other": {
        "context": "other focus challenges",
        "examples": ["specific situations", "unique problems", "personal struggles"]
    }
}


@bp.route("/quick-prompts", methods=["POST"])
def get_quick_prompts():
    """Generate 3-4 quick prompt options based on selected challenges."""
    try:
        data = request.get_json() or {}
        challenges = data.get("challenges", [])
        
        if not challenges:
            return jsonify({"error": "No challenges provided"}), 400
        
        # Build context from selected challenges
        challenge_texts = [c.get("text", "") for c in challenges]
        challenge_values = [c.get("value", "") for c in challenges]
        
        # Get contexts for selected challenges
        contexts = []
        for value in challenge_values:
            if value in CATEGORY_CONTEXTS:
                ctx = CATEGORY_CONTEXTS[value]
                contexts.append(f"{ctx['context']} (e.g., {', '.join(ctx['examples'][:2])})")
        
        combined_context = "; ".join(contexts)
        
        # Create prompt for OpenAI
        system_prompt = """You are a helpful assistant for students. Generate 3-4 short, specific follow-up prompts 
that would help us understand the student's focus challenges better. Each prompt should:
- Be 5-10 words maximum
- Be conversational and friendly
- Ask about specific situations or triggers
- Help understand when/how/why the distraction happens
- Be in first person (starting with "I" or "My")

Return ONLY a JSON array of strings, nothing else."""

        user_prompt = f"""The student selected these challenges: {', '.join(challenge_texts)}.

Context about these challenges: {combined_context}

Generate 3-4 brief, specific follow-up prompts that would help us understand their situation better.
Examples of good prompts:
- "I lose track of time scrolling"
- "It happens mostly at night"
- "I feel anxious before tests"
- "My friends distract me often"

Return ONLY the JSON array, no markdown, no explanation."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,
            max_tokens=150
        )
        
        content = response.choices[0].message.content.strip()
        
        # Try to parse JSON from the response
        # Remove markdown code blocks if present
        content = content.replace("```json", "").replace("```", "").strip()
        prompts = json.loads(content)
        
        if not isinstance(prompts, list):
            raise ValueError("Response is not a list")
        
        # Ensure we have 3-4 prompts
        prompts = prompts[:4]
        
        logger.info(f"Generated {len(prompts)} quick prompts for challenges: {challenge_texts}")
        
        return jsonify({
            "prompts": prompts,
            "count": len(prompts)
        })
        
    except Exception as e:
        logger.error(f"Error generating quick prompts: {e}")
        # Return fallback prompts
        return jsonify({
            "prompts": [
                "It happens most during study time",
                "I lose track of time easily",
                "It affects my performance",
                "I want to change this habit"
            ],
            "count": 4,
            "fallback": True
        })


@bp.route("/text-completion", methods=["POST"])
def get_text_completion():
    """Generate text completion suggestions based on partial input."""
    try:
        data = request.get_json() or {}
        partial_text = data.get("text", "").strip()
        challenges = data.get("challenges", [])
        
        if not partial_text or len(partial_text) < 5:
            return jsonify({"suggestions": []})
        
        # Build context
        challenge_texts = [c.get("text", "") for c in challenges]
        
        system_prompt = """You are helping a student complete their thought about focus challenges. 
Generate 2-3 natural, relevant completions for their sentence. Each completion should:
- Continue from where they left off naturally
- Be specific and actionable
- Be 5-15 words
- Stay on topic with their challenge

Return ONLY a JSON array of completion strings (just the completion part, not the full sentence)."""

        user_prompt = f"""Student's challenges: {', '.join(challenge_texts)}
Student started typing: "{partial_text}"

Generate 2-3 natural ways to complete this sentence. Return ONLY the JSON array of completions."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=100
        )
        
        content = response.choices[0].message.content.strip()
        
        # Parse JSON
        content = content.replace("```json", "").replace("```", "").strip()
        suggestions = json.loads(content)
        
        if not isinstance(suggestions, list):
            suggestions = []
        
        suggestions = suggestions[:3]  # Max 3 suggestions
        
        return jsonify({
            "suggestions": suggestions,
            "count": len(suggestions)
        })
        
    except Exception as e:
        logger.error(f"Error generating text completion: {e}")
        return jsonify({"suggestions": []})
