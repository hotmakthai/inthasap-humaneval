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
import sys
import threading
from typing import Any

# Safety net: ensure stdout can handle non-ASCII on Windows (cp874/cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from arc_diff import analyze_diff
from arc_dsl import RULES  # kept for backward compat with old tests
from arc_generator import Candidate  # kept for backward compat
from arc_perception import analyze_scene, extract_objects, background_color
from arc_verifier import verify, grids_equal
from arc_viewer import grid_to_str

# Avoid importing the heavy `core.llm` at import time; load it lazily.
_LLM = None
_LLM_LOADED = False

# ── Telemetry accumulator (T6) ──
_TELEMETRY: dict[str, Any] = {
    "llm_calls": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cached_tokens": 0,
    "total_cost_usd": 0.0,
    "calls_by_tier": {},
}


def _telemetry_callback(tier: str, model: str, usage: dict | None) -> None:
    """Callback registered with core.llm to capture per-call telemetry."""
    _TELEMETRY["llm_calls"] += 1
    if usage:
        _TELEMETRY["total_input_tokens"] += usage.get("input_tokens", 0)
        _TELEMETRY["total_output_tokens"] += usage.get("output_tokens", 0)
        _TELEMETRY["total_cached_tokens"] += usage.get("cached_tokens", 0)
        _TELEMETRY["total_cost_usd"] += usage.get("cost_usd", 0.0)
    tier_key = f"{tier}/{model}"
    _TELEMETRY["calls_by_tier"][tier_key] = _TELEMETRY["calls_by_tier"].get(tier_key, 0) + 1


def get_telemetry() -> dict[str, Any]:
    """Return a copy of the current telemetry accumulator."""
    return dict(_TELEMETRY)


def reset_telemetry() -> None:
    """Reset the telemetry accumulator to zero."""
    for k in _TELEMETRY:
        if k == "calls_by_tier":
            _TELEMETRY[k] = {}
        elif isinstance(_TELEMETRY[k], float):
            _TELEMETRY[k] = 0.0
        else:
            _TELEMETRY[k] = 0


def _llm():
    global _LLM, _LLM_LOADED
    if _LLM is None:
        import core.llm as _LLM
    if not _LLM_LOADED:
        _LLM.set_cost_callback(_telemetry_callback)
        _LLM_LOADED = True
    return _LLM


# ── Safe execution namespace ──
_SAFE_BUILTINS = {
    'range': range, 'len': len, 'int': int, 'str': str, 'list': list,
    'tuple': tuple, 'dict': dict, 'set': set, 'frozenset': frozenset,
    'sorted': sorted, 'enumerate': enumerate, 'zip': zip, 'map': map,
    'filter': filter, 'sum': sum, 'min': min, 'max': max, 'abs': abs,
    'any': any, 'all': all, 'reversed': reversed, 'round': round,
    'isinstance': isinstance, 'type': type, 'bool': bool, 'float': float,
    'repr': repr, 'print': lambda *a, **k: print(*a, **{**k, 'file': sys.stdout}), 'ord': ord, 'chr': chr,
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


def _cell_fitness(candidate, train: list[dict]) -> tuple[float, list]:
    """Compute fitness as % of correct cells across all training examples.

    Returns (score 0.0-1.0, details) where details is a list of
    (idx, expected, got, correct_cells, total_cells, diff_grid).
    """
    details = []
    total_correct = 0
    total_cells = 0
    for idx, ex in enumerate(train):
        if "input" not in ex or "output" not in ex:
            continue
        expected = ex["output"]
        try:
            got = _exec_or_call(candidate, ex["input"])
        except Exception:
            h = len(expected)
            w = len(expected[0]) if expected else 0
            got = [[0] * w for _ in range(h)]

        # Count matching cells (handle size mismatch)
        correct = 0
        cells = 0
        diff_grid = []
        max_rows = max(len(expected), len(got))
        for r in range(max_rows):
            diff_row = []
            exp_row = expected[r] if r < len(expected) else None
            got_row = got[r] if r < len(got) else None
            max_cols = max(
                len(exp_row) if exp_row else 0,
                len(got_row) if got_row else 0,
            )
            for c in range(max_cols):
                cells += 1
                ev = exp_row[c] if exp_row and c < len(exp_row) else None
                gv = got_row[c] if got_row and c < len(got_row) else None
                if ev == gv:
                    correct += 1
                    diff_row.append(".")
                else:
                    diff_row.append("X")
            diff_grid.append(diff_row)

        total_correct += correct
        total_cells += cells
        details.append((idx, expected, got, correct, cells, diff_grid))

    score = total_correct / total_cells if total_cells > 0 else 0.0
    return score, details


def _exec_or_call(candidate, grid):
    """Run a candidate (PythonCandidate or Candidate) on a grid."""
    if isinstance(candidate, PythonCandidate):
        return _exec_transform(candidate.code, grid, candidate.func_name)
    return candidate(grid)


def _build_diff_feedback(task: dict, details: list) -> str:
    """Build deterministic ASCII diff feedback for the LLM.

    Shows expected vs got vs diff (X=wrong, .=correct) for each failed example.
    """
    lines = []
    for idx, expected, got, correct, cells, diff_grid in details[:3]:
        pct = (correct / cells * 100) if cells > 0 else 0
        lines.append(f"Example {idx + 1}: {correct}/{cells} cells correct ({pct:.0f}%)")

        # Side-by-side: Expected | Got | Diff
        max_rows = max(len(expected), len(got), len(diff_grid))
        for r in range(max_rows):
            exp_row = expected[r] if r < len(expected) else []
            got_row = got[r] if r < len(got) else []
            diff_row = diff_grid[r] if r < len(diff_grid) else []

            max_cols = max(len(exp_row), len(got_row), len(diff_row))
            exp_str = " ".join(str(exp_row[c]) if c < len(exp_row) else "?" for c in range(max_cols))
            got_str = " ".join(str(got_row[c]) if c < len(got_row) else "?" for c in range(max_cols))
            diff_str = " ".join(diff_row[c] if c < len(diff_row) else "?" for c in range(max_cols))
            lines.append(f"  exp: {exp_str}  |  got: {got_str}  |  diff: {diff_str}")
        lines.append("")
    return "\n".join(lines)


def _build_perception_hints(task: dict) -> str:
    """Extract deterministic perception facts from the task for LLM prompting.

    Only includes facts that are consistent across ALL training examples.
    No speculation — just observable, computed facts.
    """
    examples = task.get("train", [])
    if not examples:
        return ""

    hints = []

    # Diff analysis facts
    diff = analyze_diff(task)
    if diff.size_relation:
        hints.append(f"Size relation: input scaled by {diff.size_relation[0]}x rows, {diff.size_relation[1]}x cols")
    if diff.color_map:
        cm_str = ", ".join(f"{k}->{v}" for k, v in sorted(diff.color_map.items()))
        hints.append(f"Color mapping: {cm_str}")
    if diff.bg_color_in is not None and diff.bg_color_out is not None:
        if diff.bg_color_in != diff.bg_color_out:
            hints.append(f"Background color changes: {diff.bg_color_in} -> {diff.bg_color_out}")
        else:
            hints.append(f"Background color unchanged: {diff.bg_color_in}")
    if diff.object_count_in is not None and diff.object_count_out is not None:
        if diff.object_count_in != diff.object_count_out:
            hints.append(f"Object count changes: {diff.object_count_in} -> {diff.object_count_out}")
        else:
            hints.append(f"Object count unchanged: {diff.object_count_in}")
    if diff.detected_transforms:
        hints.append(f"Detected transforms: {', '.join(diff.detected_transforms[:3])}")

    # Perception facts from first example (consistent ones only)
    first_ex = examples[0]
    in_scene = analyze_scene(first_ex["input"])
    out_scene = analyze_scene(first_ex["output"])

    # Symmetries that are consistent across all examples
    in_syms_all = set()
    out_syms_all = set()
    for ex in examples:
        in_s = analyze_scene(ex["input"])
        out_s = analyze_scene(ex["output"])
        in_syms = {k for k, v in in_s.symmetries.items() if v}
        out_syms = {k for k, v in out_s.symmetries.items() if v}
        if not in_syms_all:
            in_syms_all = in_syms
        else:
            in_syms_all &= in_syms
        if not out_syms_all:
            out_syms_all = out_syms
        else:
            out_syms_all &= out_syms

    if in_syms_all:
        hints.append(f"Input symmetries (all examples): {', '.join(sorted(in_syms_all))}")
    if out_syms_all:
        hints.append(f"Output symmetries (all examples): {', '.join(sorted(out_syms_all))}")

    # Color counts comparison (first example as representative)
    in_colors = set(in_scene.color_counts.keys())
    out_colors = set(out_scene.color_counts.keys())
    if in_colors != out_colors:
        added = out_colors - in_colors
        removed = in_colors - out_colors
        if added:
            hints.append(f"Colors added in output: {sorted(added)}")
        if removed:
            hints.append(f"Colors removed in output: {sorted(removed)}")

    # Object sizes (first example)
    in_objs = extract_objects(first_ex["input"], in_scene.bg_color)
    out_objs = extract_objects(first_ex["output"], out_scene.bg_color)
    if in_objs:
        sizes = sorted(set(o.size for o in in_objs))
        hints.append(f"Input object sizes: {sizes}")
    if out_objs:
        sizes = sorted(set(o.size for o in out_objs))
        hints.append(f"Output object sizes: {sizes}")

    if not hints:
        return ""
    return "Perception facts:\n" + "\n".join(f"- {h}" for h in hints)


def _build_prompt(task: dict, attempt: int, history: str = "", strategy_hint: str = "") -> tuple[str, str]:
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

    perception_hints = _build_perception_hints(task)

    user = (
        "\n".join(example_text)
        + "\n"
        + diff_text
        + "\n"
    )
    if perception_hints:
        user += perception_hints + "\n\n"
    if strategy_hint:
        user += f"Strategy hint: {strategy_hint}\n\n"
    if attempt > 1 and history:
        user += (
            f"Previous attempt {attempt - 1} failed. Feedback:\n{history}\n"
            "The diff above shows expected vs got output. 'X' marks wrong cells, '.' marks correct cells.\n"
            "Fix the function so ALL cells match. Return only the Python code.\n"
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


def _is_llm_error(text: str) -> bool:
    """Detect error responses from core.llm (all tiers failed / quota / connection)."""
    if not text:
        return True
    t = text.strip()
    return (
        t.startswith("(ทุก tier ล้มเหลว")
        or t.startswith("QUOTA_EXHAUSTED")
        or t.startswith("(DeepSeek error")
        or t.startswith("(DeepSeek HTTP")
        or t.startswith("(ไม่มี DEEPSEEK_API_KEY")
    )


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


# ── Evolutionary search strategies (T2) ──
_STRATEGY_HINTS = [
    "Focus on color mapping — identify how colors change from input to output.",
    "Focus on spatial transformations — rotation, reflection, or translation.",
    "Focus on object detection — identify connected components and their properties.",
    "Focus on grid size changes — cropping, padding, or resizing.",
    "Focus on pattern completion — fill in missing parts of a pattern.",
    "Focus on counting — count objects and produce a grid based on counts.",
    "Focus on symmetry — mirror or complete symmetric patterns.",
    "Focus on line/edge detection — identify borders, boundaries, or outlines.",
    "Focus on flood fill — fill enclosed regions with a specific color.",
    "Focus on sorting/reordering — rearrange rows, columns, or objects by some criterion.",
]


def _evolutionary_solve(
    task: dict, train: list[dict], n_initial: int = 8,
) -> tuple[PythonCandidate | Candidate | None, str, dict]:
    """Evolutionary 4-round search.

    Round 1: Generate n_initial diverse candidates (different strategy hints).
    Round 2: Individual revision — top candidates get diff feedback + retry.
    Round 3: Pooled hybridization — combine best candidates' code into one attempt.
    Round 4: Targeted repair — if fitness >= 0.9, tell LLM exactly which cells are wrong.

    Returns (best_candidate, note, telemetry_dict).
    """
    telemetry = {
        "llm_calls": 0, "candidates_generated": 0, "best_fitness": 0.0,
        "solved_round": None,  # 1, 2, 3, or 4 — which round solved it
        "solved_candidate_idx": None,  # which candidate index in that round
        "fitness_trajectory": [],  # list of (round, candidate_idx, fitness)
        "had_perception_hints": False,
        "round1_best_fitness": 0.0,
        "round2_best_fitness": 0.0,
        "round3_best_fitness": 0.0,
        "round4_best_fitness": 0.0,
        "round1_calls": 0,
        "round2_calls": 0,
        "round3_calls": 0,
        "round4_calls": 0,
    }
    best_candidate = None
    best_fitness = 0.0
    all_candidates: list[tuple[float, PythonCandidate, str]] = []  # (fitness, candidate, note)

    # ── Round 1: Diverse initial generation ──
    hints = _STRATEGY_HINTS[:n_initial]
    llm_error_count = 0
    for i, hint in enumerate(hints):
        system, user = _build_prompt(task, attempt=1, strategy_hint=hint)
        text, note = _call_llm("deepseek", system, user, max_tokens=4000, no_fallback=True)
        telemetry["llm_calls"] += 1

        # ตรวจจับ LLM unreachable — error text จาก core.llm เมื่อทุก tier ล้มเหลว (เน็ตหลุด/ไฟดับ)
        if _is_llm_error(text):
            llm_error_count += 1
            # 3 ครั้งติดกัน = LLM ตายจริง — หยุดทันที อย่าเผา call ต่อ
            if llm_error_count >= 3 and telemetry["candidates_generated"] == 0:
                telemetry["llm_unreachable"] = True
                telemetry["round1_best_fitness"] = best_fitness
                telemetry["round1_calls"] = telemetry["llm_calls"]
                return None, f"LLM_UNREACHABLE: {text[:120]}", telemetry
            continue

        code = _extract_python(text)
        if code is None:
            continue
        try:
            cand = PythonCandidate(code)
        except Exception:
            continue
        telemetry["candidates_generated"] += 1

        fitness, _ = _cell_fitness(cand, train)
        all_candidates.append((fitness, cand, note))
        if fitness > best_fitness:
            best_fitness = fitness
            best_candidate = cand
        telemetry["fitness_trajectory"].append((1, i, fitness))
        if fitness >= 1.0:
            telemetry["best_fitness"] = 1.0
            telemetry["solved_round"] = 1
            telemetry["solved_candidate_idx"] = i
            telemetry["round1_best_fitness"] = 1.0
            return cand, f"evolutionary round1 candidate {i+1} perfect; {note}", telemetry

    telemetry["round1_best_fitness"] = best_fitness
    telemetry["round1_calls"] = telemetry["llm_calls"]

    if not all_candidates:
        # ถ้ามี LLM error เกินครึ่งของ calls และไม่ได้ code เลย — น่าจะ unreachable
        if llm_error_count >= n_initial // 2:
            telemetry["llm_unreachable"] = True
            return None, "LLM_UNREACHABLE: no valid candidates, mostly LLM errors", telemetry
        return None, "evolutionary round1: no valid candidates", telemetry

    # ── T2: Strategy rotation fallback ──
    # If all candidates scored < 0.3, strategy hints may have misdirected the LLM.
    # Try 2 more candidates with default prompt (no strategy hint) as a safety net.
    if best_fitness < 0.3:
        for i in range(2):
            system, user = _build_prompt(task, attempt=1, strategy_hint="")
            text, note = _call_llm("deepseek", system, user, max_tokens=4000, no_fallback=True)
            telemetry["llm_calls"] += 1

            code = _extract_python(text)
            if code is None:
                continue
            try:
                cand = PythonCandidate(code)
            except Exception:
                continue
            telemetry["candidates_generated"] += 1

            fitness, _ = _cell_fitness(cand, train)
            all_candidates.append((fitness, cand, note))
            if fitness > best_fitness:
                best_fitness = fitness
                best_candidate = cand
            telemetry["fitness_trajectory"].append((1, n_initial + i, fitness))
            if fitness >= 1.0:
                telemetry["best_fitness"] = 1.0
                telemetry["solved_round"] = 1
                telemetry["solved_candidate_idx"] = n_initial + i
                telemetry["round1_best_fitness"] = 1.0
                telemetry["round1_calls"] = telemetry["llm_calls"]
                return cand, f"evolutionary round1 fallback candidate perfect; {note}", telemetry

        telemetry["round1_best_fitness"] = best_fitness
        telemetry["round1_calls"] = telemetry["llm_calls"]

    # Sort by fitness descending
    all_candidates.sort(key=lambda x: x[0], reverse=True)
    telemetry["best_fitness"] = best_fitness

    # ── Round 2: Individual revision (top 3 candidates get diff feedback) ──
    top_n = min(3, len(all_candidates))
    for i in range(top_n):
        fitness, cand, note = all_candidates[i]
        _, details = _cell_fitness(cand, train)
        diff_feedback = _build_diff_feedback(task, details)

        history = (
            f"Previous fitness={fitness:.2f}.\n"
            f"{diff_feedback}\n"
            f"Fix the function so ALL cells match."
        )
        system, user = _build_prompt(task, attempt=2, history=history,
                                     strategy_hint=_STRATEGY_HINTS[i % len(_STRATEGY_HINTS)])
        text, note2 = _call_llm("deepseek", system, user, max_tokens=4000, no_fallback=True)
        telemetry["llm_calls"] += 1

        code = _extract_python(text)
        if code is None:
            continue
        try:
            cand2 = PythonCandidate(code)
        except Exception:
            continue
        telemetry["candidates_generated"] += 1

        fitness2, _ = _cell_fitness(cand2, train)
        all_candidates.append((fitness2, cand2, note2))
        if fitness2 > best_fitness:
            best_fitness = fitness2
            best_candidate = cand2
        telemetry["fitness_trajectory"].append((2, i, fitness2))
        if fitness2 >= 1.0:
            telemetry["best_fitness"] = 1.0
            telemetry["solved_round"] = 2
            telemetry["solved_candidate_idx"] = i
            telemetry["round2_best_fitness"] = 1.0
            return cand2, f"evolutionary round2 candidate {i+1} perfect; {note2}", telemetry

    telemetry["round2_best_fitness"] = best_fitness
    telemetry["round2_calls"] = telemetry["llm_calls"] - telemetry["round1_calls"]

    # ── T4: EV Stopping Criterion ──
    # If Round 2 didn't improve fitness at all over Round 1, skip Round 3.
    # R3 data: hybridization gave only +4 from ~33% of total calls.
    # Save budget for Round 4 targeted repair instead.
    r1_best = telemetry["round1_best_fitness"]
    r2_best = telemetry["round2_best_fitness"]
    if r2_best <= r1_best and r1_best < 1.0:
        telemetry["round3_best_fitness"] = best_fitness
        telemetry["round3_calls"] = 0
        # Jump directly to Round 4 if eligible
        if best_fitness >= 0.9 and best_fitness < 1.0 and best_candidate is not None:
            pass  # Fall through to Round 4 block below
        else:
            telemetry["best_fitness"] = best_fitness
            if best_candidate is not None:
                return best_candidate, f"evolutionary best fitness={best_fitness:.2f} (R3 skipped, stuck); {all_candidates[0][2]}", telemetry
            return None, "evolutionary: no valid candidates (R3 skipped, stuck)", telemetry

    # ── Round 3: Pooled hybridization ──
    # Show the LLM the top 2 candidates' code + their fitness scores
    # and ask it to combine the best ideas.
    top2 = all_candidates[:2]
    if len(top2) >= 2:
        cand_a_code = top2[0][1].code
        cand_b_code = top2[1][1].code
        fit_a = top2[0][0]
        fit_b = top2[1][0]

        hybrid_system = (
            "You are an ARC-AGI puzzle solver. "
            "Two candidate solutions are shown below with their fitness scores.\n"
            "Combine the best ideas from both into a single `def transform(grid)` function.\n"
            "Keep what works, fix what doesn't. Return ONLY Python code in a ```python block."
        )
        hybrid_user = (
            f"Candidate A (fitness={fit_a:.2f}):\n```python\n{cand_a_code}\n```\n\n"
            f"Candidate B (fitness={fit_b:.2f}):\n```python\n{cand_b_code}\n```\n\n"
        )
        # Add training examples
        for j, ex in enumerate(train):
            hybrid_user += f"Example {j+1}:\nInput:\n{_grid_to_text(ex['input'])}\nOutput:\n{_grid_to_text(ex['output'])}\n\n"
        hybrid_user += "Combine and fix. Return only the Python code in a ```python block."

        text, note3 = _call_llm("deepseek", hybrid_system, hybrid_user, max_tokens=4000, no_fallback=True)
        telemetry["llm_calls"] += 1

        code = _extract_python(text)
        if code is not None:
            try:
                cand3 = PythonCandidate(code)
                telemetry["candidates_generated"] += 1
                fitness3, _ = _cell_fitness(cand3, train)
                all_candidates.append((fitness3, cand3, note3))
                if fitness3 > best_fitness:
                    best_fitness = fitness3
                    best_candidate = cand3
                telemetry["fitness_trajectory"].append((3, 0, fitness3))
                if fitness3 >= 1.0:
                    telemetry["best_fitness"] = 1.0
                    telemetry["solved_round"] = 3
                    telemetry["solved_candidate_idx"] = 0
                    telemetry["round3_best_fitness"] = 1.0
                    return cand3, f"evolutionary round3 hybrid perfect; {note3}", telemetry
            except Exception:
                pass

    telemetry["round3_best_fitness"] = best_fitness
    telemetry["round3_calls"] = telemetry["llm_calls"] - telemetry["round1_calls"] - telemetry["round2_calls"]

    # ── Round 4: Targeted repair (near-miss fix) ──
    # If best fitness >= 0.9 but not perfect, try cell-level targeted repair.
    # Tell the LLM exactly which cells are wrong and ask for a minimal fix.
    if best_fitness >= 0.9 and best_fitness < 1.0 and best_candidate is not None:
        _, repair_details = _cell_fitness(best_candidate, train)
        wrong_cells = []
        for idx, expected, got, correct, cells, diff_grid in repair_details:
            for r, diff_row in enumerate(diff_grid):
                for c, marker in enumerate(diff_row):
                    if marker == "X":
                        exp_val = expected[r][c] if r < len(expected) and c < len(expected[r]) else "?"
                        got_val = got[r][c] if r < len(got) and c < len(got[r]) else "?"
                        wrong_cells.append(f"Example {idx+1}, cell ({r},{c}): expected {exp_val}, got {got_val}")

        if wrong_cells:
            repair_system = (
                "You are an ARC-AGI puzzle solver. "
                "Your solution is ALMOST correct — only a few cells are wrong.\n"
                "Here is your current code and the specific cells that need fixing.\n"
                "Make a MINIMAL change to fix ONLY the wrong cells. Do not rewrite the whole function.\n"
                "Return ONLY the corrected Python code in a ```python block."
            )
            repair_user = (
                f"Current fitness: {best_fitness:.4f}\n"
                f"Wrong cells ({len(wrong_cells)} total):\n"
            )
            for wc in wrong_cells[:20]:
                repair_user += f"  {wc}\n"
            if len(wrong_cells) > 20:
                repair_user += f"  ... and {len(wrong_cells) - 20} more\n"
            repair_user += f"\nCurrent code:\n```python\n{best_candidate.code}\n```\n\n"
            repair_user += "Training examples for reference:\n"
            for j, ex in enumerate(train):
                repair_user += f"Example {j+1}:\nInput:\n{_grid_to_text(ex['input'])}\nOutput:\n{_grid_to_text(ex['output'])}\n\n"
            repair_user += "Fix ONLY the wrong cells. Return the corrected code."

            for repair_attempt in range(3):
                text, note4 = _call_llm("deepseek", repair_system, repair_user, max_tokens=4000, no_fallback=True)
                telemetry["llm_calls"] += 1

                code = _extract_python(text)
                if code is None:
                    continue
                try:
                    cand4 = PythonCandidate(code)
                except Exception:
                    continue
                telemetry["candidates_generated"] += 1

                fitness4, _ = _cell_fitness(cand4, train)
                all_candidates.append((fitness4, cand4, note4))
                if fitness4 > best_fitness:
                    best_fitness = fitness4
                    best_candidate = cand4
                telemetry["fitness_trajectory"].append((4, repair_attempt, fitness4))
                if fitness4 >= 1.0:
                    telemetry["best_fitness"] = 1.0
                    telemetry["solved_round"] = 4
                    telemetry["solved_candidate_idx"] = repair_attempt
                    telemetry["round4_best_fitness"] = 1.0
                    telemetry["round4_calls"] = repair_attempt + 1
                    return cand4, f"evolutionary round4 targeted repair perfect; {note4}", telemetry

            telemetry["round4_best_fitness"] = best_fitness
            telemetry["round4_calls"] = telemetry["llm_calls"] - telemetry["round1_calls"] - telemetry["round2_calls"] - telemetry["round3_calls"]

    telemetry["best_fitness"] = best_fitness
    if best_candidate is not None:
        return best_candidate, f"evolutionary best fitness={best_fitness:.2f}; {all_candidates[0][2]}", telemetry
    return None, "evolutionary: no valid candidates", telemetry


def llm_solve(task: dict, max_attempts: int = 2, evolutionary: bool = False) -> tuple[PythonCandidate | Candidate | None, str, dict]:
    """Try to solve a task using LLM. Return (candidate, model_note, telemetry).

    Path A: DeepSeek writes a Python `def transform(grid)` function.
    Falls back to legacy DSL JSON path if Python extraction fails.
    Uses deterministic ASCII diff feedback (no GLM critique call).
    When evolutionary=True, uses 3-round evolutionary search (8 initial candidates,
    individual revision, pooled hybridization).
    """
    train = task.get("train", [])

    if evolutionary:
        cand, note, evo_telem = _evolutionary_solve(task, train, n_initial=8)
        # Check if perception hints were non-empty
        ph = _build_perception_hints(task)
        evo_telem["had_perception_hints"] = len(ph) > 0
        # Merge with global telemetry
        global _TELEMETRY
        evo_telem["total_input_tokens"] = _TELEMETRY["total_input_tokens"]
        evo_telem["total_output_tokens"] = _TELEMETRY["total_output_tokens"]
        evo_telem["total_cached_tokens"] = _TELEMETRY["total_cached_tokens"]
        evo_telem["total_cost_usd"] = _TELEMETRY["total_cost_usd"]
        evo_telem["calls_by_tier"] = dict(_TELEMETRY["calls_by_tier"])
        return cand, note, evo_telem

    # Helper: build per-task telemetry snapshot from global accumulator
    def _snapshot_telemetry(calls: int, fit: float) -> dict:
        """Merge per-path data with global cumulative telemetry."""
        t = {
            "llm_calls": calls,
            "best_fitness": fit,
            "solved_round": None,
            "candidates_generated": calls,
            "fitness_trajectory": [],
            "had_perception_hints": len(_build_perception_hints(task)) > 0,
            "round1_best_fitness": 0.0,
            "round2_best_fitness": 0.0,
            "round3_best_fitness": 0.0,
            "round1_calls": 0,
            "round2_calls": 0,
            "round3_calls": 0,
        }
        # Copy cumulative global fields (cost, tokens are running totals across all tasks)
        global _TELEMETRY
        t["total_input_tokens"] = _TELEMETRY["total_input_tokens"]
        t["total_output_tokens"] = _TELEMETRY["total_output_tokens"]
        t["total_cached_tokens"] = _TELEMETRY["total_cached_tokens"]
        t["total_cost_usd"] = _TELEMETRY["total_cost_usd"]
        t["calls_by_tier"] = dict(_TELEMETRY["calls_by_tier"])
        return t

    history = ""
    last_note = ""
    best_candidate = None
    best_fitness = 0.0
    train = task.get("train", [])

    for attempt in range(1, max_attempts + 1):
        system, user = _build_prompt(task, attempt, history)
        text, note = _call_llm("deepseek", system, user, max_tokens=4000, no_fallback=True)
        last_note = note

        # Path A: extract Python code.
        code = _extract_python(text)
        if code is not None:
            try:
                candidate = PythonCandidate(code)
            except Exception as e:
                history = f"Attempt {attempt}: PythonCandidate creation failed: {e}"
                continue

            fitness, details = _cell_fitness(candidate, train)
            if fitness > best_fitness:
                best_fitness = fitness
                best_candidate = candidate

            if fitness >= 1.0:
                return candidate, f"deepseek attempt {attempt} ok (fitness=1.0); {note}", _snapshot_telemetry(attempt, 1.0)

            # Deterministic diff feedback — no GLM call needed
            diff_feedback = _build_diff_feedback(task, details)
            history = (
                f"Attempt {attempt} fitness={fitness:.2f}.\n"
                f"Your function produced wrong output for some examples.\n"
                f"{diff_feedback}\n"
                f"Fix the function so ALL cells match. Pay attention to cells marked X in the diff."
            )
            continue

        # Legacy fallback: try JSON DSL path.
        data = _extract_json(text)
        if data is not None:
            candidate = _parse_candidate(data)
            if candidate is not None:
                ok, _ = verify(candidate, train)
                if ok:
                    return candidate, f"deepseek attempt {attempt} ok (dsl); {note}", _snapshot_telemetry(attempt, 1.0)
                # Deterministic diff for DSL path too
                fitness, details = _cell_fitness(candidate, train)
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_candidate = candidate
                diff_feedback = _build_diff_feedback(task, details)
                history = (
                    f"Attempt {attempt} (dsl) fitness={fitness:.2f}.\n"
                    f"{diff_feedback}\n"
                    f"Write a Python function instead of DSL JSON for better flexibility."
                )
                continue

        history = f"Attempt {attempt}: could not extract Python code or JSON from response."

    # Return best partial candidate if we have one (even if not perfect)
    if best_candidate is not None:
        return best_candidate, f"deepseek best fitness={best_fitness:.2f} after {max_attempts} attempts; {last_note}", _snapshot_telemetry(max_attempts, best_fitness)
    return None, f"deepseek failed after {max_attempts} attempts; {last_note}", _snapshot_telemetry(max_attempts, 0.0)
