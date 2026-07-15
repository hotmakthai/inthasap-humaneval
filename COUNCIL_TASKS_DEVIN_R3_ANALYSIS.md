# DEVIN TASK — R3 Post-Run Analysis & Reviewer Report

## Context
ARC Engine Round 3 (evolutionary search + diff feedback + perception hints) is running on 400 training tasks.
State file: `Council_Lab/r3_state.json` | Predictions: `Council_Lab/r3_baseline_predictions.json`
Summary (when complete): `Council_Lab/r3_summary.json`

Previous rounds for comparison:
- P5b baseline: ~97 solved, ~$5.60 total cost (load from existing summary if available)
- R2: ~40–50% pass rate (load from r2_summary.json if exists)

---

## TASK: Run r3_compare.py (or write it if missing) to produce Reviewer Report

When R3 finishes (r3_state.json shows completed=400), produce a report answering these 4 reviewer questions with **real numbers from telemetry**.

---

### Reviewer Q1 — Attribution by Stage
**Question:** Evolution contributed how many additional solved tasks compared with baseline search?

From r3_state.json results, for each solved task read `solved_round` field:
- `solved_round == 1` → Initial search solved it
- `solved_round == 2` → Evolution solved it  
- `solved_round == 3` → Hybrid/perception solved it

Produce table:
```
Stage       | Solved | % of all solved
Initial     |   XX   |   XX%
Evolution   |   XX   |   XX%
Hybrid      |   XX   |   XX%
TOTAL       |   XX   |  100%
```
Summary line: "Evolution contributed +N solved tasks (X% of all solved tasks)."

---

### Reviewer Q2 — Perception Hints Impact
**Question:** What measurable impact did deterministic perception hints have on solving performance?

From r3_state.json results, read `had_perception_hints` boolean per task:
```
Setting        | Tasks | Solved | Pass Rate
Without hints  |  XXX  |  XXX  |   XX%
With hints     |  XXX  |  XXX  |   XX%
Δ              |       |  +XX  |  +XX%
```

---

### Reviewer Q3 — Marginal Cost Efficiency
**Question:** What is the additional cost per additional solved task vs previous best?

From r3_summary.json telemetry vs P5b:
```
Version | Solved | Total Cost | Cost/task
P5b     |   97   |   $5.60   |  $0.058
R3      |  XXX   |   $X.XX   |  $0.0XX
Delta   |  +XX   |   +$X.XX  |
```
Marginal Cost = ΔCost / ΔSolved = $X.XX per additional solved task

---

### Reviewer Q4 — Solved Distribution (calls needed)
**Question:** Did the system get smarter, or just fire more API calls?

From r3_state.json results, read `telemetry.llm_calls` per task:
```
Calls Needed | Tasks Solved | % of Solved
1            |     XX       |    XX%
2–4          |     XX       |    XX%
5–8          |     XX       |    XX%
9–12         |     XX       |    XX%
Failed (any) |     XX       |    —
```
If most solved tasks used 1–4 calls → system is smart.
If most used 9–12 → brute force concern.

---

### Reproducibility Note (add to report footer)
Record exact values for reproducibility:
- Model ID used (from telemetry `calls_by_tier`)
- Run date
- Random seed (if any)
- ARC dataset version (training set, 400 tasks)
- Resume capability: r3_state.json allows exact resume

---

---

### R3 Baseline Report Template — เติมตัวเลขจริงทุกช่อง

```
R3 Baseline (400 tasks)
═══════════════════════════════════════
Tasks:                    400
Solved:                   ___
Accuracy:                 ___%

Total Cost:               $___
Cost / Task:              $___
Cost / Solved Task:       $___

Total LLM Calls:          ___
Avg Calls / Task:         ___
Avg Tokens / Task:        ___

Calls by Tier:
  DeepSeek:               ___
  GLM:                    ___
  Gemini:                 ___

Solved by Stage:
  Initial:                ___
  Evolution:              ___
  Revision:               ___
  Hybrid:                 ___
═══════════════════════════════════════
```

---

### Core Question — หัวใจของรายงาน

> "จากองค์ประกอบทั้งหมด อะไรสร้างผลกระทบมากที่สุดต่อคะแนน เมื่อเทียบกับต้นทุนที่เพิ่มขึ้น?"

ตอบด้วยตาราง Feature Impact:
```
Feature        | ΔSolved | ΔCost  | Cost per +1 Solved
Evolution      |   +XX   |  +XX%  |   $X.XX
Perception     |   +XX   |  +XX%  |   $X.XX
Diff Feedback  |   +XX   |  -XX%  |   $X.XX  ← ลด cost หรือเพิ่ม solved?
```
Summary: "Feature X สร้างผลกระทบสูงสุดต่อคะแนนในสัดส่วนต้นทุนที่เพิ่มขึ้น"

---

## Output
Write final report to: `Council_Lab/r3_reviewer_report.md`

Format: markdown table + summary sentences per question. No fluff — numbers only.

## Definition of Done
- [ ] r3_reviewer_report.md exists with all 4 sections filled with real numbers
- [ ] All tables have actual values (no XXX placeholders)
- [ ] R3 Baseline Report Template filled completely (all rows)
- [ ] Feature Impact table with ΔSolved + ΔCost per feature
- [ ] Marginal cost per additional solved task calculated
- [ ] Solved distribution table complete
- [ ] Core Question answered with evidence
