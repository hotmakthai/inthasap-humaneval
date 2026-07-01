# 🏛️ โครงสร้างโปรเจกต์ Council Trinity Lab (ฉบับจริง)

> เอกสารนี้อ้างอิงจากไฟล์จริงในโปรเจกต์ (ตรวจสอบโดย Claude Code) — ไม่มีการกุชื่อไฟล์

## 1. ภาพรวม
Council Trinity Lab = สภา AI สามพี่น้องที่ช่วยทำงานให้คนทั่วไป แยกขาดจากระบบบ้าน (Iron Rule: ไม่ import อะไรจากบ้าน) ใช้ API หลายค่าย (DeepSeek→Gemini→Claude)

**2 ราง (ใหม่ 26/6) — `router.py` จำแนกอัตโนมัติ หรือคนเลือกเอง (dropdown):**
- 🅰️ **ราง A** (งานโค้ด/ตรวจได้) → `orchestrator.py` เขียน-เทส-ตรวจ-แก้ในกล่องทราย
- 🅱️ **ราง B** (งานคิด/ปรึกษา/ตัดสินใจ) → `discussion.py` ถก→ค้าน→ตกผลึก→สรุป

ตัวแทน 3 คน:
- 📐 **แจ่มจูน** — สถาปนิก/นักเขียน (ออกแบบ + สรุป)
- 👩‍💻 **แจงจูน** — Coder (เขียนโค้ด + สั่งรัน)
- 🔍 **เจนจูน** — นักรีวิว/นักสืบ (ตรวจ + ยับยั้ง + อนุมัติ)

## 2. ไฟล์จริงทั้งหมด

### ราก (root)
| ไฟล์ | หน้าที่ |
|------|---------|
| `council_lab.py` | ปุ่มสตาร์ทแบบ CLI (`python council_lab.py "งาน" --project PATH`) |
| `council_web.py` | เซิร์ฟเวอร์เว็บ (Flask จิ๋ว + SSE สด) พอร์ต 8091 |
| `council_config.json` | ตั้งค่า: model_mode, tier_order, timeouts, budget cap, claude_model |
| `.env` | กุญแจ API (DEEPSEEK / GEMINI / ANTHROPIC) |
| `README.txt` | คู่มือ + กฎเหล็ก 6 ข้อ |
| `Start_Council_Trinity.bat` | ดับเบิลคลิกเปิดเซิร์ฟเวอร์ + เบราว์เซอร์ |
| `research_cost.py` | **(ใหม่ 25/6)** งานวิจัยวัดต้นทุน — รันบน log จริง เทียบแบบเดิม vs ระบบเรา |
| `run_benchmark.py` | **(ใหม่ 26/6)** วัดสภาด้วยชุดข้อสอบ + เทสลับ (objective) — `benchmarks/` · `Run_Benchmark.bat` ดับเบิลคลิก |
| `STRUCTURE.md` | เอกสารนี้ |

### core/ (แกนหลัก — 14 ไฟล์)
| ไฟล์ | หน้าที่ |
|------|---------|
| `__init__.py` | ทำให้ core เป็น package |
| `personas.py` | นิยามลูกสาว 3 คน + บทบาท + กฎ sandbox (TOOLING_RULE) + **VOICE_RULE (พูด ค่ะ/หนู)** |
| `llm.py` | เรียกโมเดล + **Fallback chain** DeepSeek→Gemini→Claude + budget cap + call_tier |
| `sandbox.py` | กล่องทราย: เขียน/รัน jailed เฉพาะ workspace/ + env scrub + เรียก scanner |
| `scanner_rules.py` | **ตัวสแกนอันตราย** (บล็อก shell/ลบไฟล์/network/eval/getattr/open-escape) |
| `orchestrator.py` | **วงประชุม Layer B**: ออกแบบ→เขียน→Auto-Test→ตรวจ(escalate tier)→แก้ วนจนผ่าน |
| `checkpoint.py` | Undo/Checkpoint — snapshot workspace ก่อนแก้แต่ละรอบ (เก็บที่ checkpoints/) |
| `diffview.py` | คำนวณ diff (เขียว/แดง) ส่งให้ reviewer ประหยัด token |
| `project_context.py` | อ่านโปรเจกต์ที่มีอยู่ (read-only) — ใช้ผ่านช่อง --project |
| `memory.py` | Rolling Summary — บทสนทนายาวย่อของเก่า ประหยัด token |
| `logfilter.py` | **(ใหม่ 25/6)** ตัด log/traceback ยาวก่อนป้อนกลับเข้าสภา (เก็บเฉพาะ error+ไฟล์:บรรทัด ตัด ~86%) |
| `applier.py` | **(ใหม่ 25/6 รอบ 6)** แก้ไฟล์จริงในโปรเจกต์ — สำรองก่อนทับทุกไฟล์ + ย้อนคืน (restore) + เขตต้องห้าม (PROTECTED) |
| `router.py` | **(ใหม่ 26/6)** ตัวจำแนกงาน 2 ราง — A(โค้ด)/B(คิด)/MIXED + confidence + escalation (<0.7 ถามคน) |
| `discussion.py` | **(ใหม่ 26/6)** **ราง B**: สภาถกงานคิด — แจ่มจูนเสนอ→เจนจูนค้าน→ประธานชี้ขาด(CHANGE/MINOR)→สรุป 4 ส่วน (ไม่มี sandbox) |

### web/
| ไฟล์ | หน้าที่ |
|------|---------|
| `index.html` | หน้าเว็บธีมเข้ม IDE (vanilla JS + SSE สด) — ไฟล์เดียว ไม่มี framework + **โหมดแชทเดี่ยว** |

### โฟลเดอร์ข้อมูล (สร้างเองตอนรัน)
| โฟลเดอร์ | หน้าที่ |
|------|---------|
| `workspace/` | กล่องทรายที่สภาเขียน/รันโค้ด (ล้างทุกงานใหม่) |
| `checkpoints/` | สำเนา workspace ก่อนแก้แต่ละรอบ (undo ได้) |
| `logs/` | บันทึกการประชุม (session_*.json) + งบ (budget_*.txt) |
| `chats/` | **(ใหม่ 25/6)** ประวัติแชทเดี่ยวถาวรต่อคน (แจ่มจูน/แจงจูน/เจนจูน .json) |
| `projects/` | **(ใหม่ 25/6 รอบ 5)** ส่งมอบงานถาวร — ราง A: ไฟล์โค้ด · ราง B: `summary.md` (ข้อสรุปการประชุม) · แต่ละงานแยกโฟลเดอร์ `<ชื่องาน_เวลา>/` พ่อเปิดใช้ได้เลย |
| `backups/` | **(ใหม่ 25/6 รอบ 6)** สำรองไฟล์เดิมก่อน "แก้ไฟล์จริง" — มี _manifest.json ใช้ย้อนคืน |
| `benchmarks/` | **(ใหม่ 26/6)** ชุดข้อสอบวัดสภา: `cases/`(โจทย์ดิบ) + `hidden/`(เทสลับ) + `results/` |

## 3. การไหลของข้อมูล
