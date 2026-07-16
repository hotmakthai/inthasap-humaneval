"""tmp_r4_zero_fitness.py — Why do 112 tasks have R1 fitness=0.00 in R4 but 1.00 in R3?
Check if it's LLM error, code extraction failure, or runtime error."""
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

# Find tasks: R4 R1=0.00, R3 R1=1.00, calls=8
zero_tasks = []
for tid, r in r4r.items():
    r4t = r.get("telemetry", {})
    r3t = r3r.get(tid, {}).get("telemetry", {})
    if (r4t.get("round1_best_fitness", 0) == 0.0 
        and r3t.get("round1_best_fitness", 0) == 1.0
        and r4t.get("llm_calls", 0) == 8):
        zero_tasks.append(tid)

print(f"Total zero-fitness tasks: {len(zero_tasks)}")

# Check candidates_generated — if 0, LLM returned no valid code
# If 8 but fitness=0, code runs but produces wrong output
# If <8, some calls failed to produce code
zero_details = []
for tid in zero_tasks[:30]:
    r4t = r4r[tid].get("telemetry", {})
    cand_gen = r4t.get("candidates_generated", 0)
    calls = r4t.get("llm_calls", 0)
    best = r4t.get("best_fitness", 0)
    trajectory = r4t.get("fitness_trajectory", [])
    # trajectory has (round, idx, fitness) tuples
    r1_trajectories = [t for t in trajectory if t[0] == 1] if trajectory else []
    zero_details.append((tid, calls, cand_gen, best, len(r1_trajectories), r1_trajectories[:3]))

print(f"\n--- First 30 tasks ---")
for tid, calls, cand_gen, best, n_traj, traj_sample in zero_details:
    print(f"  {tid}: calls={calls} cand_gen={cand_gen} best={best:.2f} traj_pts={n_traj} sample={traj_sample}")

# If candidates_generated == 0, LLM didn't return valid Python code
# If candidates_generated == 8 but all fitness=0, code runs but wrong output
no_code = sum(1 for _, _, cg, _, _, _ in zero_details if cg == 0)
some_code = sum(1 for _, _, cg, _, _, _ in zero_details if 0 < cg < 8)
all_code = sum(1 for _, _, cg, _, _, _ in zero_details if cg == 8)
print(f"\nSummary (first 30):")
print(f"  No valid code (cand_gen=0): {no_code}")
print(f"  Some code (0<cand_gen<8): {some_code}")
print(f"  All code (cand_gen=8): {all_code}")

# Check all 112
all_details = []
for tid in zero_tasks:
    r4t = r4r[tid].get("telemetry", {})
    cand_gen = r4t.get("candidates_generated", 0)
    all_details.append((tid, cand_gen))

no_code_all = sum(1 for _, cg in all_details if cg == 0)
some_code_all = sum(1 for _, cg in all_details if 0 < cg < 8)
all_code_all = sum(1 for _, cg in all_details if cg == 8)
print(f"\nSummary (all {len(zero_tasks)}):")
print(f"  No valid code (cand_gen=0): {no_code_all}")
print(f"  Some code (0<cand_gen<8): {some_code_all}")
print(f"  All code (cand_gen=8): {all_code_all}")

# Check if these are the same 19 non-evo tasks
non_evo = [tid for tid in zero_tasks if r4r[tid].get("telemetry", {}).get("solved_round") is None and r4r[tid]["status"] == "solved"]
print(f"\nOf these, solved without LLM (non-evo): {len(non_evo)}")
print(f"Unsolved: {len(zero_tasks) - len(non_evo)}")
