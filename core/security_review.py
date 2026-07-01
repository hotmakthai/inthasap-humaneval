# -*- coding: utf-8 -*-
"""
core/security_review.py — ซีเคียวริตี้ รีวิว
สแกน codebase ทั้งโปรเจกต์หาช่องโหว่ก่อนขึ้น live
ผสม static analysis (regex) + AI analysis (Gemini)
"""
import os
import re
from core import llm

# ── กฎ static scan (regex) ──
STATIC_RULES = [
    ("hardcoded_password", "รหัสผ่านตัวเขียนแข็ง", "สูง",
     r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']{3,}["\']'),
    ("hardcoded_secret", "API key/secret ตัวเขียนแข็ง", "สูง",
     r'(?i)(api_key|apikey|secret|token)\s*[=:]\s*["\'][^"\']{10,}["\']'),
    ("sql_injection", "SQL injection เป็นไปได้", "สูง",
     r'(?:execute|cursor\.execute)\s*\(\s*(?:["\'].*(?:%s|\+|\.format|f["\']).*(?:SELECT|INSERT|UPDATE|DELETE))'),
    ("eval_exec", "eval/exec อันตราย", "สูง",
     r'\beval\s*\(|\bexec\s*\('),
    ("shell_injection", "os.system/subprocess อันตราย", "สูง",
     r'os\.system\s*\(|subprocess\.(?:call|run|Popen)\s*\(\s*(?:["\'].*(?:%s|\+|\.format|f["\']))'),
    ("path_traversal", "Path traversal เป็นไปได้", "กลาง",
     r'(?:open|send_from_directory|send_file)\s*\(\s*(?:.*\.\./|.*request\.)'),
    ("xss_reflected", "XSS reflected เป็นไปได้", "กลาง",
     r'(?:innerHTML|document\.write)\s*=\s*(?:.*request\.|.*\$\{)'),
    ("debug_mode", "Debug mode เปิดอยู่", "กลาง",
     r'(?i)debug\s*=\s*True'),
    ("cors_wildcard", "CORS * เปิดหมด", "กลาง",
     r'Access-Control-Allow-Origin.*\*'),
    ("pickle_load", "pickle.loads อันตราย", "สูง",
     r'pickle\.loads?\s*\('),
    ("yaml_unsafe", "yaml.load ไม่ใช้ SafeLoader", "กลาง",
     r'yaml\.load\s*\((?!.*SafeLoader)'),
    ("assert_usage", "assert ใช้ใน production (ควรเป็น if-raise)", "ต่ำ",
     r'\bassert\s+'),
]

SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "checkpoints",
             "workspace", "exports", "chats", "logs", "projects", "sandbox"}
CODE_EXTS = {".py", ".js", ".html", ".css", ".json", ".yaml", ".yml"}


def static_scan(project_path):
    """สแกนด้วย regex — คืน list ของ {file, line, rule, severity, description, match}"""
    findings = []
    if not project_path or not os.path.isdir(project_path):
        return findings
    for root, dirs, fnames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in fnames:
            if os.path.splitext(fn)[1] not in CODE_EXTS:
                continue
            fp = os.path.join(root, fn)
            try:
                lines = open(fp, encoding="utf-8", errors="replace").readlines()
            except Exception:
                continue
            rel = os.path.relpath(fp, project_path)
            for i, line in enumerate(lines, 1):
                for rule_id, desc, severity, pattern in STATIC_RULES:
                    if re.search(pattern, line):
                        findings.append({
                            "file": rel,
                            "line": i,
                            "rule": rule_id,
                            "severity": severity,
                            "description": desc,
                            "match": line.strip()[:120]
                        })
    return findings


def _collect_suspicious_code(project_path, findings, max_chars=15000):
    """เก็บโค้ดรอบๆ บรรทัดที่มีปัญหาเพื่อส่งให้ AI วิเคราะห์"""
    chunks = []
    total = 0
    seen_files = set()
    for f in findings[:20]:
        fp = os.path.join(project_path, f["file"])
        if f["file"] in seen_files or not os.path.isfile(fp):
            continue
        seen_files.add(f["file"])
        try:
            lines = open(fp, encoding="utf-8", errors="replace").readlines()
            start = max(0, f["line"] - 3)
            end = min(len(lines), f["line"] + 3)
            snippet = "".join(lines[start:end])
            chunks.append(f"=== {f['file']} (บรรทัด {f['line']}, {f['description']}) ===\n{snippet}")
            total += len(snippet)
            if total >= max_chars:
                break
        except Exception:
            continue
    return "\n\n".join(chunks)


def run_security_review(project_path, on_event=None, should_stop=None):
    """รัน security review — static + AI คืน (summary, static_findings, ai_report)"""
    def emit(sp, txt):
        if on_event:
            on_event(sp, txt)

    def stopped():
        return bool(should_stop and should_stop())

    # ── ชั้น 1: Static scan ──
    emit("🔒 Security Scanner", "กำลังสแกนด้วย static analysis...")
    findings = static_scan(project_path)
    high = sum(1 for f in findings if f["severity"] == "สูง")
    mid = sum(1 for f in findings if f["severity"] == "กลาง")
    low = sum(1 for f in findings if f["severity"] == "ต่ำ")
    emit("🔒 Security Scanner",
         f"พบ {len(findings)} จุด (สูง:{high} กลาง:{mid} ต่ำ:{low})")

    if stopped():
        return "หยุดกลางทาง", findings, ""

    # ── ชั้น 2: AI analysis ──
    ai_report = ""
    if findings and llm._key_for("gemini"):
        emit("🤖 AI Auditor", "กำลังวิเคราะห์ช่องโหว่ด้วย AI...")
        suspicious = _collect_suspicious_code(project_path, findings)
        prompt = (
            "คุณเป็น Security Auditor วิเคราะห์ช่องโหว่จากโค้ดต่อไปนี้\n"
            "จัดอันดับความเสี่ยง อธิบาย impact และแนะนำวิธีแก้\n"
            "ตอบเป็นรายการ: ไฟล์:บรรทัด — ช่องโหว่ — ระดับ — วิธีแก้\n\n"
            f"โค้ดที่น่าสงสัย:\n{suspicious}\n\n"
            f"ผล static scan ({len(findings)} จุด):\n"
            + "\n".join(f"• {f['file']}:{f['line']} [{f['severity']}] {f['description']}: {f['match']}"
                        for f in findings[:30])
        )
        try:
            reply, tier, _ = llm.call_tier("gemini",
                "คุณเป็น Security Auditor ตอบเป็นรายการกระชับ ไม่ต้องมีคำนำ",
                prompt, max_tokens=3000)
            ai_report = reply
            emit("✅ AI Auditor", reply[:500])
        except Exception as e:
            ai_report = f"(AI analysis ไม่สำเร็จ: {e})"
            emit("⚠️ AI Auditor", f"ไม่สำเร็จ: {e}")
    elif not findings:
        ai_report = "ไม่พบช่องโหว่จาก static scan (อาจมีช่องโหว่ที่ static scan ตรวจไม่เจอ)"
        emit("✅ Security Scanner", "ไม่พบช่องโหว่จาก static scan")

    # ── สรุป ──
    summary = (
        f"Security Review สำเร็จ\n"
        f"Static scan: {len(findings)} จุด (สูง:{high} กลาง:{mid} ต่ำ:{low})\n"
        f"AI analysis: {'เสร็จ' if ai_report and 'ไม่สำเร็จ' not in ai_report else 'ไม่สำเร็จ/ไม่มี'}\n"
    )
    if high > 0:
        summary += f"\n⚠️ มี {high} ช่องโหว่ระดับสูง — ควรแก้ก่อนขึ้น live!"
    elif mid > 0:
        summary += f"\n⚠️ มี {mid} ช่องโหว่ระดับกลาง — ควรตรวจสอบ"
    else:
        summary += "\n✅ ไม่มีช่องโหว่ระดับสูง/กลาง"

    return summary, findings, ai_report
