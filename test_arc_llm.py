"""test_arc_llm.py — unit tests for LLM candidate generation (P5)"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from arc_generator import Candidate
from arc_llm import _extract_json, _extract_python, _parse_candidate, llm_solve, PythonCandidate


class TestLLMHelpers(unittest.TestCase):
    def test_extract_json_from_code_fence(self):
        text = '```json\n{"steps": [{"name": "recolor", "params": {"color_map": {"1": 2}}}]}\n```'
        self.assertEqual(
            _extract_json(text),
            {"steps": [{"name": "recolor", "params": {"color_map": {"1": 2}}}]},
        )

    def test_extract_json_raw(self):
        text = '{"steps": [{"name": "rotate_90", "params": {}}]}'
        self.assertEqual(_extract_json(text), {"steps": [{"name": "rotate_90", "params": {}}]})

    def test_parse_candidate_valid(self):
        data = {"steps": [{"name": "recolor", "params": {"color_map": {1: 2}}}]}
        cand = _parse_candidate(data)
        self.assertIsInstance(cand, Candidate)
        self.assertEqual(cand.steps[0]["name"], "recolor")

    def test_parse_candidate_invalid_name(self):
        data = {"steps": [{"name": "not_a_rule", "params": {}}]}
        self.assertIsNone(_parse_candidate(data))


class TestLLMSolve(unittest.TestCase):
    def _make_task(self):
        # A simple task: input is two color 1 cells, output is two color 2 cells.
        return {
            "train": [
                {"input": [[1, 0], [0, 1]], "output": [[2, 0], [0, 2]]},
                {"input": [[0, 1], [1, 0]], "output": [[0, 2], [2, 0]]},
            ],
            "test": [{"input": [[1, 0], [0, 1]], "output": [[2, 0], [0, 2]]}],
        }

    @patch("core.llm.call_tier")
    def test_llm_solve_returns_correct_python_candidate(self, mock_call_tier):
        # Mock DeepSeek to return a Python function that recolors 1->2.
        deepseek_code = (
            "def transform(grid):\n"
            "    return [[2 if c == 1 else c for c in row] for row in grid]\n"
        )
        deepseek_response = f"```python\n{deepseek_code}```"

        def side_effect(tier, *args, **kwargs):
            if tier == "deepseek":
                return deepseek_response, "deepseek", "ok"
            raise AssertionError(f"Unexpected tier {tier}")

        mock_call_tier.side_effect = side_effect

        task = self._make_task()
        candidate, note = llm_solve(task, max_attempts=2)
        self.assertIsNotNone(candidate)
        self.assertIsInstance(candidate, PythonCandidate)
        self.assertIn("deepseek", note)

    @patch("core.llm.call_tier")
    def test_llm_solve_returns_correct_dsl_candidate(self, mock_call_tier):
        # Mock DeepSeek to return a JSON DSL candidate (legacy fallback).
        deepseek_response = {
            "steps": [{"name": "recolor", "params": {"color_map": {"1": 2}}}]
        }

        def side_effect(tier, *args, **kwargs):
            if tier == "deepseek":
                return json.dumps(deepseek_response, ensure_ascii=False), "deepseek", "ok"
            raise AssertionError(f"Unexpected tier {tier}")

        mock_call_tier.side_effect = side_effect

        task = self._make_task()
        candidate, note = llm_solve(task, max_attempts=2)
        self.assertIsNotNone(candidate)
        self.assertIsInstance(candidate, Candidate)
        self.assertIn("deepseek", note)


if __name__ == "__main__":
    unittest.main()
