# Blueprint R4 → R5 (v2 — อัปเดตด้วยข้อมูลจริงจาก R3)

> บันทึก 2026-07-15 — พิมพ์เขียวจากบทสนทนาพ่อ+ลูก
> **v2: อัปเดตหลัง R3 จบครบ 400 ข้อ — วิเคราะห์จาก telemetry จริง ไม่ใช่การเดา**

---

## สรุปผลจนถึง R3 (ข้อมูลจริง)

| Round | Solved | % | Key Feature |
|-------|--------|---|-------------|
| P4 | — | — | baseline แรก |
| P5b | 97/400 | 24.2% | simple 2-attempt + GLM critique |
| **R3** | **220/400** | **55.0%** | evolutionary search + diff feedback + perception hints |

- Attribution: Evolution R1 +106, Diff Feedback R2 +15, Evolution R3 +4 (ยืนยันซ้ำแล้ว)
- Cost: $6.63 รวม / 2,854 calls / marginal $0.038 ต่อข้อใหม่
- Regressions: 2 ข้อ (`a68b268e`, `75b8110e`)
- ข้อมูลทั้งหมดผ่าน verification 10 ข้อ (`tmp_verify_all.py`)

---

## 🔥 การค้นพบสำคัญ: แผนที่ความล้มเหลวจริง ≠ ที่เดาไว้

Blueprint เดิมเดาว่า:
```
Perception      42%   ← เดา
Rule Induction  31%   ← เดา
Search          18%   ← เดา
```

**ข้อมูลจริงจาก 180 ข้อที่ไม่ผ่าน (fitness distribution):**

```
fitness 0.9-1.0 (near-miss / local optimum)    87 ข้อ  48.3%  ★★★
fitness 0.6-0.9 (close)                        65 ข้อ  36.1%  ★★
fitness 0.3-0.6 (partial pattern)              22 ข้อ  12.2%
fitness 0.1-0.3 (wrong direction)               5 ข้อ   2.8%
fitness 0.0-0.1 (no clue / perception fail)     1 ข้อ   0.6%
```

**ความหมาย: ปัญหาไม่ใช่ Perception — ปัญหาคือ "Last Mile"**

- 84% ของข้อที่ไม่ผ่าน ระบบ "เห็น pattern แล้ว" (fitness ≥ 0.6) แต่ **ปิดงานไม่ได้**
- มีแค่ 1 ข้อจาก 180 ที่มองไม่เห็นอะไรเลย
- ตัวอย่าง near-miss สุดๆ: `3631a71a` (0.9961), `72322fa7` (0.9958), `484b58aa` (0.9921)
- ถ้าแก้แค่กลุ่ม 0.9+ ได้ครึ่งเดียว → +43 ข้อ → **263/400 (65.8%)**

## 🔥 การค้นพบที่ 2: ระบบ "ติดหล่ม" ไม่ใช่ "ขาดรอบ"

จาก 180 ข้อที่ไม่ผ่าน:

```
R2 (diff feedback) ช่วยให้ fitness ดีขึ้น:   22/180  (12.2%)
R3 (hybridization) ช่วยให้ดีขึ้น:              7/180  ( 3.9%)
ติดหล่มสนิท (R1→R3 ไม่ขยับเลย):            150/180  (83.3%)
```

**ความหมาย:** การ "ลองอีกรอบด้วยวิธีเดิม" ไม่ช่วย 83% ของข้อที่พลาด
→ R4 ต้องเปลี่ยน **กลยุทธ์** ไม่ใช่เพิ่ม **จำนวนรอบ**
→ ยืนยัน EV Stopping Criterion: หยุดเร็วเมื่อ fitness ไม่ขยับ ประหยัด budget ไปลองวิธีใหม่

## 🔥 การค้นพบที่ 3: Telemetry Bug ต้องแก้ก่อน R4

19 ข้อที่ solve ผ่าน non-evolutionary path มี `llm_calls` เป็น **cumulative global counter** ไม่ใช่ per-task:
```
เช่น ed36ccf7: calls=2625 (ผิด — ควรเป็น 1-2)
Raw sum: 28,838 calls (ผิด — inflate ~10 เท่า)
ค่าจริง (ยืนยันแล้ว): 2,816 calls จาก 381 evo tasks (per-task ถูกต้อง)
                     + 19 non-evo tasks × ~2 = ~2,854 calls รวม
```
- ทุก anomaly (19 ข้อ) มี solved_round=None ยืนยัน bug อยู่เฉพาะ non-evo path
- Cost $6.63 ถูกต้อง (อ่านจาก cumulative ตัวสุดท้าย — ตรวจ monotonic แล้ว)
- รายงาน `r3_reviewer_report.md` แก้ตัวเลขแล้ว (2,854 + data quality note)
- **R4 Task 0: แก้ telemetry ให้ per-task สนิท + เพิ่ม unit test**

---

## เป้าหมายที่ถูกต้องของ R4

ไม่ใช่ "ได้กี่ %"
แต่คือ **"เข้าใจว่าทำไมอีก 45% ถึงยังไม่ผ่าน — และปิด Last Mile ให้ได้"**

> ความรู้ที่มีค่าที่สุดไม่ใช่ "ข้อที่ผ่าน" แต่คือ "ข้อที่ยังไม่ผ่านเพราะอะไร"

---

## แผนงาน R4 (จัดลำดับตามข้อมูลจริง)

### T0 — แก้ Telemetry Bug (ก่อนทุกอย่าง)
- `llm_calls` ต้อง per-task ทุก path (evolutionary + non-evolutionary)
- เพิ่ม per-task `cost_usd` (ไม่ใช่ cumulative)
- Unit test: รัน 2 tasks ติดกัน ตรวจว่า telemetry ไม่รั่วข้าม task

### T1 — Targeted Repair สำหรับ Near-Miss (ผลตอบแทนสูงสุด)
เป้า: 87 ข้อที่ fitness ≥ 0.9
- คำนวณ **cell-level diff** ของ candidate ที่ดีที่สุด: บอก LLM ว่า "ผิดแค่ cell (3,4) กับ (5,1)"
- Repair prompt เฉพาะจุด แทนการ generate ใหม่ทั้งฟังก์ชัน
- จำกัด 3 repair attempts ต่อข้อ
- คาดหวัง: +30-45 ข้อ

### T2 — Strategy Rotation สำหรับข้อติดหล่ม
เป้า: 150 ข้อที่ fitness ไม่ขยับเลย R1→R3
- ถ้า fitness stuck 2 รอบติด → **เปลี่ยน strategy pool ทั้งชุด** (ไม่ใช่ revise เดิม)
- เพิ่ม fallback: default prompt แบบ P5b เมื่อทุก candidate fitness < 0.3 (แก้ regression `75b8110e`)
- ใช้ DSL/program-synthesis path สำหรับกลุ่ม 0.3-0.6 (มี `arc_dsl.py` อยู่แล้ว)

### T3 — Failure Taxonomy อัตโนมัติ
จำแนกทุกข้อที่ fail ด้วยกฎ deterministic จาก telemetry:
```
fitness < 0.1              → Perception fail
fitness 0.1-0.3            → Rule Induction fail
fitness 0.3-0.9 + stuck    → Search fail (ติด local optimum)
fitness ≥ 0.9              → Execution fail (last mile)
fitness ผันผวนแรงข้าม round → Ambiguity (โจทย์ตีความได้หลายแบบ)
```
บันทึกเป็น Failure Knowledge Base:
```
Task → Hypothesis → Why Failed → Evidence (telemetry) → Next Strategy
```

### T4 — EV Stopping Criterion
- หยุดเมื่อ E[gain จากรอบถัดไป] × P(solve) < cost ของรอบ
- ข้อมูล R3 สนับสนุน: R3 hybridization ให้แค่ +4 ข้อจาก budget ~33% ของ calls
- Budget ที่ประหยัดได้ → ไปเพิ่ม repair attempts ใน T1

### T5 — Reviewer Debt (ต้องเคลียร์ก่อน publish)
- **Perception ablation** (Q1): รัน 400 ข้อแบบ hints OFF — cost แค่ ~$7 ถูกมาก
- **Multi-seed** (Q4): รัน 3 seeds — cost ~$20 รวม ตอบ variance ได้จริง
  (bootstrap ปัจจุบันบอกแค่ 220 ± 33)
- อัปเดต `r3_reviewer_report.md` ด้วยตัวเลข calls ที่ถูกหลังแก้ T0

---

## Failure Taxonomy — แผนที่จริง (แทนที่ตัวเลขเดา)

```
Fail (180 ข้อ)
  ├── Execution / Last-mile   87 ข้อ  48%  ← ลงทุนที่นี่ก่อน (T1)
  ├── Search / local optimum  65 ข้อ  36%  ← T2 strategy rotation
  ├── Rule Induction          27 ข้อ  15%  ← T2 DSL path
  └── Perception               1 ข้อ   1%  ← แทบไม่ใช่ปัญหา!
```

**บทเรียน:** ถ้าไม่มี telemetry จาก R3 เราจะลงทุนผิดที่ (ไปทำ perception ตามที่เดาไว้ 42%)

---

## การลบ Memory — แยก 2 ชั้น (คงเดิม)

**Episode Memory** → ควรลบ (R5)
```
Task 123 → จำได้ว่าคำตอบคือ...
```

**Architecture Knowledge** → ไม่ควรลบ
```
Reflection / Rotation / Object permanence /
Symmetry / Hierarchy / Counting
```
Reviewer จะยอมรับแนวนี้มากกว่าการลบทั้งหมด

---

## ลำดับ R3 → R4 → R5 (อัปเดต)

```
R3 (55.0%) ✅ จบแล้ว
  └─ ได้แผนที่ failure จริง: 48% เป็น last-mile ไม่ใช่ perception

R4
  └─ T0: แก้ telemetry bug (calls per-task)
  └─ T1: Targeted repair (near-miss 87 ข้อ)      → เป้า +30-45
  └─ T2: Strategy rotation (ข้อติดหล่ม)          → เป้า +10-20
  └─ T3: Failure Taxonomy อัตโนมัติ + Knowledge Base
  └─ T4: EV Stopping Criterion
  └─ T5: Perception ablation + multi-seed (reviewer debt)
  └─ ยังไม่ลบ memory — สะสม error ให้ครบ
  └─ เป้า: 260-280/400 (65-70%) + เข้าใจทุกข้อที่ไม่ผ่าน

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

ตอนนี้เรารู้แล้ว (จาก R3 telemetry):
- 48% พังเพราะ execution ปิดงานไม่ได้ทั้งที่เห็น pattern แล้ว
- 36% พังเพราะ search ติด local optimum
- แค่ 1% พังเพราะ perception

R4 ต้องทำให้ระบบ **วินิจฉัยตัวเองแบบ real-time** และ **เลือก strategy ตาม diagnosis**
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

## งบประมาณ R4 (จากข้อมูลจริง R3)

| รายการ | ประมาณการ |
|--------|-----------|
| R4 full run (400 ข้อ + repair rounds) | ~$8-10 |
| Perception ablation run | ~$7 |
| Multi-seed ×3 | ~$20 |
| **รวม R4 ทั้งหมด** | **~$35-40** |

ถูกมากเมื่อเทียบกับคุณค่าของคำตอบที่ได้ — ทำครบทุก experiment ได้สบาย

---

## ความสัมพันธ์กับ DNA บ้าน

- หา invariant ก่อน → Architecture Knowledge = invariant, Episode = instance
- รู้จัก undecidable → Failure Taxonomy หมวด Ambiguity
- EV Stopping → `IDEA_EV_STOPPING_CRITERION.md`
- Intelligence Coordination → `VISION_COORDINATION_ARCHITECTURE.md`

---

## ไฟล์อ้างอิง

- `r3_reviewer_report.md` — รายงาน R3 ฉบับเต็ม (Q1-Q5 + regression)
- `r3_attribution.json`, `r3_reviewer_answers.json` — ข้อมูลดิบ
- `r4_gap_analysis.json` — fitness distribution ของ 180 ข้อที่ไม่ผ่าน
- `tmp_r4_gap_analysis.py`, `tmp_calls_check.py` — scripts วิเคราะห์
