"""run_r3_baseline.py -- Round 3 baseline: evolutionary search + diff feedback + perception hints

Runs the ARC engine with LLM evolutionary solver on 400 training tasks.
Saves state with telemetry (llm_calls, tokens, cost_usd) per task.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Safety net for Windows console encoding
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

    state_path = "r3_state.json"
    pred_path = "r3_baseline_predictions.json"

    print(f"Running Round 3 baseline (evolutionary + diff + perception) on {min(LIMIT, len(paths))}/{len(paths)} tasks...")
    result = run_baseline(
        paths,
        limit=LIMIT,
        resume_path=state_path,
        output_path=pred_path,
        use_llm=True,
    )
    score = score_predictions(pred_path, TRAINING_DIR)

    print("\n=== Round 3 Baseline Result ===")
    print(f"Tasks run: {result['completed']}")
    print(f"Correct: {score['correct']}/{score['total']} (pass rate {score['pass_rate']:.2%})")
    print(f"Predictions saved to: {pred_path}")
    print(f"Resume state: {state_path}")

    # Aggregate telemetry from results
    total_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    calls_by_tier: dict[str, int] = {}
    for r in result.get("results", []):
        t = r.get("telemetry", {})
        total_calls += t.get("llm_calls", 0)
        total_input_tokens += t.get("total_input_tokens", 0)
        total_output_tokens += t.get("total_output_tokens", 0)
        total_cost += t.get("total_cost_usd", 0.0)
        for k, v in t.get("calls_by_tier", {}).items():
            calls_by_tier[k] = calls_by_tier.get(k, 0) + v

    print(f"\n--- Telemetry ---")
    print(f"Total LLM calls: {total_calls}")
    print(f"Total input tokens: {total_input_tokens}")
    print(f"Total output tokens: {total_output_tokens}")
    print(f"Total cost (USD): ${total_cost:.4f}")
    print(f"Calls by tier: {calls_by_tier}")

    # Save summary
    summary = {
        "correct": score["correct"],
        "total": score["total"],
        "pass_rate": score["pass_rate"],
        "telemetry": {
            "total_llm_calls": total_calls,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost_usd": total_cost,
            "calls_by_tier": calls_by_tier,
        },
    }
    Path("r3_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Summary saved to r3_summary.json")


if __name__ == "__main__":
    main()
