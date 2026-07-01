# -*- coding: utf-8 -*-
"""
core/project_context.py — อ่านโปรเจกต์ที่มีอยู่ (CORE #1)
ให้สภาเห็นโค้ดโปรเจกต์จริงเพื่อแก้/ต่อยอด (read-only) ไม่ใช่เขียนจากศูนย์
ความปลอดภัย: อ่านอย่างเดียว + จำกัดขนาด + ข้ามไฟล์ลับ/ไบนารี/โฟลเดอร์ขยะ
"""
import os
import re

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".idea", ".vscode",
             "venv", ".venv", "dist", "build", ".secrets", "checkpoints",
             "backups"}
TEXT_EXT  = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h",
             ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css", ".json",
             ".yaml", ".yml", ".md", ".txt", ".sql", ".sh", ".toml", ".cfg"}
SECRET_HINT = ("token", "secret", "credential", "password", "api_key", "apikey")
MAX_FILES        = 60        # อ่านเนื้อหาสูงสุดกี่ไฟล์
MAX_BYTES_FILE   = 12_000    # ต่อไฟล์
MAX_TOTAL_BYTES  = 120_000   # รวม (กัน context ใหญ่เกิน/แพง token)


def _is_secret(name):
    low = name.lower()
    return low == ".env" or low.endswith(".env") or any(k in low for k in SECRET_HINT)


# ── สแกน "เนื้อในไฟล์" หาค่าลับ (ปิดช่องโหว่: ไฟล์ชื่อปกติแต่มีความลับซ่อนใน) ──
# จับเฉพาะ 'ค่าลับจริง' ไม่ใช่แค่เจอคำว่า password → กัน false positive (โค้ดปกติไม่โดนตัด)
_KV_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|secret|token|password|passwd|credential|auth[_-]?token|access[_-]?key)\b\s*[=:]\s*)"
    r"(['\"][^'\"]{6,}['\"]|[A-Za-z0-9_\-./+]{12,})")
_KEY_FORMATS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),           # Google API key
    re.compile(r"sk-[A-Za-z0-9]{20,}"),               # OpenAI/DeepSeek
    re.compile(r"gh[posru]_[A-Za-z0-9]{20,}"),        # GitHub token
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"), # Bearer token
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}"),  # JWT
]


def _redact_secrets(text):
    """ปิดค่าที่ดูเป็นความลับในเนื้อไฟล์ก่อนส่ง API — คืน (text_ปิดแล้ว, จำนวนจุดที่ปิด)
    ปิดเฉพาะ 'ค่า' คงโครงโค้ดไว้ให้สภาอ่านได้"""
    total = 0
    text, c = _KV_SECRET.subn(r"\1[REDACTED]", text)
    total += c
    for pat in _KEY_FORMATS:
        text, c = pat.subn("[REDACTED]", text)
        total += c
    return text, total


def load(project_path: str) -> str:
    """คืนข้อความ context: โครงสร้าง + เนื้อไฟล์สำคัญ (read-only)"""
    if not project_path or not os.path.isdir(project_path):
        return ""
    root = os.path.abspath(project_path)
    tree, bodies = [], []
    total = 0
    nfiles = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted([d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")])
        level = dirpath.replace(root, "").count(os.sep)
        if level > 4:
            dirs.clear(); continue
        tree.append("  " * level + "📁 " + (os.path.basename(dirpath) or os.path.basename(root)) + "/")
        for f in sorted(files):
            tree.append("  " * (level + 1) + "📄 " + f)
            ext = os.path.splitext(f)[1].lower()
            fp = os.path.join(dirpath, f)
            if _is_secret(f) or ext not in TEXT_EXT:
                continue
            if nfiles >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                continue
            try:
                data = open(fp, encoding="utf-8", errors="replace").read(MAX_BYTES_FILE)
            except Exception:
                continue
            data, nred = _redact_secrets(data)            # ปิดค่าลับในเนื้อไฟล์ก่อนส่ง API
            rel = os.path.relpath(fp, root).replace("\\", "/")
            if nred >= 5:   # ค่าลับหนาแน่น = น่าจะไฟล์ credential → ไม่ส่งเนื้อหาเลย
                bodies.append(f"=== {rel} ===\n(ข้ามเนื้อหา: พบค่าที่ดูเป็นความลับ {nred} จุด — กันหลุดเข้า API)")
                total += 70; nfiles += 1
                continue
            bodies.append(f"=== {rel} ===\n{data}")
            total += len(data); nfiles += 1

    header = (f"[โปรเจกต์ที่อ่าน: {root}]\n"
              f"โครงสร้าง:\n" + "\n".join(tree[:200]) +
              f"\n\nเนื้อไฟล์ ({nfiles} ไฟล์, ~{total:,} ตัวอักษร):\n")
    return header + "\n\n".join(bodies)


def stats(project_path: str) -> dict:
    if not project_path or not os.path.isdir(project_path):
        return {"ok": False}
    nfiles = nbytes = 0
    for dp, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            nfiles += 1
            try:
                nbytes += os.path.getsize(os.path.join(dp, f))
            except Exception:
                pass
    return {"ok": True, "files": nfiles, "bytes": nbytes}
