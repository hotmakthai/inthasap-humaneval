"""arc_engine.py — ตัวประกอบหลักของ ARC-AGI Engine"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from arc_generator import Candidate, generate_candidates
from arc_ranking import rank
from arc_verifier import grids_equal, verify

Grid = list[list[int]]


def _grids_equal(a: Grid, b: Grid) -> bool:
    if len(a) != len(b):
        return False
    return all(row_a == row_b for row_a, row_b in zip(a, b))


def solve_task(task: dict, top_k: int = 2, use_llm: bool = False) -> dict[str, Any]:
    """แก้โจทย์ 1 ข้อ คืนคำตอบที่ดีที่สุด (และอันดับ 2 ถ้าต่างกัน)"""
    examples = task.get("train", [])
    if not examples or not task.get("test"):
        return {"output": None, "candidate": None, "status": "no_data"}

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
        # ขั้น 4: ให้ LLM ลองเสนอ candidate สูงสุด 2 ครั้ง
        try:
            from arc_llm import llm_solve

            llm_candidate, note, llm_telemetry = llm_solve(task, max_attempts=2, evolutionary=True)
            if llm_candidate is not None:
                ok, _ = verify(llm_candidate, examples)
                if ok:
                    passing = [llm_candidate]
        except Exception as e:
            # LLM ใช้ไม่ได้ ให้คืนสถานะ unsolved
            llm_telemetry = _get_telemetry() if _get_telemetry else {}
            return {"output": None, "candidate": None, "status": f"unsolved (llm error: {e})",
                    "telemetry": llm_telemetry}

    if not passing:
        # LLM unreachable (เน็ตหลุด/ไฟดับ) — ใช้ status พิเศษเพื่อให้ rerun แยกข้อได้
        if llm_telemetry.get("llm_unreachable"):
            return {"output": None, "candidate": None, "status": "llm_unreachable",
                    "telemetry": llm_telemetry}
        return {"output": None, "candidate": None, "status": "unsolved",
                "telemetry": llm_telemetry if llm_telemetry else (_get_telemetry() if _get_telemetry else {})}

    # Solved without LLM — telemetry is empty (no LLM calls)

    ranked = rank(passing)
    best = ranked[0]
    test_input = task["test"][0]["input"]
    outputs = [best(test_input)]
    chosen = [best]
    for cand in ranked[1:]:
        if len(outputs) >= top_k:
            break
        out = cand(test_input)
        if not any(_grids_equal(out, o) for o in outputs):
            outputs.append(out)
            chosen.append(cand)

    return {
        "output": outputs[0],
        "outputs": outputs,
        "candidate": repr(chosen[0]),
        "candidates": [repr(c) for c in chosen],
        "status": "solved",
        "telemetry": llm_telemetry if llm_telemetry else {},
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
                # ยังไม่ฟื้น — บันทึก unreachable ไว้ ให้ rerun ภายหลังด้วย script ล้าง state
                pass
            else:
                consecutive_unreachable = 0
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
        predictions[path.stem] = sol.get("output")
        _save_state(output_path, predictions)

    return {
        "total": len(results),
        "completed": state["index"],
        "results": results,
    }


def score_predictions(predictions_path: str | Path, ground_truth_dir: str | Path) -> dict[str, Any]:
    """ให้คะแนน predictions กับ ground truth (test output)"""
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
        if pred is not None and _grids_equal(pred, true_output):
            correct += 1
    return {"correct": correct, "total": total, "pass_rate": correct / total if total else 0.0}
