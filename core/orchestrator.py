# -*- coding: utf-8 -*-
"""
core/orchestrator.py — วงประชุมสภา Layer B (รวม CORE 4 ฟีเจอร์)
  #1 อ่านโปรเจกต์ (project_context)  #2 diff (diffview)
  #3 Layer B: แจ่มจูนออกแบบ → แจงจูนเขียน → Auto-Test → เจนจูนตรวจ(escalate tier) → แก้ วนจนผ่าน
  #4 checkpoint ก่อนแก้แต่ละรอบ

workflow ต้นทุน (ตามที่พ่อออกแบบ): แจงจูน=DeepSeek เขียน(ถูก) · เจนจูน=Gemini→Claude ตรวจ(escalate)
"""
import os
import re
import glob
import json
import shutil
from datetime import datetime

from core import personas, llm, sandbox, checkpoint, diffview, project_context, memory, logfilter, applier, cross_memory, code_review, security_review, error_memory

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_BASE, "logs")
PROJECTS_DIR = os.path.join(_BASE, "projects")     # โฟลเดอร์ส่งมอบงาน (ถาวร แยกต่องาน)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(PROJECTS_DIR, exist_ok=True)

# reviewer ใช้ Gemini 3.5 ทุกรอบ (gemini_model=3.5-flash, สำรอง 2.5 อัตโนมัติถ้า 3.5 หลุด)
# Claude สงวนไว้เฉพาะปุ่ม 🤍 ส่งให้พี่จูน ที่พ่อกดเอง (ด่านสุดท้าย ไม่ใช้อัตโนมัติ)
REVIEWER_TIER = {1: "gemini", 2: "gemini", 3: "gemini", 4: "gemini"}


def _slugify(task):
    """ชื่อโฟลเดอร์จากชื่องาน — ตัดอักขระอันตราย กัน path escape"""
    first = (task or "งาน").strip().splitlines()[0][:40]
    s = re.sub(r"[^0-9A-Za-z฀-๿]+", "_", first).strip("_") or "งาน"
    return s + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def deliver(task):
    """ก๊อปไฟล์ที่สภาทำเสร็จจาก workspace/ → projects/<slug>/ (ถาวร)
    SAFETY: ปลายทางถูกบังคับให้อยู่ใต้ projects/ เท่านั้น แตะระบบ/บ้านไม่ได้"""
    files = [f for f in os.listdir(sandbox.WORKSPACE)
             if os.path.isfile(os.path.join(sandbox.WORKSPACE, f))]
    if not files:
        return ""
    dest = os.path.join(PROJECTS_DIR, _slugify(task))
    # ด่านเหล็ก: ปลายทางต้องอยู่ใต้ PROJECTS_DIR จริงๆ (กัน .. / symlink หลุด)
    if not os.path.realpath(dest).startswith(os.path.realpath(PROJECTS_DIR) + os.sep):
        return ""
    os.makedirs(dest, exist_ok=True)
    for f in files:
        shutil.copy2(os.path.join(sandbox.WORKSPACE, f), os.path.join(dest, f))
    return dest


def _read_ws(rel):
    ap = sandbox._safe_path(rel)
    if ap and os.path.exists(ap):
        try:
            return open(ap, encoding="utf-8", errors="replace").read()
        except Exception:
            return ""
    return ""


def _run_tests():
    """รัน test_*.py ทุกไฟล์ใน workspace ผ่าน sandbox — คืน (all_passed, report)"""
    paths = glob.glob(os.path.join(sandbox.WORKSPACE, "**", "test_*.py"), recursive=True)
    tests = sorted(os.path.relpath(p, sandbox.WORKSPACE).replace(os.sep, "/") for p in paths)
    if not tests:
        return (True, "(ยังไม่มีไฟล์ test_*.py)")
    allpass, rep = True, []
    for t in tests:
        code, out = sandbox.run_python(t)
        ok = (code == 0) and not out.startswith("🚫")
        allpass = allpass and ok
        rep.append(f"[{'ผ่าน' if ok else 'ไม่ผ่าน'}] {t} (exit={code})\n{logfilter.compress(out, 800)}")
    return (allpass, "\n".join(rep))


def _failed_tests(test_rep):
    """ลายเซ็น 'เทสที่ล้ม' (ไฟล์เทสไม่ผ่าน + ชื่อ test case ที่ FAIL/ERROR) — กันตัวเลขรันผันแปร
    ใช้เทียบรอบต่อรอบว่า 'ติดที่เดิม' ไหม"""
    fails = re.findall(r"\[ไม่ผ่าน\]\s+(\S+)", test_rep)
    cases = re.findall(r"(?:FAIL|ERROR):\s+(\w+)", test_rep)
    return tuple(sorted(set(fails)) + sorted(set(cases)))


def _review_cause(review):
    """ดึง 'ต้นเหตุ' จากบล็อกคำตัดสินเจนจูน (normalize) — ใช้จับ 'ชี้เรื่องเดิมซ้ำ' = ไม่คืบ
    แม้ coder จะแก้โค้ด/เทสไปแล้ว (signature เปลี่ยน) แต่ถ้าเจนจูนยังติเรื่องเดิม = วนเปล่า"""
    m = re.search(r"ต้นเหตุ[:：]?\s*(.+)", review)
    if not m:
        return ""
    return re.sub(r"\s+", "", m.group(1))[:50].lower()


def _ctx(context):
    return ("\n\n[โค้ดโปรเจกต์ที่ต้องทำงานด้วย]\n" + context[:60000]) if context else ""


def _design_prompt(task, context):
    return (f"งาน:\n{task}{_ctx(context)}\n\n"
            "ในฐานะสถาปนิก/ประธานสภา: ออกแบบโครงสร้าง/แผนสั้นๆ ให้แจงจูนทำต่อ "
            "และ 'ตีกรอบงานให้ชัด' — ปิดท้ายด้วยหัวข้อ 'เกณฑ์เสร็จ (Definition of Done):' "
            "เป็น checklist สั้นๆ ว่างานนี้ถือว่าเสร็จเมื่อทำอะไรครบ (เฉพาะ must-have จริงๆ ไม่เกินจำเป็น) "
            "— นี่คือ 'เส้นชัย' ที่ทุกคนยึด ห้ามขยายเกินนี้ระหว่างทาง\n\n"
            "‼️ สำคัญ: ระบุว่างานนี้เป็น 'งานโค้ด' หรือ 'งานไม่ใช่โค้ด' (เช่น เอกสาร/ประชาสัมพันธ์/วางแผน/คำแนะนำ) "
            "ถ้าเป็นงานไม่ใช่โค้ด ให้วางแผนเป็นเนื้อหา/ข้อความ/เอกสาร ห้ามสั่งเขียนโค้ดหรือ test_*.py "
            "เกณฑ์เสร็จของงานไม่ใช่โค้ด ให้วัดจากความครบถ้วนของเนื้อหา ไม่ใช่จากไฟล์โค้ด")


def _planning_prompt(task, design, context):
    """Planning phase — สร้างแผนละเอียด + test strategy ก่อนเขียนโค้ด"""
    return (f"งาน:\n{task}{_ctx(context)}\n\n"
            f"[แบบออกแบบจากแจ่มจูน]\n{design[:3000]}\n\n"
            "ในฐานะสถาปนิก: สร้าง 'แผนปฏิบัติ' ละเอียดระดับไฟล์ — มี:\n"
            "1. ไฟล์ที่ต้องสร้าง/แก้ (ชื่อไฟล์ + หน้าที่สั้นๆ)\n"
            "2. ลำดับการทำ (ขั้นตอน 1→2→3)\n"
            "3. 'Test Strategy': test case ที่ต้องเขียน พร้อม input → expected output\n"
            "   ระบุ test case ขั้นต่ำ 3 กรณี: (ก) กรณีปกติ (ข) กรณี edge case (ค) กรณี error\n"
            "4. ความเสี่ยงที่อาจทำให้ติด และวิธีกัน\n"
            "ตอบสั้น กระชับ อ่านได้ใน 1 นาที")


def _coder_prompt(task, plan, context, transcript, rnd, stuck_note=""):
    hist = memory.build_context(transcript)   # ยาว→[สรุป+ล่าสุด] ประหยัด token
    extra = "" if rnd == 1 else (
        "\n(รอบแก้ — อ่านผลเทส+คำตัดสินเจนจูนข้างบน แล้วแก้ 'เฉพาะที่ขาดจากเกณฑ์เสร็จ')"
        "\n‼️ แก้แบบ incremental: ถ้าไฟล์เทส/โค้ดมีส่วนที่ 'ผ่านแล้ว' ห้ามเขียนใหม่ทั้งไฟล์/ห้ามรื้อ — "
        "แก้เฉพาะจุดที่เจนจูนชี้เท่านั้น. ถ้าเจนจูนบอก 'เทสผิด' ให้แก้เฉพาะ assert/บรรทัดที่ผิดนั้น "
        "ห้ามแตะเทสตัวอื่นที่ผ่านอยู่แล้ว (กันอาการ 'แก้ A แล้ว B พัง' วนไม่จบทั้งคืน)")
    return (f"งาน:\n{task}{_ctx(context)}\n\n[แผน+เกณฑ์เสร็จที่ล็อกไว้ — ทำให้ครบเฉพาะนี้ ห้ามแตกประเด็น]\n{plan[:3000]}\n\n"
            f"บทสนทนา+ผลล่าสุด:\n{hist}\n"
            f"{extra}{stuck_note}\n\n"
            f"ถ้าแผนระบุว่าเป็น 'งานโค้ด': เขียน/แก้โค้ดด้วย code block file= และเขียน test_*.py พิสูจน์ + สั่ง RUN ถ้าต้องการ\n"
            f"ถ้าแผนระบุว่าเป็น 'งานไม่ใช่โค้ด': ตอบเป็นเนื้อหา/ข้อความ/เอกสารโดยตรง ห้ามเขียนโค้ด ห้ามใช้ file= ห้ามสร้าง test_*.py")


def _review_prompt(task, plan, files_present, diff_txt, test_rep, passed, stuck_note=""):
    return (f"งาน:\n{task}\n\n[เกณฑ์เสร็จที่ล็อกไว้ — ตัดสินเทียบกับนี้เท่านั้น]\n{plan[:3000]}\n\n"
            f"[ไฟล์ที่มีจริงในระบบตอนนี้]\n{files_present}\n"
            f"‼️ ห้ามติ๊กผ่านเกณฑ์ที่ต้องมีไฟล์ ถ้าไฟล์นั้นไม่อยู่ในรายการ 'ไฟล์ที่มีจริง' ข้างบน "
            f"(เช่นเกณฑ์บอกต้องมี demo.py แต่ไม่เห็นในรายการ = ยังไม่ผ่าน ต้องให้แจงจูนเขียนก่อน)\n\n"
            f"การเปลี่ยนแปลง (diff):\n{diff_txt[:8000]}\n\n"
            f"ผล Auto-Test:\n{test_rep[:3000]}\n\n"
            f"ตรวจ 'เทียบเกณฑ์เสร็จ' เท่านั้น: ถ้าครบเกณฑ์ พิมพ์ {personas.APPROVE_TOKEN} ทันที "
            f"ห้ามเรียกร้องเกินเกณฑ์ (nice-to-have จดไว้เฉยๆ ไม่ใช่เหตุบล็อก) "
            f"ถ้ายังไม่ครบ ให้ชี้ 'เฉพาะข้อที่ขาดจากเกณฑ์' สั้นๆ "
            f"‼️ ถ้าแผนระบุว่าเป็น 'งานไม่ใช่โค้ด' ให้ตรวจความถูกต้อง/ครบถ้วนของเนื้อหาเท่านั้น ห้ามตรวจไฟล์โค้ด ห้ามตัดสินว่าไม่ผ่านเพราะไม่มี test_*.py "
            f"(ตอนนี้เทส{'ผ่าน' if passed else 'ยังไม่ผ่าน'}){stuck_note}")


def _summary_prompt(task, transcript, approved):
    hist = memory.build_context(transcript)   # ยาว→[สรุป+ล่าสุด] ประหยัด token
    return (f"งาน:\n{task}\n\nบทสนทนาทั้งหมด:\n{hist}\n\n"
            f"สรุป: ทำอะไร, ผลลัพธ์หลัก, ผ่านการตรวจไหม ({'ผ่าน' if approved else 'ยังไม่ผ่าน/ครบรอบ'}), "
            f"ขั้นต่อไป — สั้น อ่านง่าย")


def run_task(task, project_path=None, max_rounds=4, on_event=None, should_stop=None, apply_to=None, username=None):
    transcript = []
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")

    def emit(sp, txt):
        transcript.append((sp, txt))
        if on_event:
            on_event(sp, txt)

    def stopped():
        return bool(should_stop and should_stop())

    # ── ปั๊กอิน 1: อ่านความจำข้ามเซสชั่นก่อนเริ่มงาน ──
    if username:
        mem_ctx = cross_memory.context_block(username)
        if mem_ctx:
            emit("🧠 ความจำ", mem_ctx[:500])
            task = task + "\n\n" + mem_ctx

    # ── ปั๊กอิน 1.1: ฉีดบทเรียนจากข้อผิดพลาดที่เคยเจอ ──
    lessons_ctx = error_memory.lessons_block()
    if lessons_ctx:
        emit("📚 บทเรียน", lessons_ctx[:300])
        task = task + "\n\n" + lessons_ctx

    # ── ปั๊กอิน 1.5: ฉีดโปรไฟล์ผู้ใช้เข้า task ──
    if username:
        try:
            import json as _json, os as _os
            _base = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            _ppath = _os.path.join(_base, "chats", username, "_profile.json")
            if _os.path.exists(_ppath):
                with open(_ppath, "r", encoding="utf-8") as f:
                    pd = _json.load(f)
                cg = (pd.get("career_group") or "").strip()
                if cg and cg != "ข้ามการตั้งค่า":
                    p_parts = [f"กลุ่มอาชีพ: {cg}"]
                    if pd.get("skills"):
                        p_parts.append(f"ทักษะ: {', '.join(pd['skills'])}")
                    if pd.get("style"):
                        p_parts.append(f"สไตล์: {', '.join(pd['style'])}")
                    proj = pd.get("project") or {}
                    if proj.get("name"):
                        p_parts.append(f"โปรเจกต์: {proj['name']}")
                    profile_ctx = "\n[โปรไฟล์ผู้ใช้ — ปรับคำตอบให้เข้ากับบริบท]\n" + "\n".join(p_parts) + "\n"
                    task = task + "\n\n" + profile_ctx
        except Exception:
            pass

    # CORE #1: อ่านโปรเจกต์
    context = ""
    if project_path:
        st = project_context.stats(project_path)
        if st.get("ok"):
            context = project_context.load(project_path)
            emit("📂 โปรเจกต์", f"อ่าน {project_path} — {st['files']} ไฟล์ (~{st['bytes']:,} B)")
        else:
            emit("📂 โปรเจกต์", f"⚠️ ไม่พบโฟลเดอร์ {project_path} — ทำงานแบบเขียนใหม่")

    checkpoint.snapshot("start")
    # เริ่มงานใหม่ด้วย workspace สะอาด (ของเก่า checkpoint ไว้แล้ว) — กันไฟล์เก่าปน/auto-test เพี้ยน
    import shutil as _sh
    for _f in os.listdir(sandbox.WORKSPACE):
        _p = os.path.join(sandbox.WORKSPACE, _f)
        try:
            _sh.rmtree(_p) if os.path.isdir(_p) else os.remove(_p)
        except Exception:
            pass

    # Phase 1: แจ่มจูน ออกแบบ (deepseek)
    a = personas.PERSONAS["แจ่มจูน"]
    design, dt, _ = llm.call_tier("deepseek", a["system"], _design_prompt(task, context))
    emit(f"📐 แจ่มจูน [{dt}]", design)

    # ตรวจประเภทงาน — ถ้าแจ่มจูนระบุว่าไม่ใช่โค้ด ข้าม test/review cycle
    is_noncode = "งานไม่ใช่โค้ด" in design or "ไม่ใช่โค้ด" in design

    # Phase 1.5: Planning — สร้างแผนละเอียด + test strategy ก่อนเขียนโค้ด (เฉพาะงานโค้ด)
    if not is_noncode:
        plan, pt, _ = llm.call_tier("deepseek", a["system"], _planning_prompt(task, design, context))
        emit(f"📋 แผนปฏิบัติ [{pt}]", plan)
        # ใช้ plan แทน design ในรอบ coding (plan มี test strategy ด้วย)
        design = design + "\n\n[แผนปฏิบัติ]\n" + plan

    if is_noncode:
        # โหมดงานไม่ใช่โค้ด: แจงจูนทำเนื้อหา → เจนจูนตรวจเนื้อหา → สรุป (ไม่มี test_*.py)
        c = personas.PERSONAS["แจงจูน"]
        content_reply, ct, _ = llm.call_tier("deepseek", c["system"],
                                              _coder_prompt(task, design, context, [], 1), max_tokens=8000)
        emit(f"👩‍💻 แจงจูน [{ct}]", content_reply)

        # เจนจูนตรวจเนื้อหา (ไม่มี test/diff)
        rev = personas.PERSONAS["เจนจูน"]
        review, rt, _ = llm.call_tier("gemini", rev["system"],
                                       _review_prompt(task, design, "(งานไม่ใช่โค้ด — ไม่มีไฟล์)", "(ไม่มี diff)", "(ไม่มีเทส)", True), max_tokens=8000)
        emit(f"🔍 เจนจูน [{rt}]", review)

        approved = personas.APPROVE_TOKEN in review
        if approved:
            emit("✅ สถานะ", "ผ่านการตรวจ (งานไม่ใช่โค้ด)")
        else:
            # แก้ครั้งเดียวถ้าไม่ผ่าน
            content_reply2, ct2, _ = llm.call_tier("deepseek", c["system"],
                                                    _coder_prompt(task, design, context, [(f"👩‍💻 แจงจูน [{ct}]", content_reply),
                                                                                          (f"🔍 เจนจูน [{rt}]", review)], 2), max_tokens=8000)
            emit(f"👩‍💻 แจงจูน [{ct2}]", content_reply2)
            review2, rt2, _ = llm.call_tier("gemini", rev["system"],
                                            _review_prompt(task, design, "(งานไม่ใช่โค้ด)", "(ไม่มี diff)", "(ไม่มีเทส)", True,
                                                           "\n⚠️ รอบแก้ — อ่านคำติเจนจูนข้างบน แล้วแก้เฉพาะที่ชี้"), max_tokens=8000)
            emit(f"🔍 เจนจูน [{rt2}]", review2)
            approved = personas.APPROVE_TOKEN in review2
            if approved:
                emit("✅ สถานะ", "ผ่านการตรวจรอบ 2 (งานไม่ใช่โค้ด)")
            else:
                emit("⚠️ สถานะ", "ยังไม่ผ่านหลังแก้ 1 รอบ — ส่งมอบเนื้อหาล่าสุดให้ผู้ใช้ตัดสินต่อ")

        # สรุป
        summary, sm, _ = llm.call_tier("deepseek", a["system"], _summary_prompt(task, transcript, approved))
        emit(f"📋 สรุปมติ [{sm}]", summary)

        # บันทึก session
        try:
            with open(os.path.join(LOG_DIR, f"session_{sid}.json"), "w", encoding="utf-8") as f:
                json.dump({"task": task, "project": project_path, "approved": approved,
                           "username": username or "admin",
                           "rounds": 1, "transcript": transcript, "summary": summary},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return summary, transcript

    approved = False
    # ── ข้อ 2: ตัวจับ "ไม่คืบหน้า" (กันวนเผาโทเค็น) ──
    prev_failed = None   # ลายเซ็นเทสที่ล้มรอบก่อน
    prev_code = None     # โค้ดที่เขียนรอบก่อน
    prev_cause = None    # 'ต้นเหตุ' ที่เจนจูนชี้รอบก่อน (จับการชี้เรื่องเดิมซ้ำ)
    stuck = 0            # นับรอบติดที่เดิมต่อเนื่อง
    stuck_note = ""      # สัญญาณฉีดเข้าหัวสภารอบถัดไป
    for rnd in range(1, max_rounds + 1):
        if stopped():
            emit("⏹ หยุด", "ผู้ใช้สั่งหยุดการประชุม")
            return "หยุดโดยผู้ใช้", transcript
        # แจงจูน เขียน/แก้ (deepseek — ของถูกทำงานหนัก)
        c = personas.PERSONAS["แจงจูน"]
        code_reply, ct, _ = llm.call_tier("deepseek", c["system"],
                                           _coder_prompt(task, design, context, transcript, rnd, stuck_note), max_tokens=8000)
        emit(f"👩‍💻 แจงจูน [{ct}]", code_reply)

        # CORE #4: checkpoint ก่อนแก้ + CORE #2: เก็บของเดิมไว้ทำ diff
        files = sandbox.extract_files(code_reply)
        code_concat = "".join(content for _, content in files)   # ลายเซ็นโค้ดรอบนี้
        olds = {rel: _read_ws(rel) for rel, _ in files}
        checkpoint.snapshot(f"r{rnd}")
        wrote = sandbox.write_files(files)
        if wrote:
            emit("🛠️ sandbox", "เขียนไฟล์ → " + " | ".join(f"{s}:{r}" for s, r, _ in wrote))
        diffs = {rel: diffview.compute(olds.get(rel, ""), content, rel) for rel, content in files}
        diff_txt = diffview.summarize_changes(diffs)

        # รันที่ coder สั่ง RUN เอง
        for rp in sandbox.find_runs(code_reply):
            rc, ro = sandbox.run_python(rp)
            emit("▶️ sandbox", f"รัน {rp} (exit={rc})\n{logfilter.compress(ro, 800)}")

        # CORE #3: Auto-Test
        passed, test_rep = _run_tests()
        emit("🧪 Auto-Test", test_rep[:1200])

        # บันทึกเทสที่ล้ม → สะสมบทเรียน
        if not passed:
            failed_names = ", ".join(_failed_tests(test_rep))
            if failed_names:
                error_memory.record_test_failure(
                    "sandbox", failed_names[:200],
                    f"เทสล้มรอบ {rnd}: {test_rep[:300]}"
                )

        # เจนจูน ตรวจ (escalate tier ตามรอบ) — เห็น diff + ผลเทส
        rev = personas.PERSONAS["เจนจูน"]
        rtier = REVIEWER_TIER.get(rnd, "gemini")
        present = ", ".join(sorted(
            os.path.relpath(p, sandbox.WORKSPACE).replace(os.sep, "/")
            for p in glob.glob(os.path.join(sandbox.WORKSPACE, "**", "*.py"), recursive=True))) or "(ยังไม่มีไฟล์)"
        review, rt, _ = llm.call_tier(rtier, rev["system"],
                                      _review_prompt(task, design, present, diff_txt, test_rep, passed, stuck_note), max_tokens=8000)
        emit(f"🔍 เจนจูน [{rt}]", review)

        if passed and personas.APPROVE_TOKEN in review:
            approved = True
            emit("✅ สถานะ", f"ผ่านการตรวจรอบ {rnd}")
            break
        if stopped():
            emit("⏹ หยุด", "ผู้ใช้สั่งหยุดการประชุม")
            return "หยุดโดยผู้ใช้", transcript

        # ── ข้อ 2: ตรวจความคืบหน้า — "ไม่คืบ" = อย่างใดอย่างหนึ่ง:
        #   (ก) เทสล้มแบบเดิม  (ข) โค้ดไม่เปลี่ยน  (ค) เจนจูนชี้ 'ต้นเหตุเดิม' ซ้ำ (แม้ coder รื้อโค้ด/เทสใหม่) ──
        failed = _failed_tests(test_rep)
        cause = _review_cause(review)
        same_result = (prev_failed is not None and failed == prev_failed and not passed)
        same_code = (prev_code is not None and code_concat == prev_code)
        same_cause = (bool(prev_cause) and bool(cause) and cause == prev_cause and not passed)
        stuck = stuck + 1 if ((same_result or same_code or same_cause) and not passed) else 0
        prev_failed, prev_code, prev_cause = failed, code_concat, cause

        # หยุดอัตโนมัติเมื่อไม่คืบหน้า 2 รอบติด — กันวนเผาโทเค็นเปล่า (ความเจ็บปวด 'แก้สิบรอบทั้งคืน')
        if stuck >= 2:
            ติด = (", ".join(failed) or "เทสไม่ผ่าน") + (" · เจนจูนชี้เรื่องเดิมซ้ำ" if same_cause else "")
            # บันทึกบทเรียน: ติดที่เดิม → บอกว่าเกิดจากอะไร
            error_memory.record_stuck(
                task[:100],
                ติด[:200],
                f"ติด {stuck+1} รอบ — สาเหตุที่พบบ่อย: เทสตั้งโจทย์ผิด / coder แก้ไม่ตรงที่เจนจูนชี้ / โจทย์ขาดข้อมูล"
            )
            emit("🛑 หยุด (ประหยัดโทเค็น)",
                 f"ไม่คืบหน้า {stuck + 1} รอบติด — ติดที่: {ติด}\n"
                 "หยุดวนเพื่อไม่เผาโทเค็นเปล่า · สภาส่งงานล่าสุด + จุดที่ติดให้ผู้ใช้ตัดสิน "
                 "(สาเหตุที่พบบ่อย: เทสตั้งโจทย์ผิด / coder แก้ไม่ตรงที่เจนจูนชี้ / โจทย์ขาดข้อมูลที่ต้องถามผู้ใช้)")
            break

        # ฉีดสัญญาณเข้าหัวสภารอบหน้า ให้เปลี่ยนวิธีคิด ไม่แก้ซ้ำเดิม
        stuck_note = ("\n\n⚠️ [สัญญาณไม่คืบหน้า] รอบที่แล้วแก้แล้ว 'ผลเทสยังเหมือนเดิมเป๊ะ' = แก้ไม่ตรงจุด "
                      "หรือเทสเขียนผิดเอง — ห้ามแก้ซ้ำแนวเดิม! ให้: (1) อ่าน error จริงในผลเทสหา root cause ที่แท้ "
                      "(2) ถามตัวเองว่า 'สิ่งที่เทสคาดหวังถูกต้องตามความจริงไหม' ถ้าเทสผิดให้แก้เทส "
                      "(3) ถ้าติดจุดเดิม ลองเปลี่ยนวิธีคิดคนละทาง") if stuck >= 1 else ""
        emit("🔄 สถานะ", f"รอบ {rnd} ยังไม่ผ่าน → แก้รอบถัดไป"
             + ("  ⚠️ ติดที่เดิม — สั่งสภาเปลี่ยนวิธีคิด" if stuck >= 1 else ""))

    # สรุป
    summary, sm, _ = llm.call_tier("deepseek", a["system"], _summary_prompt(task, transcript, approved))
    emit(f"📋 สรุปมติ [{sm}]", summary)

    # ── ปั๊กอิน 2: รีวิว 5 เอเจนต์ (รอบสุดท้าย ก่อนส่งมอบ) ──
    if approved and not is_noncode:
        emit("🔍 รีวิว 5 เอเจนต์", "กำลังตรวจด้วย 5 มุมมอง: Bug · Style · Performance · Security · Git")
        try:
            rv_summary, rv_findings = code_review.run_review(
                sandbox.WORKSPACE, should_stop=should_stop)
            for key, f in rv_findings.items():
                emit(f"🔍 {f['name']}", f.get("report", "")[:800])
            emit("🔍 สรุปรีวิว", rv_summary)
        except Exception as e:
            emit("🔍 รีวิว 5 เอเจนต์", f"(รีวิวไม่สำเร็จ: {str(e)[:120]})")

    # ── ปั๊กอิน 3: ซีเคียวริตี้ สแกน ก่อนส่งมอบ ──
    if approved and not is_noncode:
        emit("🔒 ซีเคียวริตี้", "กำลังสแกนช่องโหว่ก่อนส่งมอบ...")
        try:
            sec_summary, sec_findings, sec_ai = security_review.run_security_review(
                sandbox.WORKSPACE, should_stop=should_stop)
            high_count = sum(1 for f in sec_findings if f.get("severity") == "สูง")
            if high_count > 0:
                emit("🔒 ซีเคียวริตี้", f"⚠️ พบ {high_count} ช่องโหว่ระดับสูง — ควรแก้ก่อนใช้!\n{sec_summary}")
            else:
                emit("🔒 ซีเคียวริตี้", sec_summary)
            if sec_ai:
                emit("🔒 AI Audit", sec_ai[:800])
        except Exception as e:
            emit("🔒 ซีเคียวริตี้", f"(สแกนไม่สำเร็จ: {str(e)[:120]})")

    # ส่งมอบงาน: ก๊อปไฟล์ที่ทำเสร็จไป projects/<งาน>/ (ถาวร พ่อเปิดใช้ได้เลย ไม่ต้องก๊อปวาง)
    try:
        dest = deliver(task)
        if dest:
            rel = os.path.relpath(dest, _BASE)
            emit("📦 ส่งมอบงาน", f"เขียนไฟล์ให้ผู้ใช้แล้วที่โฟลเดอร์: {rel}\n"
                                 f"(เปิดดู/ใช้ได้เลย ไม่ต้องก๊อปวาง){'  ✅ ผ่านการตรวจ' if approved else '  ⚠️ ยังไม่ผ่านการตรวจครบ — ตรวจก่อนใช้'}")
    except Exception as e:
        emit("📦 ส่งมอบงาน", f"(ส่งมอบไม่สำเร็จ: {str(e)[:120]})")

    # แก้ไฟล์จริงในโปรเจกต์ (ถ้าพ่อเปิด) — สำรองของเดิมก่อนทับทุกไฟล์ ย้อนคืนได้
    if apply_to:
        try:
            m = applier.apply_files(sandbox.WORKSPACE, apply_to)
            brel = os.path.relpath(m["backup_dir"], _BASE)
            emit("✍️ แก้ไฟล์จริง", f"แก้ในโปรเจกต์: {apply_to} ({len(m['applied'])} ไฟล์)\n"
                                   f"สำรองของเดิมไว้แล้วที่: {brel}\n"
                                   f"ถ้าพัง สั่ง 'ย้อนคืน' ได้ทุกเมื่อ (backup id: {os.path.basename(m['backup_dir'])})")
        except applier.GuardError as e:
            emit("✍️ แก้ไฟล์จริง", f"⛔ ไม่แก้ให้เพื่อความปลอดภัย — {e}")
        except Exception as e:
            emit("✍️ แก้ไฟล์จริง", f"(แก้ไม่สำเร็จ: {str(e)[:150]})")

    try:
        with open(os.path.join(LOG_DIR, f"session_{sid}.json"), "w", encoding="utf-8") as f:
            json.dump({"task": task, "project": project_path, "approved": approved,
                       "username": username or "admin",
                       "rounds": max_rounds, "transcript": transcript, "summary": summary},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return summary, transcript


# ── โหมดตรวจสอบบั๊กทั้งโปรเจกต์ (Project Audit) ──

def _list_project_files(project_path):
    """ลิสต์ไฟล์โค้ดในโปรเจกต์ ข้าม skip_dirs และไฟล์ลับ"""
    files = []
    for dirpath, dirs, fnames in os.walk(project_path):
        dirs[:] = sorted([d for d in dirs if d not in project_context.SKIP_DIRS and not d.startswith(".")])
        for f in sorted(fnames):
            ext = os.path.splitext(f)[1].lower()
            if ext not in project_context.TEXT_EXT:
                continue
            if project_context._is_secret(f):
                continue
            fp = os.path.join(dirpath, f)
            rel = os.path.relpath(fp, project_path).replace("\\", "/")
            files.append((rel, fp))
    return files


def _audit_scan_prompt(file_list, context, batch_info=""):
    """สร้าง prompt ให้ AI สแกนบั๊กจากรายการไฟล์ + เนื้อหา"""
    return (f"[งาน: ตรวจสอบบั๊กทั้งโปรเจกต์]\n\n"
            f"โครงสร้างไฟล์ทั้งโปรเจกต์ (path แบบ relative):\n{file_list}\n\n"
            f"{batch_info}"
            f"เนื้อไฟล์ที่ต้องตรวจ:\n{context}\n\n"
            "ในฐานะ Senior Software Engineer ที่ค่ายยักษ์ใหญ่: ตรวจสอบทุกไฟล์อย่างละเอียด\n\n"
            "ตรวจสอบครบทุกด้าน:\n"
            "1. บั๊ก logic — ผิดพลาดในการคำนวณ, เงื่อนไขผิด, ลำดับผิด\n"
            "2. Edge case — ค่าว่าง, ค่าติดลบ, ค่าเกินขอบเขต, ข้อมูลผิดรูปแบบ\n"
            "3. Race condition / Thread safety — การเข้าถึงทรัพยากรร่วมกัน\n"
            "4. Resource leak — ไฟล์/การเชื่อมต่อไม่ปิด, memory leak\n"
            "5. Security — injection, path traversal, ข้อมูลลับรั่ว, input ไม่ validate\n"
            "6. Error handling — exception ไม่ catch, catch ผิดประเภท, ไม่ log\n"
            "7. Type safety — ประเภทข้อมูลผิด, None ไม่เช็ค, แปลงประเภทไม่ปลอดภัย\n"
            "8. Code quality — โค้ดซ้ำซ้อน, ชื่อไม่สื่อ, ฟังก์ชันยาวเกิน, ไม่ follow best practice\n\n"
            "รายงานเป็นรูปแบบ:\n"
            "=== ไฟล์: <path แบบ relative ตามที่อยู่ในรายการด้านบน> ===\n"
            "บั๊ก: <อธิบายบั๊กและสาเหตุ>\n"
            "ระดับ: <สูง=ทำงานผิด/ล่ม/ช่องโหว่ | กลาง=ทำงานได้แต่ผิดบางกรณี | ต่ำ=คุณภาพโค้ด>\n"
            "ประเภท: <logic/edge-case/race/resource/security/error-handling/type/quality>\n"
            "แนวทางแก้: <สั้นๆ พร้อมตัวอย่างโค้ดถ้าต้องการ>\n\n"
            "‼️ ใช้ path แบบ relative ตรงตามรายการไฟล์ด้านบน เช่น workflow/task_queue.py ไม่ใช่ task_queue.py\n"
            "‼️ บั๊กระดับกลางก็ต้องรายงาน — อย่าจัดเป็น 'ข้อกังวล' แล้วข้าม\n"
            "‼️ ถ้าเป็นประเด็นออกแบบที่อาจทำให้โปรแกรมทำงานผิด ให้จัดระดับกลาง ไม่ใช่ต่ำ\n"
            "ถ้าไฟล์ไหนไม่มีบั๊กจริง ข้ามไฟล์นั้น\n"
            "ถ้าทุกไฟล์ผ่านจริงๆ พิมพ์ [ไม่มีบั๊ก] ชัดเจน\n"
            "ตอบกระชับ ตรงประเด็น แต่ละไฟล์แยกชัด")


def _audit_fix_prompt(file_rel, file_content, bug_desc):
    """สร้าง prompt ให้ AI แก้ไฟล์เดียวที่มีบั๊ก"""
    return (f"[งาน: แก้บั๊กในไฟล์ {file_rel}]\n\n"
            f"บั๊กที่พบ:\n{bug_desc}\n\n"
            f"เนื้อไฟล์ปัจจุบัน:\n```\n{file_content[:20000]}\n```\n\n"
            f"‼️ สำคัญ: เขียนไฟล์ที่แก้แล้วด้วย code block ที่มี file={file_rel}\n"
            f"‼️ ห้ามเปลี่ยน path ห้ามใช้ชื่อไฟล์อื่น ต้องใช้ file={file_rel} เท่านั้น\n"
            f"‼️ ห้ามสร้างไฟล์ใหม่ที่ root — ต้องเขียนทับไฟล์เดิมที่ path เดิม\n\n"
            "เขียนเฉพาะส่วนที่แก้ ห้ามรื้อโค้ดที่ไม่เกี่ยวข้อง\n"
            "ถ้าบั๊กเล็ก แก้เฉพาะบรรทัดที่มีปัญหา\n"
            "ถ้าไฟล์ใหญ่ เขียนเฉพาะส่วนที่เปลี่ยน พร้อม comment บอกบรรทัดที่แก้")


def run_project_audit(project_path, on_event=None, should_stop=None, username=None, get_answer=None):
    """ตรวจสอบบั๊กทั้งโปรเจกต์ — สแกน → แก้ → ทดสอบ → วนจนเสร็จ"""
    transcript = []
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")

    def emit(sp, txt):
        transcript.append((sp, txt))
        if on_event:
            on_event(sp, txt)

    def stopped():
        return bool(should_stop and should_stop())

    if not project_path or not os.path.isdir(project_path):
        emit("⚠️ error", f"ไม่พบโฟลเดอร์: {project_path}")
        return "ไม่พบโฟลเดอร์", transcript

    emit("📂 โปรเจกต์", f"เริ่มตรวจสอบทั้งโปรเจกต์: {project_path}")

    # ฉีดบทเรียนจากข้อผิดพลาดที่เคยเจอ
    lessons_ctx = error_memory.lessons_block()
    if lessons_ctx:
        emit("📚 บทเรียน", lessons_ctx[:300])

    # อ่านไฟล์ทั้งโปรเจกต์
    all_files = _list_project_files(project_path)
    if not all_files:
        emit("⚠️ error", "ไม่พบไฟล์โค้ดในโปรเจกต์")
        return "ไม่พบไฟล์", transcript

    emit("📋 ไฟล์ทั้งหมด", f"พบ {len(all_files)} ไฟล์: " + ", ".join(r for r, _ in all_files[:20]) +
         ("..." if len(all_files) > 20 else ""))

    # ฉีด profile ถ้ามี
    profile_block = ""
    if username:
        try:
            import json as _json, os as _os
            _ppath = _os.path.join(_BASE, "chats", username, "_profile.json")
            if _os.path.exists(_ppath):
                with open(_ppath, "r", encoding="utf-8") as f:
                    pd = _json.load(f)
                cg = (pd.get("career_group") or "").strip()
                if cg and cg != "ข้ามการตั้งค่า":
                    profile_block = f"\n[โปรไฟล์ผู้ใช้ — กลุ่มอาชีพ: {cg}]\n"
        except Exception:
            pass

    # วนสแกน + แก้ สูงสุด 5 รอบ
    MAX_AUDIT_ROUNDS = 5
    a = personas.PERSONAS["แจ่มจูน"]
    c = personas.PERSONAS["แจงจูน"]
    rev = personas.PERSONAS["เจนจูน"]

    for audit_round in range(1, MAX_AUDIT_ROUNDS + 1):
        if stopped():
            emit("⏹ หยุด", "ผู้ใช้สั่งหยุดการตรวจสอบ")
            return "หยุดโดยผู้ใช้", transcript

        emit(f"🔄 รอบตรวจที่ {audit_round}", f"สแกนบั๊กรอบที่ {audit_round}/{MAX_AUDIT_ROUNDS}")

        # อ่านเนื้อไฟล์ทั้งหมด (รีเฟรชทุกรอบ เพราะอาจแก้ไปแล้ว)
        all_files = _list_project_files(project_path)
        file_list_str = "\n".join(r for r, _ in all_files)

        # อ่านเนื้อไฟล์ทั้งหมด — ไม่จำกัดขนาด แต่แบ่งเป็น batch เพื่อส่ง AI
        file_contents = []  # [(rel, content), ...]
        for rel, fp in all_files:
            try:
                data = open(fp, encoding="utf-8", errors="replace").read()
                data, _ = project_context._redact_secrets(data)
                file_contents.append((rel, data))
            except Exception:
                continue

        # แบ่งเป็น batch ๆ ละ ~50,000 ตัวอักษร (ประมาณ 12-15 ไฟล์ต่อ batch)
        BATCH_SIZE = 50000
        batches = []
        current_batch = []
        current_size = 0
        for rel, data in file_contents:
            if current_size + len(data) > BATCH_SIZE and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_size = 0
            current_batch.append((rel, data))
            current_size += len(data)
        if current_batch:
            batches.append(current_batch)

        emit("📋 สแกน", f"แบ่ง {len(file_contents)} ไฟล์เป็น {len(batches)} ชุด สแกนทีละชุด")

        # สแกนทีละ batch รวมบั๊กทั้งหมด
        all_scan_results = []
        all_bugs = {}
        for bi, batch in enumerate(batches):
            if stopped():
                break
            batch_context = "\n\n".join(f"=== {rel} ===\n{data}" for rel, data in batch)
            batch_info = f"(ชุดที่ {bi+1}/{len(batches)} — ตรวจเฉพาะไฟล์ในชุดนี้)\n" if len(batches) > 1 else ""
            scan_prompt = _audit_scan_prompt(file_list_str, batch_context, batch_info) + profile_block
            scan_result, st, _ = llm.call_tier("deepseek", a["system"], scan_prompt, max_tokens=8000)
            batch_files = ", ".join(rel for rel, _ in batch[:5])
            emit(f"📐 แจ่มจูน สแกน ชุด {bi+1}/{len(batches)} [{st}]",
                 f"ตรวจ {len(batch)} ไฟล์: {batch_files}{'...' if len(batch)>5 else ''}\n{scan_result[:5000]}")
            all_scan_results.append(scan_result)

            # แยกบั๊กจาก batch นี้
            batch_bugs = _parse_audit_bugs(scan_result)
            if batch_bugs:
                all_bugs.update(batch_bugs)

        # ตรวจว่าทุก batch บอกไม่มีบั๊ก
        if not all_bugs:
            # ไม่ parse ได้ — เช็คว่า AI บอก [ไม่มีบั๊ก] จริงๆ หรือไม่
            no_bug_count = sum(1 for r in all_scan_results if "[ไม่มีบั๊ก]" in r)
            if no_bug_count == len(all_scan_results):
                emit("✅ สถานะ", f"รอบ {audit_round}: ไม่พบบั๊กในโปรเจกต์ทั้งหมด — ตรวจเสร็จ!")
                break
            # AI ไม่ได้บอก [ไม่มีบั๊ก] แต่ก็ไม่ parse ได้ — อาจมีบั๊กแต่ format ไม่ตรง
            emit("ℹ️ สถานะ", f"รอบ {audit_round}: AI รายงานประเด็นบางอย่าง แต่ไม่สามารถแยกเป็นรายไฟล์ได้ — ตรวจสอบด้วยตา")
            # ส่งรายงานดิบให้ผู้ใช้ดู
            for r in all_scan_results:
                if r.strip() and "[ไม่มีบั๊ก]" not in r:
                    emit("📋 รายงานดิบ", r[:1500])
            break

        file_bugs = all_bugs
        emit("📋 บั๊กที่พบ", f"รอบ {audit_round}: พบบั๊กใน {len(file_bugs)} ไฟล์ (จาก {len(batches)} ชุด)")

        # ถามผู้ใช้: แก้ทั้งหมดหรือเฉพาะระดับสูง?
        fix_mode = "all"  # default: แก้ทั้งหมด
        if get_answer and len(file_bugs) > 1:
            bug_summary = "\n".join(f"  {i+1}. {f}: {d[:80]}" for i, (f, d) in enumerate(file_bugs.items()))
            question = f"พบบั๊ก {len(file_bugs)} ข้อ:\n{bug_summary}\n\nต้องการให้แก้ทั้งหมด หรือเฉพาะบั๊กระดับสูง?"
            options = [
                {"label": "แก้ทั้งหมด", "value": "all"},
                {"label": "เฉพาะระดับสูง", "value": "high"},
                {"label": "ข้ามรอบนี้", "value": "skip"}
            ]
            emit("__question__", json.dumps({"question": question, "options": options}, ensure_ascii=False))
            answer = get_answer(timeout=120)
            if answer:
                fix_mode = answer
                emit("🙋 คำตอบ", f"ผู้ใช้เลือก: {answer}")
            else:
                emit("⏱ หมดเวลา", "ไม่ตอบใน 2 นาที — แก้ทั้งหมด")

        if fix_mode == "skip":
            emit("⏭ ข้าม", f"รอบ {audit_round}: ผู้ใช้เลือกข้าม — ไปรอบถัดไป")
            continue

        # กรองบั๊กตามที่ผู้ใช้เลือก
        bugs_to_fix = file_bugs
        if fix_mode == "high":
            bugs_to_fix = {f: d for f, d in file_bugs.items() if "สูง" in d or "high" in d.lower()}
            if not bugs_to_fix:
                emit("ℹ️ สถานะ", "ไม่มีบั๊กระดับสูง — ข้ามรอบนี้")
                continue
            emit("📋 กรอง", f"แก้เฉพาะบั๊กระดับสูง: {len(bugs_to_fix)}/{len(file_bugs)} ไฟล์")

        # แก้ทีละไฟล์
        fixed_count = 0
        for file_rel, bug_desc in bugs_to_fix.items():
            if stopped():
                emit("⏹ หยุด", "ผู้ใช้สั่งหยุดระหว่างแก้ไฟล์")
                break

            # หาไฟล์จริง
            fp = os.path.join(project_path, file_rel.replace("/", os.sep))
            if not os.path.exists(fp):
                emit("⚠️ ข้าม", f"ไม่พบไฟล์: {file_rel}")
                continue

            try:
                file_content = open(fp, encoding="utf-8", errors="replace").read()
            except Exception as e:
                emit("⚠️ ข้าม", f"อ่านไม่ได้: {file_rel} — {e}")
                continue

            emit(f"🔧 แก้ไฟล์", f"กำลังแก้: {file_rel} — {bug_desc[:100]}")

            # สั่งแจงจูนแก้
            fix_prompt = _audit_fix_prompt(file_rel, file_content, bug_desc) + profile_block
            fix_reply, ft, _ = llm.call_tier("deepseek", c["system"], fix_prompt, max_tokens=8000)
            emit(f"👩‍💻 แจงจูน แก้ [{ft}]", fix_reply[:5000])

            # ดึงไฟล์ที่แก้แล้ว
            files = sandbox.extract_files(fix_reply)
            if not files:
                emit("⚠️ ไม่ได้แก้", f"แจงจูนไม่ส่งไฟล์ที่แก้แล้วสำหรับ {file_rel}")
                continue

            # ตรวจว่า AI เขียน path ถูกต้องไหม — ถ้าผิด แก้กลับ
            fixed_files = []
            for rel_path, content in files:
                if rel_path != file_rel:
                    # AI เขียนผิดที่ — ใช้ path ที่ถูกต้อง
                    emit("⚠️ แก้ path", f"AI เขียน file={rel_path} แก้เป็น {file_rel}")
                    fixed_files.append((file_rel, content))
                else:
                    fixed_files.append((rel_path, content))
            files = fixed_files

            # เขียนลง sandbox ก่อน (เพื่อทดสอบ)
            write_results = sandbox.write_files(files)
            written = [r[1] for r in write_results if r[0] == "WROTE"]
            if not written:
                emit("⚠️ ไม่ได้แก้", f"ไม่สามารถเขียนไฟล์ลง sandbox สำหรับ {file_rel}: {write_results}")
                continue

            # ก๊อปไฟล์ dependencies จากโปรเจกต์ลง sandbox (เพื่อให้ import ทำงานได้)
            for dep_rel, dep_fp in all_files:
                if dep_rel == file_rel:
                    continue
                dep_sandbox = os.path.join(sandbox.WORKSPACE, dep_rel.replace("/", os.sep))
                dep_dir = os.path.dirname(dep_sandbox)
                try:
                    os.makedirs(dep_dir, exist_ok=True)
                    shutil.copy2(dep_fp, dep_sandbox)
                except Exception:
                    pass

            # ทดสอบรันถ้าเป็น .py — ข้ามถ้าเป็น test file ที่ import โมดูลเฉพาะ
            for rel_path, _ in files:
                if rel_path.endswith(".py"):
                    rc, out = sandbox.run_python(rel_path)
                    if rc == 0:
                        emit("▶️ ทดสอบ", f"{rel_path} รันผ่าน (exit=0)")
                    else:
                        # ตรวจว่าเป็น import error หรือบั๊กจริง
                        if "ModuleNotFoundError" in out or "ImportError" in out:
                            emit("▶️ ทดสอบ", f"{rel_path} import error (ไม่ใช่บั๊กโค้ด) — ข้าม\n{out[:200]}")
                        else:
                            emit("▶️ ทดสอบ", f"{rel_path} รันไม่ผ่าน (exit={rc})\n{out[:500]}")

            # ก๊อปกลับโปรเจกต์จริง — เฉพาะไฟล์ที่แก้ (ไม่รวม dependencies)
            applied_ok = False
            apply_dir = os.path.join(sandbox.WORKSPACE, "_apply_tmp")
            try:
                os.makedirs(apply_dir, exist_ok=True)
                for rel_path, content in files:
                    dest = os.path.join(apply_dir, rel_path.replace("/", os.sep))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "w", encoding="utf-8") as f:
                        f.write(content)
                m = applier.apply_files(apply_dir, project_path)
                brel = os.path.relpath(m["backup_dir"], _BASE)
                emit("✍️ แก้ไฟล์จริง", f"แก้ {len(m['applied'])} ไฟล์ใน {project_path}\n"
                     f"สำรองของเดิมไว้ที่: {brel}")
                fixed_count += 1
                applied_ok = True
            except applier.GuardError as e:
                emit("✍️ แก้ไฟล์จริง", f"⛔ ไม่แก้เพื่อความปลอดภัย — {e}")
            except Exception as e:
                emit("✍️ แก้ไฟล์จริง", f"(แก้ไม่สำเร็จ: {str(e)[:150]})")
            finally:
                shutil.rmtree(apply_dir, ignore_errors=True)

            # ── Review หลังแก้: ใช้ Gemini ตรวจทบ (fallback 3 รุ่น) ──
            # ทำนอก try block ของ apply เพื่อให้แน่ใจว่าทำงานเสมอ
            if applied_ok:
                try:
                    fixed_content = open(fp, encoding="utf-8", errors="replace").read()
                    review_prompt = (f"[งาน: ตรวจทบการแก้บั๊กในไฟล์ {file_rel}]\n\n"
                                     f"บั๊กเดิม:\n{bug_desc[:500]}\n\n"
                                     f"ไฟล์หลังแก้:\n```\n{fixed_content[:15000]}\n```\n\n"
                                     "ตรวจสอบ:\n"
                                     "1. บั๊กเดิมหายหรือไม่?\n"
                                     "2. มีบั๊กใหม่เกิดจากการแก้ไหม?\n"
                                     "3. โค้ดอื่นที่ไม่เกี่ยวข้องถูกแก้ไหม?\n"
                                     "ตอบสั้น: ผ่าน/ไม่ผ่าน + เหตุผล")
                    emit("🔍 เจนจูน ตรวจทบ", f"กำลังตรวจทบ {file_rel}...")
                    review_result, rt, _ = llm.call_tier("gemini", rev["system"], review_prompt, max_tokens=2000)
                    if rt == "none":
                        emit("ℹ️ เจนจูน ตรวจทบ", f"{file_rel}: ไม่สามารถเรียก AI ตรวจทบได้ — {review_result[:200]}")
                    elif "ผ่าน" in review_result and "ไม่ผ่าน" not in review_result:
                        emit(f"✅ เจนจูน ตรวจทบ [{rt}]", f"{file_rel}: แก้ถูกต้อง — ผ่าน")
                    else:
                        emit(f"⚠️ เจนจูน ตรวจทบ [{rt}]", f"{file_rel}: {review_result[:500]}")
                except Exception as re:
                    emit("ℹ️ ตรวจทบ", f"{file_rel}: ข้าม review เพราะ error: {str(re)[:150]}")

            # เคลียร์ sandbox ระหว่างไฟล์
            for _f in os.listdir(sandbox.WORKSPACE):
                _p = os.path.join(sandbox.WORKSPACE, _f)
                try:
                    shutil.rmtree(_p) if os.path.isdir(_p) else os.remove(_p)
                except Exception:
                    pass

        emit("📊 สรุปรอบ", f"รอบ {audit_round}: แก้ไข้ {fixed_count}/{len(file_bugs)} ไฟล์")

        if fixed_count == 0:
            emit("⚠️ สถานะ", f"รอบ {audit_round}: ไม่สามารถแก้ไฟล์ใดได้ — หยุดประหยัดโทเค็น")
            break

    # สรุป
    summary_prompt = (f"งาน: ตรวจสอบบั๊กทั้งโปรเจกต์ {project_path}\n"
                      f"จำนวนรอบ: {audit_round}\n"
                      f"บทสนทนา:\n" + "\n".join(f"[{sp}] {txt[:200]}" for sp, txt in transcript[-20:]) +
                      "\n\nสรุป: ตรวจพบและแก้บั๊กอะไรบ้าง สั้น อ่านง่าย")
    summary, sm, _ = llm.call_tier("deepseek", a["system"], summary_prompt, max_tokens=2000)
    emit(f"📋 สรุปมติ [{sm}]", summary)

    # บันทึก session
    try:
        with open(os.path.join(LOG_DIR, f"audit_{sid}.json"), "w", encoding="utf-8") as f:
            json.dump({"type": "audit", "project": project_path,
                       "username": username or "admin",
                       "rounds": audit_round, "transcript": transcript, "summary": summary},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return summary, transcript


def _parse_audit_bugs(scan_text):
    """แยกบั๊กจากผลสแกนเป็น dict {file_rel: bug_desc}"""
    bugs = {}
    current_file = None
    current_desc = []
    for line in (scan_text or "").splitlines():
        # จับหลายรูปแบบ: === ไฟล์:, ## === ไฟล์:, ## ไฟล์:, **ไฟล์:**
        m = re.match(r"(?:#{1,6}\s*)?(?:===\s*)?ไฟล์[:：]\s*(.+?)(?:\s*===)?\s*$", line)
        if not m:
            m = re.match(r"(?:#{1,6}\s*)?===\s*ไฟล์[:：]\s*(.+?)\s*===", line)
        if not m:
            m = re.match(r"\*\*ไฟล์[:：]\s*(.+?)\*\*", line)
        if not m:
            m = re.match(r"(?:#{1,6}\s*)?===\s*ไฟล์[:：]\s*(.+?)\s*$", line)
        if m:
            if current_file and current_desc:
                bugs[current_file] = "\n".join(current_desc).strip()
            # ตัดคำอธิบายในวงเล็บออก เช่น "task_queue.py (รากโปรเจกต์)" → "task_queue.py"
            fname = m.group(1).strip()
            fname = re.sub(r"\s*\(.*\)$", "", fname).strip()
            current_file = fname
            current_desc = []
            continue
        if current_file:
            if line.strip().startswith("===") and "ไฟล์" not in line:
                if current_file and current_desc:
                    bugs[current_file] = "\n".join(current_desc).strip()
                current_file = None
                current_desc = []
                continue
            # ถ้าเจอ ## หัวข้อใหม่ (ไม่ใช่ ไฟล์:) ให้จบไฟล์เดิม
            # แต่ ### ระดับ 3+ (เช่น ### บั๊กที่ 1:) ถือเป็นส่วนหนึ่งของ description
            if re.match(r"^#{1,2}\s", line) and "ไฟล์" not in line:
                if current_file and current_desc:
                    bugs[current_file] = "\n".join(current_desc).strip()
                current_file = None
                current_desc = []
                continue
            current_desc.append(line)
    if current_file and current_desc:
        bugs[current_file] = "\n".join(current_desc).strip()
    # กรองไฟล์ที่ไม่มีบั๊กจริง — เก็บบั๊กระดับกลาง/ต่ำไว้
    return {k: v for k, v in bugs.items()
            if v and "[ไม่มีบั๊ก]" not in v
            and "ไม่พบบั๊ก" not in v
            and "ไม่มีบั๊ก" not in v}
