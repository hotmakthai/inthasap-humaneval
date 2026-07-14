"""run_p5b_baseline.py — รัน Engine P5b (Path A: LLM writes free Python) บน 400 ข้อ ARC-AGI training"""

from __future__ import annotations

import json
import os
from pathlib import Path

from arc_engine import run_baseline, score_predictions

TRAINING_DIR = Path("arc_data/data/training")
LIMIT = 400


def main():
    paths = sorted(TRAINING_DIR.glob("*.json"))
    if not paths:
        print("ไม่พบ dataset ใน", TRAINING_DIR)
        return

    state_path = "p5b_state.json"
    pred_path = "p5b_baseline_predictions.json"

    print(f"Running P5b baseline (Path A: free Python) on {min(LIMIT, len(paths))}/{len(paths)} tasks...")
    result = run_baseline(
        paths,
        limit=LIMIT,
        resume_path=state_path,
        output_path=pred_path,
        use_llm=True,
    )
    score = score_predictions(pred_path, TRAINING_DIR)

    print("\n=== P5b Baseline Result ===")
    print(f"Tasks run: {result['completed']}")
    print(f"Correct: {score['correct']}/{score['total']} (pass rate {score['pass_rate']:.2%})")
    print(f"Predictions saved to: {pred_path}")
    print(f"Resume state: {state_path}")


if __name__ == "__main__":
    main()
