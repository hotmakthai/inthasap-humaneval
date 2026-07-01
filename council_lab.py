# -*- coding: utf-8 -*-
"""
council_lab.py — Council Lab (สภาตัวแทนอัจฉริยะ ฉบับแยกบ้าน)
สภา 3 ตัวแทน: แจ่มจูน(สถาปนิก) · แจงจูน(coder) · เจนจูน(รีวิว) เขียน+รันโค้ดใน sandbox

วิธีใช้:
  python council_lab.py "งานที่อยากให้สภาทำ"          (ค่าเริ่มต้น 3 รอบ)
  python council_lab.py "งาน..." 3                     (กำหนดจำนวนรอบ)
  python council_lab.py                                 (ถามงานแบบ interactive)

Iron Rule: ไม่ import อะไรจากระบบบ้าน (Sovereign_Bridge / Inthasap_Guard) เลย
"""
import sys
import io

# กัน console cp874 พังเวลามี emoji/ไทย
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from core import orchestrator, personas


def _print_event(speaker, text):
    print("\n" + "─" * 60)
    print(speaker)
    print("─" * 60)
    print(text)


def main():
    args = list(sys.argv[1:])
    rounds = 3
    project = None
    # --project PATH (อ่านโปรเจกต์ที่มีอยู่)
    if "--project" in args:
        i = args.index("--project")
        if i + 1 < len(args):
            project = args[i + 1]
            del args[i:i + 2]
    if args and args[-1].isdigit():
        rounds = max(1, min(4, int(args[-1])))
        args = args[:-1]
    task = " ".join(args).strip()
    if not task:
        try:
            task = input("งานที่อยากให้สภาทำ: ").strip()
        except EOFError:
            task = ""
    if not task:
        print("ไม่มีงาน — จบ")
        return

    from core import llm
    print("=" * 60)
    print(" 🏛️  COUNCIL TRINITY LAB — สภาสามพี่น้อง (Layer B)")
    print("    📐แจ่มจูน(ออกแบบ) · 👩‍💻แจงจูน(เขียน) · 🔍เจนจูน(ตรวจ)")
    print(f"    งาน: {task}")
    if project:
        print(f"    โปรเจกต์: {project}")
    print(f"    รอบสูงสุด: {rounds}  |  tier ที่ใช้ได้: {', '.join(llm.available_tiers()) or 'ไม่มี!'}")
    print("=" * 60)

    summary, _ = orchestrator.run_task(task, project_path=project, max_rounds=rounds,
                                       on_event=_print_event)

    print("\n" + "=" * 60)
    print(" ✅ จบการประชุม — ดูไฟล์ที่สภาเขียนได้ใน Council_Lab/workspace/")
    print("=" * 60)


if __name__ == "__main__":
    main()
