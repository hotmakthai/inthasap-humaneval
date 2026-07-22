# DEVIN TASK — Upgrade near_miss_verifier → Failure Classifier

**ไฟล์ที่แก้:** `C:\Inthasap_Guard\Council_Lab\near_miss_verifier.py`
**ห้ามแตะ:** arc_engine.py, council_web.py, core/*, .env

---

## Context

`near_miss_verifier.py` ปัจจุบันคืน `list[str]` ของ hint ข้อความ
ต้องการ upgrade ให้คืน **FailureReport dataclass** ที่มี:
- `failure_class` — ประเภทความผิด (enum)
- `confidence` — ความมั่นใจ 0.0–1.0
- `hints` — รายละเอียด (เก็บ list[str] เดิมไว้)

ผลทดสอบปัจจุบัน (อ้างอิง): Precision=0.50, FP=4/197, detect 1/4 near-miss

---

## งานที่ต้องทำ

### 1. เพิ่ม enum `FailureClass` และ dataclass `FailureReport`

```python
from enum import Enum
from dataclasses import dataclass, field

class FailureClass(str, Enum):
    DELTA_MAGNITUDE  = "DELTA_MAGNITUDE"
    COLOR_MAP        = "COLOR_MAP"
    ALIEN_COLOR      = "ALIEN_COLOR"
    BORDER           = "BORDER"
    COLOR_COUNT      = "COLOR_COUNT"
    POSITION         = "POSITION"   # reserved — ยังไม่มี invariant แต่จองชื่อไว้
    SYMMETRY         = "SYMMETRY"   # reserved
    OBJECT_COUNT     = "OBJECT_COUNT"  # reserved
    CONNECTIVITY     = "CONNECTIVITY"  # reserved
    UNKNOWN          = "UNKNOWN"

@dataclass
class FailureReport:
    failure_class: FailureClass
    confidence: float          # 0.0–1.0
    hints: list[str] = field(default_factory=list)
```

### 2. แก้ `check_invariants` signature

**ก่อน:**
```python
def check_invariants(task: dict, predicted_output: Grid) -> list[str]:
```

**หลัง:**
```python
def check_invariants(task: dict, predicted_output: Grid) -> list[FailureReport]:
```

คืน `list[FailureReport]` — แต่ละ invariant ที่ fail คืน FailureReport 1 ตัว
ถ้าผ่านทุก invariant คืน `[]`

### 3. กฎ mapping invariant → FailureClass + confidence

| invariant เดิม | failure_class | confidence |
|---|---|---|
| `DELTA_MAGNITUDE_VIOLATION` | `DELTA_MAGNITUDE` | 0.85 |
| `ALIEN_COLOR` (ไม่เคยอยู่ในโจทย์เลย) | `ALIEN_COLOR` | 0.90 |
| `ALIEN_COLOR` (อยู่ใน train_input แต่ไม่ใน train_output) | `COLOR_MAP` | 0.70 |
| `COLOR_MAP_VIOLATION` | `COLOR_MAP` | 0.80 |
| `BORDER_VIOLATION` | `BORDER` | 0.75 |
| `COLOR_COUNT_VIOLATION` | `COLOR_COUNT` | 0.65 |
| `MISSING_INPUT_COLOR` | `COLOR_MAP` | 0.70 |

confidence ตั้งไว้คงที่ตามตาราง (ไม่ต้องคำนวณ dynamic ใน Phase 1)

### 4. แก้ `cell_accuracy` — ไม่ต้องเปลี่ยน signature

ฟังก์ชัน `cell_accuracy(predicted, truth) -> float` เก็บไว้เหมือนเดิม

### 5. อัปเดต test script

แก้ `test_full_precision.py` ใน scratchpad:
```
C:\Users\9E84~1\AppData\Local\Temp\claude\C--Inthasap-Guard\918e0e9e-2dd9-46ae-885b-b60d8b6de5e2\scratchpad\test_full_precision.py
```

เปลี่ยน `hints = check_invariants(...)` → loop ผ่าน `list[FailureReport]`
แสดง failure_class แทน hint string ใน output

แก้ `test_near_miss.py` ในบรรทัดเดียวกัน:
```
C:\Users\9E84~1\AppData\Local\Temp\claude\C--Inthasap-Guard\918e0e9e-2dd9-46ae-885b-b60d8b6de5e2\scratchpad\test_near_miss.py
```

---

## Definition of Done

รัน test ทั้ง 2 แล้วผ่านทั้งหมด:

```
python test_full_precision.py
```
ต้องแสดง:
- Precision ≥ 0.45
- FP ≤ 6/197
- failure_class ปรากฏใน output (ไม่ใช่แค่ hint string)

```
python test_near_miss.py
```
ต้องแสดง:
- [11852cab] detected → failure_class=DELTA_MAGNITUDE
- [7f4411dc] หรือ [c444b776] อาจ miss (acceptable — position error ยังไม่มี invariant)
- 0 false positive บน 5 correct samples

---

## ห้ามทำ

- ห้ามแก้ arc_engine.py, council_web.py, core/*, .env
- ห้าม integrate เข้า arc_engine ใด ๆ ทั้งสิ้น (Phase 2 เท่านั้น)
- ห้ามเพิ่ม invariant ใหม่ (ทำแค่ rename/restructure output)
- ห้ามเปลี่ยน `cell_accuracy` signature
