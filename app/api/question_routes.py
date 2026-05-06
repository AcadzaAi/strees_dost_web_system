"""Stress Dost - Acadza Question Integration Service."""
from __future__ import annotations

import json
import logging
import os
import random
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from flask import Blueprint, jsonify, request
# from flask_caching import Cache  # Temporarily disabled to fix circular import

try:
    import certifi
    _CERTIFI_PATH = certifi.where()
except ImportError:  # pragma: no cover
    _CERTIFI_PATH = None

from ..services.question_mutator import mutate_question
from ..services.question_trigger_decision import (
    get_full_test_plan,
    get_trigger_for_question,
    is_new_user,
)
from ..realtime.scheduler import is_popup_simulation_active

logger = logging.getLogger(__name__)

question_bp = Blueprint("questions", __name__, url_prefix="/api/questions")
# cache = Cache(config={"CACHE_TYPE": "simple"})  # Temporarily disabled

# Paths and API config ------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
ACADZA_API_URL = os.getenv("ACADZA_API_URL", "https://api.acadza.in/question/details")
QUESTIONS_CSV_PATH = os.getenv("QUESTION_IDS_CSV", str(BASE_DIR / "data" / "question_ids.csv"))
CACHE_TIMEOUT = 3600  # 1 hour

def _build_acadza_headers() -> Dict:
    """Build headers from latest env vars to avoid stale auth/course values."""
    course = os.getenv("ACADZA_COURSE", "").strip()
    auth = os.getenv("ACADZA_AUTH", "").strip()
    apikey = os.getenv("ACADZA_API_KEY", "postmanrulz").strip()

    if not course:
        logger.warning("ACADZA_COURSE is not set; defaulting to 'JEE'.")
        course = "JEE"
    if not auth:
        logger.warning("ACADZA_AUTH is not set; requests may return 401.")

    headers: Dict = {
        "Accept": "application/json",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8,hi;q=0.7",
        "Content-Type": "application/json",
        "Origin": "https://www.acadza.com",
        "Referer": "https://www.acadza.com/",
        "Connection": "keep-alive",
        "User-Agent": os.getenv(
            "ACADZA_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        ),
        "api-key": apikey,
        "course": course,
    }
    if auth:
        headers["Authorization"] = auth
    return headers


ACADZA_HEADERS = _build_acadza_headers()


def _local_fallback_questions(count: int = 7) -> List[Dict]:
    """Return deterministic local questions when Acadza questions are unavailable."""
    bank = [
        {
            "question_id": "fallback-1",
            "question_type": "scq",
            "subject": "Mathematics",
            "chapter": "Algebra",
            "difficulty": "Easy",
            "level": "EASY",
            "question_html": "<p>If 2x + 3 = 11, what is x?</p>",
            "question_images": [],
            "options": [
                {"label": "A", "text": "2"},
                {"label": "B", "text": "3"},
                {"label": "C", "text": "4"},
                {"label": "D", "text": "5"},
            ],
            "correct_answer": "C",
            "solution_html": "<p>2x = 8, so x = 4.</p>",
            "solution_images": [],
            "metadata": {"fallback": True},
        },
        {
            "question_id": "fallback-2",
            "question_type": "scq",
            "subject": "Physics",
            "chapter": "Kinematics",
            "difficulty": "Easy",
            "level": "EASY",
            "question_html": "<p>A body starts from rest and accelerates at 2 m/s<sup>2</sup>. Distance covered in 3 s is?</p>",
            "question_images": [],
            "options": [
                {"label": "A", "text": "3 m"},
                {"label": "B", "text": "6 m"},
                {"label": "C", "text": "9 m"},
                {"label": "D", "text": "12 m"},
            ],
            "correct_answer": "C",
            "solution_html": "<p>s = 1/2 at<sup>2</sup> = 1/2 * 2 * 3<sup>2</sup> = 9 m.</p>",
            "solution_images": [],
            "metadata": {"fallback": True},
        },
        {
            "question_id": "fallback-3",
            "question_type": "integer",
            "subject": "Chemistry",
            "chapter": "Mole Concept",
            "difficulty": "Easy",
            "level": "EASY",
            "question_html": "<p>How many atoms are present in 1 mole of a substance? (Enter integer part of coefficient x in x × 10<sup>23</sup>)</p>",
            "question_images": [],
            "integer_answer": 6,
            "solution_html": "<p>Avogadro number is 6.022 × 10<sup>23</sup>.</p>",
            "solution_images": [],
            "metadata": {"fallback": True},
        },
        {
            "question_id": "fallback-4",
            "question_type": "scq",
            "subject": "Mathematics",
            "chapter": "Trigonometry",
            "difficulty": "Medium",
            "level": "MEDIUM",
            "question_html": "<p>sin<sup>2</sup>theta + cos<sup>2</sup>theta equals:</p>",
            "question_images": [],
            "options": [
                {"label": "A", "text": "0"},
                {"label": "B", "text": "1"},
                {"label": "C", "text": "2"},
                {"label": "D", "text": "Depends on theta"},
            ],
            "correct_answer": "B",
            "solution_html": "<p>Identity: sin<sup>2</sup>theta + cos<sup>2</sup>theta = 1.</p>",
            "solution_images": [],
            "metadata": {"fallback": True},
        },
        {
            "question_id": "fallback-5",
            "question_type": "scq",
            "subject": "Physics",
            "chapter": "Units and Dimensions",
            "difficulty": "Easy",
            "level": "EASY",
            "question_html": "<p>The SI unit of force is:</p>",
            "question_images": [],
            "options": [
                {"label": "A", "text": "Joule"},
                {"label": "B", "text": "Watt"},
                {"label": "C", "text": "Newton"},
                {"label": "D", "text": "Pascal"},
            ],
            "correct_answer": "C",
            "solution_html": "<p>Force = mass × acceleration, SI unit is Newton.</p>",
            "solution_images": [],
            "metadata": {"fallback": True},
        },
        {
            "question_id": "fallback-6",
            "question_type": "integer",
            "subject": "Physics",
            "chapter": "Rotational Mechanics",
            "difficulty": "Hard",
            "level": "HARD",
            "question_html": "<p>A solid sphere rolls down an incline of height h without slipping. What is the ratio of its translational kinetic energy to total kinetic energy? (Answer as integer * 7)</p>",
            "question_images": [],
            "integer_answer": 5,
            "solution_html": "<p>Ratio is 5/7. 5/7 * 7 = 5.</p>",
            "solution_images": [],
            "metadata": {"fallback": True},
        },
        {
            "question_id": "fallback-7",
            "question_type": "scq",
            "subject": "Chemistry",
            "chapter": "Thermodynamics",
            "difficulty": "Hard",
            "level": "HARD",
            "question_html": "<p>Which of the following is true for an adiabatic free expansion of an ideal gas?</p>",
            "question_images": [],
            "options": [
                {"label": "A", "text": "Q = W = deltaU = 0"},
                {"label": "B", "text": "Q > 0, W < 0"},
                {"label": "C", "text": "deltaT < 0"},
                {"label": "D", "text": "deltaS = 0"},
            ],
            "correct_answer": "A",
            "solution_html": "<p>For adiabatic free expansion, Q=0, W=0, so deltaU=0.</p>",
            "solution_images": [],
            "metadata": {"fallback": True},
        },
    ]

    # Pick 2 hard and 5 easy/medium
    hard_pool = [q for q in bank if q["difficulty"].lower() == "hard"]
    easy_pool = [q for q in bank if q["difficulty"].lower() != "hard"]
    
    selected_hard = hard_pool[:min(2, len(hard_pool))]
    selected_easy = easy_pool[:min(5, len(easy_pool))]
    picked = selected_hard + selected_easy
    
    if len(picked) < count:
        while len(picked) < count:
            picked.append(random.choice(easy_pool))

    out: List[Dict] = []
    for idx, q in enumerate(picked):
        item = dict(q)
        item["question_index"] = idx + 1
        out.append(item)
    return out


# CSV loader ---------------------------------------------------------------
class QuestionIDLoader:
    """Manages loading and selection of question IDs from CSV."""

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.enriched_csv_path = csv_path.replace(".csv", "_enriched.csv")
        self.question_ids: list[str] = []
        self.enriched_data: list[dict] = []
        self.load_ids()

    def load_ids(self) -> None:
        # Load enriched data if available
        if os.path.exists(self.enriched_csv_path):
            try:
                with open(self.enriched_csv_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    self.enriched_data = list(reader)
                self.question_ids = [r["question_id"] for r in self.enriched_data if r.get("question_id")]
                logger.info("Loaded %s enriched question IDs from %s", len(self.question_ids), self.enriched_csv_path)
                return
            except Exception as exc:
                logger.error("Error loading enriched CSV %s: %s", self.enriched_csv_path, exc)

        # Fallback to normal CSV
        try:
            with open(self.csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                seen: set[str] = set()
                ids: list[str] = []
                for row in reader:
                    qid = (row.get("question_id") or "").strip()
                    if qid and qid not in seen:
                        seen.add(qid)
                        ids.append(qid)
                self.question_ids = ids
            logger.info("Loaded %s question IDs from %s", len(self.question_ids), self.csv_path)
        except FileNotFoundError:
            logger.warning("Question ID CSV not found: %s", self.csv_path)
            self.question_ids = []
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Error loading CSV %s: %s", self.csv_path, exc)
            self.question_ids = []

    def get_random_ids(self, count: int = 20) -> List[str]:
        if len(self.question_ids) <= count:
            return list(self.question_ids)
        return random.sample(self.question_ids, count)

    def get_test_ids(self, subject: str = None, topics: list = None) -> List[str]:
        """Get 7 unique test IDs filtered by subject/topics with graceful fallback.
        
        Priority: topic-matching → same-subject fill → all questions fill.
        Aims for 2 hard + 5 easy/medium but adapts when pools are small.
        """
        TARGET = 7
        if not self.enriched_data:
            return self.get_random_ids(TARGET)

        # ---- Build pools ----
        subject_pool = self.enriched_data  # all questions
        topic_pool: list[dict] = []

        if subject:
            subject_pool = [
                q for q in self.enriched_data
                if (q.get("subject") or "").lower() == subject.lower()
            ]

        if topics and subject_pool:
            topic_lower = [t.lower() for t in topics]
            for q in subject_pool:
                q_topics: set[str] = set()
                if q.get("chapter"):
                    q_topics.add(q["chapter"].lower())
                if q.get("concepts"):
                    q_topics.update(c.lower() for c in q["concepts"].split("|"))
                if q.get("sub_concepts"):
                    q_topics.update(c.lower() for c in q["sub_concepts"].split("|"))
                if any(t in q_topics for t in topic_lower):
                    topic_pool.append(q)

        # ---- Select with dedup ----
        selected: list[dict] = []
        seen_ids: set[str] = set()

        def _add(items: list[dict], count: int) -> None:
            """Add up to `count` unique items from `items` into selected."""
            available = [q for q in items if q["question_id"] not in seen_ids]
            pick = random.sample(available, min(count, len(available)))
            for q in pick:
                selected.append(q)
                seen_ids.add(q["question_id"])

        # Step 1: grab all topic-matching questions (up to TARGET)
        if topic_pool:
            _add(topic_pool, TARGET)
            logger.info("Topic pool gave %d questions", len(selected))

        # Step 2: fill remaining from subject pool
        if len(selected) < TARGET and subject_pool:
            _add(subject_pool, TARGET - len(selected))
            logger.info("Subject pool filled to %d questions", len(selected))

        # Step 3: fill from everything if still short
        if len(selected) < TARGET:
            _add(self.enriched_data, TARGET - len(selected))
            logger.info("Global pool filled to %d questions", len(selected))

        # Shuffle and return IDs
        random.shuffle(selected)
        return [q["question_id"] for q in selected]

    def get_all_ids(self) -> List[str]:
        return self.question_ids

question_loader = QuestionIDLoader(QUESTIONS_CSV_PATH)


# Acadza client ------------------------------------------------------------
class AcadzaQuestionFetcher:
    """Handles communication with Acadza API."""

    def __init__(self, api_url: str, headers: Dict):
        self.api_url = api_url
        self.headers = _build_acadza_headers()
        self.request_timeout = 10
        raw_verify = os.getenv("ACADZA_VERIFY", "true").strip().lower()
        self.verify_ssl = raw_verify not in {"0", "false", "no"}
        self.cert_path = _CERTIFI_PATH if self.verify_ssl and _CERTIFI_PATH else self.verify_ssl

    def fetch_question(self, question_id: str) -> Optional[Dict]:
        try:
            payload = {}
            headers = self.headers.copy()
            headers["questionId"] = question_id

            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.request_timeout,
                verify=self.cert_path,
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get("status") == "error":
                    logger.warning("Acadza API error for %s: %s", question_id, data.get("message"))
                    return None
                if isinstance(data, dict) and data.get("message") == "Auth failed":
                    logger.warning("Acadza API Auth failed for %s", question_id)
                    return None
                
                logger.info("Fetched question: %s", question_id)
                return data

            logger.warning("API returned %s for %s body=%s", response.status_code, question_id, response.text)
            return None

        except requests.Timeout:
            logger.error("Timeout fetching question %s", question_id)
            return None
        except requests.RequestException as exc:
            logger.error("Error fetching question %s: %s", question_id, exc)
            return None
        except json.JSONDecodeError:
            logger.error("Invalid JSON response for question %s", question_id)
            return None

    def fetch_multiple(self, question_ids: List[str]) -> List[Dict]:
        questions: list[Dict] = []
        if not question_ids:
            return questions

        for qid in question_ids:
            data = self.fetch_question(qid)
            if data:
                questions.append(data)
                
        logger.info("Fetched %s/%s questions", len(questions), len(question_ids))
        return questions


acadza_fetcher = AcadzaQuestionFetcher(ACADZA_API_URL, ACADZA_HEADERS)


# Formatter ---------------------------------------------------------------
class QuestionFormatter:
    """Formats raw Acadza question data into frontend-ready format."""

    @staticmethod
    def format_question(raw_data: Dict, question_index: int = 0) -> Dict:
        question_type = raw_data.get("questionType", "scq")
        if question_type == "mcq":
            return QuestionFormatter._format_mcq(raw_data, question_index)
        if question_type == "integerQuestion":
            return QuestionFormatter._format_integer(raw_data, question_index)
        return QuestionFormatter._format_scq(raw_data, question_index)

    @staticmethod
    def _format_scq(raw_data: Dict, idx: int) -> Dict:
        scq_data = raw_data.get("scq", {})
        full_html = scq_data.get("question", "<p>Question not available</p>")
        stem_html, options = QuestionFormatter._split_question_and_options(full_html)
        return {
            "question_id": raw_data.get("_id", "unknown"),
            "question_index": idx + 1,
            "question_type": "scq",
            "subject": raw_data.get("subject", "Unknown"),
            "chapter": raw_data.get("chapter", "Unknown"),
            "difficulty": raw_data.get("difficulty", "Medium"),
            "level": raw_data.get("level", "MEDIUM"),
            # Return stem-only HTML. Options are supplied separately in "options".
            # Sending full_html here causes duplicate option rendering in clients.
            "question_html": stem_html,
            "question_images": scq_data.get("quesImages", []),
            "options": options,
            "correct_answer": scq_data.get("answer", "A"),
            "solution_html": scq_data.get("solution", "<p>Solution not available</p>"),
            "solution_images": scq_data.get("solutionImages", []),
            "metadata": {
                "smart_trick": raw_data.get("smartTrick", False),
                "trap": raw_data.get("trap", False),
                "silly_mistake": raw_data.get("sillyMistake", False),
                "is_lengthy": raw_data.get("isLengthy", 0),
                "is_ncert": raw_data.get("isNCERT", False),
                "tag_subconcepts": QuestionFormatter._extract_subconcepts(raw_data),
            },
        }

    @staticmethod
    def _format_mcq(raw_data: Dict, idx: int) -> Dict:
        mcq_data = raw_data.get("mcq", {})
        question_html = raw_data.get("scq", {}).get("question", "<p>Question not available</p>")
        return {
            "question_id": raw_data.get("_id", "unknown"),
            "question_index": idx + 1,
            "question_type": "mcq",
            "subject": raw_data.get("subject", "Unknown"),
            "chapter": raw_data.get("chapter", "Unknown"),
            "difficulty": raw_data.get("difficulty", "Medium"),
            "level": raw_data.get("level", "MEDIUM"),
            "question_html": question_html,
            "question_images": mcq_data.get("quesImages", []),
            "correct_answers": mcq_data.get("answer", []),
            "solution_html": raw_data.get("scq", {}).get("solution", "<p>Solution not available</p>"),
            "solution_images": mcq_data.get("solutionImages", []),
            "metadata": {
                "smart_trick": raw_data.get("smartTrick", False),
                "trap": raw_data.get("trap", False),
            },
        }

    @staticmethod
    def _format_integer(raw_data: Dict, idx: int) -> Dict:
        int_data = raw_data.get("integerQuestion", {})
        question_html = (
            int_data.get("question")
            or raw_data.get("scq", {}).get("question")
            or "<p>Question not available</p>"
        )
        solution_html = (
            int_data.get("solution")
            or raw_data.get("scq", {}).get("solution")
            or "<p>Solution not available</p>"
        )
        return {
            "question_id": raw_data.get("_id", "unknown"),
            "question_index": idx + 1,
            "question_type": "integer",
            "subject": raw_data.get("subject", "Unknown"),
            "chapter": raw_data.get("chapter", "Unknown"),
            "difficulty": raw_data.get("difficulty", "Medium"),
            "level": raw_data.get("level", "MEDIUM"),
            "question_html": question_html,
            "question_images": int_data.get("quesImages") or raw_data.get("scq", {}).get("quesImages", []),
            "integer_answer": int_data.get("answer"),
            "solution_html": solution_html,
            "solution_images": int_data.get("solutionImages") or raw_data.get("scq", {}).get("solutionImages", []),
            "metadata": {},
        }

    @staticmethod
    def _split_question_and_options(html: str):
        """Split Acadza SCQ HTML into question stem and option list.

        Acadza packs the stem and all four options into one HTML blob, e.g.:
          <h3>Question text...</h3><h3>(A) ... (B) ... (C) ... (D) ...</h3>

        Returns (stem_html, options) where each option keeps its raw HTML
        (MathML, images, etc.) so the frontend can render it properly.
        """
        import re

        if not html:
            return "<p>Question not available</p>", []

        # Find the first (A) marker — everything before it is the stem.
        first_a = re.search(r"\(A\)", html)
        if not first_a:
            # No options embedded — return full HTML as stem
            return html, [
                {"label": "A", "text": "Option A"},
                {"label": "B", "text": "Option B"},
                {"label": "C", "text": "Option C"},
                {"label": "D", "text": "Option D"},
            ]

        stem = html[: first_a.start()].strip()
        options_part = html[first_a.start() :]

        # Split at (A), (B), (C), (D) markers — keep full HTML in each chunk.
        pattern = r"\(([A-D])\)\s*(.*?)(?=\([A-D]\)|$)"
        matches = re.findall(pattern, options_part, re.DOTALL)

        options: list[dict] = []
        for label, content in matches:
            text = content.strip()
            if text:
                options.append({"label": label, "text": text})

        if len(options) < 4:
            options = [
                {"label": "A", "text": "Option A"},
                {"label": "B", "text": "Option B"},
                {"label": "C", "text": "Option C"},
                {"label": "D", "text": "Option D"},
            ]

        # Clean up dangling closing tags in the stem (e.g. unclosed <h3>)
        if stem and not stem.rstrip().endswith(">"):
            stem += "</h3>"

        return stem, options

    @staticmethod
    def _extract_subconcepts(raw_data: Dict) -> List[str]:
        subconcepts: list[str] = []
        for tag in raw_data.get("tagSubConcept", []) or []:
            if isinstance(tag, dict) and "subConcept" in tag:
                subconcepts.append(tag["subConcept"])
        return subconcepts


# Routes -------------------------------------------------------------------
@question_bp.route("/load-test-questions", methods=["GET", "POST"])
def load_test_questions():
    # Do not cache this route: fallback responses should not persist across retries.
    subject = None
    topics = []
    
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        subject = data.get("subject")
        topics = data.get("topics") or []

    question_ids = question_loader.get_test_ids(subject=subject, topics=topics)
    if not question_ids:
        fallback = _local_fallback_questions(count=7)
        return jsonify(
            {
                "status": "success",
                "message": "Using local fallback questions (no question IDs available)",
                "questions": fallback,
                "total_questions": len(fallback),
                "fallback": True,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    raw_questions = acadza_fetcher.fetch_multiple(question_ids)
    if not raw_questions:
        fallback = _local_fallback_questions(count=7)
        return jsonify(
            {
                "status": "success",
                "message": "Using local fallback questions (Acadza returned no data)",
                "questions": fallback,
                "total_questions": len(fallback),
                "fallback": True,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    formatted = [QuestionFormatter.format_question(q, idx) for idx, q in enumerate(raw_questions)]

    return jsonify(
        {
            "status": "success",
            "questions": formatted,
            "total_questions": len(formatted),
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


@question_bp.route("/get-question/<question_id>", methods=["GET"])
# @cache.cached(timeout=CACHE_TIMEOUT, query_string=True)  # Temporarily disabled
def get_single_question(question_id: str):
    raw_question = acadza_fetcher.fetch_question(question_id)
    if not raw_question:
        return (
            jsonify({"status": "error", "message": f"Question {question_id} not found"}),
            404,
        )

    formatted = QuestionFormatter.format_question(raw_question)
    return jsonify({"status": "success", "question": formatted})


@question_bp.route("/prefetch-batch", methods=["POST"])
def prefetch_batch():
    data = request.get_json(force=True, silent=True) or {}
    question_ids = data.get("question_ids") or []
    if not question_ids:
        return (
            jsonify({"status": "error", "message": "No question IDs provided"}),
            400,
        )

    raw_questions = acadza_fetcher.fetch_multiple(question_ids)
    formatted = [QuestionFormatter.format_question(q, idx) for idx, q in enumerate(raw_questions)]
    return jsonify({"status": "success", "questions": formatted, "prefetched_count": len(formatted)})


@question_bp.route("/stats", methods=["GET"])
def get_stats():
    return jsonify(
        {
            "total_questions_available": len(question_loader.question_ids),
            "csv_path": QUESTIONS_CSV_PATH,
            "sample_ids": question_loader.get_random_ids(5),
        }
    )


@question_bp.route("/trigger-plan", methods=["POST"])
def get_trigger_plan():
    """Generate trigger plan for Focus Zones test.
    
    Request body:
    {
        "user_profile": {
            "name": "John",  // Empty if new user
            "test_count": 0,  // 0 for new user
            "last_test_date": "2026-05-01",
            "previous_triggers": ["SPOTLIGHT_HUNT", "HARD_FOG", ...]  // From last test
        }
    }
    
    Response:
    {
        "status": "success",
        "is_new_user": true,
        "total_questions": 7,
        "medium_count": 5,
        "hard_count": 2,
        "sequence": [
            {
                "question_number": 1,
                "trigger_name": "SPOTLIGHT_HUNT",
                "difficulty": "medium",
                "intensity": "mild",
                "description": "...",
                "is_hard": false,
                "is_meta_question": false
            },
            ...
        ],
        "medium_questions": [...],  // 5 medium trigger configs
        "hard_questions": [...]     // 2 hard trigger configs
    }
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
        user_profile = body.get("user_profile") or {}
        
        # Extract previous triggers if available
        previous_triggers = user_profile.get("previous_triggers")
        
        # Generate test plan
        plan = get_full_test_plan(user_profile, previous_triggers)
        
        logger.info(
            "trigger_plan: user_type=%s medium=%d hard=%d",
            plan["user_type"],
            plan["medium_count"],
            plan["hard_count"],
        )
        
        return jsonify({
            "status": "success",
            **plan,
        })
    
    except Exception as exc:
        logger.exception("trigger_plan failed: %s", exc)
        return jsonify({
            "status": "error",
            "message": "Failed to generate trigger plan",
            "detail": str(exc),
        }), 500


@question_bp.route("/trigger/<int:question_number>", methods=["POST"])
def get_question_trigger(question_number: int):
    """Get trigger for a specific question number.
    
    Request body:
    {
        "user_profile": {
            "name": "John",
            "test_count": 0,
            "previous_triggers": [...]
        }
    }
    
    Response:
    {
        "status": "success",
        "question_number": 1,
        "trigger_name": "SPOTLIGHT_HUNT",
        "difficulty": "medium",
        "intensity": "mild",
        "description": "...",
        "is_hard": false,
        "is_meta_question": false
    }
    """
    try:
        if not 1 <= question_number <= 7:
            return jsonify({
                "status": "error",
                "message": "Invalid question_number. Must be 1-7.",
            }), 400
        
        body = request.get_json(force=True, silent=True) or {}
        user_profile = body.get("user_profile") or {}
        previous_triggers = user_profile.get("previous_triggers")
        
        trigger_config = get_trigger_for_question(
            question_number,
            user_profile,
            previous_triggers,
        )
        
        logger.info(
            "question_trigger: q=%d trigger=%s difficulty=%s",
            question_number,
            trigger_config["trigger_name"],
            trigger_config["difficulty"],
        )
        
        return jsonify({
            "status": "success",
            **trigger_config,
        })
    
    except ValueError as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
        }), 400
    
    except Exception as exc:
        logger.exception("question_trigger failed: %s", exc)
        return jsonify({
            "status": "error",
            "message": "Failed to get trigger",
            "detail": str(exc),
        }), 500


@question_bp.route("/check-user-type", methods=["POST"])
def check_user_type():
    """Check if user is new or returning.
    
    Request body:
    {
        "user_profile": {
            "name": "John",
            "test_count": 0
        }
    }
    
    Response:
    {
        "status": "success",
        "is_new_user": true,
        "should_ask_name": true,
        "message": "New user detected"
    }
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
        user_profile = body.get("user_profile") or {}
        
        new_user = is_new_user(user_profile)
        
        return jsonify({
            "status": "success",
            "is_new_user": new_user,
            "should_ask_name": new_user,
            "message": "New user detected" if new_user else "Returning user detected",
        })
    
    except Exception as exc:
        logger.exception("check_user_type failed: %s", exc)
        return jsonify({
            "status": "error",
            "message": "Failed to check user type",
            "detail": str(exc),
        }), 500


@question_bp.route("/mutate/<question_id>", methods=["POST"])
def mutate(question_id: str):
    """Mutate a question (scq/integer) by changing numeric values and answers."""
    body = request.get_json(force=True, silent=True) or {}
    session_id = str(body.get("session_id") or "").strip()
    if is_popup_simulation_active(session_id or None):
        logger.info(
            "mutate_endpoint skipped question_id=%s reason=popup_simulation_active session_id=%s",
            question_id,
            session_id or "*",
        )
        return jsonify(
            {
                "status": "success",
                "mutated": False,
                "skipped": True,
                "reason": "popup_simulation_active",
            }
        )

    raw_question = acadza_fetcher.fetch_question(question_id)
    if not raw_question:
        return (
            jsonify({"status": "error", "message": f"Question {question_id} not found"}),
            404,
        )

    formatted = QuestionFormatter.format_question(raw_question)
    if formatted.get("question_type") not in {"scq", "integer"}:
        return jsonify({"status": "error", "message": "Only scq/integer supported"}), 400

    mutated, changed = mutate_question(formatted)
    logger.info("mutate_endpoint question_id=%s mutated=%s", question_id, changed)
    return jsonify(
        {
            "status": "success",
            "mutated": changed,
            "question": mutated,
        }
    )


# Integration --------------------------------------------------------------
def init_question_service(app) -> None:
    # cache.init_app(app)  # Temporarily disabled to fix import issues
    app.register_blueprint(question_bp)
    logger.info("Question service initialized")


__all__ = ["init_question_service"]
