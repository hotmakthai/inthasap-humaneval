# DEVIN DONE — Upgrade near_miss_verifier → Failure Classifier

## สรุปงาน

อัปเกรด `near_miss_verifier.py` จากคืน `list[str]` เป็น `list[FailureReport]` พร้อม `FailureClass` enum และ confidence score

---

## ไฟล์ที่แก้

### 1. `Council_Lab/near_miss_verifier.py`
- เพิ่ม `FailureClass(str, Enum)` — 10 ค่า (5 active + 4 reserved + UNKNOWN)
- เพิ่ม `FailureReport` dataclass — `failure_class`, `confidence`, `hints: list[str]`
- แก้ `check_invariants()` signature: `list[str]` → `list[FailureReport]`
- แก้ทุก `_check_*` function: คืน `FailureReport | None` แทน `str | None`
- `cell_accuracy()` — **ไม่เปลี่ยน** (ตาม spec)

### 2. `scratchpad/test_full_precision.py`
- เปลี่ยน `hints = check_invariants(...)` → `reports = check_invariants(...)`
- แสดง `failure_class` + `confidence` ใน output แทน hint string

### 3. `scratchpad/test_near_miss.py`
- เหมือนกัน — แสดง `failure_class` + `confidence` ใน output

---

## Mapping invariant → FailureClass + confidence

| invariant เดิม | failure_class | confidence |
|---|---|---|
| `DELTA_MAGNITUDE_VIOLATION` | `DELTA_MAGNITUDE` | 0.85 |
| `ALIEN_COLOR` (ไม่เคยอยู่ในโจทย์) | `ALIEN_COLOR` | 0.90 |
| `ALIEN_COLOR` (train_input only) | `COLOR_MAP` | 0.70 |
| `COLOR_MAP_VIOLATION` | `COLOR_MAP` | 0.80 |
| `BORDER_VIOLATION` | `BORDER` | 0.75 |
| `COLOR_COUNT_VIOLATION` | `COLOR_COUNT` | 0.65 |
| `MISSING_INPUT_COLOR` | `COLOR_MAP` | 0.70 |

---

## ผลทดสอบ

### test_near_miss.py
```
[11852cab] acc=0.980 (1 report)
  ⚠ failure_class=DELTA_MAGNITUDE conf=0.85
[7f4411dc] acc=0.990 — miss (position error, ยังไม่มี invariant)
[1f642eb9] acc=0.980 — miss
[c444b776] acc=0.927 — miss

สรุป: detect 1/4 near-miss tasks
      false positives: 0/5 correct tasks ✅
```

### test_full_precision.py
```
DATASET: 400 tasks · correct=197 · wrong=203
TRUE  POSITIVE: 4/203
FALSE POSITIVE: 4/197
Precision: 0.500   Recall: 0.020
Near-miss detected: 1/4
  [11852cab] failure_class=DELTA_MAGNITUDE conf=0.85
```

---

## Definition of Done

- [x] `FailureClass` enum + `FailureReport` dataclass เพิ่มแล้ว
- [x] `check_invariants` คืน `list[FailureReport]`
- [x] `cell_accuracy` signature ไม่เปลี่ยน
- [x] Precision = 0.50 ≥ 0.45 ✅
- [x] FP = 4/197 ≤ 6/197 ✅
- [x] `failure_class` ปรากฏใน output (ไม่ใช่ hint string) ✅
- [x] `[11852cab]` detected → `failure_class=DELTA_MAGNITUDE` ✅
- [x] 0 false positive บน 5 correct samples ✅
- [x] ไม่แตะ `arc_engine.py`, `council_web.py`, `core/*`, `.env`
- [x] ไม่เพิ่ม invariant ใหม่ — แค่ rename/restructure output
- [x] `python -m py_compile` ผ่าน
