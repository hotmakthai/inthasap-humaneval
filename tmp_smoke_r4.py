"""tmp_smoke_r4.py -- Smoke test R4 engine on 3 near-miss tasks from R3."""
import json, sys, time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from arc_engine import solve_task

TRAINING_DIR = Path("arc_data/data/training")
# 3 near-miss tasks from R3 (fitness >= 0.9 but unsolved)
SMOKE_TASKS = ["3631a71a", "72322fa7", "484b58aa"]

for tid in SMOKE_TASKS:
    path = TRAINING_DIR / f"{tid}.json"
    if not path.exists():
        print(f"  {tid}: file not found, skipping")
        continue
    task = json.loads(path.read_text(encoding="utf-8"))
    task.setdefault("task_id", tid)
    
    t0 = time.time()
    result = solve_task(task, use_llm=True)
    elapsed = time.time() - t0
    
    status = result["status"]
    tel = result.get("telemetry", {})
    print(f"  {tid}: status={status} fitness={tel.get('best_fitness', '?')} "
          f"round={tel.get('solved_round')} calls={tel.get('llm_calls')} "
          f"r4_calls={tel.get('round4_calls', 0)} time={elapsed:.1f}s")
