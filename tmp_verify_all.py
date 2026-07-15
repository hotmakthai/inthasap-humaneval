"""tmp_verify_all.py -- Full verification of all numbers cited in blueprint and report."""
import json, sys
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

p5b = json.loads(Path("p5b_state.json").read_text(encoding="utf-8"))
r3 = json.loads(Path("r3_state.json").read_text(encoding="utf-8"))
results = r3.get("results", [])
p5b_results = {r["task_id"]: r for r in p5b.get("results", [])}
r3_results = {r["task_id"]: r for r in results}

print("=" * 70)
print("VERIFICATION 1: Basic counts")
print("=" * 70)
p5b_solved = {t for t, r in p5b_results.items() if r["status"] == "solved"}
r3_solved = {t for t, r in r3_results.items() if r["status"] == "solved"}
newly = r3_solved - p5b_solved
lost = p5b_solved - r3_solved
print(f"  P5b solved: {len(p5b_solved)}/400  (claim: 97) {'OK' if len(p5b_solved)==97 else 'MISMATCH!'}")
print(f"  R3 solved: {len(r3_solved)}/400  (claim: 220) {'OK' if len(r3_solved)==220 else 'MISMATCH!'}")
print(f"  Newly: {len(newly)} (claim: 125) {'OK' if len(newly)==125 else 'MISMATCH!'}")
print(f"  Lost: {len(lost)} (claim: 2) {'OK' if len(lost)==2 else 'MISMATCH!'}")
print(f"  Lost tasks: {sorted(lost)} (claim: a68b268e, 75b8110e)")
print(f"  Unique task_ids: {len(r3_results)} (should be 400)")
print(f"  Duplicates in results list: {len(results) - len(r3_results)}")

print()
print("=" * 70)
print("VERIFICATION 2: Attribution by round")
print("=" * 70)
newly_by_round = Counter()
all_solved_by_round = Counter()
for t in r3_solved:
    sr = r3_results[t].get("telemetry", {}).get("solved_round")
    all_solved_by_round[sr] += 1
    if t in newly:
        newly_by_round[sr] += 1
print(f"  All solved by round: {dict(all_solved_by_round)}")
print(f"    claim: R1=181, R2=16, R3=4, None=19")
print(f"  Newly solved by round: {dict(newly_by_round)}")
print(f"    claim: R1=+106, R2=+15, R3=+4, None=0")

print()
print("=" * 70)
print("VERIFICATION 3: Cost & tokens (cumulative check)")
print("=" * 70)
last_tel = results[-1].get("telemetry", {})
print(f"  Last task cumulative cost: ${last_tel.get('total_cost_usd', 0):.4f} (claim: $6.63)")
print(f"  Last input tokens: {last_tel.get('total_input_tokens', 0):,} (claim: 8,517,879)")
print(f"  Last output tokens: {last_tel.get('total_output_tokens', 0):,} (claim: 3,742,163)")
# Check monotonic increase (confirms cumulative)
costs = [r.get("telemetry", {}).get("total_cost_usd", 0) for r in results]
mono = all(costs[i] <= costs[i+1] + 1e-9 for i in range(len(costs)-1))
print(f"  Cost monotonically increasing (= cumulative confirmed): {mono}")

print()
print("=" * 70)
print("VERIFICATION 4: llm_calls anomaly (telemetry bug)")
print("=" * 70)
anomalies = [(r["task_id"], r.get("telemetry", {}).get("llm_calls", 0), r.get("telemetry", {}).get("solved_round"))
             for r in results if r.get("telemetry", {}).get("llm_calls", 0) > 12]
print(f"  Tasks with calls > 12: {len(anomalies)} (claim: 19)")
all_none_round = all(sr is None for _, _, sr in anomalies)
print(f"  All anomalies have solved_round=None (non-evo path): {all_none_round}")
# What's the realistic total? Evo tasks have valid per-task calls.
evo_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in results
                if r.get("telemetry", {}).get("llm_calls", 0) <= 12)
n_evo = sum(1 for r in results if r.get("telemetry", {}).get("llm_calls", 0) <= 12)
print(f"  Valid per-task calls sum ({n_evo} tasks): {evo_calls}")
print(f"  + 19 non-evo tasks (~1-2 calls each): ~{evo_calls + 19} to ~{evo_calls + 38}")

print()
print("=" * 70)
print("VERIFICATION 5: Fitness distribution of 180 unsolved (CRITICAL)")
print("=" * 70)
unsolved = [r for r in results if r["status"] != "solved"]
print(f"  Unsolved count: {len(unsolved)} (claim: 180)")
buckets = Counter()
for r in unsolved:
    f = r.get("telemetry", {}).get("best_fitness", 0) or 0
    if f < 0.1: buckets["<0.1"] += 1
    elif f < 0.3: buckets["0.1-0.3"] += 1
    elif f < 0.6: buckets["0.3-0.6"] += 1
    elif f < 0.9: buckets["0.6-0.9"] += 1
    else: buckets[">=0.9"] += 1
print(f"  Buckets: {dict(buckets)}")
print(f"    claim: <0.1=1, 0.1-0.3=5, 0.3-0.6=22, 0.6-0.9=65, >=0.9=87")
# Sanity: does best_fitness match max over round fitnesses?
mismatch_fit = 0
for r in unsolved:
    tel = r.get("telemetry", {})
    bf = tel.get("best_fitness", 0) or 0
    mx = max(tel.get("round1_best_fitness", 0) or 0,
             tel.get("round2_best_fitness", 0) or 0,
             tel.get("round3_best_fitness", 0) or 0)
    if abs(bf - mx) > 0.001:
        mismatch_fit += 1
print(f"  best_fitness != max(round fitnesses): {mismatch_fit} tasks")

print()
print("=" * 70)
print("VERIFICATION 6: 'Stuck 83%' claim (SUSPECT - re-check logic)")
print("=" * 70)
# Check whether round2/3 fitness fields are actually populated on unsolved
r2_zero = sum(1 for r in unsolved if (r.get("telemetry", {}).get("round2_best_fitness", 0) or 0) == 0)
r3_zero = sum(1 for r in unsolved if (r.get("telemetry", {}).get("round3_best_fitness", 0) or 0) == 0)
print(f"  Unsolved with round2_best_fitness == 0: {r2_zero}/180")
print(f"  Unsolved with round3_best_fitness == 0: {r3_zero}/180")
# Check calls per round on unsolved
r2_calls_zero = sum(1 for r in unsolved if (r.get("telemetry", {}).get("round2_calls", 0) or 0) == 0)
r3_calls_zero = sum(1 for r in unsolved if (r.get("telemetry", {}).get("round3_calls", 0) or 0) == 0)
print(f"  Unsolved with round2_calls == 0: {r2_calls_zero}/180")
print(f"  Unsolved with round3_calls == 0: {r3_calls_zero}/180")

# ORIGINAL stuck logic (potentially wrong):
stuck_v1 = 0
for r in unsolved:
    tel = r.get("telemetry", {})
    f1 = tel.get("round1_best_fitness", 0) or 0
    f2 = tel.get("round2_best_fitness", 0) or 0
    f3 = tel.get("round3_best_fitness", 0) or 0
    if abs(f2 - f1) < 0.01 and abs(f3 - f1) < 0.01:
        stuck_v1 += 1
print(f"  Stuck (original logic v1): {stuck_v1}/180 ({stuck_v1/180*100:.1f}%) -- claim: 150 (83.3%)")

# CORRECTED stuck logic: only count if R2/R3 actually ran (calls > 0),
# and improvement means f2 > f1 or f3 > max(f1,f2)
stuck_v2 = 0
improved_r2_v2 = 0
improved_r3_v2 = 0
not_run_r2 = 0
for r in unsolved:
    tel = r.get("telemetry", {})
    f1 = tel.get("round1_best_fitness", 0) or 0
    f2 = tel.get("round2_best_fitness", 0) or 0
    f3 = tel.get("round3_best_fitness", 0) or 0
    c2 = tel.get("round2_calls", 0) or 0
    c3 = tel.get("round3_calls", 0) or 0
    if c2 == 0:
        not_run_r2 += 1
        continue
    imp2 = f2 > f1 + 0.01
    imp3 = f3 > max(f1, f2) + 0.01
    if imp2: improved_r2_v2 += 1
    if imp3: improved_r3_v2 += 1
    if not imp2 and not imp3:
        stuck_v2 += 1
print(f"  R2 did not run (calls=0): {not_run_r2}")
print(f"  Stuck (corrected v2, among tasks where R2 ran): {stuck_v2}")
print(f"  Improved by R2 (v2): {improved_r2_v2}")
print(f"  Improved by R3 (v2): {improved_r3_v2}")

print()
print("=" * 70)
print("VERIFICATION 7: Perception hint counts")
print("=" * 70)
with_hints = sum(1 for r in results if r.get("telemetry", {}).get("had_perception_hints"))
without = 400 - with_hints
wh_solved = sum(1 for r in results if r.get("telemetry", {}).get("had_perception_hints") and r["status"] == "solved")
wo_solved = sum(1 for r in results if not r.get("telemetry", {}).get("had_perception_hints") and r["status"] == "solved")
newly_with_hints = sum(1 for t in newly if r3_results[t].get("telemetry", {}).get("had_perception_hints"))
print(f"  With hints: {with_hints} (claim: 381), solved: {wh_solved} (claim: 201)")
print(f"  Without hints: {without} (claim: 19), solved: {wo_solved} (claim: 19)")
print(f"  Newly solved with hints: {newly_with_hints}/{len(newly)} (claim: 125/125)")

print()
print("=" * 70)
print("VERIFICATION 8: Regression task details")
print("=" * 70)
for tid in sorted(lost):
    tel = r3_results[tid].get("telemetry", {})
    print(f"  {tid}: best_fitness={tel.get('best_fitness')} r1={tel.get('round1_best_fitness')} "
          f"r2={tel.get('round2_best_fitness')} r3={tel.get('round3_best_fitness')} "
          f"r2_calls={tel.get('round2_calls')} r3_calls={tel.get('round3_calls')}")

print()
print("=" * 70)
print("VERIFICATION 9: Near-miss examples cited in blueprint")
print("=" * 70)
for tid in ["3631a71a", "72322fa7", "484b58aa"]:
    r = r3_results.get(tid)
    if r:
        f = r.get("telemetry", {}).get("best_fitness", 0)
        print(f"  {tid}: status={r['status']} fitness={f:.4f}")

print()
print("=" * 70)
print("VERIFICATION 10: Q2 diff-feedback examples cited in report")
print("=" * 70)
for tid in ["d687bc17", "5c0a986e", "6b9890af"]:
    r = r3_results.get(tid)
    if r:
        tel = r.get("telemetry", {})
        print(f"  {tid}: status={r['status']} solved_round={tel.get('solved_round')} "
              f"r1={tel.get('round1_best_fitness'):.3f} r2={tel.get('round2_best_fitness'):.3f} "
              f"calls={tel.get('llm_calls')}")
