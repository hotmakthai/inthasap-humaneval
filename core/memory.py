# -*- coding: utf-8 -*-
"""
core/memory.py — Rolling Summary Memory (ประหยัด token)
บทสนทนาสั้น → ส่งทั้งหมด · บทสนทนายาว → [สรุปของเก่า(ย่อ)] + [ล่าสุด N รอบ]
ย่อด้วย heuristic (ฟรี) สำหรับ 18-50 entries · ย่อด้วย AI (เสีย 1 call) เฉพาะ 50+ entries
ประวัติเต็มยังเก็บใน logs/ เสมอ (ดึงกลับได้ถ้าต้องการรายละเอียด)
"""
import re
from core import llm

KEEP_RECENT = 6      # เก็บล่าสุดเต็มกี่ entry
COMPRESS_AT = 18     # entry เกินนี้ค่อยเริ่มย่อของเก่า
AI_COMPRESS_AT = 50  # เกินนี้ค่อยใช้ AI สรุป (เสีย API)
MAX_EACH    = 700    # ตัดความยาวต่อ entry กันยาวเกิน


def _fmt(entries):
    return "\n".join(f"[{s}] {(t or '')[:MAX_EACH]}" for s, t in entries)


def _heuristic_summary(entries):
    """สรุปแบบ heuristic (ฟรี ไม่เสีย API) — เอาบรรทัดแรกสำคัญของแต่ละ entry"""
    lines = []
    for speaker, text in entries:
        # ตัดเอาแค่บรรทัดแรกที่ไม่ใช่ empty สั้นๆ
        first = ""
        for line in text.splitlines():
            s = line.strip()
            if s:
                first = s[:200]
                break
        if first:
            lines.append(f"[{speaker}] {first}")
    return "\n".join(lines)


def build_context(transcript):
    """คืน context string สำหรับใส่ prompt — สั้น=ทั้งหมด / ยาว=สรุป+ล่าสุด"""
    n = len(transcript)
    if n <= COMPRESS_AT:
        return _fmt(transcript)

    old = transcript[:-KEEP_RECENT]
    recent = transcript[-KEEP_RECENT:]

    # 18-50 entries: ใช้ heuristic (ฟรี) — ประหยัด 1 API call/รอบ
    if n <= AI_COMPRESS_AT:
        summary = _heuristic_summary(old)
        return f"[สรุปบทสนทนาก่อนหน้า (ย่อแบบเร็ว)]\n{summary}\n\n[ล่าสุด {KEEP_RECENT} รายการ]\n{_fmt(recent)}"

    # 50+ entries: ใช้ AI สรุป (เสีย 1 call แต่ได้สรุปดีกว่า)
    summary, _, _ = llm.call_tier(
        "deepseek",
        "ย่อบทสนทนาการพัฒนาโค้ดให้สั้นที่สุด เก็บเฉพาะ: เป้าหมาย, การตัดสินใจ, "
        "ไฟล์/ฟังก์ชันที่เขียน, บั๊กที่เจอ, สิ่งที่ยังค้าง — เป็น bullet กระชับ",
        _fmt(old), max_tokens=600)
    return f"[สรุปบทสนทนาก่อนหน้า (ย่อ)]\n{summary}\n\n[ล่าสุด {KEEP_RECENT} รายการ]\n{_fmt(recent)}"
