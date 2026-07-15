"""tmp_r4_gap_analysis.py -- Analyze R3 unsolved tasks to inform R4 blueprint."""
import json, sys
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

r3 = json.loads(Path("r3_state.json").read_text(encoding="utf-8"))
results = r3.get("results", [])

unsolved = [r for r in results if r["status"] != "solved"]
solved = [r for r in results if r["status"] == "solved"]
print(f"Total: {len(results)}, Solved: {len(solved)}, Unsolved: {len(unsolved)}")

# Fitness distribution of unsolved tasks -> proxy for failure taxonomy
buckets = {"0.0-0.1 (no clue)": 0, "0.1-0.3 (wrong direction)": 0,
           "0.3-0.6 (partial pattern)": 0, "0.6-0.9 (close)": 0,
           "0.9-1.0 (very close / local optimum)": 0}
near_miss = []
no_clue = []
for r in unsolved:
    tel = r.get("telemetry", {})
    f = tel.get("best_fitness", 0) or 0
    if f < 0.1:
        buckets["0.0-0.1 (no clue)"] += 1
        no_clue.append((r["task_id"], f))
    elif f < 0.3:
        buckets["0.1-0.3 (wrong direction)"] += 1
    elif f < 0.6:
        buckets["0.3-0.6 (partial pattern)"] += 1
    elif f < 0.9:
        buckets["0.6-0.9 (close)"] += 1
    else:
        buckets["0.9-1.0 (very close / local optimum)"] += 1
        near_miss.append((r["task_id"], f))

print("\n=== Unsolved fitness distribution (proxy failure taxonomy) ===")
for k, v in buckets.items():
    print(f"  {k:<40} {v:>4}  ({v/len(unsolved)*100:.1f}%)")

print(f"\n=== Near-miss tasks (fitness >= 0.9, likely Search/Execution failures) ===")
print(f"  Count: {len(near_miss)}")
for tid, f in sorted(near_miss, key=lambda x: -x[1])[:20]:
    print(f"    {tid}: {f:.4f}")

print(f"\n=== No-clue tasks (fitness < 0.1, likely Perception failures) ===")
print(f"  Count: {len(no_clue)}")
for tid, f in sorted(no_clue)[:15]:
    print(f"    {tid}: {f:.4f}")

# Round progression on unsolved: did R2/R3 improve over R1?
improved_r2 = 0
improved_r3 = 0
stuck = 0
for r in unsolved:
    tel = r.get("telemetry", {})
    f1 = tel.get("round1_best_fitness", 0) or 0
    f2 = tel.get("round2_best_fitness", 0) or 0
    f3 = tel.get("round3_best_fitness", 0) or 0
    if f2 > f1 + 0.01:
        improved_r2 += 1
    if f3 > max(f1, f2) + 0.01:
        improved_r3 += 1
    if abs(f2 - f1) < 0.01 and abs(f3 - f1) < 0.01:
        stuck += 1

print(f"\n=== Round progression on unsolved tasks ===")
print(f"  R2 improved over R1: {improved_r2}/{len(unsolved)} ({improved_r2/len(unsolved)*100:.1f}%)")
print(f"  R3 improved over R1+R2: {improved_r3}/{len(unsolved)} ({improved_r3/len(unsolved)*100:.1f}%)")
print(f"  Completely stuck (no improvement R1->R3): {stuck}/{len(unsolved)} ({stuck/len(unsolved)*100:.1f}%)")

# Calls spent on unsolved (wasted budget)
unsolved_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in unsolved)
solved_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in solved)
print(f"\n=== Budget efficiency ===")
print(f"  Calls on solved:   {solved_calls} ({solved_calls/(solved_calls+unsolved_calls)*100:.1f}%)")
print(f"  Calls on unsolved: {unsolved_calls} ({unsolved_calls/(solved_calls+unsolved_calls)*100:.1f}%)")
print(f"  Avg calls per solved: {solved_calls/max(len(solved),1):.1f}")
print(f"  Avg calls per unsolved: {unsolved_calls/max(len(unsolved),1):.1f}")

# Solved-round distribution for context
sr = Counter(r.get("telemetry", {}).get("solved_round") for r in solved)
print(f"\n=== Solved by round: {dict(sr)} ===")

# Save summary json
out = {
    "unsolved_count": len(unsolved),
    "fitness_buckets": buckets,
    "near_miss_tasks": [t for t, _ in near_miss],
    "no_clue_tasks": [t for t, _ in no_clue],
    "stuck_count": stuck,
    "r2_improved": improved_r2,
    "r3_improved": improved_r3,
    "unsolved_calls": unsolved_calls,
    "solved_calls": solved_calls,
}
Path("r4_gap_analysis.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print("\nSaved to r4_gap_analysis.json")
