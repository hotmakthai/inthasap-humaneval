"""tmp_r4_latency.py — Check latency pattern to find where LLM calls failed."""
import json, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

r4 = json.loads(Path("r4_state.json").read_text(encoding="utf-8"))

# Group by calls vs cand_gen
zero_code = []  # calls=8, cand_gen=0
normal = []     # calls>0, cand_gen>0

for r in r4["results"]:
    t = r.get("telemetry", {})
    calls = t.get("llm_calls", 0)
    cg = t.get("candidates_generated", 0)
    lat = r.get("latency_sec", 0)
    if calls > 0 and cg == 0:
        zero_code.append((r["task_id"], calls, lat))
    elif calls > 0:
        normal.append((r["task_id"], calls, cg, lat))

print(f"Tasks with LLM calls but 0 candidates: {len(zero_code)}")
print(f"Tasks with LLM calls and >0 candidates: {len(normal)}")

# Latency comparison
if zero_code:
    avg_zero = sum(x[2] for x in zero_code) / len(zero_code)
    print(f"\nZero-code tasks: avg latency={avg_zero:.1f}s")
    print(f"  Latency range: {min(x[2] for x in zero_code):.1f}s - {max(x[2] for x in zero_code):.1f}s")
    print(f"  First 10:")
    for tid, calls, lat in zero_code[:10]:
        print(f"    {tid}: calls={calls} latency={lat:.1f}s")

if normal:
    avg_normal = sum(x[3] for x in normal) / len(normal)
    print(f"\nNormal tasks: avg latency={avg_normal:.1f}s")
    print(f"  Latency range: {min(x[3] for x in normal):.1f}s - {max(x[3] for x in normal):.1f}s")

# Check if zero-code tasks are clustered (API outage) or spread out
print(f"\nZero-code task indices (order in results):")
zero_indices = [i for i, r in enumerate(r4["results"]) if r.get("telemetry",{}).get("llm_calls",0) > 0 and r.get("telemetry",{}).get("candidates_generated",0) == 0]
print(f"  Count: {len(zero_indices)}")
print(f"  First 20 indices: {zero_indices[:20]}")
print(f"  Last 20 indices: {zero_indices[-20:]}")

# Check for gaps — are there normal tasks between zero-code tasks?
if zero_indices:
    # Find contiguous runs of zero-code
    runs = []
    start = zero_indices[0]
    prev = zero_indices[0]
    for idx in zero_indices[1:]:
        if idx != prev + 1:
            runs.append((start, prev))
            start = idx
        prev = idx
    runs.append((start, prev))
    print(f"\nContiguous runs of zero-code tasks: {len(runs)}")
    for s, e in runs[:10]:
        print(f"  Run: index {s}-{e} ({e-s+1} tasks)")
    if len(runs) > 10:
        print(f"  ... {len(runs)-10} more runs")
