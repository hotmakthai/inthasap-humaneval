"""run_r4_baseline.py -- Round 4 baseline: evolutionary search + targeted repair + strategy rotation

R4 improvements over R3:
- T0: Fixed telemetry bug (per-task llm_calls, reset between tasks)
- T1: Round 4 targeted repair for near-miss tasks (fitness >= 0.9)
- T2: Strategy rotation fallback when all candidates < 0.3 fitness

Runs the ARC engine with LLM evolutionary solver on 400 training tasks.
Saves state with telemetry per task.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from arc_engine import run_baseline, score_predictions

TRAINING_DIR = Path("arc_data/data/training")
LIMIT = 400


def main():
    paths = sorted(TRAINING_DIR.glob("*.json"))
    if not paths:
        print("Dataset not found in", TRAINING_DIR)
        return

    state_path = "r4_state.json"
    pred_path = "r4_baseline_predictions.json"

    print(f"Running Round 4 baseline (evolutionary + targeted repair + strategy rotation) on {min(LIMIT, len(paths))}/{len(paths)} tasks...")
    result = run_baseline(
        paths,
        limit=LIMIT,
        resume_path=state_path,
        output_path=pred_path,
        use_llm=True,
    )
    score = score_predictions(pred_path, TRAINING_DIR)

    print("\n=== Round 4 Baseline Result ===")
    print(f"Tasks run: {result['completed']}")
    print(f"Correct: {score['correct']}/{score['total']} (pass rate {score['pass_rate']:.2%})")
    print(f"Predictions saved to: {pred_path}")
    print(f"Resume state: {state_path}")

    # Aggregate telemetry — use last task's cumulative for cost/tokens
    results = result.get("results", [])
    total_calls = 0
    calls_by_tier: dict[str, int] = {}
    last_cost = 0.0
    last_input = 0
    last_output = 0

    for r in results:
        t = r.get("telemetry", {})
        # llm_calls is now per-task (T0 fix) — safe to sum
        total_calls += t.get("llm_calls", 0)
        # cost/tokens are cumulative — take last
        last_cost = t.get("total_cost_usd", last_cost)
        last_input = t.get("total_input_tokens", last_input)
        last_output = t.get("total_output_tokens", last_output)
        for k, v in t.get("calls_by_tier", {}).items():
            calls_by_tier[k] = calls_by_tier.get(k, 0) + v

    # Round attribution
    from collections import Counter
    round_counts = Counter()
    for r in results:
        sr = r.get("telemetry", {}).get("solved_round")
        if r["status"] == "solved":
            round_counts[sr] += 1

    print(f"\n--- Telemetry ---")
    print(f"Total LLM calls: {total_calls}")
    print(f"Total input tokens: {last_input:,}")
    print(f"Total output tokens: {last_output:,}")
    print(f"Total cost (USD): ${last_cost:.4f}")
    print(f"Calls by tier: {calls_by_tier}")
    print(f"Solved by round: {dict(round_counts)}")

    summary = {
        "correct": score["correct"],
        "total": score["total"],
        "pass_rate": score["pass_rate"],
        "telemetry": {
            "total_llm_calls": total_calls,
            "total_input_tokens": last_input,
            "total_output_tokens": last_output,
            "total_cost_usd": last_cost,
            "calls_by_tier": calls_by_tier,
            "solved_by_round": dict(round_counts),
        },
    }
    Path("r4_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Summary saved to r4_summary.json")


if __name__ == "__main__":
    main()
