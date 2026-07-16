"""tmp_r4_test_one.py — Test R1 generation on one zero-fitness task."""
import json, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from arc_llm import _build_prompt, _call_llm, _extract_python, reset_telemetry

reset_telemetry()

# Task that R3 solved R1=1.00 but R4 got 0.00
tid = "42a50994"
task = json.loads(Path(f"arc_data/data/training/{tid}.json").read_text(encoding="utf-8"))
task.setdefault("task_id", tid)

# Generate 1 candidate
system, user = _build_prompt(task, attempt=1, strategy_hint="Count objects and use the count as output.")
print(f"System prompt length: {len(system)}")
print(f"User prompt length: {len(user)}")
print(f"User prompt (first 500 chars):\n{user[:500]}")
print()

text, note = _call_llm("deepseek", system, user, max_tokens=4000, no_fallback=True)
print(f"LLM response length: {len(text)}")
print(f"Note: {note}")
print(f"Response (first 500 chars):\n{text[:500]}")
print()

code = _extract_python(text)
print(f"Extracted code: {code is not None}")
if code:
    print(f"Code length: {len(code)}")
    print(f"Code (first 200 chars):\n{code[:200]}")
else:
    print("=== NO CODE EXTRACTED ===")
    print(f"Full response:\n{text[:2000]}")
