# -*- coding: utf-8 -*-
"""
core/router.py — ตัวจำแนกงาน 2 ราง + ระดับความมั่นใจ (เฟส 1 ของ Router)
  A     = งานตรวจได้ด้วยโค้ด/เทส (เขียน/แก้โปรแกรม, wiring, คำนวณ)  → ราง orchestrator เดิม
  B     = งานความคิด (วางแผน/ตัดสินใจ/ปรึกษา/กลยุทธ์)                → ราง discussion (เฟส 2)
  MIXED = ปนกัน (ออกแบบ→เขียนโค้ด, วิเคราะห์ข้อมูล→ตีความ)          → ต้องให้คนดูก่อน

จาก confidence → action (เกณฑ์สภาบ้านอินทรัพย์ 2026-06-26):
  < 0.7      → ask_human (ถามคนก่อน)
  0.7–0.9    → warn      (ทำได้แต่แจ้งเตือน)
  >= 0.9     → auto      (อัตโนมัติเต็มรูปแบบ)  · ยกเว้น MIXED ไม่ auto (ปนกันต้องคนดู)
ใช้ DeepSeek (ถูก) · parse ไม่ได้/error → default A + ask_human (ปลอดภัย ให้คนตัดสิน)
"""
import re
from core import llm

# เกณฑ์ escalation (สภาบ้านเสนอ — พ่ออนุมัติ 2026-06-26) แก้ที่เดียวได้
ASK_BELOW = 0.7      # ต่ำกว่านี้ → ถามคน
AUTO_FROM = 0.9      # ตั้งแต่นี้ → auto

_SYS = ("คุณเป็นตัวจำแนกประเภทงานของสภา Council Lab อ่านโจทย์แล้วบอกชนิดงาน + ความมั่นใจ "
        "ตอบตามรูปแบบที่กำหนดเป๊ะ ไม่อธิบายยาว")


def _prompt(task):
    return (
        "จำแนกโจทย์ต่อไปนี้เป็น A / B / MIXED:\n\n"
        "A = งานที่ 'ตรวจถูก/ผิดได้ด้วยโค้ดหรือเทส' (เขียนโปรแกรม แก้บั๊ก สร้างไฟล์ wiring คำนวณ)\n"
        "B = 'งานความคิด' ที่ไม่มีคำตอบเดียว (วางแผน ตัดสินใจ ปรึกษา วิเคราะห์ข้อดีข้อเสีย กลยุทธ์)\n"
        "MIXED = ปนกันชัดเจน เช่น 'ออกแบบอัลกอริทึมใหม่แล้วเขียนโค้ด', "
        "'วิเคราะห์ข้อมูลแล้วตีความเชิงตัดสินใจ', 'เลือกไลบรารีแล้วเขียนตามนั้น'\n\n"
        f"[โจทย์]\n{task[:2000]}\n\n"
        "ตอบ 3 บรรทัดนี้เป๊ะ:\n"
        "ROUTE: <A หรือ B หรือ MIXED>\n"
        "CONFIDENCE: <ตัวเลข 0.0-1.0 ว่ามั่นใจแค่ไหน>\n"
        "REASON: <เหตุผลสั้น 1 ประโยค>"
    )


def _parse(reply):
    route, conf, reason = "A", 0.5, ""
    m = re.search(r"ROUTE\s*[:：]\s*(MIXED|A|B)", reply, re.I)
    if m:
        route = m.group(1).upper()
    m = re.search(r"CONFIDENCE\s*[:：]\s*([0-9]*\.?[0-9]+)", reply, re.I)
    if m:
        try:
            conf = max(0.0, min(1.0, float(m.group(1))))
        except ValueError:
            pass
    m = re.search(r"REASON\s*[:：]\s*(.+)", reply, re.I | re.S)
    reason = (m.group(1) if m else reply).strip().replace("\n", " ")[:200] or "(ไม่มีเหตุผล)"
    return route, conf, reason


def _action(route, conf):
    if route == "MIXED":
        return "warn" if conf >= AUTO_FROM else "ask_human"   # ปนกัน → ไม่ auto
    if conf < ASK_BELOW:
        return "ask_human"
    if conf < AUTO_FROM:
        return "warn"
    return "auto"


def classify(task):
    """จำแนกโจทย์ → dict: route(A/B/MIXED), confidence(0-1), action, reason, model"""
    if not task or not task.strip():
        return {"route": "A", "confidence": 0.0, "action": "ask_human",
                "reason": "(โจทย์ว่าง)", "model": "none"}
    reply, model, _ = llm.call_tier("deepseek", _SYS, _prompt(task), max_tokens=200)
    if not reply or reply.startswith("("):                    # error จาก llm
        return {"route": "A", "confidence": 0.0, "action": "ask_human",
                "reason": f"(จำแนกไม่สำเร็จ: {reply[:80]})", "model": model}
    route, conf, reason = _parse(reply)
    return {"route": route, "confidence": conf, "action": _action(route, conf),
            "reason": reason, "model": model}
