# Blueprint R5 — จากข้อมูลจริง R4 Postmortem

> บันทึก 2026-07-17 — วางแผนจาก R4 ที่จบครบ 400 ข้อ (230/400 = 57.5%)
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
- เก็บ (best_fitness, solved?) ทุกข้อจาก R4 + multi-seed runs
- สร้าง calibration curve: fitness 0.9-1.0 → แก้ได้จริงกี่ %
- วัด ECE (Expected Calibration Error)
- **Acceptance:** ถ้า fitness=0.99 แต่ solve rate จริง 30% → รู้ว่า fitness เป็น proxy ที่ overconfident
- ต่อยอด: ใช้ calibrated confidence ตัดสินใจ tier routing (ข้อที่มั่นใจต่ำ → โมเดลแพงขึ้น)
- งบ: $0 (ใช้ข้อมูลที่มีแล้ว)

### T2 — Refinement Group (42 ข้อ, fitness > 0.95)
สาเหตุที่ Targeted Repair (prompt-based) ไม่พอ: LLM เห็น diff แล้วยังแก้ไม่ถูก
- **Cell-level constraint solver**: ถ้าผิด ≤ 3 cells ลอง enumerate ค่า 0-9 ที่ cell ผิด
  แล้ว verify กับ training examples (deterministic — ไม่ใช้ LLM)
- ถ้า enumerate ไม่ได้ (ผิดหลาย cell) → repair แบบเดิมแต่เพิ่ม attempts เป็น 5
- **เป้า:** +20 จาก 42 ข้อ → ~250/400 (62.5%)
- งบ: ~$1 (ส่วนใหญ่ deterministic)

### T3 — Search Group (62 ข้อ, fitness 0.80-0.95)
ข้อมูลจริง: ทุกข้อ fitness ตันตั้งแต่ R1 (r1≈r2≈r3) — เพิ่มรอบไม่ช่วย
- **Failure-aware regeneration**: แทน revision ให้ส่ง "สิ่งที่ทุก candidate ทำผิดเหมือนกัน"
  กลับไปเป็น negative constraint ("ห้ามใช้วิธี X — พิสูจน์แล้วว่าผิด")
- **Structured decomposition**: แยกโจทย์เป็น sub-transform (crop → recolor → tile)
  ให้ LLM แก้ทีละขั้น แทน transform เดียวจบ
- **เป้า:** +15 จาก 62 ข้อ
- งบ: ~$3

### T4 — Perception Group (14 ข้อ, fitness < 0.50)
- วิเคราะห์มือ 14 ข้อ (จำนวนน้อยพอทำได้) — จัดหมวด pattern ที่ LLM มองไม่เห็น
- เพิ่ม deterministic perception hints เฉพาะหมวดที่พบ (เช่น symmetry detection,
  object counting, grid partitioning) เข้า `_build_perception_hints`
- **เป้า:** +4 จาก 14 ข้อ (กลุ่มนี้ยากสุด — เป้าต่ำตามจริง)
- งบ: ~$1

### T5 — Architecture Knowledge Base (นิยามที่ตรวจสอบได้ — จาก blueprint R4)
- สกัด invariant จาก R3+R4+R5 runs: "โจทย์ประเภท X → strategy Y ได้ผล Z%"
- เก็บใน `arc_knowledge.json` — ตรวจสอบได้ 3 เกณฑ์ (ตาม BLUEPRINT_R4_R5.md):
  1. อ้างอิงข้อมูลจริง (task IDs + fitness)
  2. ทำนายได้ (ใช้กับข้อใหม่แล้ววัดผล)
  3. แยกจาก episode memory (ไม่จำเฉลยรายข้อ)
- ลบ episode memory ทิ้ง → รันใหม่ด้วย architecture knowledge เท่านั้น
- **นี่คือหลักฐาน generalization ที่ผู้ประเมินต้องการ**

---

## ลำดับการทำ (dependency)

```
T0 multi-seed (รู้ variance ก่อน)
 ├→ T1 calibration (ใช้ข้อมูล T0)
 └→ T2 refinement + T3 search + T4 perception (ทำขนาน — คนละกลุ่มโจทย์)
      └→ T5 knowledge base (สกัดจากทุก run)
```

## งบประมาณรวม

| Task | งบ |
|------|-----|
| T0 multi-seed ×2 | ~$11 |
| T1 calibration | $0 |
| T2 refinement | ~$1 |
| T3 search | ~$3 |
| T4 perception | ~$1 |
| T5 + final run | ~$6 |
| **รวม** | **~$22** |

## การประเมินผลสำเร็จ R5

| เกณฑ์ | เป้า |
|-------|------|
| Solved (ถ้า T2-T4 ได้ตามเป้า) | ~265-270/400 (66-67%) |
| Variance ระหว่าง run | รายงานได้เป็นตัวเลข |
| Calibration curve | มี ECE ที่วัดได้ |
| Architecture knowledge | ทำนายข้อใหม่ได้ดีกว่า random |

## คำถามที่ R5 ต้องตอบได้

1. คะแนน 230 เสถียรแค่ไหน? (T0)
2. ระบบรู้ตัวไหมว่ามั่นใจแค่ไหน? (T1)
3. ปัญหา 3 ชนิดแก้ด้วยยาคนละตัวได้จริงไหม? (T2-T4)
4. ความรู้ที่ได้ generalize ได้ไหม? (T5)
