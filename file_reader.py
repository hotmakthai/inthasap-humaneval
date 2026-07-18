"""
file_reader.py — สภาขอเปิดไฟล์เองได้ระหว่างทำงาน

API: read_requests(reply_text, project_path) -> str | None
- จับ pattern READ: <relative_path> ในคำตอบ coder/reviewer (สูงสุด 3 ไฟล์/รอบ)
- อ่านได้เฉพาะใต้ project_path เท่านั้น (กัน .. / absolute path / ไฟล์ลับ / ไฟล์ใหญ่)
- คืน block [FILE: path]\\n<เนื้อหา> รวมกัน หรือ None ถ้าไม่มีคำขอ
"""

import os
import re
from core.project_context import _is_secret

MAX_FILES_PER_ROUND = 3
MAX_FILE_BYTES = 200 * 1024  # 200 KB

_READ_PATTERN = re.compile(r"^\s*READ:\s*(\S+)", re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    """ลบเนื้อหาภายใน code fence (``` ... ```) ออกเพื่อไม่ให้จับ READ: ในโค้ด/comment"""
    # ลบ block code fence ทั้งบรรทัดที่เปิด/ปิด และเนื้อหาระหว่างนั้น
    return re.sub(r"```[\s\S]*?```", "", text)


def read_requests(reply_text: str, project_path: str) -> str | None:
    """
    ตรวจหา READ: <path> ในคำตอบสภา แล้วอ่านไฟล์ที่ขอ

    Args:
        reply_text: คำตอบของ coder/reviewer ที่อาจมี READ: <path>
        project_path: absolute path ของโปรเจกต์ที่ทำงานอยู่

    Returns:
        str: block [FILE: path]\\n<เนื้อหา> ของทุกไฟล์ที่อ่านได้ รวมกัน
        None: ถ้าไม่มี READ: เลย หรืออ่านไม่ได้ทุกไฟล์
    """
    if not reply_text or not project_path:
        return None

    text_outside_fences = _strip_code_fences(reply_text)
    matches = _READ_PATTERN.findall(text_outside_fences)
    if not matches:
        return None

    # จำกัดสูงสุด 3 ไฟล์/รอบ แล้วรายงานที่ถูกตัดทิ้ง
    skipped = matches[MAX_FILES_PER_ROUND:] if len(matches) > MAX_FILES_PER_ROUND else []
    matches = matches[:MAX_FILES_PER_ROUND]

    real_project = os.path.realpath(project_path)
    blocks = []

    for rel_path in matches:
        rel_path = rel_path.strip()

        # ป้องกัน absolute path
        if os.path.isabs(rel_path):
            blocks.append(f"[FILE: {rel_path}]\n⛔ ปฏิเสธ: ห้ามใช้ absolute path")
            continue

        # resolve แล้วตรวจว่าอยู่ใต้ project เท่านั้น
        abs_path = os.path.realpath(os.path.join(real_project, rel_path))
        if not abs_path.startswith(real_project + os.sep) and abs_path != real_project:
            blocks.append(f"[FILE: {rel_path}]\n⛔ ปฏิเสธ: path อยู่นอกโปรเจกต์")
            continue

        # ป้องกันไฟล์ลับ
        filename = os.path.basename(abs_path)
        if _is_secret(filename):
            blocks.append(f"[FILE: {rel_path}]\n⛔ ปฏิเสธ: ไฟล์ลับ ห้ามอ่าน")
            continue

        # ตรวจว่าไฟล์มีอยู่จริง
        if not os.path.isfile(abs_path):
            blocks.append(f"[FILE: {rel_path}]\n⛔ ไม่พบไฟล์")
            continue

        # ตรวจขนาด
        size = os.path.getsize(abs_path)
        if size > MAX_FILE_BYTES:
            blocks.append(f"[FILE: {rel_path}]\n⛔ ข้ามไฟล์ใหญ่เกิน 200KB ({size // 1024}KB)")
            continue

        # อ่านไฟล์
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            blocks.append(f"[FILE: {rel_path}]\n{content}")
        except Exception as e:
            blocks.append(f"[FILE: {rel_path}]\n⛔ อ่านไม่ได้: {e}")

    if skipped:
        blocks.append(f"[INFO: ไฟล์ที่ถูกข้ามเนื่องจากเกิน limit {MAX_FILES_PER_ROUND} ไฟล์/รอบ]\n{', '.join(skipped)}")

    if not blocks:
        return None

    return "\n\n".join(blocks)


def extract_read_paths(reply_text: str) -> list[str]:
    """คืนรายชื่อ path ที่ขอ READ: (ใช้สำหรับ emit ให้ผู้ใช้เห็น)"""
    if not reply_text:
        return []
    return _READ_PATTERN.findall(reply_text)[:MAX_FILES_PER_ROUND]
