"""r4_clean_state.py — Remove broken tasks (LLM errors during network outage) from r4_state.json.

Broken task signature: llm_calls > 0 but candidates_generated == 0 (no tokens used, no cost).
These tasks never actually reached the LLM API. After cleaning, resume run_r4_baseline.py
will re-run only the broken tasks.

Usage: python r4_clean_state.py [--dry-run]
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STATE_PATH = Path("r4_state.json")
PRED_PATH = Path("r4_baseline_predictions.json")
TRAINING_DIR = Path("arc_data/data/training")


def is_broken(result: dict) -> bool:
    """A task is broken if LLM was called but produced zero candidates AND used zero tokens."""
    t = result.get("telemetry", {})
    calls = t.get("llm_calls", 0)
    cg = t.get("candidates_generated", 0)
    tiers = t.get("calls_by_tier", {})
    # llm_unreachable status from the new detection is also broken
    if result.get("status") == "llm_unreachable":
        return True
    # Old signature: calls counted client-side but no tier ever succeeded
    return calls > 0 and cg == 0 and not tiers


def main():
    dry_run = "--dry-run" in sys.argv

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    results = state["results"]

    # Map results to task order (sorted training files — same as run_r4_baseline)
    paths = sorted(TRAINING_DIR.glob("*.json"))
    task_order = [p.stem for p in paths[:400]]

    broken_ids = {r["task_id"] for r in results if is_broken(r)}
    keep = [r for r in results if r["task_id"] not in broken_ids]

    print(f"Total results: {len(results)}")
    print(f"Broken (to re-run): {len(broken_ids)}")
    print(f"Keep: {len(keep)}")

    if dry_run:
        print("\n--dry-run: no changes made")
        for tid in sorted(broken_ids)[:20]:
            print(f"  would remove: {tid}")
        return

    # Backup
    shutil.copy(STATE_PATH, STATE_PATH.with_suffix(".json.bak"))
    print(f"Backup saved: {STATE_PATH}.bak")

    # Rebuild state: keep results in task order; find first missing index for resume
    kept_ids = {r["task_id"] for r in keep}
    # New index = position of first broken task in task order
    new_index = len(task_order)
    for pos, tid in enumerate(task_order):
        if tid in broken_ids:
            new_index = pos
            break

    # Keep only results before new_index (run_baseline resumes sequentially)
    task_pos = {tid: pos for pos, tid in enumerate(task_order)}
    keep_sequential = [r for r in keep if task_pos.get(r["task_id"], 999999) < new_index]
    removed_extra = len(keep) - len(keep_sequential)

    state["results"] = keep_sequential
    state["index"] = new_index
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nNew state: index={new_index}, results={len(keep_sequential)}")
    print(f"Note: {removed_extra} good results after the first broken task were also removed")
    print(f"      (sequential resume requires it — they will be re-run, cost ~${removed_extra * 0.02:.2f})")
    print(f"Tasks to run: {400 - new_index}")

    # Clean predictions for removed tasks
    if PRED_PATH.exists():
        preds = json.loads(PRED_PATH.read_text(encoding="utf-8"))
        kept_seq_ids = {r["task_id"] for r in keep_sequential}
        preds = {k: v for k, v in preds.items() if k in kept_seq_ids}
        PRED_PATH.write_text(json.dumps(preds, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Predictions cleaned: {len(preds)} kept")


if __name__ == "__main__":
    main()
