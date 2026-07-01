# -*- coding: utf-8 -*-
"""
core/sandbox.py — กล่องทรายของสภา (เขียน/รันโค้ดได้เฉพาะใน workspace/ เท่านั้น)
ความปลอดภัย 3 ชั้น:
  1. Path jail — แปลง realpath แล้วบังคับต้องอยู่ใต้ workspace/ ห้าม .. ห้าม absolute นอกเขต
  2. Run jail — รันด้วย cwd=workspace, timeout, จับ output
  3. Env scrub — subprocess ไม่เห็นกุญแจ API (กันโค้ดที่สภาเขียนแอบดูด key)
"""
import os
import re
import sys
import subprocess

from core import scanner_rules

# เปิดเป็น True เพื่ออนุญาตรันโค้ดที่มี pattern อันตราย (ใช้เมื่อจำเป็นจริงเท่านั้น)
ALLOW_DANGEROUS = False

BASE      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Council_Lab/
WORKSPACE = os.path.join(BASE, "workspace")
RUN_TIMEOUT = 30          # วินาที
MAX_OUTPUT  = 4000        # ตัด output ไม่ให้ยาวเกิน

os.makedirs(WORKSPACE, exist_ok=True)
_WS_REAL = os.path.realpath(WORKSPACE)

# จับ code block ที่มี file=ชื่อไฟล์
_FILE_BLOCK = re.compile(
    r"```[^\n]*?file=([^\s`]+)\s*\n(.*?)```", re.DOTALL)
# จับบรรทัด RUN: ชื่อไฟล์
_RUN_LINE = re.compile(r"^\s*RUN:\s*([^\s`]+)\s*$", re.MULTILINE)

# กุญแจที่ต้องลบออกจาก env ของ subprocess
_SECRET_KEYS = ("DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
                "BRIDGE_AUTH_TOKEN", "TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY")


def _safe_path(relpath: str):
    """คืน absolute path ที่ปลอดภัย หรือ None ถ้าหลุดเขต"""
    relpath = relpath.strip().strip('"').strip("'").replace("\\", "/")
    if relpath.startswith("/") or re.match(r"^[A-Za-z]:", relpath):
        return None                       # absolute → ปฏิเสธ
    cand = os.path.realpath(os.path.join(WORKSPACE, relpath))
    if cand == _WS_REAL or cand.startswith(_WS_REAL + os.sep):
        return cand
    return None                           # หลุดออกนอก workspace → ปฏิเสธ


def extract_files(text: str):
    """ดึง (relpath, content) จากทุก code block ที่มี file="""
    out = []
    for m in _FILE_BLOCK.finditer(text or ""):
        out.append((m.group(1).strip(), m.group(2)))
    return out


def write_files(files):
    """เขียนไฟล์ลง workspace แบบปลอดภัย — คืน list ของผล"""
    results = []
    for relpath, content in files:
        ap = _safe_path(relpath)
        if ap is None:
            results.append(("REJECT", relpath, "หลุดนอก workspace/ — ไม่เขียน"))
            continue
        try:
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            with open(ap, "w", encoding="utf-8") as f:
                f.write(content)
            results.append(("WROTE", relpath, f"{len(content)} ตัวอักษร"))
        except Exception as e:
            results.append(("ERROR", relpath, str(e)[:100]))
    return results


def find_runs(text: str):
    return [m.group(1).strip() for m in _RUN_LINE.finditer(text or "")]


def run_python(relpath: str):
    """รันไฟล์ Python ใน sandbox — คืน (exit_code, output)"""
    ap = _safe_path(relpath)
    if ap is None:
        return (-1, f"ปฏิเสธ: {relpath} อยู่นอก workspace/")
    if not os.path.exists(ap):
        return (-1, f"ไม่พบไฟล์: {relpath}")

    # ── สแกนอันตรายก่อนรัน ──
    try:
        code_text = open(ap, encoding="utf-8", errors="replace").read()
    except Exception:
        code_text = ""
    allowed, findings = scanner_rules.verdict(code_text)
    if findings:
        rep = "\n".join(f"   [{f['severity']}] {f['category']} (บรรทัด {f['line']}): "
                        f"{f['desc']} → {f['code']}" for f in findings)
        if not allowed and not ALLOW_DANGEROUS:
            return (-2, f"🚫 บล็อก: พบโค้ดอันตราย (HIGH) ไม่รัน\n{rep}")
        # มีแต่ MED หรือเปิด ALLOW → รันแต่แนบคำเตือน
        _warn = f"⚠️ คำเตือนความปลอดภัย:\n{rep}\n---\n"
    else:
        _warn = ""

    # env ที่ลบกุญแจออก
    env = {k: v for k, v in os.environ.items() if k not in _SECRET_KEYS}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = WORKSPACE
    try:
        p = subprocess.run(
            [sys.executable, ap],
            cwd=WORKSPACE, env=env,
            capture_output=True, text=True, timeout=RUN_TIMEOUT,
            encoding="utf-8", errors="replace",
        )
        out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
        if len(out) > MAX_OUTPUT:
            out = out[:MAX_OUTPUT] + "\n...(ตัด)"
        return (p.returncode, _warn + (out.strip() or "(ไม่มี output)"))
    except subprocess.TimeoutExpired:
        return (-1, f"หมดเวลา {RUN_TIMEOUT}s — อาจมี loop ไม่จบ")
    except Exception as e:
        return (-1, f"รันล้มเหลว: {str(e)[:150]}")
