# -*- coding: utf-8 -*-
"""
core/cross_memory.py — ความจำข้ามเซสชั่น
สะสมบริบทจาก: แชทเก่า + บันทึกสภา + งานส่งมอบ → ฉีดเข้า prompt อัตโนมัติ
ทำให้ AI จำได้ว่า user ทำอะไรมาก่อน ไม่ต้องอธิบายซ้ำ
"""
import os
import json
import glob
import threading
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAT_DIR = os.path.join(_BASE, "chats")
_LOG_DIR = os.path.join(_BASE, "logs")
_PROJECTS_DIR = os.path.join(_BASE, "projects")

MAX_MEMORY_ITEMS = 30       # เก็อุดสูงใน _memory.json
MAX_CONTEXT_CHARS = 2000    # ตัด context ไม่ให้ยาวเกิน

_mem_locks = {}
_mem_locks_guard = threading.Lock()

def _get_mem_lock(path):
    with _mem_locks_guard:
        if path not in _mem_locks:
            _mem_locks[path] = threading.Lock()
        return _mem_locks[path]


def _safe(s):
    return "".join(c for c in (s or "") if c.isalnum() or 0x0e01 <= ord(c) <= 0x0e5b) or "x"


def _memory_path(username):
    user_dir = os.path.join(_CHAT_DIR, _safe(username))
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, "_memory.json")


def load_memory(username):
    """อ่านความจำสะสมของ user"""
    path = _memory_path(username)
    lock = _get_mem_lock(path)
    with lock:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"facts": [], "last_updated": None}


def save_memory(username, mem):
    """บันทึกความจำ"""
    mem["last_updated"] = datetime.now().isoformat()
    path = _memory_path(username)
    lock = _get_mem_lock(path)
    with lock:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def add_fact(username, fact, fact_type="note"):
    """เพิ่มความจำใหม่ — fact_type: note/preference/project/decision"""
    path = _memory_path(username)
    lock = _get_mem_lock(path)
    with lock:
        try:
            with open(path, encoding="utf-8") as f:
                mem = json.load(f)
        except Exception:
            mem = {"facts": [], "last_updated": None}
        facts = mem.get("facts", [])
        # กันซ้ำ — ถ้า fact คล้ายของเก่า (ต้นนำ 50 ตัว) ไม่เพิ่ม
        prefix = fact[:50]
        if any(f.get("text", "")[:50] == prefix for f in facts):
            return
        facts.append({
            "text": fact[:300],
            "type": fact_type,
            "time": datetime.now().strftime("%d/%m/%Y %H:%M")
        })
        # เก็บเฉพาะล่าสุด
        mem["facts"] = facts[-MAX_MEMORY_ITEMS:]
        mem["last_updated"] = datetime.now().isoformat()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def _recent_sessions(username, limit=5):
    """อ่าน session logs ล่าสุดของ user"""
    sessions = []
    for path in sorted(glob.glob(os.path.join(_LOG_DIR, "session_*.json")), reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("username") != username:
                continue
            task = (data.get("task") or "")[:100]
            approved = data.get("approved", False)
            summary = (data.get("summary") or "")[:200]
            sessions.append(f"• {task} — {'ผ่าน' if approved else 'ยังไม่ผ่าน'}: {summary}")
            if len(sessions) >= limit:
                break
        except Exception:
            continue
    return sessions


def _recent_chats(username, limit=5):
    """อ่านบทสนทนาล่าสุดจากทุก persona — เอาเฉพาะ 2 ข้อความล่าสุดต่อ persona"""
    user_dir = os.path.join(_CHAT_DIR, _safe(username))
    if not os.path.isdir(user_dir):
        return []
    snippets = []
    for fn in os.listdir(user_dir):
        if fn == "_memory.json" or not fn.endswith(".json"):
            continue
        persona = fn.replace(".json", "")
        try:
            with open(os.path.join(user_dir, fn), encoding="utf-8") as f:
                msgs = json.load(f)
            if not msgs:
                continue
            # เอา 2 ข้อความล่าสุด
            recent = msgs[-2:]
            text = " ".join(m.get("text", "")[:80] for m in recent)
            snippets.append(f"• คุยกับ {persona}: {text[:150]}")
        except Exception:
            continue
    return snippets[:limit]


def _recent_projects(username, limit=3):
    """อ่าน summary ล่าสุดจาก projects/"""
    projects = []
    for path in sorted(glob.glob(os.path.join(_PROJECTS_DIR, "*")), reverse=True):
        summary_path = os.path.join(path, "summary.md")
        if not os.path.isfile(summary_path):
            continue
        try:
            with open(summary_path, encoding="utf-8") as f:
                content = f.read()[:200]
            name = os.path.basename(path)
            projects.append(f"• {name}: {content}")
            if len(projects) >= limit:
                break
        except Exception:
            continue
    return projects


def build_context(username, max_chars=MAX_CONTEXT_CHARS):
    """สร้าง context string สำหรับฉีดเข้า prompt — รวมจากทุกแหล่ง"""
    parts = []

    # 1. ความจำสะสม (facts)
    mem = load_memory(username)
    facts = mem.get("facts", [])
    if facts:
        recent_facts = facts[-10:]  # เอา 10 ข้อล่าสุด
        fact_lines = [f"  - [{f.get('type','note')}] {f.get('text','')}" for f in recent_facts]
        parts.append("ความจำสะสมของผู้ใช้:\n" + "\n".join(fact_lines))

    # 2. งานสภาล่าสุด
    sessions = _recent_sessions(username)
    if sessions:
        parts.append("งานที่ส่งให้สภาล่าสุด:\n" + "\n".join(sessions))

    # 3. แชทล่าสุด
    chats = _recent_chats(username)
    if chats:
        parts.append("บทสนทนาล่าสุด:\n" + "\n".join(chats))

    # 4. งานส่งมอบล่าสุด
    projects = _recent_projects(username)
    if projects:
        parts.append("งานส่งมอบล่าสุด:\n" + "\n".join(projects))

    if not parts:
        return ""

    context = "\n\n".join(parts)
    return context[:max_chars]


def context_block(username):
    """สร้าง block สำหรับใส่ใน prompt — พร้อม header"""
    ctx = build_context(username)
    if not ctx:
        return ""
    return f"\n[ความจำข้ามเซสชั่น — บริบทของผู้ใช้ที่สะสมไว้]\n{ctx}\n"
