# -*- coding: utf-8 -*-
"""
core/error_memory.py — ความจำข้อผิดพลาดข้ามเซสชั่น
สะสมบทเรียนจากข้อผิดพลาดที่ AI ทำ → ฉีดเข้า prompt รอบถัดไป
ทำให้ AI ไม่ทำผิดซ้ำ → ประหยัด API call ไม่ต้องวนหาคำตอบใหม่

โครงสร้างไฟล์: logs/error_lessons.json
[
  {
    "pattern": "ImportError: No module named 'xxx'",
    "file": "core/orchestrator.py",
    "fix": "เพิ่ม sys.path.insert ก่อน import",
    "count": 3,
    "last_seen": "01/07/2026 20:00",
    "category": "import"
  }
]
"""
import os
import json
import re
import threading
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LESSONS_FILE = os.path.join(_BASE, "logs", "error_lessons.json")

MAX_LESSONS = 100          # เก็บสูงสุด 100 บทเรียน
MAX_PATTERN_LEN = 200      # ตัด pattern ไม่ให้ยาวเกิน
MAX_FIX_LEN = 500          # ตัดคำอธิบาย fix
MAX_CONTEXT_CHARS = 1500   # ตัด context ที่ฉีดเข้า prompt

_lock = threading.Lock()


def _load():
    """อ่านบทเรียนทั้งหมด"""
    with _lock:
        try:
            with open(_LESSONS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []


def _save(lessons):
    """บันทึกบทเรียน"""
    with _lock:
        try:
            os.makedirs(os.path.dirname(_LESSONS_FILE), exist_ok=True)
            with open(_LESSONS_FILE, "w", encoding="utf-8") as f:
                json.dump(lessons, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def _categorize(error_text):
    """จัดหมวดข้อผิดพลาด"""
    e = error_text.lower()
    if "importerror" in e or "modulenotfound" in e:
        return "import"
    if "syntaxerror" in e:
        return "syntax"
    if "typeerror" in e:
        return "type"
    if "valueerror" in e:
        return "value"
    if "attributeerror" in e:
        return "attribute"
    if "keyerror" in e:
        return "key"
    if "indexerror" in e:
        return "index"
    if "filenotfound" in e or "no such file" in e:
        return "file"
    if "permission" in e:
        return "permission"
    if "timeout" in e or "timed out" in e:
        return "timeout"
    if "connection" in e or "network" in e:
        return "network"
    if "assertion" in e:
        return "assertion"
    if "429" in e or "quota" in e:
        return "api_quota"
    if "dangerous" in e or "blocked" in e:
        return "security"
    return "other"


def _normalize_pattern(text):
    """ทำให้ pattern สั้นและเปรียบเทียบได้ — ตัด path/เลขบรรทัดเฉพาะ"""
    # ลบ path เฉพาะในวงเล็บ
    t = re.sub(r"File \"[^\"]+\"", "File \"...\"", text)
    # ลบเลขบรรทัด
    t = re.sub(r"line \d+", "line N", t)
    # ลบ timestamp
    t = re.sub(r"\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}", "TIMESTAMP", t)
    # ย่อวงเล็บซ้อน
    t = re.sub(r"\s+", " ", t).strip()
    return t[:MAX_PATTERN_LEN]


def record_error(error_text, file_path="", fix=""):
    """บันทึกข้อผิดพลาดใหม่ — ถ้าเคยเจอแล้วเพิ่ม count"""
    if not error_text or not error_text.strip():
        return

    pattern = _normalize_pattern(error_text)
    category = _categorize(error_text)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    lessons = _load()

    # หาบทเรียนที่ pattern คล้ายกัน
    for lesson in lessons:
        if lesson.get("pattern", "")[:80] == pattern[:80]:
            lesson["count"] = lesson.get("count", 1) + 1
            lesson["last_seen"] = now
            if fix and fix.strip():
                lesson["fix"] = fix.strip()[:MAX_FIX_LEN]
            if file_path:
                lesson["file"] = file_path
            _save(lessons)
            return lesson

    # บทเรียนใหม่
    lesson = {
        "pattern": pattern,
        "file": file_path or "",
        "fix": (fix or "").strip()[:MAX_FIX_LEN],
        "count": 1,
        "last_seen": now,
        "category": category,
    }
    lessons.append(lesson)

    # เก็บเฉพาะ MAX_LESSONS ล่าสุด — เรียงตาม count และ last_seen
    lessons.sort(key=lambda x: (x.get("count", 0), x.get("last_seen", "")), reverse=True)
    lessons = lessons[:MAX_LESSONS]
    _save(lessons)
    return lesson


def record_stuck(task, error_summary, fix_applied):
    """บันทึกการติดที่เดิม (stuck loop) — สำคัญที่สุดเพราะเผา token"""
    pattern = f"STUCK: {task[:100]} → {error_summary[:100]}"
    return record_error(pattern, "", fix_applied)


def record_test_failure(test_file, test_cases, fix=""):
    """บันทึกเทสที่ล้ม"""
    pattern = f"TEST_FAIL: {test_file} → {test_cases[:150]}"
    return record_error(pattern, test_file, fix)


def find_similar(error_text):
    """หาบทเรียนที่คล้ายกับ error ที่กำลังเจอ — คืน list ของ lessons ที่เกี่ยวข้อง"""
    if not error_text:
        return []

    pattern = _normalize_pattern(error_text)
    category = _categorize(error_text)
    lessons = _load()

    matches = []
    for lesson in lessons:
        # match ถ้า pattern ต้นนำ 60 ตัวตรง หรือหมวดเดียวกัน + คล้ายกัน
        lp = lesson.get("pattern", "")
        if lp[:60] == pattern[:60]:
            matches.append(lesson)
        elif lesson.get("category") == category and lp[:30] == pattern[:30]:
            matches.append(lesson)

    return matches[:5]  # เอาแค่ 5 อันที่เกี่ยวข้องสุด


def build_lessons_context(error_text=None, max_chars=MAX_CONTEXT_CHARS):
    """สร้าง context สำหรับฉีดเข้า prompt

    ถ้า error_text มี → หาบทเรียนที่คล้ายกัน (เจอเอ๋อ → ดึงประสบการณ์เก่า)
    ถ้าไม่มี → ส่งบทเรียนที่เจอบ่อยสุด (เตือนล่วงหน้า)
    """
    lessons = _load()
    if not lessons:
        return ""

    if error_text:
        relevant = find_similar(error_text)
        if not relevant:
            return ""
        lines = []
        for r in relevant:
            fix = r.get("fix", "")
            if fix:
                lines.append(f"  - เคยเจอ: {r['pattern'][:100]}\n    แก้โดย: {fix[:200]}\n    (เจอ {r.get('count', 1)} ครั้ง)")
        if lines:
            return f"[บทเรียนจากข้อผิดพลาดที่เคยเจอ — ใช้แก้ปัญหานี้]\n" + "\n".join(lines)
    else:
        # ส่งบทเรียนที่เจอบ่อยสุด 5 อัน — เตือนล่วงหน้า
        top = sorted(lessons, key=lambda x: x.get("count", 0), reverse=True)[:5]
        lines = []
        for r in top:
            fix = r.get("fix", "")
            if fix:
                lines.append(f"  - [{r.get('category', '?')}] {r['pattern'][:80]} → {fix[:150]} (เจอ {r.get('count', 1)} ครั้ง)")
        if lines:
            return f"[บทเรียนจากข้อผิดพลาดที่เคยเจอ — ระวังอย่าทำซ้ำ]\n" + "\n".join(lines)

    return ""


def lessons_block(error_text=None):
    """สร้าง block สำหรับใส่ใน prompt — พร้อม header"""
    ctx = build_lessons_context(error_text)
    if not ctx:
        return ""
    return f"\n{ctx}\n"


def get_stats():
    """สถิติบทเรียน — สำหรับแสดงใน /api/system"""
    lessons = _load()
    if not lessons:
        return {"total": 0, "categories": {}, "top": []}
    cats = {}
    for l in lessons:
        c = l.get("category", "other")
        cats[c] = cats.get(c, 0) + 1
    top = sorted(lessons, key=lambda x: x.get("count", 0), reverse=True)[:3]
    return {
        "total": len(lessons),
        "categories": cats,
        "top": [{"pattern": l.get("pattern", "")[:80], "count": l.get("count", 1)} for l in top],
    }
