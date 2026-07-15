"""tmp_regression_analysis.py -- Find and analyze the 2 regression tasks."""
import json, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

p5b = json.loads(Path("p5b_state.json").read_text(encoding="utf-8"))
r3 = json.loads(Path("r3_state.json").read_text(encoding="utf-8"))

p5b_results = {r["task_id"]: r for r in p5b.get("results", [])}
r3_results = {r["task_id"]: r for r in r3.get("results", [])}

p5b_solved = {tid for tid, r in p5b_results.items() if r["status"] == "solved"}
r3_solved = {tid for tid, r in r3_results.items() if r["status"] == "solved"}

lost = p5b_solved - r3_solved
print(f"Regression tasks (P5b solved, R3 failed): {lost}")
print()

for tid in lost:
    p5b_r = p5b_results.get(tid, {})
    r3_r = r3_results.get(tid, {})
    tel = r3_r.get("telemetry", {})
    
    print(f"=== Task {tid} ===")
    print(f"  P5b status: {p5b_r.get('status', '?')}")
    print(f"  P5b candidate: {str(p5b_r.get('candidate', 'N/A'))[:120]}...")
    print(f"  R3 status: {r3_r.get('status', '?')}")
    print(f"  R3 telemetry:")
    print(f"    solved_round: {tel.get('solved_round')}")
    print(f"    llm_calls: {tel.get('llm_calls')}")
    print(f"    best_fitness: {tel.get('best_fitness')}")
    print(f"    round1_best_fitness: {tel.get('round1_best_fitness')}")
    print(f"    round2_best_fitness: {tel.get('round2_best_fitness')}")
    print(f"    round3_best_fitness: {tel.get('round3_best_fitness')}")
    print(f"    had_perception_hints: {tel.get('had_perception_hints')}")
    print(f"    fitness_trajectory (first 10): {tel.get('fitness_trajectory', [])[:10]}")
    print(f"    round1_calls: {tel.get('round1_calls')}")
    print(f"    round2_calls: {tel.get('round2_calls')}")
    print(f"    round3_calls: {tel.get('round3_calls')}")
    print(f"  R3 candidate: {str(r3_r.get('candidate', 'N/A'))[:120]}...")
    print()

# Also compute some stats for Q4 (statistical significance)
print("\n=== Q4: Variance analysis across task subsets ===")
r3_raw = r3.get("results", [])
solved_flags = [1 if r["status"] == "solved" else 0 for r in r3_raw]

# Split into 4 quarters
n = len(solved_flags)
q = n // 4
quarters = [solved_flags[i*q:(i+1)*q] for i in range(4)]
for i, q_data in enumerate(quarters):
    s = sum(q_data)
    print(f"  Quarter {i+1} (tasks {i*q+1}-{(i+1)*q}): {s}/{len(q_data)} solved ({s/len(q_data)*100:.1f}%)")

# Split into 10 deciles
d = n // 10
deciles = [solved_flags[i*d:(i+1)*d] for i in range(10)]
print()
for i, d_data in enumerate(deciles):
    s = sum(d_data)
    print(f"  Decile {i+1}: {s}/{len(d_data)} solved ({s/len(d_data)*100:.1f}%)")

# Bootstrap-like analysis: random subsets
import random
random.seed(42)
subset_solves = []
for _ in range(100):
    sample = random.sample(solved_flags, 100)
    subset_solves.append(sum(sample))
mean_s = sum(subset_solves) / len(subset_solves)
var_s = sum((x - mean_s)**2 for x in subset_solves) / len(subset_solves)
std_s = var_s ** 0.5
print(f"\n  Bootstrap (100 random subsets of 100 tasks):")
print(f"    Mean solves per 100: {mean_s:.1f}")
print(f"    Std dev: {std_s:.2f}")
print(f"    95% CI: [{mean_s - 1.96*std_s:.1f}, {mean_s + 1.96*std_s:.1f}]")
print(f"    Projected for 400: {mean_s*4:.0f} ± {1.96*std_s*4:.0f}")
