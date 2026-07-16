"""tmp_r4_diagnosis.py — Diagnose R4 regression vs R3."""
import json, sys
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

r4 = json.loads(Path("r4_state.json").read_text(encoding="utf-8"))
r3 = json.loads(Path("r3_state.json").read_text(encoding="utf-8"))

r4_results = {r["task_id"]: r for r in r4["results"]}
r3_results = {r["task_id"]: r for r in r3["results"]}

# Basic counts
r4_solved = {tid for tid, r in r4_results.items() if r["status"] == "solved"}
r3_solved = {tid for tid, r in r3_results.items() if r["status"] == "solved"}
print(f"R3 solved: {len(r3_solved)}")
print(f"R4 solved: {len(r4_solved)}")

# 1. None solved_round
none_round = [r for tid, r in r4_results.items() if r["status"] == "solved" and r.get("telemetry", {}).get("solved_round") is None]
print(f"\n=== 1. Solved but solved_round=None: {len(none_round)} ===")
for r in none_round:
    t = r.get("telemetry", {})
    print(f"  {r['task_id']}: fit={t.get('best_fitness',0):.2f} calls={t.get('llm_calls',0)} r1_fit={t.get('round1_best_fitness',0):.2f}")

# 2. Regression analysis
regressed = r3_solved - r4_solved  # solved in R3 but not R4
new_solved = r4_solved - r3_solved  # solved in R4 but not R3
print(f"\n=== 2. Regression vs R3 ===")
print(f"Regressed (R3 OK → R4 FAIL): {len(regressed)}")
print(f"New solved (R3 FAIL → R4 OK): {len(new_solved)}")
print(f"Net: {len(new_solved) - len(regressed)}")

# Show regressed tasks with fitness details
print(f"\n--- Regressed tasks (first 30) ---")
for tid in sorted(regressed)[:30]:
    r3r = r3_results.get(tid, {})
    r4r = r4_results.get(tid, {})
    r3t = r3r.get("telemetry", {})
    r4t = r4r.get("telemetry", {})
    print(f"  {tid}: R3 fit={r3t.get('best_fitness',0):.2f} rnd={r3t.get('solved_round')} | R4 fit={r4t.get('best_fitness',0):.2f} rnd={r4t.get('solved_round')} calls={r4t.get('llm_calls',0)}")

# 3. T2 fallback trigger detection
# T2 fallback: candidates with no strategy hint. Hard to detect directly from telemetry.
# But we can check: tasks where r1_best_fitness < 0.3 (fallback threshold)
print(f"\n=== 3. T2 Fallback Analysis ===")
r4_fail = {tid: r for tid, r in r4_results.items() if r["status"] != "solved"}
low_fitness_r1 = []
for tid, r in r4_fail.items():
    t = r.get("telemetry", {})
    r1_fit = t.get("round1_best_fitness", 0)
    if r1_fit < 0.3:
        low_fitness_r1.append((tid, r1_fit, t.get("best_fitness", 0), r3_solved.__contains__(tid)))

print(f"Tasks with R1 fitness < 0.3 (T2 trigger zone): {len(low_fitness_r1)}")
r3_ok_in_trigger = [x for x in low_fitness_r1 if x[3]]
print(f"  Of those, R3 solved them: {len(r3_ok_in_trigger)}")
for tid, r1f, bestf, r3ok in r3_ok_in_trigger[:20]:
    r3t = r3_results.get(tid, {}).get("telemetry", {})
    print(f"  {tid}: R1_fit={r1f:.2f} R4_best={bestf:.2f} R3_fit={r3t.get('best_fitness',0):.2f} R3_rnd={r3t.get('solved_round')}")

# 4. Cost comparison
r4_last_cost = max((r.get("telemetry", {}).get("total_cost_usd", 0) for r in r4_results.values()), default=0)
r3_last_cost = max((r.get("telemetry", {}).get("total_cost_usd", 0) for r in r3_results.values()), default=0)
r4_total_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in r4_results.values())
r3_total_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in r3_results.values())
print(f"\n=== 4. Cost & Calls ===")
print(f"R4: ${r4_last_cost:.4f} / {r4_total_calls} calls")
print(f"R3: ${r3_last_cost:.4f} / {r3_total_calls} calls")

# 5. R3 skipped count (T4 EV stopping)
r3_skipped = sum(1 for r in r4_results.values() if r.get("telemetry", {}).get("round3_calls", -1) == 0)
print(f"\n=== 5. T4 EV Stopping: R3 skipped ===")
print(f"Tasks where Round 3 was skipped: {r3_skipped}")

# 6. Round distribution
round_dist = Counter()
for r in r4_results.values():
    if r["status"] == "solved":
        sr = r.get("telemetry", {}).get("solved_round")
        round_dist[sr] += 1
print(f"\n=== 6. R4 Solved by round ===")
for rnd, cnt in sorted(round_dist.items(), key=lambda x: str(x[0])):
    print(f"  Round {rnd}: {cnt}")

# 7. Check if T2 fallback is breaking things — look at r1 fitness distribution
print(f"\n=== 7. R1 Fitness distribution (R4 failed tasks) ===")
r1_bins = Counter()
for tid, r in r4_fail.items():
    r1f = r.get("telemetry", {}).get("round1_best_fitness", 0)
    if r1f < 0.3: r1_bins["0.0-0.3"] += 1
    elif r1f < 0.6: r1_bins["0.3-0.6"] += 1
    elif r1f < 0.9: r1_bins["0.6-0.9"] += 1
    elif r1f < 1.0: r1_bins["0.9-1.0"] += 1
    else: r1_bins["1.0"] += 1
for k in ["0.0-0.3", "0.3-0.6", "0.6-0.9", "0.9-1.0", "1.0"]:
    print(f"  {k}: {r1_bins.get(k, 0)}")

# Compare R1 fitness for regressed tasks
print(f"\n=== 8. R1 fitness for regressed tasks ===")
regressed_r1 = []
for tid in regressed:
    r4t = r4_results[tid].get("telemetry", {})
    r3t = r3_results.get(tid, {}).get("telemetry", {})
    regressed_r1.append((tid, r4t.get("round1_best_fitness", 0), r3t.get("round1_best_fitness", 0), r4t.get("best_fitness", 0)))
for tid, r4r1, r3r1, r4best in sorted(regressed_r1, key=lambda x: -x[3])[:30]:
    print(f"  {tid}: R4_R1={r4r1:.2f} R3_R1={r3r1:.2f} R4_best={r4best:.2f}")
