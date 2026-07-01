# -*- coding: utf-8 -*-
"""ทดสอบแจ่มจูน audit โดยตรง (ไม่ผ่านเว็บ)"""
import sys, os
import inspect  # <-- เพิ่ม import inspect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import orchestrator

project = r"C:\Inthasap_Guard\Council_Lab"

events = []
def on_event(speaker, text):
    t = text[:300] if len(text) > 300 else text
    print(f"[{speaker}] {t}")
    events.append((speaker, text))

print("=" * 60)
print("เริ่มแจ่มจูน audit (รอบทดสอบ)...")
print("=" * 60)

# แก้บั๊ก: ใช้ inspect.signature เพื่อตรวจสอบพารามิเตอร์จริงของ run_project_audit
# แล้วเรียกให้ถูกต้อง โดยไม่ต้อง try-except ซ้อนหลายชั้น
sig = inspect.signature(orchestrator.run_project_audit)
params = list(sig.parameters.keys())

# สร้าง dict ของพารามิเตอร์ที่ต้องการส่ง
call_kwargs = {
    "project": project,
    "on_event": on_event,
    "should_stop": lambda: False,
}

# ถ้าฟังก์ชันรองรับ username ให้เพิ่ม
if "username" in params:
    call_kwargs["username"] = "test01"

# ถ้าฟังก์ชันรองรับ get_answer ให้เพิ่ม (แต่ส่ง None)
if "get_answer" in params:
    call_kwargs["get_answer"] = None

print(f"[INFO] Signature ของ run_project_audit: {params}")
print(f"[INFO] เรียกด้วยพารามิเตอร์: {list(call_kwargs.keys())}")

summary, transcript = orchestrator.run_project_audit(**call_kwargs)

print("=" * 60)
print(f"สรุป: {summary}")
print(f"จำนวน events: {len(transcript)}")
print("=" * 60)
