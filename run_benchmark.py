# -*- coding: utf-8 -*-
"""
run_benchmark.py — วัดสภาด้วยชุดข้อสอบมาตรฐาน (objective, มีเฉลยลับ)

รันเมื่อต้องการวัด:  python run_benchmark.py
  ⚠️ เสีย API จริง (สภารันทุกข้อ) — ไม่ auto เพื่อคุมต้นทุน
ผลเก็บลง benchmarks/results/ เทียบ regression รอบก่อนได้

วัด 3 อย่าง: hidden_pass (เฉลยถูกจริง-สำคัญสุด) · approved (ลงมติเสร็จ) · rounds (กี่รอบ)
"""
import os
import sys
import io
import json
import glob
import time
import re
import subprocess

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
from core import orchestrator, sandbox


def _score_transcript(transcript):
    """อ่าน approved + จำนวนรอบ จาก transcript (objective จากสถานะที่ระบบ emit)

    รองรับ transcript หลายรูปแบบ:
    - tuple (role, content) — รูปแบบดั้งเดิม
    - list [role, content] — รูปแบบทางเลือก
    - dict {"role": ..., "content": ...} — รูปแบบ API
    """
    approved, rounds = False, 0
    
    # [แก้บั๊ก 1] ลบ fallback string ที่ไม่มีทางเกิดขึ้นจริง
    # orchestrator.run_task คืนค่าเป็น tuple เสมอ
    
    for t in transcript:
        # ดึง content จาก transcript ทุกรูปแบบ
        if isinstance(t, dict):
            content = t.get("content") or ""
        elif isinstance(t, (list, tuple)) and len(t) > 1:
            # [แก้บั๊ก 1] ป้องกัน TypeError เมื่อ t[1] เป็น None
            content = t[1] or ""
        else:
            continue

        if "ผ่านการตรวจรอบ" in content:
            approved = True
        m = re.search(r"รอบ (\d+)", content)
        if m:
            rounds = max(rounds, int(m.group(1)))
    return approved, rounds


def _run_hidden(case):
    """รันเทสลับกับไฟล์ที่สภาเพิ่งส่งมอบใน workspace — คืน True/False/None(ไม่มีเทสลับ)"""
    rel = case.get("hidden_test")
    if not rel:
        return None
    ht_path = os.path.join(BASE, "benchmarks", rel)
    if not os.path.exists(ht_path):
        return None
    code = open(ht_path, encoding="utf-8").read()
    dst = os.path.join(sandbox.WORKSPACE, "_hidden_check.py")
    # [แก้บั๊ก 2] ตรวจสอบ sandbox.WORKSPACE ก่อนสร้างโฟลเดอร์
    workspace = sandbox.WORKSPACE
    if not workspace:
        return None
    os.makedirs(workspace, exist_ok=True)
    open(dst, "w", encoding="utf-8").write(code)
    try:
        r = subprocess.run([sys.executable, "_hidden_check.py"], cwd=workspace,
                           capture_output=True, text=True, timeout=30)
        return "HIDDEN_OK" in (r.stdout or "")
    except Exception:
        return False
    finally:
        try:
            os.remove(dst)
        except Exception:
            pass


def run_case(case):
    t0 = time.time()
    summary, transcript = orchestrator.run_task(
        case["task"], project_path=case.get("project"),
        max_rounds=case.get("max_rounds", 4))
    approved, rounds = _score_transcript(transcript)
    hidden = _run_hidden(case)   # ต้องรันก่อนข้อถัดไป (workspace ถูกล้างตอนเริ่มงานใหม่)
    return {"id": case["id"], "level": case.get("level", "-"),
            "hidden_pass": hidden, "approved": approved,
            "rounds": rounds, "sec": round(time.time() - t0, 1)}


def main():
    files = sorted(glob.glob(os.path.join(BASE, "benchmarks", "cases", "*.json")))
    if not files:
        print("ไม่พบ benchmark cases"); return
    print(f"=== Council Benchmark · {len(files)} ข้อ ===\n")
    results = []
    for cf in files:
        case = json.load(open(cf, encoding="utf-8"))
        print(f"▶ รัน {case['id']} ({case.get('level','-')}) ...")
        try:
            r = run_case(case)
        except Exception as e:
            r = {"id": case["id"], "error": str(e)[:140]}
        results.append(r)
        mark = "✅" if r.get("hidden_pass") else ("⚠️" if r.get("approved") else "❌")
        print(f"  {mark} {r}\n")

    print("=" * 50)
    nh = sum(1 for r in results if r.get("hidden_pass"))
    na = sum(1 for r in results if r.get("approved"))
    rs = [r["rounds"] for r in results if "rounds" in r]
    print(f"เฉลยถูกจริง (hidden): {nh}/{len(results)}  ← คะแนนจริง")
    print(f"สภาลงมติเสร็จ (approved): {na}/{len(results)}")
    if rs:
        print(f"รอบเฉลี่ย: {sum(rs)/len(rs):.1f}")

    outdir = os.path.join(BASE, "benchmarks", "results")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, time.strftime("bench_%Y%m%d_%H%M%S.json"))
    # [แก้บั๊ก 3] ลบ exist_ok=False ออกจาก json.dump (ไม่ใช่พารามิเตอร์ที่รองรับ)
    json.dump({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nบันทึกผล: {os.path.relpath(out, BASE)}")


if __name__ == "__main__":
    main()
