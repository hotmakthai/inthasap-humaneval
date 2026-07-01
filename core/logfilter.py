# -*- coding: utf-8 -*-
"""
core/logfilter.py — ตัวคัด log อัจฉริยะ (ลด input token ขากลับเข้าสภา)
แนวคิด: ผลรัน/stack trace ยาวเฟื้อยที่ป้อนกลับให้ AI ตรวจ มีแต่ขยะซ้ำๆ
เก็บเฉพาะบรรทัดที่ "ใช้แก้บั๊กได้จริง": error, ไฟล์+เลขบรรทัด, assert ที่ล้ม, สรุปเทส
ตัด traceback frame กลางๆ ที่ไม่เกี่ยวออก — ทำในบ้านเรา ปลอดภัย คุมเองทุกบรรทัด
(ทดแทนปลั๊กอินภายนอกแบบ RTK โดยไม่ต้องให้ใครมาดักดู log ของเรา)
"""
import re

# บรรทัดที่ "มีความหมาย" ต่อการแก้บั๊ก — เก็บไว้เสมอ
_SIGNAL = re.compile(
    r'(Traceback|Error|Exception|assert|FAIL|FAILED|OK$|Ran \d+ test|'
    r'ModuleNotFound|SyntaxError|IndentationError|NameError|TypeError|'
    r'ValueError|KeyError|IndexError|AttributeError|EOFError|'
    r'🚫|⚠️|✅|❌|line \d+|exit=|^E\s|^FAILED|^ERROR:|^FAIL:|^PASSED)',
    re.IGNORECASE | re.MULTILINE)

# เฟรมของ traceback:  File "xxx.py", line 12, in func
_FILE_FRAME = re.compile(r'^\s*File "(.+?)", line (\d+)')


def compress(text, max_chars=1200, head=4, tail=6):
    """
    ย่อ log ยาวให้เหลือเฉพาะแก่น คืน string สั้นลงมาก แต่ยังพอแก้บั๊กได้
    - log สั้น (<= max_chars) คืนเดิม (ไม่แตะ)
    - log ยาว: เก็บหัว head บรรทัด + ท้าย tail บรรทัด + ทุกบรรทัดสัญญาณ
      + เฟรม traceback 2 อันสุดท้าย (จุดเกิด error) ส่วนกลางยุบเป็น "… ตัด N บรรทัด …"
    """
    if not text:
        return text or ""
    text = text.rstrip()
    if len(text) <= max_chars:
        return text

    lines = text.split("\n")
    n = len(lines)
    keep = [False] * n

    # หัว–ท้าย เก็บเป็นบริบท (อะไรรัน + ผลสรุปท้ายสุด)
    for i in list(range(min(head, n))) + list(range(max(0, n - tail), n)):
        keep[i] = True

    file_idx = []
    for i, ln in enumerate(lines):
        if _FILE_FRAME.match(ln):
            file_idx.append(i)
        elif _SIGNAL.search(ln):
            keep[i] = True

    # เฟรมไฟล์: เก็บแค่ 2 อันสุดท้าย (จุดที่บั๊กเกิดจริง) + บรรทัดโค้ดถัดไป
    for i in file_idx[-2:]:
        keep[i] = True
        if i + 1 < n and lines[i + 1].strip() and not _FILE_FRAME.match(lines[i + 1]):
            keep[i + 1] = True

    # ประกอบกลับ ใส่ตัวคั่นเมื่อข้ามช่วงที่ตัดทิ้ง
    out, skipped = [], 0
    for i in range(n):
        if keep[i]:
            if skipped:
                out.append(f"   … ตัด {skipped} บรรทัด …")
                skipped = 0
            out.append(lines[i])
        else:
            skipped += 1
    if skipped:
        out.append(f"   … ตัด {skipped} บรรทัด …")

    res = "\n".join(out)
    if len(res) > max_chars * 2:               # กันเคสผิดปกติยังยาวเกิน
        res = res[: max_chars * 2] + "\n   …(ตัดท้าย)…"
    return res


if __name__ == "__main__":
    # self-test เล็กๆ
    sample = "เริ่มรัน\n" + "\n".join(
        f'  File "deep{i}.py", line {i}, in f{i}\n    call_next()' for i in range(20)
    ) + "\nValueError: boom\nRan 3 tests in 0.01s\nFAILED (failures=1)"
    print("ก่อน:", len(sample), "ตัวอักษร,", sample.count(chr(10)) + 1, "บรรทัด")
    c = compress(sample)
    print("หลัง:", len(c), "ตัวอักษร")
    print("-" * 40)
    print(c)
