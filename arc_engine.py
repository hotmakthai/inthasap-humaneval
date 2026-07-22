"""arc_engine.py — ตัวประกอบหลักของ ARC-AGI Engine"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from arc_generator import Candidate, generate_candidates
from arc_ranking import rank
from arc_verifier import grids_equal, verify

try:
    from near_miss_verifier import check_invariants, FailureReport
    _HAS_FAILURE_CLASSIFIER = True
except ImportError:
    _HAS_FAILURE_CLASSIFIER = False

Grid = list[list[int]]


def _grids_equal(a: Grid, b: Grid) -> bool:
    if a is None or b is None:
        return False
    if len(a) != len(b):
        return False
    return all(row_a == row_b for row_a, row_b in zip(a, b))


def _valid_grid(g: Any) -> bool:
    """ตรวจว่า output grid ถูกรูปแบบ (list-of-lists of ints, ไม่ empty)"""
    if not isinstance(g, list) or not g:
        return False
    if not all(isinstance(row, list) and row for row in g):
        return False
    if not all(isinstance(c, int) for row in g for c in row):
        return False
    return True


def solve_task(task: dict, top_k: int = 2, use_llm: bool = False) -> dict[str, Any]:
    """แก้โจทย์ 1 ข้อ คืนคำตอบที่ดีที่สุด (และอันดับ 2 ถ้าต่างกัน)"""
    examples = task.get("train", [])
    if not examples or not task.get("test"):
        return {"output": None, "candidate": None, "status": "no_data",
                "failure_reports": [], "has_invariant_warning": False}

    _get_telemetry = None
    _reset_telemetry = None
    if use_llm:
        try:
            from arc_llm import get_telemetry as _get_telemetry, reset_telemetry as _reset_telemetry
        except ImportError:
            pass
        if _reset_telemetry:
            _reset_telemetry()

    passing: list[Candidate] = []
    for candidate in generate_candidates(task):
        ok, _ = verify(candidate, examples)
        if ok and candidate not in passing:
            passing.append(candidate)
            if len(passing) >= top_k:
                # ยังค้นต่อเพื่อให้ rank ได้อย่างน้อย top_k ตัว
                if len(passing) >= top_k * 3:
                    break

    llm_telemetry = {}
    if not passing and use_llm:
        # ขั้น 4: ให้ LLM เสนอ candidate ที่ผ่าน train ได้สูงสุด 2 ตัว
        try:
            from arc_llm import llm_solve

            llm_candidates, note, llm_telemetry = llm_solve(
                task, max_attempts=2, evolutionary=True, return_all=True
            )
            # llm_candidates เป็น list ของ candidate ที่ verify ผ่าน train แล้ว (0-2 ตัว)
            for cand in llm_candidates or []:
                ok, _ = verify(cand, examples)
                if ok and cand not in passing:
                    passing.append(cand)
                    if len(passing) >= top_k * 3:
                        break
        except Exception as e:
            # LLM ใช้ไม่ได้ ให้คืนสถานะ unsolved
            llm_telemetry = _get_telemetry() if _get_telemetry else {}
            return {"output": None, "candidate": None, "status": f"unsolved (llm error: {e})",
                    "telemetry": llm_telemetry,
                    "failure_reports": [], "has_invariant_warning": False}

    if not passing:
        # LLM unreachable (เน็ตหลุด/ไฟดับ) — ใช้ status พิเศษเพื่อให้ rerun แยกข้อได้
        if llm_telemetry.get("llm_unreachable"):
            return {"output": None, "candidate": None, "status": "llm_unreachable",
                    "telemetry": llm_telemetry,
                    "failure_reports": [], "has_invariant_warning": False}
        return {"output": None, "candidate": None, "status": "unsolved",
                "telemetry": llm_telemetry if llm_telemetry else (_get_telemetry() if _get_telemetry else {}),
                "failure_reports": [], "has_invariant_warning": False}

    # Solved without LLM — telemetry is empty (no LLM calls)

    ranked = rank(passing)
    test_input = task["test"][0]["input"]
    outputs: list[Grid] = []
    chosen = []
    for cand in ranked:
        if len(outputs) >= top_k:
            break
        try:
            out = cand(test_input)
        except Exception:
            out = None
        if _valid_grid(out) and not any(_grids_equal(out, o) for o in outputs):
            outputs.append(out)
            chosen.append(cand)

    if not outputs:
        return {"output": None, "candidate": None, "status": "unsolved (invalid output)",
                "telemetry": llm_telemetry if llm_telemetry else {},
                "failure_reports": [], "has_invariant_warning": False}

    failure_reports = []
    if _HAS_FAILURE_CLASSIFIER and outputs:
        try:
            failure_reports = check_invariants(task, outputs[0])
        except Exception:
            failure_reports = []

    return {
        "output": outputs[0],
        "outputs": outputs,
        "attempt_1": outputs[0],
        "attempt_2": outputs[1] if len(outputs) > 1 else None,
        "candidate": repr(chosen[0]),
        "candidates": [repr(c) for c in chosen],
        "status": "solved",
        "train_fit_only": True,
        "ambiguous": len(outputs) > 1,
        "telemetry": llm_telemetry if llm_telemetry else {},
        "failure_reports": [
            {"failure_class": r.failure_class.value, "confidence": r.confidence, "hints": r.hints}
            for r in failure_reports
        ],
        "has_invariant_warning": len(failure_reports) > 0,
    }


def _load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"index": 0, "results": []}


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def run_baseline(
    task_paths: list[Path],
    limit: int | None = None,
    resume_path: str | Path = "p4_state.json",
    output_path: str | Path = "p4_baseline_predictions.json",
    use_llm: bool = False,
) -> dict[str, Any]:
    """รัน baseline บนชุดโจทย์ พร้อม resume"""
    resume_path = Path(resume_path)
    output_path = Path(output_path)
    state = _load_state(resume_path)
    start = state["index"]
    tasks = task_paths[:limit] if limit else task_paths
    results = state["results"]

    consecutive_unreachable = 0
    for i in range(start, len(tasks)):
        path = tasks[i]
        task = json.loads(path.read_text(encoding="utf-8"))
        task.setdefault("task_id", path.stem)
        start_time = time.time()
        try:
            sol = solve_task(task, use_llm=use_llm)
        except Exception as e:
            sol = {"output": None, "candidate": None, "status": f"error:{e}"}
        latency = time.time() - start_time

        # Circuit breaker — LLM unreachable ติดกัน 3 ข้อ = เน็ตตายยาว → หยุดรอ 5 นาทีแล้วลองข้อเดิมซ้ำ
        if sol["status"] == "llm_unreachable":
            consecutive_unreachable += 1
            print(f"[{i+1}/{len(tasks)}] {path.stem}: LLM UNREACHABLE ({consecutive_unreachable} in a row)", flush=True)
            if consecutive_unreachable >= 3:
                print("[circuit breaker] LLM unreachable 3 tasks in a row — sleeping 300s before retrying...", flush=True)
                time.sleep(300)
                consecutive_unreachable = 0
            # ไม่บันทึกผลข้อนี้ทันที — ลองข้อเดิมซ้ำ 1 ครั้งหลังพัก
            start_time = time.time()
            try:
                sol = solve_task(task, use_llm=use_llm)
            except Exception as e:
                sol = {"output": None, "candidate": None, "status": f"error:{e}"}
            latency = time.time() - start_time
            if sol["status"] == "llm_unreachable":
                # ยังไม่ฟื้น — พัก 60s แล้วลองครั้งสุดท้าย
                print(f"[circuit breaker] {path.stem} still unreachable after 300s — sleeping 60s for last attempt...", flush=True)
                time.sleep(60)
                start_time = time.time()
                try:
                    sol = solve_task(task, use_llm=use_llm)
                except Exception as e:
                    sol = {"output": None, "candidate": None, "status": f"error:{e}"}
                latency = time.time() - start_time
                if sol["status"] != "llm_unreachable":
                    consecutive_unreachable = 0
                else:
                    print(f"[circuit breaker] {path.stem} still unreachable — recording and moving on", flush=True)
        else:
            consecutive_unreachable = 0
        result = {
            "task_id": path.stem,
            "status": sol["status"],
            "candidate": sol.get("candidate"),
            "latency_sec": latency,
            "telemetry": sol.get("telemetry", {}),
        }
        results.append(result)
        state["index"] = i + 1
        state["results"] = results
        _save_state(resume_path, state)

        # Progress print — flush so output is visible in real-time
        tel = sol.get("telemetry", {})
        fit = tel.get("best_fitness", 0.0)
        rnd = tel.get("solved_round", "-")
        calls = tel.get("llm_calls", 0)
        status_short = "OK" if sol["status"] == "solved" else "FAIL"
        print(f"[{i+1}/{len(tasks)}] {path.stem}: {status_short} fit={fit:.2f} rnd={rnd} calls={calls} {latency:.0f}s", flush=True)

        # บันทึก predictions แยก (บันทึกทุกข้อ แม้ None)
        predictions = _load_state(output_path) if output_path.exists() else {}
        # รูปแบบใหม่: เก็บ 2 attempts (backward-compatible ด้วย attempt_1)
        if isinstance(sol.get("output"), list):
            predictions[path.stem] = {
                "attempt_1": sol.get("output"),
                "attempt_2": sol.get("attempt_2"),
            }
        else:
            predictions[path.stem] = sol.get("output")
        _save_state(output_path, predictions)

    return {
        "total": len(results),
        "completed": state["index"],
        "results": results,
    }


def score_predictions(predictions_path: str | Path, ground_truth_dir: str | Path) -> dict[str, Any]:
    """ให้คะแนน predictions กับ ground truth (test output)

    รองรับ 2 รูปแบบ:
      - เก่า: {task_id: grid}
      - ใหม่: {task_id: {"attempt_1": grid, "attempt_2": grid_or_null}}
    ถูกถ้า attempt ใด attempt หนึ่งตรง
    """
    predictions = json.loads(Path(predictions_path).read_text(encoding="utf-8"))
    gt_dir = Path(ground_truth_dir)
    correct = 0
    total = 0
    for task_id, pred in predictions.items():
        gt_path = gt_dir / f"{task_id}.json"
        if not gt_path.exists():
            continue
        task = json.loads(gt_path.read_text(encoding="utf-8"))
        total += 1
        true_output = task["test"][0]["output"]

        if isinstance(pred, dict) and ("attempt_1" in pred or "attempt_2" in pred):
            attempts = [pred.get("attempt_1"), pred.get("attempt_2")]
        else:
            attempts = [pred]

        if any(a is not None and _grids_equal(a, true_output) for a in attempts):
            correct += 1
    return {"correct": correct, "total": total, "pass_rate": correct / total if total else 0.0}
