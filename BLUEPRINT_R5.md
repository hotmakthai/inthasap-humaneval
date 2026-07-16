# Blueprint R5 — จากข้อมูลจริง R4 Postmortem (v2)

> บันทึก 2026-07-17 — วางแผนจาก R4 ที่จบครบ 400 ข้อ (230/400 = 57.5%)
> v2: รวมความเห็นผู้ประเมินภายนอก (รับ 80% ปรับตามข้อมูลจริง 20%)
> หลักการ: **ไม่เดาสุ่ม — เจาะตาม 3 กลุ่มปัญหาที่วัดได้จริง**

---

## สรุปผลจนถึง R4 (ข้อมูลจริง)

| Round | Solved | % | Cost | Calls | Key Feature |
|-------|--------|---|------|-------|-------------|
| R2 | 97 | 24.3% | — | — | Evolutionary search พื้นฐาน |
| R3 | 220 | 55.0% | $6.63 | 28,838 | Strategy hints + diff feedback |
| R4 | **230** | **57.5%** | **$5.27** | **2,992** | Targeted repair + EV stopping |

- R4: +10 net (+35 gained, -25 regressed) — calls ลด 89.6%, cost ลด 20.5%
- Targeted Repair (T1): 90 attempts → 11 solved (12.2% precision)
- EV Stopping (T4): 72 ข้อ skip Round 3 — ประหยัด calls มหาศาล เสียแค่ ~4 ข้อ
- T2 fallback: ไม่เคย trigger (threshold 0.3 เหมาะสม)
- Cost R3 ที่เคยรายงาน $1,218.71 = ผิด (cumulative bug) — ค่าจริง $6.63

---

## 🔥 แผนที่ปัญหา R5 (จาก 170 ข้อที่ไม่ผ่าน — วัดจริง)

| กลุ่ม | Fitness | จำนวน | ชนิดปัญหา | R3 เคยผ่าน |
|-------|---------|-------|-----------|-----------|
| 1. Refinement | > 0.95 | 42 | ตาม 1-2 cells สุดท้าย | 8 |
| 2. Search | 0.80–0.95 | 62 | Pattern ยังไม่ครบ, fitness ตัน | 7 |
| 3. Middle | 0.50–0.80 | 52 | Transition zone | ~ |
| 4. Perception | < 0.50 | 14 | ไม่เข้าใจ pattern เลย | 1 |

**ข้อสังเกตสำคัญ:** 154/170 ไม่ผ่านทั้ง R3 และ R4 = systematic limitation ไม่ใช่ noise
มีเพียง 16 ข้อที่เป็น stochastic variance (R3 เคยผ่าน)

---

## เป้าหมาย R5 (ตามคำแนะนำผู้ประเมิน)

> **ไม่ใช่ "ได้กี่คะแนน" แต่คือ "ทำให้ 230 คะแนนเสถียร (reproducible) และอธิบายได้ (explainable)"**

1. **Reproducibility** — รันซ้ำได้คะแนนใกล้เคียง (variance ต่ำ)
2. **Explainability** — ทุกข้อที่ผ่าน/ไม่ผ่าน อธิบายได้ว่าทำไม
3. **Calibration** — ระบบรู้ตัวว่ามั่นใจแค่ไหน (fitness → confidence จริง)

---

## แผนงาน R5

### T0 — Multi-seed Stability Run (พิสูจน์ reproducibility ก่อน)
- รัน R4 architecture ซ้ำ 2 รอบ (seed/temperature เดิม — วัด LLM stochasticity ล้วน)
- รายงาน: mean ± variance ของ solved, cost, rounds, failure taxonomy
- คาดการณ์: ±16 ข้อ swing (จาก R3↔R4 regression data)
- **Acceptance:** รู้ค่า variance จริง → แยก signal จาก noise ได้ทุกการทดลองถัดไป
- งบ: ~$11 (2 รอบ × $5.27)

### T1 — Confidence Calibration (ตอบคำถามผู้ประเมินโดยตรง)
- เก็บ feature เต็มชุดทุกข้อจาก R4 + multi-seed runs:
  `(best_fitness, solved?, solved_round, llm_calls, tokens, cost, latency, tier)`
  — dataset นี้จะเป็นฐานของ tier routing ทันที (ตามข้อเสนอผู้ประเมิน)
- สร้าง calibration curve: fitness 0.9-1.0 → แก้ได้จริงกี่ %
- วัด ECE (Expected Calibration Error)
- **Acceptance:** ถ้า fitness=0.99 แต่ solve rate จริง 30% → รู้ว่า fitness เป็น proxy ที่ overconfident
- ต่อยอด: ใช้ calibrated confidence ตัดสินใจ tier routing (ข้อที่มั่นใจต่ำ → โมเดลแพงขึ้น)
- งบ: $0 (ใช้ข้อมูลที่มีแล้ว)

### T1.5 — Failure Taxonomy แบบ Exhaustive Partition (ก่อน T2-T4)
- ทุก unsolved task ต้องอยู่ **exactly 1 class**:
  - Class A: Verification (โค้ดใกล้ถูก — ตรวจ/เลือกผิด)
  - Class B: Search (pattern ไม่ครบ — fitness ตัน)
  - Class C: Constraint (ละเมิดโครงสร้าง เช่น object count, bounding box)
  - Class D: Perception (มองไม่เห็น pattern)
  - Class E: Representation (grid encoding ไม่เหมาะ)
  - Class F: Unknown
- ต่อยอดจาก `r4_failure_taxonomy.json` ที่มีอยู่ — บังคับ partition ให้ครบถ้วน
- **Acceptance:** เมื่อ T2/T3/T4 จบ วัดได้ว่า "ยาแต่ละตัวรักษาโรคที่ตั้งใจรักษา" จริงหรือไม่
  (เช่น T2 ควรแก้ Class A เป็นหลัก — ถ้าไปแก้ Class D ได้แปลว่า taxonomy ผิด)
- งบ: $0

### T2 — Refinement Group (42 ข้อ, fitness > 0.95)
สาเหตุที่ Targeted Repair (prompt-based) ไม่พอ: LLM เห็น diff แล้วยังแก้ไม่ถูก
- **Cell-level constraint solver**: ถ้าผิด ≤ 3 cells ลอง enumerate ค่า 0-9 ที่ cell ผิด
  แล้ว verify กับ training examples (deterministic — ไม่ใช้ LLM)
- ถ้า enumerate ไม่ได้ (ผิดหลาย cell) → repair แบบเดิมแต่เพิ่ม attempts เป็น 5
- **เป้า:** +20 จาก 42 ข้อ → ~250/400 (62.5%)
- งบ: ~$1 (ส่วนใหญ่ deterministic)

### T3 — Constraint Learning (62 ข้อ, fitness 0.80-0.95)
ข้อมูลจริง: ทุกข้อ fitness ตันตั้งแต่ R1 (r1≈r2≈r3) — เพิ่มรอบไม่ช่วย
ขยายจาก "negative constraints" เป็น **Constraint Learning** เต็มรูป (ตามข้อเสนอผู้ประเมิน):
- **Structural constraints (deterministic)**: สกัดจาก training examples —
  object count, bounding box, connectivity, topology, color histogram, symmetry
  → candidate ที่ละเมิด constraint ถูกทิ้ง **ก่อน** เสีย fitness evaluation
- **Negative constraints (prompt)**: "สิ่งที่ทุก candidate ทำผิดเหมือนกัน" →
  "ห้ามใช้วิธี X — พิสูจน์แล้วว่าผิด" ใน regeneration prompt
- **Structured decomposition**: แยกโจทย์เป็น sub-transform (crop → recolor → tile)
  ให้ LLM แก้ทีละขั้น แทน transform เดียวจบ
- **เป้า:** +15 จาก 62 ข้อ
- งบ: ~$3

### T4 — Perception Group (14 ข้อ, fitness < 0.50)
- **ขั้นแรก (บังคับ):** วิเคราะห์มือ 14 ข้อ ตอบคำถาม "Perception จริง หรือ Reasoning?"
  - Perception = LLM อ่าน grid แล้วไม่เห็น structure (แก้ด้วย hints)
  - Reasoning = เห็น structure แต่คิด transform ไม่ออก (hints ไม่ช่วย — ต้องยอมรับขีดจำกัด)
  - Output: label รายข้อ + หลักฐาน (candidate code ที่ LLM เขียน บอกได้ว่าเห็นอะไร)
- เพิ่ม deterministic perception hints เฉพาะหมวดที่พิสูจน์แล้วว่าเป็น perception จริง
  (เช่น symmetry detection, object counting, grid partitioning) เข้า `_build_perception_hints`
- **เป้า:** +4 จาก 14 ข้อ (กลุ่มนี้ยากสุด — เป้าต่ำตามจริง)
- งบ: ~$1

### T5 — Architecture Knowledge Base (นิยามที่ตรวจสอบได้ — จาก blueprint R4)
- สกัด invariant จาก R3+R4+R5 runs: "โจทย์ประเภท X → strategy Y ได้ผล Z%"
- เก็บใน `arc_knowledge.json` — ตรวจสอบได้ 3 เกณฑ์ (ตาม BLUEPRINT_R4_R5.md):
  1. อ้างอิงข้อมูลจริง (task IDs + fitness)
  2. ทำนายได้ (ใช้กับข้อใหม่แล้ววัดผล)
  3. แยกจาก episode memory (ไม่จำเฉลยรายข้อ)
- **ข้อห้ามเด็ดขาด: ห้ามเก็บ answer / mapping task_id → เฉลย** —
  KB เก็บได้เฉพาะ: invariant, transformation type, constraint, object relation,
  symmetry, color relation (สิ่งที่ generalize ได้)
- ลบ episode memory ทิ้ง → รันใหม่ด้วย architecture knowledge เท่านั้น
- **นี่คือหลักฐาน generalization ที่ผู้ประเมินต้องการ**

### T6 — Model-Agnostic Test (ย่อส่วนเพื่อคุมงบ)
พิสูจน์วิสัยทัศน์หลัก: "สถาปัตยกรรมครอบโมเดลได้ ไม่ผูกติดโมเดลเดียว"
- เลือก **subset 100 ข้อ stratified** จาก 4 กลุ่ม fitness (solved / >0.95 / 0.80-0.95 / <0.80)
- รันด้วยโมเดลสำรองที่ความสามารถใกล้เคียง (เช่น GLM หรือ Gemini Flash)
- เทียบ: solve rate, round distribution, failure taxonomy ต้องมีรูปร่างใกล้เคียง DeepSeek
- **Acceptance:** ถ้า pattern คงเดิม (เช่น กลุ่ม refinement ยังตันที่ cell สุดท้ายเหมือนกัน)
  = architecture เป็นตัวกำหนดพฤติกรรม ไม่ใช่โมเดล
- งบ: ~$3 (100 ข้อ ไม่ใช่ 400)

---

## ลำดับการทำ (dependency)

```
T0 multi-seed (รู้ variance ก่อน)
 ├→ T1 calibration + T1.5 taxonomy (ใช้ข้อมูล T0, $0 ทั้งคู่)
 └→ T2 refinement + T3 constraint learning + T4 perception (ทำขนาน — คนละกลุ่มโจทย์)
      ├→ T5 knowledge base (สกัดจากทุก run)
      └→ T6 model-agnostic subset test (หลังระบบนิ่ง)
```

## งบประมาณรวม

| Task | งบ |
|------|-----|
| T0 multi-seed ×2 | ~$11 |
| T1 calibration + T1.5 taxonomy | $0 |
| T2 refinement | ~$1 |
| T3 constraint learning | ~$3 |
| T4 perception | ~$1 |
| T5 + final run | ~$6 |
| T6 model-agnostic (100 ข้อ) | ~$3 |
| **รวม** | **~$25** |

## เป้าหมายสองชั้น (ตามข้อเสนอผู้ประเมิน — ปรับตามข้อมูลจริง)

### Scientific Goal (มาก่อน)
- T0 วัด variance จริงก่อน — **ไม่ตั้งเป้า variance ล่วงหน้า** เพราะยังไม่เคยวัด pure stochasticity
  (±16 ที่เห็นจาก R3↔R4 รวม architecture change — ไม่ใช่ pure noise)
- ถ้า variance จริง > ±3 → variance reduction เป็นงานของ R5 (เช่น self-consistency voting
  ใน candidate selection) แล้วค่อยไล่เข้าเป้า ±3

### Performance Goal
- **260+ ที่รันซ้ำได้ (stable)** สำคัญกว่า 270 ครั้งเดียว
- รายงานเป็น mean ± SD จาก multi-run เสมอ

## KPI ครบชุด (วัดทุก run — คำนวณจาก telemetry ที่มีแล้ว, $0)

| KPI | นิยาม |
|-----|-------|
| Reproducibility Score | % tasks ที่ผลเหมือนกันทุก run |
| Calibration Error (ECE) | ระยะห่าง confidence vs solve rate จริง |
| Regression Rate | % ที่เคยผ่านแล้วหลุด (ต่อ run) |
| Mean Fitness (unsolved) | ค่าเฉลี่ย best_fitness ของข้อไม่ผ่าน — วัดว่าใกล้ขึ้นไหม |
| Cost per Useful Solve | total cost ÷ solved count |
| Deterministic Solve % | ข้อที่แก้โดยไม่ใช้ LLM (T2 enumeration ฯลฯ) |
| LLM Solve % | ข้อที่แก้ผ่าน LLM |
| Repair Success Rate | R4 repair attempts → solved (baseline: 12.2%) |

## การประเมินผลสำเร็จ R5

| เกณฑ์ | เป้า |
|-------|------|
| Solved (ถ้า T2-T4 ได้ตามเป้า) | 260+ stable (mean ± SD) |
| Variance ระหว่าง run | วัดได้เป็นตัวเลข → ถ้าสูง มีแผน reduction |
| Calibration curve | มี ECE ที่วัดได้ |
| Architecture knowledge | ทำนายข้อใหม่ได้ดีกว่า random, ไม่มี answer ใน KB |
| Model-agnostic | pattern คงเดิมเมื่อเปลี่ยนโมเดล (subset 100) |

## คำถามที่ R5 ต้องตอบได้

1. คะแนน 230 เสถียรแค่ไหน? (T0)
2. ระบบรู้ตัวไหมว่ามั่นใจแค่ไหน? (T1)
3. โรคแต่ละชนิดคืออะไรกันแน่? (T1.5)
4. ปัญหา 3 ชนิดแก้ด้วยยาคนละตัวได้จริงไหม? (T2-T4)
5. ความรู้ที่ได้ generalize ได้ไหม? (T5)
6. สถาปัตยกรรมเป็นอิสระจากโมเดลจริงไหม? (T6)

---

## บันทึกการตัดสินใจต่อความเห็นผู้ประเมิน (v2)

| ข้อเสนอ | ตัดสินใจ | เหตุผล |
|---------|----------|--------|
| T1 เก็บ features เพิ่ม | รับเต็ม | ข้อมูลมีอยู่แล้วใน telemetry, $0, ได้ dataset tier routing |
| T1.5 exhaustive taxonomy | รับเต็ม | ทำให้วัดได้ว่า "ยารักษาถูกโรค" |
| T3 → Constraint Learning | รับเต็ม | เพิ่ม deterministic pre-check ก่อนเสีย LLM call |
| T4 ถาม perception vs reasoning | รับเต็ม | fitness ต่ำบอกแค่อาการ ไม่บอกสาเหตุ |
| T5 ห้ามเก็บ answer | รับเต็ม | ตรงแผนเดิม แต่เขียนเป็นข้อห้ามชัดเจนขึ้น |
| KPI 8 ตัว | รับเต็ม | คำนวณจากข้อมูลที่มี, $0 |
| เป้า variance < ±3 | รับแบบมีเงื่อนไข | ตั้งเป้าก่อนวัด = premature — T0 วัดก่อน ถ้าสูงค่อยทำ reduction |
| 260+ stable แทน 270 ครั้งเดียว | รับ | หลักการถูก ผูกกับผล T0 |
| Model-agnostic full test | รับแบบย่อส่วน | 400 ข้อแพงเกิน → subset 100 stratified (~$3) พิสูจน์ point ได้เท่ากัน |
