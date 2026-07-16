"""tmp_r4_postmortem.py — R4 Postmortem: 3 groups of unsolved tasks + R3 cost verification."""
import json, sys
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

r4 = json.loads(Path("r4_state.json").read_text(encoding="utf-8"))
r3 = json.loads(Path("r3_state.json").read_text(encoding="utf-8"))
r4r = {r["task_id"]: r for r in r4["results"]}
r3r = {r["task_id"]: r for r in r3["results"]}

# ═══════════════════════════════════════════════
# Part 1: R3 Cost Verification
# ═══════════════════════════════════════════════
print("=" * 70)
print("PART 1: R3 Cost Verification")
print("=" * 70)

# Check R3 telemetry fields — is total_cost_usd per-task or cumulative?
r3_costs = []
r3_tokens_in = []
r3_tokens_out = []
for r in r3["results"]:
    t = r.get("telemetry", {})
    r3_costs.append(t.get("total_cost_usd", 0))
    r3_tokens_in.append(t.get("total_input_tokens", 0))
    r3_tokens_out.append(t.get("total_output_tokens", 0))

# If cumulative, the last value should be the total
# If per-task, sum should be the total
sum_cost = sum(r3_costs)
last_cost = r3_costs[-1] if r3_costs else 0
max_cost = max(r3_costs) if r3_costs else 0

print(f"\nR3 total_cost_usd field:")
print(f"  Sum of all tasks: ${sum_cost:.2f}")
print(f"  Last task value:  ${last_cost:.2f}")
print(f"  Max task value:   ${max_cost:.2f}")
print(f"  First 5 values:   {[round(c,4) for c in r3_costs[:5]]}")
print(f"  Last 5 values:    {[round(c,4) for c in r3_costs[-5:]]}")

# Check if values are monotonic (cumulative) or independent (per-task)
is_monotonic = all(r3_costs[i] <= r3_costs[i+1] + 0.001 for i in range(len(r3_costs)-1) if r3_costs[i] > 0)
print(f"\n  Monotonic increasing? {is_monotonic}")
if is_monotonic:
    print(f"  → R3 telemetry is CUMULATIVE (T0 bug — not reset per task)")
    print(f"  → True R3 cost = last value = ${last_cost:.2f}")
    print(f"  → But this is WRONG — T0 was supposed to fix this in R4")
    print(f"  → R3 cost was calculated with cumulative bug, so $1,218.71 is inflated")
else:
    print(f"  → R3 telemetry is PER-TASK")
    print(f"  → True R3 cost = sum = ${sum_cost:.2f}")

# Check R3 calls
r3_calls = [r.get("telemetry", {}).get("llm_calls", 0) for r in r3["results"]]
sum_calls = sum(r3_calls)
last_calls = r3_calls[-1] if r3_calls else 0
print(f"\nR3 llm_calls field:")
print(f"  Sum of all tasks: {sum_calls}")
print(f"  Last task value:  {last_calls}")
print(f"  First 5 values:   {r3_calls[:5]}")
print(f"  Last 5 values:    {r3_calls[-5:]}")

# Check R4 for comparison
r4_costs = [r.get("telemetry", {}).get("total_cost_usd", 0) for r in r4["results"]]
r4_calls_list = [r.get("telemetry", {}).get("llm_calls", 0) for r in r4["results"]]
print(f"\nR4 total_cost_usd field (for comparison):")
print(f"  Sum of all tasks: ${sum(r4_costs):.2f}")
print(f"  First 5 values:   {[round(c,4) for c in r4_costs[:5]]}")
print(f"  Last 5 values:    {[round(c,4) for c in r4_costs[-5:]]}")
print(f"  R4 is per-task (T0 fix): {not all(r4_costs[i] <= r4_costs[i+1] + 0.001 for i in range(len(r4_costs)-1) if r4_costs[i] > 0)}")

# True cost comparison
# R3: if cumulative, real cost = sum of DELTAS between consecutive tasks
# But if T0 bug made it cumulative, the per-task cost is the delta
r3_deltas = []
for i in range(len(r3_costs)):
    if i == 0:
        r3_deltas.append(r3_costs[0])
    else:
        r3_deltas.append(max(0, r3_costs[i] - r3_costs[i-1]))
r3_true_cost = sum(r3_deltas)
print(f"\nR3 true cost (sum of deltas if cumulative): ${r3_true_cost:.2f}")
print(f"R4 true cost (sum of per-task): ${sum(r4_costs):.2f}")

# Also check R3 summary
r3_summary_path = Path("r3_summary.json")
if r3_summary_path.exists():
    r3_summary = json.loads(r3_summary_path.read_text(encoding="utf-8"))
    print(f"\nR3 summary file cost: ${r3_summary.get('total_cost_usd', 'N/A')}")

# ═══════════════════════════════════════════════
# Part 2: R4 Postmortem — 3 groups
# ═══════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 2: R4 Postmortem — Unsolved Task Groups")
print("=" * 70)

unsolved = [r for r in r4["results"] if r["status"] != "solved"]
print(f"\nTotal unsolved: {len(unsolved)}")

# Group 1: best_fitness > 0.95 (refinement problem)
group1 = sorted(
    [r for r in unsolved if r.get("telemetry", {}).get("best_fitness", 0) > 0.95],
    key=lambda r: r.get("telemetry", {}).get("best_fitness", 0),
    reverse=True
)
print(f"\n--- Group 1: best_fitness > 0.95 (Refinement Problem) — {len(group1)} tasks ---")
for r in group1[:20]:
    t = r.get("telemetry", {})
    fit = t.get("best_fitness", 0)
    calls = t.get("llm_calls", 0)
    r4_calls = t.get("round4_calls", 0)
    r3_status = r3r.get(r["task_id"], {}).get("status", "?")
    r3rnd = r3r.get(r["task_id"], {}).get("telemetry", {}).get("solved_round", "?")
    r1 = t.get("round1_best_fitness", 0)
    r2 = t.get("round2_best_fitness", 0)
    print(f"  {r['task_id']}: fit={fit:.3f} r1={r1:.2f} r2={r2:.2f} calls={calls} r4={r4_calls} R3={r3_status}({r3rnd})")

# Group 2: 0.80 <= best_fitness <= 0.95 (search problem)
group2 = sorted(
    [r for r in unsolved if 0.80 <= r.get("telemetry", {}).get("best_fitness", 0) <= 0.95],
    key=lambda r: r.get("telemetry", {}).get("best_fitness", 0),
    reverse=True
)
print(f"\n--- Group 2: 0.80 ≤ best_fitness ≤ 0.95 (Search Problem) — {len(group2)} tasks ---")
for r in group2[:20]:
    t = r.get("telemetry", {})
    fit = t.get("best_fitness", 0)
    calls = t.get("llm_calls", 0)
    r3_status = r3r.get(r["task_id"], {}).get("status", "?")
    r3rnd = r3r.get(r["task_id"], {}).get("telemetry", {}).get("solved_round", "?")
    r1 = t.get("round1_best_fitness", 0)
    r2 = t.get("round2_best_fitness", 0)
    r3_fit = t.get("round3_best_fitness", 0)
    print(f"  {r['task_id']}: fit={fit:.3f} r1={r1:.2f} r2={r2:.2f} r3={r3_fit:.2f} calls={calls} R3={r3_status}({r3rnd})")

# Group 3: best_fitness < 0.50 (perception/representation problem)
group3 = sorted(
    [r for r in unsolved if r.get("telemetry", {}).get("best_fitness", 0) < 0.50],
    key=lambda r: r.get("telemetry", {}).get("best_fitness", 0),
)
print(f"\n--- Group 3: best_fitness < 0.50 (Perception/Representation Problem) — {len(group3)} tasks ---")
for r in group3[:20]:
    t = r.get("telemetry", {})
    fit = t.get("best_fitness", 0)
    calls = t.get("llm_calls", 0)
    r3_status = r3r.get(r["task_id"], {}).get("status", "?")
    r3rnd = r3r.get(r["task_id"], {}).get("telemetry", {}).get("solved_round", "?")
    r1 = t.get("round1_best_fitness", 0)
    cg = t.get("candidates_generated", 0)
    print(f"  {r['task_id']}: fit={fit:.3f} r1={r1:.2f} cand={cg} calls={calls} R3={r3_status}({r3rnd})")

# Summary stats
print(f"\n--- Summary ---")
print(f"  Refinement (>0.95):   {len(group1)} tasks")
print(f"  Search (0.80-0.95):   {len(group2)} tasks")
print(f"  Perception (<0.50):   {len(group3)} tasks")
print(f"  Middle (0.50-0.80):   {len(unsolved) - len(group1) - len(group2) - len(group3)} tasks")
print(f"  Total unsolved:       {len(unsolved)} tasks")

# Cross-reference with R3
g1_r3_solved = sum(1 for r in group1 if r3r.get(r["task_id"], {}).get("status") == "solved")
g2_r3_solved = sum(1 for r in group2 if r3r.get(r["task_id"], {}).get("status") == "solved")
g3_r3_solved = sum(1 for r in group3 if r3r.get(r["task_id"], {}).get("status") == "solved")
print(f"\n  Of these, R3 solved:")
print(f"    Refinement (>0.95): {g1_r3_solved}/{len(group1)}")
print(f"    Search (0.80-0.95): {g2_r3_solved}/{len(group2)}")
print(f"    Perception (<0.50): {g3_r3_solved}/{len(group3)}")
