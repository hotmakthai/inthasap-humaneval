"""tmp_r4_diagnosis2.py — Deeper dive: why R1 fitness=0.00 for tasks R3 solved with R1=1.00?"""
import json, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

r4 = json.loads(Path("r4_state.json").read_text(encoding="utf-8"))
r3 = json.loads(Path("r3_state.json").read_text(encoding="utf-8"))

r4r = {r["task_id"]: r for r in r4["results"]}
r3r = {r["task_id"]: r for r in r3["results"]}

# Tasks where R4 R1=0.00 but R3 R1=1.00 (solved in round 1 in R3)
zero_r1 = []
for tid, r in r4r.items():
    r4t = r.get("telemetry", {})
    r3t = r3r.get(tid, {}).get("telemetry", {})
    if r4t.get("round1_best_fitness", 0) == 0.0 and r3t.get("round1_best_fitness", 0) == 1.0:
        zero_r1.append((tid, r4t.get("llm_calls", 0), r4t.get("best_fitness", 0)))

print(f"Tasks where R4 R1=0.00 but R3 R1=1.00: {len(zero_r1)}")
print(f"\nChecking calls pattern — 8 calls = 8 R1 candidates (no R2/R3/R4)")
eight_calls = [x for x in zero_r1 if x[1] == 8]
other_calls = [x for x in zero_r1 if x[1] != 8]
print(f"  With 8 calls (R1 only, all candidates fitness=0): {len(eight_calls)}")
print(f"  With other call counts: {len(other_calls)}")
for tid, calls, best in other_calls[:10]:
    print(f"    {tid}: calls={calls} best={best:.2f}")

# Check: is T2 fallback making things worse? 
# T2 triggers when ALL R1 candidates < 0.3, then tries 2 more without strategy hint
# If R3 solved these with strategy hints in R1, then T2 fallback is replacing good hints
print(f"\n=== T2 Fallback Impact ===")
# 8 calls = 8 R1 candidates (no fallback triggered, no R2/R3)
# 10 calls = 8 R1 + 2 fallback (T2 triggered)
# 11+ = R1 + fallback + R2...
ten_calls = []
for tid, r in r4r.items():
    r4t = r.get("telemetry", {})
    if r4t.get("llm_calls", 0) == 10 and r4t.get("round1_best_fitness", 0) < 0.3:
        r3t = r3r.get(tid, {}).get("telemetry", {})
        ten_calls.append((tid, r4t.get("best_fitness", 0), r3t.get("best_fitness", 0), r3t.get("solved_round")))

print(f"Tasks with 10 calls (8 R1 + 2 T2 fallback): {len(ten_calls)}")
r3_solved_ten = [x for x in ten_calls if x[3] is not None]
print(f"  R3 solved them: {len(r3_solved_ten)}")
for tid, r4best, r3best, r3rnd in r3_solved_ten[:15]:
    print(f"  {tid}: R4_best={r4best:.2f} R3_best={r3best:.2f} R3_rnd={r3rnd}")

# Check: T4 EV stopping — how many tasks had R3 skipped and were R3-solved?
r3_skipped_and_solved_in_r3 = 0
r3_skipped_total = 0
for tid, r in r4r.items():
    r4t = r.get("telemetry", {})
    if r4t.get("round3_calls", -1) == 0:
        r3_skipped_total += 1
        if r3r.get(tid, {}).get("status") == "solved":
            r3_solved_in_r3 = r3r[tid].get("telemetry", {}).get("solved_round")
            if r3_solved_in_r3 in [3]:
                r3_skipped_and_solved_in_r3 += 1

print(f"\n=== T4 EV Stopping Impact ===")
print(f"R3 skipped in R4: {r3_skipped_total}")
print(f"  Of those, R3 solved them in Round 3: {r3_skipped_and_solved_in_r3}")

# Cost issue — $0.0656 is suspiciously low
print(f"\n=== Cost Analysis ===")
costs = [(r["task_id"], r.get("telemetry", {}).get("total_cost_usd", 0)) for r in r4["results"]]
costs_sorted = sorted(costs, key=lambda x: -x[1])
print(f"Top 5 costs:")
for tid, c in costs_sorted[:5]:
    print(f"  {tid}: ${c:.6f}")
print(f"Max cost: ${costs_sorted[0][1]:.6f}")
print(f"R3 max cost: ${max(r.get('telemetry',{}).get('total_cost_usd',0) for r in r3['results']):.6f}")

# Check if cost is per-task now (not cumulative)
first_5 = [(r["task_id"], r.get("telemetry", {}).get("total_cost_usd", 0)) for r in r4["results"][:5]]
print(f"\nFirst 5 tasks cost:")
for tid, c in first_5:
    print(f"  {tid}: ${c:.6f}")
