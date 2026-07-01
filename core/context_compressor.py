# -*- coding: utf-8 -*-
"""
core/context_compressor.py — บีบอัด Context ก่อนส่ง AI (ประหยัด Token)
รันในเครื่อง ฟรี ไม่เสียค่า API

3 โหมด:
  1. strip_code()    — ลบ comments/docstrings/blank lines ออกจากโค้ด (ปลอดภัย 20-40%)
  2. summarize_chat() — สรุปข้อความแชทยาวเป็นสั้น (50-70% สำหรับแชท)
  3. compress_batch() — บีบไฟล์ทั้ง batch ก่อนส่ง AI
"""
import re
import os
import ast
import textwrap

# ── 1. Code Stripper — ลบส่วนฟุ่มเฟือยออกจากโค้ด ──

def strip_python(code):
    """ลบ comments + docstrings + blank lines ซ้อนจาก Python code"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _strip_python_regex(code)

    lines = code.splitlines()
    skip_ranges = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                doc_node = node.body[0]
                for ln in range(doc_node.lineno, doc_node.end_lineno + 1):
                    skip_ranges.add(ln)

    out = []
    blank_count = 0
    for i, line in enumerate(lines, 1):
        if i in skip_ranges:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if stripped == "":
            blank_count += 1
            if blank_count <= 1:
                out.append("")
            continue
        blank_count = 0
        out.append(line.rstrip())

    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def _strip_python_regex(code):
    """Fallback: ลบ docstrings/comments ด้วย regex (ถ้า parse ไม่ได้)"""
    code = re.sub(r'"""[\s\S]*?"""', '', code)
    code = re.sub(r"'''[\s\S]*?'''", '', code)
    lines = []
    blank = 0
    for line in code.splitlines():
        s = line.lstrip()
        if s.startswith("#"):
            continue
        if s == "":
            blank += 1
            if blank <= 1:
                lines.append("")
            continue
        blank = 0
        lines.append(line.rstrip())
    return "\n".join(lines)


def strip_javascript(code):
    """ลบ comments + blank lines ซ้อนจาก JS/TS/CSS/HTML"""
    # ลบ block comments /* ... */
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    # ลบ line comments // ... (ไม่ลบใน string ง่ายๆ — ลบบรรทัดที่ขึ้นต้นด้วย //)
    lines = []
    blank = 0
    in_string = False
    string_char = None
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") and not in_string:
            continue
        if stripped == "":
            blank += 1
            if blank <= 1:
                lines.append("")
            continue
        blank = 0
        lines.append(line.rstrip())
    return "\n".join(lines)


def strip_html(code):
    """ลบ HTML comments + blank lines ซ้อน"""
    code = re.sub(r'<!--[\s\S]*?-->', '', code)
    lines = []
    blank = 0
    for line in code.splitlines():
        if line.strip() == "":
            blank += 1
            if blank <= 1:
                lines.append("")
            continue
        blank = 0
        lines.append(line.rstrip())
    return "\n".join(lines)


def strip_css(code):
    """ลบ CSS comments + blank lines ซ้อน"""
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    lines = []
    blank = 0
    for line in code.splitlines():
        if line.strip() == "":
            blank += 1
            if blank <= 1:
                lines.append("")
            continue
        blank = 0
        lines.append(line.rstrip())
    return "\n".join(lines)


def strip_code(code, ext):
    """บีบโค้ดตามประเภทไฟล์ — คืน (compressed, original_size, compressed_size, ratio)"""
    original_size = len(code)
    ext = ext.lower()
    if ext == ".py":
        compressed = strip_python(code)
    elif ext in (".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".go", ".rs", ".php", ".sh"):
        compressed = strip_javascript(code)
    elif ext in (".html", ".htm", ".xml", ".svg"):
        compressed = strip_html(code)
    elif ext in (".css", ".scss", ".less"):
        compressed = strip_css(code)
    else:
        # ไฟล์ทั่วไป: ลบ blank lines ซ้อน
        compressed = strip_javascript(code)

    compressed_size = len(compressed)
    ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
    return compressed, original_size, compressed_size, ratio


# ── 2. Chat Summarizer — สรุปข้อความแชทยาว ──

def summarize_chat(messages, max_lines=5):
    """สรุปประวัติแชทเป็นบรรทัดสั้นๆ — ใช้ heuristic (ไม่เสีย API)
    messages: list of (speaker, text)
    คืน: สตริงสรุปสั้น
    """
    if not messages:
        return ""

    total_chars = sum(len(t) for _, t in messages)
    if total_chars < 2000:
        # สั้นอยู่ ไม่ต้องสรุป
        return "\n".join(f"[{s}] {t[:200]}" for s, t in messages)

    # สรุป: เอา speaker + บรรทัดแรกของแต่ละข้อความ
    summary_lines = []
    for speaker, text in messages:
        # ตัดเอาแค่บรรทัดแรกที่ไม่ใช่ empty
        first_line = ""
        for line in text.splitlines():
            if line.strip():
                first_line = line.strip()[:150]
                break
        if first_line:
            summary_lines.append(f"[{speaker}] {first_line}")

    # ถ้ายังยาวเกิน → เอาแค่ 5 บรรทัดแรก + 5 บรรทัดสุดท้าย
    if len(summary_lines) > max_lines * 2:
        head = summary_lines[:max_lines]
        tail = summary_lines[-max_lines:]
        summary_lines = head + [f"... ({len(summary_lines) - max_lines * 2} ข้อความข้าม) ..."] + tail

    return "\n".join(summary_lines)


# ── 3. Batch Compressor — บีบไฟล์ทั้ง batch ก่อนส่ง AI ──

def compress_batch(file_contents, strip_mode="auto"):
    """บีบไฟล์ทั้ง batch ก่อนส่ง AI
    file_contents: list of (rel_path, content)
    คืน: (compressed_context, stats_dict)
    """
    parts = []
    total_orig = 0
    total_comp = 0
    file_stats = []

    for rel, content in file_contents:
        ext = os.path.splitext(rel)[1]
        if strip_mode == "off":
            compressed = content
            orig_size = len(content)
            comp_size = len(content)
            ratio = 0
        else:
            compressed, orig_size, comp_size, ratio = strip_code(content, ext)

        parts.append(f"=== {rel} ===\n{compressed}")
        total_orig += orig_size
        total_comp += comp_size
        file_stats.append({"file": rel, "orig": orig_size, "comp": comp_size, "ratio": round(ratio, 1)})

    context = "\n\n".join(parts)
    overall_ratio = (1 - total_comp / total_orig) * 100 if total_orig > 0 else 0
    stats = {
        "files": len(file_contents),
        "original_chars": total_orig,
        "compressed_chars": total_comp,
        "saved_chars": total_orig - total_comp,
        "ratio_pct": round(overall_ratio, 1),
        "per_file": file_stats,
    }
    return context, stats


# ── 4. Token Estimator — ประมาณ token จากตัวอักษร ──

def estimate_tokens(text):
    """ประมาณ token: ~4 ตัวอักษรต่อ token (ภาษาอังกฤษ), ~2 ตัวอักษรต่อ token (ภาษาไทย)"""
    # ถือว่าผสม: ~3 ตัวอักษรต่อ token
    n = len(text) if isinstance(text, str) else text
    return n // 3


def estimate_cost_savings(original_chars, compressed_chars, tier="deepseek", peak=False):
    """ประมาณการประหยัด USD"""
    orig_tokens = estimate_tokens(original_chars)
    comp_tokens = estimate_tokens(compressed_chars)
    saved_tokens = orig_tokens - comp_tokens

    # input price per 1M tokens
    prices = {"deepseek": 0.27, "gemini": 0.0, "claude": 3.00}
    price = prices.get(tier, 0.27)
    if peak and tier == "deepseek":
        price *= 2.0

    saved_usd = saved_tokens * price / 1_000_000
    return {
        "original_tokens": orig_tokens,
        "compressed_tokens": comp_tokens,
        "saved_tokens": saved_tokens,
        "saved_usd": round(saved_usd, 6),
        "tier": tier,
        "peak": peak,
    }
