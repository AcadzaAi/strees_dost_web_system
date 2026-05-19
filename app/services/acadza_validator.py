"""Acadza API integration for subject and topic validation."""
from __future__ import annotations

import json
import logging
import os
import requests
from typing import Dict, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Acadza API configuration
ACADZA_API_URL = os.getenv("ACADZA_API_URL", "https://api.acadza.in/question/details")
ALLOWED_SUBJECTS = {"physics", "chemistry", "mathematics"}

def _build_acadza_headers() -> Dict[str, str]:
    """Build headers from latest env vars to avoid stale auth/course values."""
    headers = {
        "Content-Type": "application/json",
    }
    
    # Add auth headers if available
    auth_token = os.getenv("ACADZA_AUTH_TOKEN") or os.getenv("ACADZA_AUTH")
    if auth_token:
        token = auth_token.strip()
        if token.lower().startswith("bearer "):
            headers["Authorization"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"

    course_id = os.getenv("ACADZA_COURSE_ID") or os.getenv("ACADZA_COURSE")
    if course_id:
        headers["X-Course-ID"] = course_id

    api_key = os.getenv("ACADZA_API_KEY")
    if api_key:
        # Try common API key header variants when the exact header name is unknown.
        headers["x-api-key"] = api_key
        headers["X-API-KEY"] = api_key
        headers["api-key"] = api_key
    
    return headers

class AcadzaQuestionFetcher:
    """Handles communication with Acadza API."""
    
    def __init__(self):
        self.request_timeout = 10
        raw_verify = os.getenv("ACADZA_VERIFY", "true").strip().lower()
        self.verify_ssl = raw_verify not in {"0", "false", "no"}
        
        # Try to use certifi if available
        try:
            import certifi
            self.cert_path = certifi.where()
        except ImportError:
            self.cert_path = self.verify_ssl

    def fetch_question(self, question_id: str) -> Optional[Dict]:
        try:
            payload = {}
            headers = _build_acadza_headers()
            headers["questionId"] = question_id

            response = requests.post(
                ACADZA_API_URL,
                json=payload,
                headers=headers,
                timeout=self.request_timeout,
                verify=self.cert_path,
            )

            if response.status_code == 200:
                logger.info("Fetched question: %s", question_id)
                return response.json()

            logger.warning("API returned %s for %s body=%s", response.status_code, question_id, response.text)
            return None

        except requests.Timeout:
            logger.error("Timeout fetching question %s", question_id)
            return None
        except requests.RequestException as exc:
            logger.error("Error fetching question %s: %s", question_id, exc)
            return None
        except Exception as exc:
            logger.error("Unexpected error fetching question %s: %s", question_id, exc)
            return None

    def fetch_multiple(self, question_ids: List[str]) -> List[Dict]:
        questions: list[Dict] = []
        if not question_ids:
            return questions

        max_workers = min(6, len(question_ids))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_qid = {executor.submit(self.fetch_question, qid): qid for qid in question_ids}
            for future in as_completed(future_to_qid):
                data = future.result()
                if data:
                    questions.append(data)
        logger.info("Fetched %s/%s questions", len(questions), len(question_ids))
        return questions



acadza_fetcher = AcadzaQuestionFetcher()

class AcadzaValidator:
    """Validates subjects and chapters against Acadza question database."""
    
    def __init__(self):
        self._available_subjects: Set[str] = set()
        self._available_chapters: Dict[str, Set[str]] = {}
        self._available_concepts: Dict[str, Set[str]] = {}
        self._available_subconcepts: Dict[str, Set[str]] = {}
        self._initialized = False
    
    def _initialize_from_acadza(self) -> None:
        """Fetch sample questions from Acadza to build subject/topic catalog."""
        if self._initialized:
            return
            
        try:
            logger.info("Initializing Acadza validator from sample questions")
            
            # Get a sample of question IDs to understand available subjects/topics
            from ..api.question_routes import question_loader
            sample_ids = question_loader.get_random_ids(count=50)
            
            if sample_ids:
                questions = acadza_fetcher.fetch_multiple(sample_ids)
                self._build_catalog_from_questions(questions)
            
            self._initialized = True
            logger.info("Acadza validator initialized with %d subjects", len(self._available_subjects))
            
        except Exception as exc:
            logger.warning("Failed to initialize Acadza validator: %s", exc)
            self._initialized = True
    
    def _build_catalog_from_questions(self, questions: List[Dict]) -> None:
        """Build subject and chapter/concept catalog from Acadza questions."""
        for question in questions:
            subject = question.get("subject", "").strip()
            chapter = question.get("chapter", "").strip()
            
            if not subject:
                continue

            subject_key = subject.lower()
            if subject_key not in ALLOWED_SUBJECTS:
                continue

            self._available_subjects.add(subject_key)

            if chapter:
                self._available_chapters.setdefault(subject_key, set()).add(chapter.lower())

            concepts = self._extract_concepts(question)
            if concepts:
                bucket = self._available_concepts.setdefault(subject_key, set())
                for item in concepts:
                    bucket.add(item.lower())

            subconcepts = self._extract_subconcepts(question)
            if subconcepts:
                bucket = self._available_subconcepts.setdefault(subject_key, set())
                for item in subconcepts:
                    bucket.add(item.lower())

    def _extract_tag_values(self, question: Dict, keys: List[str], value_keys: List[str]) -> List[str]:
        out: list[str] = []
        for key in keys:
            raw = question.get(key, []) or []
            if isinstance(raw, dict):
                raw = [raw]
            if not isinstance(raw, list):
                continue
            for tag in raw:
                if isinstance(tag, str):
                    val = tag.strip()
                    if val:
                        out.append(val)
                    continue
                if isinstance(tag, dict):
                    for value_key in value_keys:
                        val = tag.get(value_key)
                        if isinstance(val, str) and val.strip():
                            out.append(val.strip())
        return out

    def _extract_concepts(self, question: Dict) -> List[str]:
        keys = ["tagConcept", "tagConcepts", "tag_concept", "tag_concepts", "concepts"]
        value_keys = ["concept", "conceptName", "name", "title"]
        return self._extract_tag_values(question, keys, value_keys)

    def _extract_subconcepts(self, question: Dict) -> List[str]:
        keys = ["tagSubConcept", "tagSubConcepts", "tag_subconcepts", "subConcepts", "subConcept"]
        value_keys = ["subConcept", "subconcept", "subConceptName", "name", "title"]
        return self._extract_tag_values(question, keys, value_keys)
    
    def is_subject_available(self, subject: str) -> bool:
        """Check if subject is available in Acadza catalog."""
        self._initialize_from_acadza()
        return subject.lower() in self._available_subjects
    
    def get_available_chapters(self, subject: str) -> List[str]:
        """Get available chapters for a subject."""
        self._initialize_from_acadza()
        return list(self._available_chapters.get(subject.lower(), []))

    def get_available_concepts(self, subject: str) -> List[str]:
        """Get available concepts for a subject."""
        self._initialize_from_acadza()
        return list(self._available_concepts.get(subject.lower(), []))

    def get_available_subconcepts(self, subject: str) -> List[str]:
        """Get available subconcepts for a subject."""
        self._initialize_from_acadza()
        return list(self._available_subconcepts.get(subject.lower(), []))

    def get_available_topics(self, subject: str) -> List[str]:
        """Back-compat alias for chapters."""
        return self.get_available_chapters(subject)
    
    def validate_chapter(self, subject: str, chapter: str) -> bool:
        """Check if a specific chapter is available for a subject."""
        self._initialize_from_acadza()
        subject_chapters = self._available_chapters.get(subject.lower(), set())
        return chapter.lower() in subject_chapters

    def validate_topic(self, subject: str, topic: str) -> bool:
        """Back-compat alias for chapter validation."""
        return self.validate_chapter(subject, topic)
    
    def get_subject_suggestions(self, partial_subject: str) -> List[str]:
        """Get subject suggestions for partial input."""
        self._initialize_from_acadza()
        partial = partial_subject.lower()
        suggestions = [
            subject.title() for subject in self._available_subjects
            if subject.startswith(partial)
        ]
        return suggestions[:5]  # Limit to top 5 suggestions
    
    def get_chapter_suggestions(self, subject: str, partial_chapter: str) -> List[str]:
        """Get chapter suggestions for a subject."""
        self._initialize_from_acadza()
        subject_chapters = self._available_chapters.get(subject.lower(), set())
        partial = partial_chapter.lower()
        suggestions = [
            chapter.title() for chapter in subject_chapters
            if chapter.startswith(partial)
        ]
        return suggestions[:5]  # Limit to top 5 suggestions

    def get_topic_suggestions(self, subject: str, partial_topic: str) -> List[str]:
        """Back-compat alias for chapter suggestions."""
        return self.get_chapter_suggestions(subject, partial_topic)

# Global validator instance
acadza_validator = AcadzaValidator()

__all__ = [
    "AcadzaValidator", 
    "acadza_validator"
]
