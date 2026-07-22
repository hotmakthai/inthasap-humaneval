import json
from pathlib import Path
from arc_engine import solve_task

task_file = Path('arc_data/data/training/11852cab.json')
task = json.loads(task_file.read_text(encoding='utf-8'))

pred_all = json.loads(open('t0_pred_b.json', encoding='utf-8').read())
pred = pred_all['11852cab']
if pred and isinstance(pred[0], list) and isinstance(pred[0][0], list):
    pred = pred[0]

from near_miss_verifier import check_invariants, FailureClass
reports = check_invariants(task, pred)

assert len(reports) > 0, "ต้องพบ FailureReport อย่างน้อย 1 ตัว"
assert any(r.failure_class == FailureClass.DELTA_MAGNITUDE for r in reports), "ต้องพบ DELTA_MAGNITUDE"
print("PASS: failure_reports ส่งกลับถูกต้อง")

result = solve_task(task, top_k=2, use_llm=False)
assert "failure_reports" in result, "solve_task ต้องคืน failure_reports key"
assert "has_invariant_warning" in result, "solve_task ต้องคืน has_invariant_warning key"
print(f"PASS: solve_task คืน failure_reports={result['failure_reports']}")
print(f"      has_invariant_warning={result['has_invariant_warning']}")
print("ALL PASS")
