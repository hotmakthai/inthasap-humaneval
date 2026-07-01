# -*- coding: utf-8 -*-
"""
core/code_review.py — โค้ดรีวิว 5 เอเจนต์
5 มุมมอง: Bug Hunter, Style Enforcer, Performance Optimizer, Security Auditor, Git Historian
แต่ละตัวใช้ AI ตรวจ codebase แล้วรวมผลเป็นรายงาน
"""
import os
import glob
import subprocess
from core import llm

REVIEWERS = {
    "bug": {
        "name": "🐛 Bug Hunter",
        "system": "คุณเป็นนักตรวจหาบั๊ก หา logic error, edge case, null/undefined, race condition, "
                  "off-by-one, type mismatch ตอบเป็นรายการ: ไฟล์:บรรทัด — ปัญหา — วิธีแก้",
        "focus": "หาบั๊ก logic error edge case ทุกชนิดในโค้ด"
    },
    "style": {
        "name": "📏 Style Enforcer",
        "system": "คุณเป็นผู้ตรวจสอบ coding style ตามมาตรฐาน PEP 8 / best practice "
                  "ตรวจ: naming, indentation, dead code, duplicate code, missing docstring "
                  "ตอบเป็นรายการ: ไฟล์:บรรทัด — ปัญหา — แนะนำ",
        "focus": "ตรวจ coding style naming convention dead code duplicate"
    },
    "performance": {
        "name": "⚡ Performance Optimizer",
        "system": "คุณเป็นนักเพิ่มประสิทธิภาพ หา: O(n²) loop, unnecessary I/O, "
                  "repeated computation, memory leak, blocking call ที่ควร async "
                  "ตอบเป็นรายการ: ไฟล์:บรรทัด — ปัญหา — วิธีเพิ่มเร็ว",
        "focus": "หา performance bottleneck และวิธีเพิ่มประสิทธิภาพ"
    },
    "security": {
        "name": "🔒 Security Auditor",
        "system": "คุณเป็นนักตรวจสอบความปลอดภัย หา: SQL injection, XSS, "
                  "hardcoded secret, path traversal, unsafe eval/exec, missing input validation "
                  "ตอบเป็นรายการ: ไฟล์:บรรทัด — ช่องโหว่ — ระดับ (สูง/กลาง/ต่ำ) — วิธีแก้",
        "focus": "หาช่องโหว่ด้านความปลอดภัยในโค้ด"
    },
    "git": {
        "name": "📜 Git Historian",
        "system": "คุณเป็นนักวิเคราะห์ git history หา: บั๊กที่เกิดจาก commit ล่าสุด, "
                  "ไฟล์ที่เปลี่ยนบ่อย (hot spot), TODO/FIXME ที่ค้าง, "
                  "commit message ที่บอกปัญหาที่เคยเจอ "
                  "ตอบเป็นรายการสั้นๆ",
        "focus": "วิเคราะห์ git history หาปัญหาที่เคยเกิดและอาจเกิดซ้ำ"
    },
}


def _collect_code(project_path, max_files=20, max_chars=30000):
    """อ่านไฟล์โค้ดจากโปรเจกต์ — เอาเฉพาะ .py, .js, .html, .css"""
    if not project_path or not os.path.isdir(project_path):
        return "", []
    exts = {".py", ".js", ".html", ".css", ".json"}
    skip_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", "checkpoints", "workspace", "backups"}
    files = []
    total = 0
    for root, dirs, fnames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in fnames:
            ext = os.path.splitext(fn)[1]
            if ext not in exts:
                continue
            fp = os.path.join(root, fn)
            try:
                content = open(fp, encoding="utf-8", errors="replace").read()
                if len(content) > 5000:
                    content = content[:5000] + "\n... (truncated)"
                files.append((os.path.relpath(fp, project_path), content))
                total += len(content)
                if len(files) >= max_files or total >= max_chars:
                    break
            except Exception:
                continue
        if len(files) >= max_files or total >= max_chars:
            break
    code = "\n\n".join(f"=== {rel} ===\n{content}" for rel, content in files)
    return code, [rel for rel, _ in files]


def _git_history(project_path, max_commits=10):
    """อ่าน git log ล่าสุด"""
    if not project_path or not os.path.isdir(os.path.join(project_path, ".git")):
        return "(ไม่มี git repository)"
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{max_commits}"],
            cwd=project_path, capture_output=True, text=True, timeout=10
        )
        return result.stdout if result.returncode == 0 else "(อ่าน git log ไม่ได้)"
    except Exception:
        return "(อ่าน git log ไม่ได้)"


def _git_todos(project_path):
    """หา TODO/FIXME/HACK ในโค้ด"""
    if not project_path or not os.path.isdir(project_path):
        return ""
    todos = []
    exts = {".py", ".js", ".html", ".css"}
    skip_dirs = {"node_modules", ".git", "__pycache__", "venv"}
    for root, dirs, fnames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in fnames:
            if os.path.splitext(fn)[1] not in exts:
                continue
            fp = os.path.join(root, fn)
            try:
                for i, line in enumerate(open(fp, encoding="utf-8", errors="replace"), 1):
                    for marker in ("TODO", "FIXME", "HACK", "XXX"):
                        if marker in line:
                            rel = os.path.relpath(fp, project_path)
                            todos.append(f"{rel}:{i} — {line.strip()[:100]}")
            except Exception:
                continue
    return "\n".join(todos[:30]) if todos else "(ไม่มี TODO/FIXME)"


def run_review(project_path, on_event=None, should_stop=None):
    """รันรีวิว 5 เอเจนต์ — คืน (summary, findings)"""
    code, file_list = _collect_code(project_path)
    if not code:
        return "ไม่พบไฟล์โค้ดในโปรเจกต์", {}

    git_log = _git_history(project_path)
    todos = _git_todos(project_path)

    def emit(sp, txt):
        if on_event:
            on_event(sp, txt)

    def stopped():
        return bool(should_stop and should_stop())

    findings = {}
    for key, rev in REVIEWERS.items():
        if stopped():
            break
        emit("🔍 " + rev["name"], "กำลังตรวจ...")

        if key == "git":
            user_prompt = f"Git log ล่าสุด:\n{git_log}\n\nTODO/FIXME ที่พบ:\n{todos}\n\n{rev['focus']}"
        else:
            user_prompt = f"โค้ดทั้งหมด ({len(file_list)} ไฟล์):\n{code[:20000]}\n\n{rev['focus']}"

        try:
            reply, tier, _ = llm.call_tier("gemini", rev["system"], user_prompt, max_tokens=3000)
            findings[key] = {"name": rev["name"], "report": reply, "tier": tier}
            emit("✅ " + rev["name"], reply[:500])
        except Exception as e:
            findings[key] = {"name": rev["name"], "report": f"(ตรวจไม่สำเร็จ: {e})", "tier": "error"}
            emit("⚠️ " + rev["name"], f"ตรวจไม่สำเร็จ: {e}")

    # สรุปรวม
    total_issues = sum(1 for f in findings.values() if f["report"] and f["tier"] != "error")
    summary = f"รีวิว {len(findings)} เอเจนต์ · {total_issues} รายงาน\n\n"
    for key, f in findings.items():
        lines = f["report"].count("\n") + 1 if f["report"] else 0
        summary += f"{f['name']} ({f['tier']}): {lines} บรรทัด\n"

    return summary, findings
