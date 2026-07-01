# -*- coding: utf-8 -*-
"""
core/scanner_rules.py — ตัวสแกนโค้ดอันตรายก่อนรัน (Static Danger Scanner)
ก่อน sandbox รันไฟล์ใดๆ → สแกนหา pattern อันตราย
  HIGH  = บล็อกไม่ให้รัน (เว้นแต่เปิด ALLOW_DANGEROUS)
  MED   = เตือน แต่ยังรันได้
ปรับ blacklist เพิ่ม/ลบได้ที่ DANGER_PATTERNS
"""
import re

# (regex, หมวด, ระดับ, คำอธิบาย)
DANGER_PATTERNS = [
    # ── รันคำสั่งระบบ / shell ──
    (r"\bos\.system\s*\(",            "shell",     "HIGH", "สั่ง shell ได้ทุกอย่าง"),
    (r"\bos\.popen\s*\(",             "shell",     "HIGH", "เปิด shell pipe"),
    (r"\bsubprocess\b",               "shell",     "HIGH", "spawn process ภายนอก"),
    (r"\bpty\b|\bos\.exec[lv]",       "shell",     "HIGH", "exec แทนที่ process"),
    # ── ลบ/ทำลายไฟล์ ──
    (r"\bshutil\.rmtree\s*\(",        "delete",    "HIGH", "ลบทั้งโฟลเดอร์"),
    (r"\bos\.(remove|unlink|rmdir)\s*\(", "delete","HIGH", "ลบไฟล์/โฟลเดอร์"),
    (r"\bpathlib[^\n]*\.unlink\s*\(", "delete",    "HIGH", "ลบไฟล์ผ่าน pathlib"),
    # ── รันโค้ดสด / เลี่ยง scanner (obfuscation) ──
    (r"\beval\s*\(",                  "dyn_exec",  "HIGH", "รันนิพจน์สด"),
    (r"\bexec\s*\(",                  "dyn_exec",  "HIGH", "รันโค้ดสด"),
    (r"\b__import__\s*\(",            "dyn_exec",  "HIGH", "import แบบไดนามิก (เลี่ยง scanner)"),
    (r"\bgetattr\s*\(",               "obfuscate", "HIGH", "getattr — ใช้เลี่ยง scanner ได้"),
    (r"\bsetattr\s*\(",               "obfuscate", "HIGH", "setattr — แก้ attribute"),
    (r"\bglobals\s*\(\)|\bvars\s*\(\)", "obfuscate","MED",  "เข้าถึง namespace"),
    (r"\bcompile\s*\(",               "dyn_exec",  "MED",  "compile โค้ด"),
    # ── เปิดไฟล์นอก workspace (escape ตอนรัน) ──
    (r"\bopen\s*\(\s*[rbuRBU]*['\"](\.\.|[/\\]|[A-Za-z]:)", "escape", "HIGH", "เปิดไฟล์นอก workspace (.. หรือ absolute)"),
    (r"\bpathlib\b|\bPath\s*\(",      "escape",    "MED",  "ใช้ pathlib — ระวัง path escape"),
    # ── เครือข่าย / ส่งข้อมูลออก ──
    (r"\bimport\s+socket\b|\bsocket\.socket\s*\(", "network", "HIGH", "เปิด socket เน็ต"),
    (r"\bimport\s+requests\b|\brequests\.(get|post|put|delete)\s*\(", "network", "HIGH", "ยิง HTTP ออกนอก"),
    (r"\bimport\s+urllib\b|\burllib\.request", "network", "HIGH", "ดาวน์โหลด/ส่งข้อมูล"),
    (r"\b(ftplib|smtplib|telnetlib|http\.client)\b", "network", "HIGH", "โปรโตคอลส่งข้อมูล"),
    # ── ระดับล่าง / ระบบ / persistence ──
    (r"\bimport\s+ctypes\b|\bctypes\.",  "lowlevel",  "HIGH", "เรียก Win32/C โดยตรง"),
    (r"\bimport\s+winreg\b|\bwinreg\.",  "registry",  "HIGH", "แก้ registry"),
    (r"\bwin32\w+\b",                    "lowlevel",  "HIGH", "เรียก Win32 API"),
    # ── ขโมยความลับ ──
    (r"\bos\.environ\b|\bgetenv\s*\(",   "secret",    "MED",  "อ่าน env (อาจมีกุญแจ)"),
    (r"\.secrets|FAMILY_ACCOUNTS|BRIDGE_AUTH|API_KEY", "secret", "HIGH", "พาดพิงไฟล์/ค่าลับ"),
    # ── deserialize อันตราย ──
    (r"\b(pickle|marshal)\.loads?\s*\(", "deser",     "MED",  "โหลด object อันตราย"),
]

_COMPILED = [(re.compile(p), cat, sev, desc) for p, cat, sev, desc in DANGER_PATTERNS]


def scan(code: str):
    """คืน list ของ findings: [{'pattern','category','severity','desc','line'}]"""
    findings = []
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        s = line.split("#", 1)[0]  # ข้ามคอมเมนต์
        for rx, cat, sev, desc in _COMPILED:
            if rx.search(s):
                findings.append({"category": cat, "severity": sev,
                                 "desc": desc, "line": i,
                                 "code": line.strip()[:80]})
    return findings


def verdict(code: str):
    """คืน (allowed, findings). allowed=False ถ้ามี HIGH"""
    findings = scan(code)
    has_high = any(f["severity"] == "HIGH" for f in findings)
    return (not has_high), findings
