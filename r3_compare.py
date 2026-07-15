"""r3_compare.py -- Compare P5b vs R3 results and generate reviewer-friendly attribution table.

Answers 3 questions:
1. Evolution added how many solves?
2. Perception added how many solves?
3. Cost increased how much per additional solve?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"results": []}
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    p5b = load_state("p5b_state.json")
    r3 = load_state("r3_state.json")

    p5b_results = {r["task_id"]: r for r in p5b.get("results", [])}
    r3_results = {r["task_id"]: r for r in r3.get("results", [])}

    # Overall comparison
    p5b_solved = {tid for tid, r in p5b_results.items() if r["status"] == "solved"}
    r3_solved = {tid for tid, r in r3_results.items() if r["status"] == "solved"}

    p5b_solved_count = len(p5b_solved)
    r3_solved_count = len(r3_solved)

    # Tasks only in R3 (not in P5b or P5b didn't solve)
    newly_solved = r3_solved - p5b_solved
    lost_solved = p5b_solved - r3_solved

    # Attribution by round
    r1_solves = 0  # Solved in Round 1 (diverse generation)
    r2_solves = 0  # Solved in Round 2 (individual revision with diff feedback)
    r3_solves = 0  # Solved in Round 3 (pooled hybridization)
    no_round_info = 0

    # Among newly solved tasks (not solved in P5b)
    newly_r1 = 0
    newly_r2 = 0
    newly_r3 = 0

    for tid in r3_solved:
        r = r3_results.get(tid, {})
        tel = r.get("telemetry", {})
        solved_round = tel.get("solved_round")

        if solved_round == 1:
            r1_solves += 1
            if tid in newly_solved:
                newly_r1 += 1
        elif solved_round == 2:
            r2_solves += 1
            if tid in newly_solved:
                newly_r2 += 1
        elif solved_round == 3:
            r3_solves += 1
            if tid in newly_solved:
                newly_r3 += 1
        else:
            no_round_info += 1

    # Cost analysis -- telemetry fields are CUMULATIVE (running total across all tasks)
    # So the last task's telemetry contains the final totals.
    # llm_calls is per-task (not cumulative), so we sum those.
    r3_results_list = list(r3_results.values())
    r3_sorted = sorted(r3_results_list, key=lambda x: x.get("task_id", ""))
    # Use the original order from state file instead
    r3_raw = r3.get("results", [])

    p5b_has_telemetry = any(r.get("telemetry", {}).get("total_cost_usd", 0) > 0 for r in p5b_results.values())

    # R3 totals: last task's cumulative telemetry = final totals
    if r3_raw:
        last_tel = r3_raw[-1].get("telemetry", {})
        r3_total_cost = last_tel.get("total_cost_usd", 0)
        r3_total_input_tokens = last_tel.get("total_input_tokens", 0)
        r3_total_output_tokens = last_tel.get("total_output_tokens", 0)
        r3_total_cached_tokens = last_tel.get("total_cached_tokens", 0)
    else:
        r3_total_cost = 0
        r3_total_input_tokens = 0
        r3_total_output_tokens = 0
        r3_total_cached_tokens = 0

    # llm_calls is per-task for evolutionary path (max 12), but 19 non-evolutionary
    # tasks have a BUG: llm_calls contains cumulative global counter.
    # Fix: cap invalid values (>12) at 2 (non-evo path uses 1-2 calls).
    r3_calls = sum(
        c if c <= 12 else 2
        for c in (r.get("telemetry", {}).get("llm_calls", 0) for r in r3_results.values())
    )
    r3_total_tokens = r3_total_input_tokens + r3_total_output_tokens

    # Per-task cost: compute by subtracting consecutive cumulative values
    per_task_cost = {}
    prev_cost = 0.0
    for r in r3_raw:
        tid = r.get("task_id", "")
        curr_cost = r.get("telemetry", {}).get("total_cost_usd", prev_cost)
        per_task_cost[tid] = curr_cost - prev_cost
        prev_cost = curr_cost

    # P5b cost: estimate from R3 avg cost per call × 2 calls/task
    p5b_total_cost = 0.0
    p5b_calls = 0
    if p5b_has_telemetry:
        p5b_raw = p5b.get("results", [])
        if p5b_raw:
            p5b_total_cost = p5b_raw[-1].get("telemetry", {}).get("total_cost_usd", 0)
        p5b_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in p5b_results.values())
    else:
        # P5b used 2 LLM calls per task (non-evolutionary)
        p5b_calls = 2 * len(p5b_results)
        avg_cost_per_call = r3_total_cost / max(r3_calls, 1)
        p5b_total_cost = p5b_calls * avg_cost_per_call

    # Cost per solved task
    p5b_cost_per = p5b_total_cost / max(p5b_solved_count, 1)
    r3_cost_per = r3_total_cost / max(r3_solved_count, 1)

    # Per-feature cost attribution using per-task costs
    # Round 1 = diverse candidates (evolution feature)
    # Round 2 = individual revision (diff feedback feature)
    # Round 3 = pooled hybridization (evolution feature)
    r1_cost = 0.0
    r2_cost = 0.0
    r3_round_cost = 0.0
    no_round_cost = 0.0
    for r in r3_results.values():
        tel = r.get("telemetry", {})
        if not tel:
            continue
        tid = r.get("task_id", "")
        task_cost = per_task_cost.get(tid, 0)
        calls = max(tel.get("llm_calls", 1), 1)
        r1_calls = tel.get("round1_calls", 0)
        r2_calls = tel.get("round2_calls", 0)
        r3_calls_task = tel.get("round3_calls", 0)
        solved_round = tel.get("solved_round")

        # Attribute cost by round calls ratio
        if r1_calls > 0:
            r1_cost += task_cost * (r1_calls / calls)
        if r2_calls > 0:
            r2_cost += task_cost * (r2_calls / calls)
        if r3_calls_task > 0:
            r3_round_cost += task_cost * (r3_calls_task / calls)
        if solved_round is None:
            no_round_cost += task_cost

    # Perception: tasks that had perception hints and were newly solved
    perception_newly = 0
    no_perception_newly = 0
    for tid in newly_solved:
        r = r3_results.get(tid, {})
        tel = r.get("telemetry", {})
        if tel.get("had_perception_hints"):
            perception_newly += 1
        else:
            no_perception_newly += 1

    # Print report
    total_r3 = len(r3_results)
    total_p5b = len(p5b_results)

    print("=" * 60)
    print("Round 3 vs P5b Comparison Report")
    print("=" * 60)
    print()
    print(f"P5b: {p5b_solved_count}/{total_p5b} solved ({p5b_solved_count/max(total_p5b,1)*100:.1f}%)")
    print(f"R3:  {r3_solved_count}/{total_r3} solved ({r3_solved_count/max(total_r3,1)*100:.1f}%)")
    print(f"Delta: +{len(newly_solved) - len(lost_solved)} solved ({len(newly_solved)} new, -{len(lost_solved)} lost)")
    print()

    print("--- Attribution by Feature ---")
    print()
    print(f"{'Feature':<25} {'New Solves':>10} {'Cost (est)':>12}")
    print(f"{'-'*25} {'-'*10} {'-'*12}")
    print(f"{'Evolution (R1 diverse)':<25} {newly_r1:>10} ${r1_cost:>10.2f}")
    print(f"{'Diff Feedback (R2 rev)':<25} {newly_r2:>10} ${r2_cost:>10.2f}")
    print(f"{'Evolution (R3 hybrid)':<25} {newly_r3:>10} ${r3_round_cost:>10.2f}")
    print(f"{'Perception (w/ hints)':<25} {perception_newly:>10} {'included':>12}")
    print(f"{'No round info':<25} {no_round_info:>10} {'-':>12}")
    print()

    print("--- Cost Analysis ---")
    print()
    p5b_label = "(estimated)" if not p5b_has_telemetry else ""
    print(f"P5b total cost: ${p5b_total_cost:.4f} {p5b_label} ({p5b_calls} calls)")
    print(f"R3 total cost:  ${r3_total_cost:.4f} ({r3_calls} calls, {r3_total_tokens:,} tokens)")
    print(f"  Input tokens:  {r3_total_input_tokens:,}")
    print(f"  Output tokens: {r3_total_output_tokens:,}")
    print(f"  Cached tokens: {r3_total_cached_tokens:,}")
    cost_delta = r3_total_cost - p5b_total_cost
    pct = (cost_delta / max(p5b_total_cost, 0.01) * 100) if p5b_total_cost > 0 else float('inf')
    print(f"Cost delta:     ${cost_delta:.2f} ({pct:+.1f}%)")
    print()
    print(f"P5b cost/solved: ${p5b_cost_per:.4f} {p5b_label}")
    print(f"R3 cost/solved:  ${r3_cost_per:.4f}")
    if len(newly_solved) > 0:
        marginal_cost = (r3_total_cost - p5b_total_cost) / len(newly_solved)
        print(f"Marginal cost per new solve: ${marginal_cost:.4f}")
    print()

    print("--- Summary Table (for reviewer) ---")
    print()
    print(f"{'Feature':<25} {'Delta Solved':>12} {'Delta Cost':>12}")
    print(f"{'-'*25} {'-'*12} {'-'*12}")
    evolution_total = newly_r1 + newly_r3
    print(f"{'Evolution':<25} {f'+{evolution_total}':>12} {f'+${r1_cost + r3_round_cost:.2f}':>12}")
    print(f"{'Perception':<25} {f'+{perception_newly}':>12} {'~0% (deterministic)':>12}")
    print(f"{'Diff Feedback':<25} {f'+{newly_r2}':>12} {f'+${r2_cost:.2f}':>12}")
    print(f"{'Total':<25} {f'+{len(newly_solved) - len(lost_solved)}':>12} {f'${cost_delta:+.2f}':>12}")
    print()
    print(f"Marginal cost/new solve: ${cost_delta / max(len(newly_solved), 1):.4f}")
    print(f"R3 cost/solved:          ${r3_cost_per:.4f}")
    print(f"P5b cost/solved:         ${p5b_cost_per:.4f} {p5b_label}")
    print()

    # Save report as JSON
    report = {
        "p5b_solved": p5b_solved_count,
        "r3_solved": r3_solved_count,
        "newly_solved": list(newly_solved),
        "lost_solved": list(lost_solved),
        "attribution": {
            "evolution_r1": newly_r1,
            "evolution_r3": newly_r3,
            "diff_feedback_r2": newly_r2,
            "perception": perception_newly,
        },
        "cost": {
            "p5b_total": p5b_total_cost,
            "p5b_estimated": not p5b_has_telemetry,
            "r3_total": r3_total_cost,
            "r3_calls": r3_calls,
            "r3_input_tokens": r3_total_input_tokens,
            "r3_output_tokens": r3_total_output_tokens,
            "r3_cached_tokens": r3_total_cached_tokens,
            "r3_total_tokens": r3_total_tokens,
            "p5b_per_solved": p5b_cost_per,
            "r3_per_solved": r3_cost_per,
            "marginal_per_new_solve": cost_delta / max(len(newly_solved), 1),
            "r1_cost": r1_cost,
            "r2_cost": r2_cost,
            "r3_round_cost": r3_round_cost,
        },
    }
    Path("r3_attribution.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Detailed report saved to r3_attribution.json")


if __name__ == "__main__":
    main()
