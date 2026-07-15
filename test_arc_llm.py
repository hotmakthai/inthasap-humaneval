"""test_arc_llm.py — unit tests for LLM candidate generation (P5)"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from arc_generator import Candidate
from arc_llm import _extract_json, _extract_python, _parse_candidate, llm_solve, PythonCandidate, _cell_fitness, _build_diff_feedback, _build_perception_hints, get_telemetry, reset_telemetry


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


class TestCellFitness(unittest.TestCase):
    def _make_task(self):
        return {
            "train": [
                {"input": [[1, 0], [0, 1]], "output": [[2, 0], [0, 2]]},
                {"input": [[0, 1], [1, 0]], "output": [[0, 2], [2, 0]]},
            ],
            "test": [{"input": [[1, 0], [0, 1]], "output": [[2, 0], [0, 2]]}],
        }

    def test_cell_fitness_perfect(self):
        cand = PythonCandidate("def transform(grid):\n    return [[2 if c == 1 else c for c in row] for row in grid]")
        score, details = _cell_fitness(cand, self._make_task()["train"])
        self.assertEqual(score, 1.0)
        self.assertEqual(len(details), 2)

    def test_cell_fitness_partial(self):
        # Wrong: returns input unchanged (0% correct on output cells that should change)
        cand = PythonCandidate("def transform(grid):\n    return [row[:] for row in grid]")
        score, details = _cell_fitness(cand, self._make_task()["train"])
        self.assertLess(score, 1.0)
        self.assertGreater(score, 0.0)

    def test_build_diff_feedback(self):
        cand = PythonCandidate("def transform(grid):\n    return [row[:] for row in grid]")
        _, details = _cell_fitness(cand, self._make_task()["train"])
        feedback = _build_diff_feedback(self._make_task(), details)
        self.assertIn("cells correct", feedback)
        self.assertIn("X", feedback)

    def test_perception_hints(self):
        hints = _build_perception_hints(self._make_task())
        self.assertIsInstance(hints, str)
        # Should contain some perception facts about the task
        self.assertTrue(len(hints) > 0)


class TestTelemetry(unittest.TestCase):
    def test_telemetry_reset_and_get(self):
        reset_telemetry()
        t = get_telemetry()
        self.assertEqual(t["llm_calls"], 0)
        self.assertEqual(t["total_cost_usd"], 0.0)
        self.assertEqual(t["calls_by_tier"], {})


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
        candidate, note, telem = llm_solve(task, max_attempts=2)
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
        candidate, note, telem = llm_solve(task, max_attempts=2)
        self.assertIsNotNone(candidate)
        self.assertIsInstance(candidate, Candidate)
        self.assertIn("deepseek", note)


    @patch("core.llm.call_tier")
    def test_llm_solve_evolutionary_perfect(self, mock_call_tier):
        deepseek_code = (
            "def transform(grid):\n"
            "    return [[2 if c == 1 else c for c in row] for row in grid]\n"
        )
        deepseek_response = f"```python\n{deepseek_code}```"

        mock_call_tier.side_effect = lambda tier, *a, **kw: (deepseek_response, "deepseek", "ok")

        task = self._make_task()
        candidate, note, telem = llm_solve(task, max_attempts=2, evolutionary=True)
        self.assertIsNotNone(candidate)
        self.assertIsInstance(candidate, PythonCandidate)
        self.assertIn("evolutionary", note)


class TestTelemetryPerTask(unittest.TestCase):
    """R4-T0: Verify telemetry is per-task, not cumulative across tasks."""

    def _make_task(self):
        return {
            "train": [
                {"input": [[1, 0], [0, 1]], "output": [[2, 0], [0, 2]]},
                {"input": [[1, 1], [0, 0]], "output": [[2, 2], [0, 0]]},
            ],
            "test": [{"input": [[1, 0], [1, 1]], "output": [[2, 0], [2, 2]]}],
        }

    @patch("core.llm.call_tier")
    def test_telemetry_reset_between_tasks(self, mock_call_tier):
        """llm_calls must reset between tasks — no cumulative leakage."""
        deepseek_code = (
            "def transform(grid):\n"
            "    return [[2 if c == 1 else c for c in row] for row in grid]\n"
        )
        deepseek_response = f"```python\n{deepseek_code}```"
        mock_call_tier.side_effect = lambda tier, *a, **kw: (deepseek_response, "deepseek", "ok")

        reset_telemetry()
        task = self._make_task()

        # Task 1
        _, _, t1 = llm_solve(task, max_attempts=2, evolutionary=True)
        calls1 = t1.get("llm_calls", 0)

        # Task 2 — should NOT include calls from task 1
        reset_telemetry()
        _, _, t2 = llm_solve(task, max_attempts=2, evolutionary=True)
        calls2 = t2.get("llm_calls", 0)

        self.assertGreater(calls1, 0, "Task 1 should have calls")
        self.assertGreater(calls2, 0, "Task 2 should have calls")
        self.assertEqual(calls2, calls1,
                         f"Per-task calls should match for identical tasks. "
                         f"Got calls1={calls1}, calls2={calls2} — telemetry leaked!")

    @patch("core.llm.call_tier")
    def test_non_evo_telemetry_per_task(self, mock_call_tier):
        """Non-evolutionary path must return per-task llm_calls, not global cumulative."""
        deepseek_code = (
            "def transform(grid):\n"
            "    return [[2 if c == 1 else c for c in row] for row in grid]\n"
        )
        deepseek_response = f"```python\n{deepseek_code}```"
        mock_call_tier.side_effect = lambda tier, *a, **kw: (deepseek_response, "deepseek", "ok")

        reset_telemetry()
        task = self._make_task()

        # Non-evolutionary path
        _, _, t1 = llm_solve(task, max_attempts=2, evolutionary=False)
        calls1 = t1.get("llm_calls", 0)

        # Second call — should not accumulate
        reset_telemetry()
        _, _, t2 = llm_solve(task, max_attempts=2, evolutionary=False)
        calls2 = t2.get("llm_calls", 0)

        self.assertGreater(calls1, 0, "Non-evo task 1 should have calls")
        self.assertGreater(calls2, 0, "Non-evo task 2 should have calls")
        self.assertEqual(calls2, calls1,
                         f"Non-evo per-task calls should match. "
                         f"Got calls1={calls1}, calls2={calls2} — cumulative bug!")

    @patch("core.llm.call_tier")
    def test_non_evo_telemetry_has_global_fields(self, mock_call_tier):
        """Non-evo path should include total_cost_usd and tokens from global telemetry."""
        deepseek_code = (
            "def transform(grid):\n"
            "    return [[2 if c == 1 else c for c in row] for row in grid]\n"
        )
        deepseek_response = f"```python\n{deepseek_code}```"
        mock_call_tier.side_effect = lambda tier, *a, **kw: (deepseek_response, "deepseek", "ok")

        reset_telemetry()
        task = self._make_task()
        _, _, t = llm_solve(task, max_attempts=2, evolutionary=False)

        self.assertIn("total_cost_usd", t, "Non-evo telemetry should have total_cost_usd")
        self.assertIn("total_input_tokens", t, "Non-evo telemetry should have total_input_tokens")
        self.assertIn("total_output_tokens", t, "Non-evo telemetry should have total_output_tokens")
        self.assertIn("had_perception_hints", t, "Non-evo telemetry should have had_perception_hints")


if __name__ == "__main__":
    unittest.main()
