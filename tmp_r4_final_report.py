"""tmp_r4_final_report.py — Final comparison R4 vs R3."""
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

# Basic counts
r4_solved = sum(1 for r in r4["results"] if r["status"] == "solved")
r3_solved = sum(1 for r in r3["results"] if r["status"] == "solved")
print(f"=== Solved count ===")
print(f"R3: {r3_solved}/400 ({r3_solved/4:.1f}%)")
print(f"R4: {r4_solved}/400 ({r4_solved/4:.1f}%)")
print(f"Delta: {r4_solved - r3_solved:+d}")

# Regression analysis
r4_solved_ids = {r["task_id"] for r in r4["results"] if r["status"] == "solved"}
r3_solved_ids = {r["task_id"] for r in r3["results"] if r["status"] == "solved"}
regressed = r3_solved_ids - r4_solved_ids
gained = r4_solved_ids - r3_solved_ids
print(f"\n=== Regression ===")
print(f"R3 solved but R4 failed: {len(regressed)}")
print(f"R4 solved but R3 failed: {len(gained)}")
print(f"Net: {len(gained) - len(regressed):+d}")

# solved_round distribution
round_dist = Counter()
for r in r4["results"]:
    if r["status"] == "solved":
        rnd = r.get("telemetry", {}).get("solved_round")
        round_dist[rnd] += 1
print(f"\n=== R4 Solved by round ===")
for k in sorted(round_dist.keys(), key=lambda x: (x is None, x)):
    print(f"  Round {k}: {round_dist[k]}")

# None solved_round — what are they?
none_round = [r for r in r4["results"] if r["status"] == "solved" and r.get("telemetry", {}).get("solved_round") is None]
print(f"\n=== solved_round=None ({len(none_round)} tasks) ===")
for r in none_round[:10]:
    t = r.get("telemetry", {})
    print(f"  {r['task_id']}: calls={t.get('llm_calls',0)} fit={t.get('best_fitness',0):.2f} lat={r.get('latency_sec',0):.1f}s")

# Cost comparison
r4_cost = sum(r.get("telemetry", {}).get("total_cost_usd", 0) for r in r4["results"])
r3_cost = sum(r.get("telemetry", {}).get("total_cost_usd", 0) for r in r3["results"])
r4_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in r4["results"])
r3_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in r3["results"])
print(f"\n=== Cost & calls ===")
print(f"R3: {r3_calls} calls, ${r3_cost:.2f}")
print(f"R4: {r4_calls} calls, ${r4_cost:.2f}")

# T2 fallback count
t2_count = sum(1 for r in r4["results"] if r.get("telemetry", {}).get("t2_fallback_triggered", False))
print(f"\n=== T2 fallback triggered: {t2_count} ===")

# T4 EV stopping count
t4_skipped = sum(1 for r in r4["results"] if r.get("telemetry", {}).get("round3_calls", 0) == 0 and r.get("telemetry", {}).get("round2_calls", 0) > 0)
print(f"=== T4 EV stopping (R3 skipped): {t4_skipped} ===")

# R4 targeted repair
r4_repaired = sum(1 for r in r4["results"] if r.get("telemetry", {}).get("solved_round") == 4)
r4_attempted = sum(1 for r in r4["results"] if r.get("telemetry", {}).get("round4_calls", 0) > 0)
print(f"\n=== R4 Targeted Repair ===")
print(f"Attempted: {r4_attempted}")
print(f"Solved: {r4_repaired}")

# Regressed tasks detail
print(f"\n=== Regressed tasks (R3 solved, R4 failed) — first 20 ===")
for tid in sorted(regressed)[:20]:
    r4t = r4r[tid].get("telemetry", {})
    r3t = r3r[tid].get("telemetry", {})
    print(f"  {tid}: R3_rnd={r3t.get('solved_round')} R4_fit={r4t.get('best_fitness',0):.2f} R4_rnd={r4t.get('solved_round')} R4_calls={r4t.get('llm_calls',0)}")

# LLM unreachable count
unreachable = sum(1 for r in r4["results"] if r.get("status") == "llm_unreachable")
print(f"\n=== LLM unreachable: {unreachable} ===")

# Non-evo solved (calls=0)
non_evo = sum(1 for r in r4["results"] if r["status"] == "solved" and r.get("telemetry", {}).get("llm_calls", 0) == 0)
print(f"=== Non-evo solved (calls=0): {non_evo} ===")
