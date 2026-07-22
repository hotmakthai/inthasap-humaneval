# DEVIN TASK — Failure Classifier Phase 2: Suggest Mode

**ไฟล์ที่แก้:** `C:\Inthasap_Guard\Council_Lab\arc_engine.py`
**ไฟล์อ่านอย่างเดียว:** `C:\Inthasap_Guard\Council_Lab\near_miss_verifier.py`
**ห้ามแตะ:** council_web.py, core/*, .env

---

## Context

Phase 1 เสร็จแล้ว — `near_miss_verifier.py` คืน `list[FailureReport]`
```python
@dataclass
class FailureReport:
    failure_class: FailureClass  # enum: DELTA_MAGNITUDE, COLOR_MAP, ALIEN_COLOR, BORDER, COLOR_COUNT, ...
    confidence: float
    hints: list[str]
```

Phase 2 คือ integrate แบบ **Suggest** — เพิ่ม failure_report เข้า return dict ของ `solve_task()`
**ห้ามบังคับ retry** — แค่บันทึกไว้ให้ caller รู้

---

## งานที่ต้องทำ (arc_engine.py เท่านั้น)

### 1. import near_miss_verifier แบบ optional (ไม่ break ถ้าไม่มีไฟล์)

เพิ่มที่ top ของ arc_engine.py หลัง imports เดิม:

```python
try:
    from near_miss_verifier import check_invariants, FailureReport
    _HAS_FAILURE_CLASSIFIER = True
except ImportError:
    _HAS_FAILURE_CLASSIFIER = False
```

### 2. เรียก check_invariants ใน solve_task() หลังได้ output

ใน `solve_task()` บรรทัดที่ build return dict (ประมาณ line 113–124) แก้เป็น:

```python
# เรียก failure classifier (suggest mode — ไม่ block/retry)
failure_reports = []
if _HAS_FAILURE_CLASSIFIER and outputs:
    try:
        failure_reports = check_invariants(task, outputs[0])
    except Exception:
        failure_reports = []

return {
    "output": outputs[0],
    "outputs": outputs,
    "attempt_1": outputs[0],
    "attempt_2": outputs[1] if len(outputs) > 1 else None,
    "candidate": repr(chosen[0]),
    "candidates": [repr(c) for c in chosen],
    "status": "solved",
    "train_fit_only": True,
    "ambiguous": len(outputs) > 1,
    "telemetry": llm_telemetry if llm_telemetry else {},
    # Phase 2 Suggest — ไม่ block ไม่ retry แค่บันทึก
    "failure_reports": [
        {"failure_class": r.failure_class.value, "confidence": r.confidence, "hints": r.hints}
        for r in failure_reports
    ],
    "has_invariant_warning": len(failure_reports) > 0,
}
```

### 3. เพิ่ม failure_reports ใน unsolved paths ด้วย (คืน empty list)

ทุก return ที่ status != "solved" ให้เพิ่ม:
```python
"failure_reports": [],
"has_invariant_warning": False,
```

---

## Definition of Done

เขียน test file `test_arc_engine_p2.py` ใน Council_Lab root แล้วรัน:

```python
import json
from pathlib import Path
from arc_engine import solve_task

# โหลด 1 task ที่รู้ว่า near-miss (11852cab)
task_file = Path('arc_data/data/training/11852cab.json')
task = json.loads(task_file.read_text(encoding='utf-8'))

# ใส่ pred ที่รู้ว่าผิด (จาก t0_pred_b.json) เข้าเป็น mock output
pred_all = json.loads(open('t0_pred_b.json', encoding='utf-8').read())
pred = pred_all['11852cab']
if pred and isinstance(pred[0], list) and isinstance(pred[0][0], list):
    pred = pred[0]

# สร้าง mock result เหมือน solve_task คืน แล้วเรียก check_invariants โดยตรง
from near_miss_verifier import check_invariants, FailureClass
reports = check_invariants(task, pred)

assert len(reports) > 0, "ต้องพบ FailureReport อย่างน้อย 1 ตัว"
assert any(r.failure_class == FailureClass.DELTA_MAGNITUDE for r in reports), "ต้องพบ DELTA_MAGNITUDE"
print("PASS: failure_reports ส่งกลับถูกต้อง")

# ทดสอบ solve_task คืน key ใหม่
result = solve_task(task, top_k=2, use_llm=False)
assert "failure_reports" in result, "solve_task ต้องคืน failure_reports key"
assert "has_invariant_warning" in result, "solve_task ต้องคืน has_invariant_warning key"
print(f"PASS: solve_task คืน failure_reports={result['failure_reports']}")
print(f"      has_invariant_warning={result['has_invariant_warning']}")
print("ALL PASS")
```

ผลที่ต้องการ:
- `PASS: failure_reports ส่งกลับถูกต้อง`
- `PASS: solve_task คืน failure_reports=[...]`
- `ALL PASS`
- ไม่มี Exception ใด ๆ

---

## ห้ามทำ

- ห้าม retry หรือ block output จาก failure_reports
- ห้ามเปลี่ยน signature ของ solve_task
- ห้ามแก้ near_miss_verifier.py
- ห้ามแตะ council_web.py, core/*, .env
- ห้ามเพิ่ม invariant ใหม่ใด ๆ
