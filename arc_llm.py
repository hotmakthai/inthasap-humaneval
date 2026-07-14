"""arc_llm.py — LLM-based candidate generator for ARC-AGI (P5b / Path A)

Strategy (Path A — Free Python):
1. DeepSeek writes a Python `def transform(grid)` function.
2. Function is executed in a restricted namespace (no imports, safe builtins, 5s timeout).
3. Deterministic verifier checks output against all train examples.
4. GLM critiques failures; DeepSeek retries with critique (max 2 attempts).
5. Gemini/Claude as fallback verifiers.
6. The returned candidate is a `PythonCandidate` (callable, compatible with verify/rank).
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from arc_diff import analyze_diff
from arc_dsl import RULES  # kept for backward compat with old tests
from arc_generator import Candidate  # kept for backward compat
from arc_verifier import verify, grids_equal
from arc_viewer import grid_to_str

# Avoid importing the heavy `core.llm` at import time; load it lazily.
_LLM = None


def _llm():
    global _LLM
    if _LLM is None:
        import core.llm as _LLM
    return _LLM


# ── Safe execution namespace ──
_SAFE_BUILTINS = {
    'range': range, 'len': len, 'int': int, 'str': str, 'list': list,
    'tuple': tuple, 'dict': dict, 'set': set, 'frozenset': frozenset,
    'sorted': sorted, 'enumerate': enumerate, 'zip': zip, 'map': map,
    'filter': filter, 'sum': sum, 'min': min, 'max': max, 'abs': abs,
    'any': any, 'all': all, 'reversed': reversed, 'round': round,
    'isinstance': isinstance, 'type': type, 'bool': bool, 'float': float,
    'repr': repr, 'print': print, 'ord': ord, 'chr': chr,
    'divmod': divmod, 'pow': pow,
    'True': True, 'False': False, 'None': None,
    'ValueError': ValueError, 'IndexError': IndexError, 'KeyError': KeyError,
    'TypeError': TypeError, 'Exception': Exception,
}


class PythonCandidate:
    """Wraps a Python transform function — callable like a Candidate."""

    def __init__(self, code: str, func_name: str = "transform"):
        self.code = code
        self.func_name = func_name
        self.score: float | None = None

    def __call__(self, grid: list[list[int]]) -> list[list[int]]:
        return _exec_transform(self.code, grid, self.func_name)

    def __repr__(self) -> str:
        first_line = self.code.strip().split("\n")[0][:60]
        return f"py:{first_line}"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PythonCandidate) and self.code == other.code

    def __hash__(self) -> int:
        return hash(self.code)

    @property
    def complexity(self) -> float:
        return len(self.code) / 50.0


def _exec_transform(code: str, grid: list[list[int]], func_name: str = "transform",
                     timeout: float = 5.0) -> list[list[int]]:
    """Execute LLM-generated Python code safely with timeout."""
    result: list[Any] = [None]
    exc: list[Exception | None] = [None]

    def _run() -> None:
        try:
            ns: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
            exec(code, ns)  # noqa: S102
            func = ns.get(func_name)
            if not callable(func):
                raise ValueError(f"function '{func_name}' not found in code")
            result[0] = func([row[:] for row in grid])
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        raise TimeoutError(f"execution exceeded {timeout}s")
    if exc[0] is not None:
        raise exc[0]
    out = result[0]
    if not isinstance(out, list) or not all(isinstance(r, list) for r in out):
        raise TypeError("transform must return list[list[int]]")
    return out


def _grid_to_text(grid: list[list[int]]) -> str:
    return "\n".join(" ".join(str(c) for c in row) for row in grid)


def _build_prompt(task: dict, attempt: int, history: str = "") -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the generator LLM."""
    system = (
        "You are an ARC-AGI puzzle solver. "
        "You write a Python function `def transform(grid)` that maps every input grid to its output grid.\n\n"
        "Rules:\n"
        "- grid is a list of lists of integers (0-9 representing colors).\n"
        "- Your function must return a list of lists of integers (the output grid).\n"
        "- You may define helper functions, but `transform` must be the main entry point.\n"
        "- Only use basic Python: no imports, no file I/O, no external libraries.\n"
        "- Available builtins: range, len, int, str, list, tuple, dict, set, sorted,\n"
        "  enumerate, zip, map, filter, sum, min, max, abs, any, all, reversed, round,\n"
        "  isinstance, type, bool, float, repr, ord, chr, divmod, pow.\n"
        "- The function must work for ALL training examples, not just the first one.\n"
        "- Return ONLY the Python code in a ```python code block. No explanation.\n"
    )

    examples = task.get("train", [])
    example_text = []
    for i, ex in enumerate(examples):
        example_text.append(f"Example {i + 1}:")
        example_text.append("Input:")
        example_text.append(_grid_to_text(ex["input"]))
        example_text.append("Output:")
        example_text.append(_grid_to_text(ex["output"]))
        example_text.append("")

    diff = analyze_diff(task)
    diff_text = (
        f"Diff summary:\n"
        f"- size_relation: {diff.size_relation}\n"
        f"- color_map: {diff.color_map}\n"
        f"- bg_color_in: {diff.bg_color_in}\n"
        f"- bg_color_out: {diff.bg_color_out}\n"
    )

    user = (
        "\n".join(example_text)
        + "\n"
        + diff_text
        + "\n"
    )
    if attempt > 1 and history:
        user += (
            f"Previous attempt {attempt - 1} failed. Critique:\n{history}\n"
            "Fix the function and return only the Python code.\n"
        )
    user += "Return only the Python code in a ```python block."

    return system, user


def _extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from the LLM response. (legacy DSL path)"""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _extract_python(text: str) -> str | None:
    """Extract Python code from LLM response."""
    # Try ```python code fence first.
    m = re.search(r"```(?:python)?\s*\n([\s\S]*?)```", text)
    if m:
        code = m.group(1).strip()
        if "def transform" in code:
            return code
    # Try to find `def transform` directly in the text.
    m = re.search(r"(def\s+transform\s*\([\s\S]*?)$", text)
    if m:
        return m.group(1).strip()
    return None


def _to_int(value: Any) -> Any:
    """Convert string-of-digits to int recursively; leave others unchanged."""
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    if isinstance(value, dict):
        return {_to_int(k): _to_int(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_int(v) for v in value]
    return value


def _parse_candidate(data: dict) -> Candidate | None:
    """Parse a JSON dict into a Candidate. (legacy DSL path)"""
    if not isinstance(data, dict):
        return None
    steps = data.get("steps")
    if steps is None:
        return None
    if isinstance(steps, dict):
        steps = [steps]
    if not isinstance(steps, list):
        return None

    valid_steps: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            return None
        name = step.get("name")
        params = step.get("params", {})
        if name not in RULES:
            return None
        if not isinstance(params, dict):
            return None

        converted = _to_int(params)
        if "color_map" in converted and isinstance(converted["color_map"], dict):
            converted["color_map"] = {
                int(k) if str(k).lstrip("-").isdigit() else k: int(v) if str(v).lstrip("-").isdigit() else v
                for k, v in converted["color_map"].items()
            }

        valid_steps.append({"name": name, "params": converted})

    if not valid_steps:
        return None
    return Candidate(steps=valid_steps)


def _call_llm(
    tier: str,
    system: str,
    user: str,
    max_tokens: int = 4000,
    no_fallback: bool = False,
) -> tuple[str, str]:
    """Call an LLM tier and return (response_text, usage_note)."""
    llm = _llm()
    text, model, note = llm.call_tier(
        tier,
        system_prompt=system,
        user_prompt=user,
        max_tokens=max_tokens,
        no_fallback=no_fallback,
    )
    return text, f"{model} {note}".strip()


def _critique_candidate(candidate, task: dict, attempt: int) -> str | None:
    """Ask GLM to verify and critique a candidate. Returns critique or None if it accepts."""
    ok, fails = verify(candidate, task.get("train", []))
    if ok:
        return None

    # Build a concrete failure report for the LLM.
    fail_lines = []
    for idx, key, expected, got in fails[:3]:
        fail_lines.append(f"Example {idx+1}: expected\n{_grid_to_text(expected)}\ngot\n{_grid_to_text(got)}")

    system = (
        "You are an ARC-AGI verifier. You are given a Python transform function and training examples. "
        "Check whether the function exactly maps every input to the matching output. "
        "If it is correct, reply exactly with PASS. "
        "If it is wrong, reply with a short critique of why it fails and what to change. "
        "Be concise."
    )
    examples = []
    for i, ex in enumerate(task.get("train", [])):
        examples.append(f"Example {i+1} input:\n{_grid_to_text(ex['input'])}")
        examples.append(f"Example {i+1} output:\n{_grid_to_text(ex['output'])}")

    if isinstance(candidate, PythonCandidate):
        cand_str = f"```python\n{candidate.code}\n```"
    else:
        cand_str = str(candidate)

    user = (
        f"Candidate:\n{cand_str}\n\n"
        + "\n".join(examples)
        + "\n\nFailures:\n" + "\n\n".join(fail_lines)
        + "\n\nCritique:"
    )

    def _call_verifier(tier: str) -> str:
        text, _ = _call_llm(tier, system, user, max_tokens=800, no_fallback=True)
        return text.strip()

    critique = _call_verifier("glm")
    if critique.startswith("PASS") or "correct" in critique.lower():
        return f"LLM verifier accepted, but actual execution failed. {critique}"

    if not critique:
        critique = _call_verifier("gemini")

    if not critique:
        critique = "Function failed deterministic verification; try a different approach."

    return critique


def llm_solve(task: dict, max_attempts: int = 2) -> tuple[PythonCandidate | Candidate | None, str]:
    """Try to solve a task using LLM. Return (candidate, model_note).

    Path A: DeepSeek writes a Python `def transform(grid)` function.
    Falls back to legacy DSL JSON path if Python extraction fails.
    """
    history = ""
    last_note = ""
    for attempt in range(1, max_attempts + 1):
        system, user = _build_prompt(task, attempt, history)
        text, note = _call_llm("deepseek", system, user, max_tokens=4000, no_fallback=True)
        last_note = note

        # Path A: extract Python code.
        code = _extract_python(text)
        if code is not None:
            try:
                candidate = PythonCandidate(code)
                ok, _ = verify(candidate, task.get("train", []))
                if ok:
                    return candidate, f"deepseek attempt {attempt} ok; {note}"
            except Exception as e:
                history = f"Attempt {attempt}: code execution failed: {e}"
                continue

            critique = _critique_candidate(candidate, task, attempt)
            if critique is None:
                return candidate, f"deepseek attempt {attempt} accepted by GLM; {note}"
            history = critique
            continue

        # Legacy fallback: try JSON DSL path.
        data = _extract_json(text)
        if data is not None:
            candidate = _parse_candidate(data)
            if candidate is not None:
                ok, _ = verify(candidate, task.get("train", []))
                if ok:
                    return candidate, f"deepseek attempt {attempt} ok (dsl); {note}"
                critique = _critique_candidate(candidate, task, attempt)
                if critique is None:
                    return candidate, f"deepseek attempt {attempt} accepted by GLM (dsl); {note}"
                history = critique
                continue

        history = f"Attempt {attempt}: could not extract Python code or JSON from response."

    return None, f"deepseek failed after {max_attempts} attempts; {last_note}"
