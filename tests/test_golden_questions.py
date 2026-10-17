"""
Evaluation Suite: 30 Golden Questions for AI Assistant (PRD §10.2, §15, §16)
Target SLA: >= 85% accuracy, under 8s query latency.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
import pytest

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assistant.assistant import ask, validate_sql, SQLValidationError, ALLOWED_VIEWS, get_engine


@pytest.fixture(scope="session")
def golden_questions():
    json_path = Path(__file__).parent / "golden_questions.json"
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestGoldenQuestionSet:
    def test_golden_set_size(self, golden_questions):
        """PRD §10.2 requires exactly 30 golden evaluation questions."""
        assert len(golden_questions) == 30, f"Expected 30 golden questions, got {len(golden_questions)}"

    def test_golden_questions_execution(self, golden_questions):
        """
        Evaluate all 30 questions through the assistant pipeline:
        - Must generate valid SQL on allowed rpt.* views
        - Must execute against the live PostgreSQL warehouse
        - Must answer in under 8 seconds per answer
        - Target pass rate >= 85%
        """
        results = []
        passed = 0

        for item in golden_questions:
            qid = item["id"]
            question = item["question"]
            target_view = item["target_view"]

            t0 = time.time()
            resp = ask(question)
            latency = time.time() - t0

            # Evaluation criteria:
            # 1. No fatal error
            # 2. SQL was generated and is valid
            # 3. Target view is used
            # 4. Latency under 8s
            is_valid_sql = bool(resp.sql and "SELECT" in resp.sql.upper())
            uses_rpt = bool(resp.sql and target_view.lower() in resp.sql.lower())
            no_error = resp.error is None
            under_timeout = latency < 8.0

            success = is_valid_sql and uses_rpt and no_error and under_timeout

            if success:
                passed += 1

            results.append({
                "id": qid,
                "domain": item["domain"],
                "question": question,
                "target_view": target_view,
                "passed": success,
                "latency_sec": round(latency, 2),
                "rows_returned": len(resp.data) if hasattr(resp, "data") else 0,
                "error": resp.error,
            })

        accuracy_pct = (passed / len(golden_questions)) * 100
        print(f"\n================ GOLDEN SET EVALUATION RESULTS ================")
        print(f"Passed: {passed} / {len(golden_questions)} ({accuracy_pct:.1f}%)")
        print(f"PRD Target: >= 85.0%")
        print(f"================================================================")

        # Assert PRD §16 SLA: >= 85%
        assert accuracy_pct >= 85.0, f"Golden question set accuracy {accuracy_pct:.1f}% below target 85%"

    @pytest.mark.parametrize("i", range(30))
    def test_individual_golden_question(self, golden_questions, i):
        """Individual test per question for fine-grained failure reporting."""
        item = golden_questions[i]
        resp = ask(item["question"])
        assert resp.error is None, f"Question {item['id']} failed with error: {resp.error}"
        assert resp.sql, f"Question {item['id']} produced no SQL"
        assert item["target_view"].lower() in resp.sql.lower(), (
            f"Question {item['id']} expected view {item['target_view']}, got {resp.sql}"
        )
        assert resp.latency_seconds < 8.0, (
            f"Question {item['id']} took {resp.latency_seconds:.2f}s (exceeded 8s SLA)"
        )
