"""tmp_r4_verify_root_cause.py — Verify root cause before rerun.
Check: tokens, cost, calls_by_tier of failed tasks + error handling in call path."""
import json, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

r4 = json.loads(Path("r4_state.json").read_text(encoding="utf-8"))

# 1. Check tokens/cost for zero-code tasks — did the API actually process anything?
print("=== 1. Token & cost check for zero-code tasks ===")
zero_code = []
normal = []
for i, r in enumerate(r4["results"]):
    t = r.get("telemetry", {})
    calls = t.get("llm_calls", 0)
    cg = t.get("candidates_generated", 0)
    if calls > 0 and cg == 0:
        zero_code.append((i, r))
    elif calls > 0:
        normal.append((i, r))

# For zero-code tasks: check per-task tokens
# total_input_tokens is CUMULATIVE — check delta between consecutive tasks
print(f"\nSample zero-code tasks (cumulative tokens — check if they grew):")
for i, r in zero_code[:5]:
    t = r["telemetry"]
    prev_t = r4["results"][i-1].get("telemetry", {}) if i > 0 else {}
    delta_in = t.get("total_input_tokens", 0) - prev_t.get("total_input_tokens", 0)
    delta_out = t.get("total_output_tokens", 0) - prev_t.get("total_output_tokens", 0)
    delta_cost = t.get("total_cost_usd", 0) - prev_t.get("total_cost_usd", 0)
    print(f"  [{i}] {r['task_id']}: calls={t.get('llm_calls')} delta_in={delta_in} delta_out={delta_out} delta_cost=${delta_cost:.6f} lat={r.get('latency_sec',0):.1f}s")

print(f"\nSample normal tasks:")
for i, r in normal[:5]:
    t = r["telemetry"]
    prev_t = r4["results"][i-1].get("telemetry", {}) if i > 0 else {}
    delta_in = t.get("total_input_tokens", 0) - prev_t.get("total_input_tokens", 0)
    delta_out = t.get("total_output_tokens", 0) - prev_t.get("total_output_tokens", 0)
    delta_cost = t.get("total_cost_usd", 0) - prev_t.get("total_cost_usd", 0)
    print(f"  [{i}] {r['task_id']}: calls={t.get('llm_calls')} delta_in={delta_in} delta_out={delta_out} delta_cost=${delta_cost:.6f} lat={r.get('latency_sec',0):.1f}s")

# WAIT — T0 made telemetry per-task now! Check if tokens are per-task or cumulative
print(f"\n=== 2. Is token telemetry per-task or cumulative after T0? ===")
tok_values = [(i, r["task_id"], r.get("telemetry", {}).get("total_input_tokens", 0)) for i, r in enumerate(r4["results"][:20])]
for i, tid, tok in tok_values:
    print(f"  [{i}] {tid}: total_input_tokens={tok}")

# 3. calls_by_tier for zero-code tasks
print(f"\n=== 3. calls_by_tier for zero-code tasks ===")
for i, r in zero_code[:5]:
    t = r["telemetry"]
    print(f"  {r['task_id']}: calls_by_tier={t.get('calls_by_tier', {})}")
print(f"For normal tasks:")
for i, r in normal[:5]:
    t = r["telemetry"]
    print(f"  {r['task_id']}: calls_by_tier={t.get('calls_by_tier', {})}")

# 4. Status of zero-code tasks — do any say 'llm error'?
print(f"\n=== 4. Status strings of zero-code tasks ===")
from collections import Counter
statuses = Counter(r["status"] for _, r in zero_code)
for s, c in statuses.items():
    print(f"  '{s}': {c}")

# 5. Time boundaries — when did each run of failures happen?
# Use index in results — check timestamps if available
print(f"\n=== 5. Zero-code vs normal interleaving around boundaries ===")
# Show tasks around index 96 (first failure)
for i in range(93, 112):
    if i < len(r4["results"]):
        r = r4["results"][i]
        t = r.get("telemetry", {})
        cg = t.get("candidates_generated", 0)
        calls = t.get("llm_calls", 0)
        marker = "FAIL" if (calls > 0 and cg == 0) else "ok"
        print(f"  [{i}] {r['task_id']}: {marker} calls={calls} cg={cg} lat={r.get('latency_sec',0):.1f}s status={r['status'][:40]}")
