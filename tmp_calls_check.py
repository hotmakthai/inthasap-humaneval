"""tmp_calls_check.py -- Verify llm_calls anomaly."""
import json, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

r3 = json.loads(Path("r3_state.json").read_text(encoding="utf-8"))
results = r3.get("results", [])

anomalies = [(r["task_id"], r["status"], r.get("telemetry", {}).get("llm_calls", 0))
             for r in results if r.get("telemetry", {}).get("llm_calls", 0) > 12]
print(f"Tasks with llm_calls > 12: {len(anomalies)}")
for tid, st, c in anomalies[:20]:
    print(f"  {tid}: status={st} calls={c}")

normal_calls = sum(min(r.get("telemetry", {}).get("llm_calls", 0), 12) for r in results)
raw_calls = sum(r.get("telemetry", {}).get("llm_calls", 0) for r in results)
print(f"\nRaw sum llm_calls: {raw_calls}")
print(f"Capped-at-12 sum: {normal_calls}")

# Check if anomalous values correlate with round calls
for tid, st, c in anomalies[:5]:
    r = next(x for x in results if x["task_id"] == tid)
    tel = r.get("telemetry", {})
    print(f"\n{tid}: calls={c} r1={tel.get('round1_calls')} r2={tel.get('round2_calls')} r3={tel.get('round3_calls')} solved_round={tel.get('solved_round')} cand_gen={tel.get('candidates_generated')}")
