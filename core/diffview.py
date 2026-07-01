# -*- coding: utf-8 -*-
"""
core/diffview.py — แก้เป็น Diff (CORE #2)
เทียบไฟล์เดิม vs ใหม่ ด้วย difflib → แสดงเขียว(+)/แดง(-) + ใช้ส่งให้ reviewer
(ส่ง diff ให้ตรวจ ประหยัด token กว่าส่งทั้งไฟล์)
"""
import difflib


def compute(old_text: str, new_text: str, filename: str = "") -> str:
    """unified diff (string). ถ้าไม่เปลี่ยน คืน ''"""
    old_lines = (old_text or "").splitlines(keepends=True)
    new_lines = (new_text or "").splitlines(keepends=True)
    if old_lines == new_lines:
        return ""
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}", tofile=f"b/{filename}", lineterm="")
    return "\n".join(diff)


def pretty(diff_text: str) -> str:
    """ตกแต่งให้อ่านง่าย (สัญลักษณ์ +/-)"""
    if not diff_text:
        return "(ไม่มีการเปลี่ยนแปลง)"
    out = []
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            out.append("  + " + line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            out.append("  - " + line[1:])
        elif line.startswith("@@"):
            out.append(line)
    return "\n".join(out) if out else "(เปลี่ยนเฉพาะ metadata)"


def summarize_changes(diffs: dict) -> str:
    """diffs = {filename: diff_text} → ข้อความสรุปการเปลี่ยนทั้งหมด (สำหรับ reviewer)"""
    parts = []
    for fn, d in diffs.items():
        if d:
            parts.append(f"=== {fn} ===\n{pretty(d)}")
    return "\n\n".join(parts) if parts else "(ไม่มีไฟล์เปลี่ยน)"
