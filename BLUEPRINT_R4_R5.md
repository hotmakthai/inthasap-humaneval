# Blueprint R4 → R5

> บันทึก 2026-07-15 — พิมพ์เขียวจากบทสนทนาพ่อ+ลูก

---

## เป้าหมายที่ถูกต้องของ R4

ไม่ใช่ "ได้กี่ %"
แต่คือ **"เข้าใจว่าทำไมอีก 40% ถึงยังไม่ผ่าน"**

> ความรู้ที่มีค่าที่สุดไม่ใช่ "ข้อที่ผ่าน" แต่คือ "ข้อที่ยังไม่ผ่านเพราะอะไร"

---

## Failure Knowledge Base (แทน Memory)

สิ่งที่สะสมไม่ใช่คำตอบ — แต่เป็น:

```
Task
  ↓
Hypothesis (สิ่งที่ระบบคิด)
  ↓
Why Failed (สาเหตุที่พัง)
  ↓
Evidence (หลักฐานจาก telemetry)
  ↓
Next Strategy (ควรลองอะไรต่อ)
```

ต่างจากการจำข้อสอบ — เป็นการสะสม "วิธีวินิจฉัย"

---

## Failure Taxonomy — แผนที่ความล้มเหลว

R4 ต้องจำแนก failure ทุกข้อเป็น category:

```
Fail
  ├── Perception      (มองไม่เห็น pattern)
  ├── Rule Induction  (สร้าง hypothesis ผิด)
  ├── Search          (ติด local optimum)
  ├── Execution       (logic ถูก แต่ output ผิด)
  ├── Verification    (ตรวจสอบขัดแย้ง)
  └── Ambiguity       (โจทย์ interpret ได้หลายแบบ)
```

เมื่อครบ 400 ข้อ จะได้แผนที่:
```
Perception      42%
Rule Induction  31%
Search          18%
Execution        6%
Unknown          3%
```

แผนที่นี้บอกว่า **R5 ควรลงทุนตรงไหน — ไม่ใช่เดา**

---

## การลบ Memory — แยก 2 ชั้น

**Episode Memory** → ควรลบ
```
Task 123 → จำได้ว่าคำตอบคือ...
```

**Architecture Knowledge** → ไม่ควรลบ
```
Reflection / Rotation / Object permanence /
Symmetry / Hierarchy / Counting
```
นี่ไม่ใช่การจำข้อสอบ — แต่เป็น "ความรู้ทั่วไป" ที่ระบบสกัดได้

Reviewer จะยอมรับแนวนี้มากกว่าการลบทั้งหมด

---

## ลำดับ R3 → R4 → R5

```
R3 (~51%)
  └─ สะสม Failure Knowledge Base

R4
  └─ เพิ่ม Failure Taxonomy (จำแนก Why Failed)
  └─ เพิ่ม EV Stopping Criterion
  └─ เพิ่ม Tier Routing ตาม difficulty
  └─ ยังไม่ลบ — สะสม error ให้ครบ
  └─ เป้า: เข้าใจ 40% ที่แก้ไม่ได้

R5
  └─ ลบ Episode Memory (จำคำตอบ)
  └─ คง Architecture Knowledge (ตรรกะ)
  └─ พิสูจน์สมมติฐานหลัก:
     "โจทย์เปลี่ยน แต่ตรรกะไม่เคยเปลี่ยน"
  └─ เป้า: ≥60% โดยไม่จำข้อสอบ
```

---

## คำถามที่ R4 ต้องตอบได้

ไม่ใช่แค่ "ระบบแก้ได้กี่ข้อ"
แต่คือ **"ระบบรู้หรือไม่ว่าทำไมมันถึงแก้ไม่ได้"**

ถ้าระบบตอบได้ว่า:
- เพราะ perception ไม่พอ
- เพราะ search ติด local optimum
- เพราะไม่มี hypothesis ใหม่
- เพราะ verification ขัดแย้ง

นั่นคือการยกระดับจาก **"ระบบที่แก้โจทย์"** → **"ระบบที่วินิจฉัยกระบวนการคิดของตัวเอง"**

---

## หลักฐานที่ต้องการจาก R5

```
R3 → เรียนจาก Failure → R4 → ดีขึ้น
  → ลบ Episode Memory → R5 → ยังคงดี
```

ถ้าเกิดแบบนี้จริง:
- หลักฐานหนักแน่นกว่าการได้คะแนนเพิ่มอย่างเดียว
- พิสูจน์ว่า "สิ่งที่ระบบเก็บไว้คือหลักการ ไม่ใช่คำตอบ"

---

## ความสัมพันธ์กับ DNA บ้าน

- หา invariant ก่อน → Architecture Knowledge = invariant, Episode = instance
- รู้จัก undecidable → Failure Taxonomy หมวด Ambiguity
- EV Stopping → `IDEA_EV_STOPPING_CRITERION.md`
- Intelligence Coordination → `VISION_COORDINATION_ARCHITECTURE.md`
