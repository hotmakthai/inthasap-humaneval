# DEVIN TASK COMBO — 2 งานในชุดเดียว

**งาน 1:** ARC Ollama เปลี่ยนโมเดล → `qwen2.5:7b` + ทดสอบ 3 ข้อ
**งาน 2:** Rolling summary ย้ายไปทำเบื้องหลัง (async) — จันทร์จูนตอบเร็วขึ้นโดยไม่ลดคุณภาพ

ทำงาน 1 ก่อน (สั้น) แล้วต่องาน 2

---

# งาน 1 — ARC Ollama: สลับเป็น qwen2.5:7b

**ไฟล์ที่แก้:** `arc_ollama_run.py` (มีอยู่แล้ว)
**ห้ามแตะ:** `core/*` · `arc_engine.py` · `arc_llm.py` · `t0_pred_b.json`

## ที่มา
ผลทดสอบยืนยันแล้ว: `qwen3-vl:8b` เป็น vision model — timeout 3/3 ข้อ · `qwen2.5:7b` เป็น text model ตอบ "2+2" ได้ใน 26s → พ่ออนุมัติสลับ

## งาน
1. เปลี่ยน `MODEL = "qwen3-vl:8b"` → `MODEL = "qwen2.5:7b"`
2. timeout คงไว้ 300s (ถ้า qwen2.5 ตอบใน ~60-120s ก็เหลือเฟือ)
3. เปลี่ยนชื่อ state file เป็น `arc_ollama_state_qwen25.json` (แยกจากผลรอบ qwen3-vl เดิม — อย่าลบไฟล์เก่า)
4. รัน 3 ข้อแรกแล้วรายงานผล: task_id / ✅❌ / acc / เวลา ต่อข้อ

## DoD งาน 1
- รายงานตาราง 3 ข้อ + เวลาเฉลี่ยต่อข้อ + ประมาณเวลารวม 203 ข้อ
- **หยุดแค่ 3 ข้อ — พ่อจะเคาะรันเต็มเอง**

---

# งาน 2 — Async Rolling Summary (จันทร์จูนตอบเร็วขึ้น)

**ไฟล์ที่แก้:** `council_web.py` เท่านั้น
**backup ก่อนแก้:** `council_web.py.bak_async_summary`
**ห้ามแตะ:** `rolling_summary.py` · `core/*` · `.env` · `web/*`

## ที่มา (พ่อ + พี่จูนวิเคราะห์แล้ว)

ตอนนี้ `/api/chat` (บรรทัด ~1618-1625) บีบประวัติ**ก่อน**ตอบ:

```python
# T5: Rolling summary — บีบ msgs ก่อนส่ง AI ถ้าเกิน threshold
if rolling_summary.should_compress(msgs):
    def _compress_fn(pr):
        txt, _, _ = llm.call_with_fallback(
            "คุณเป็น AI สรุปบทสนทนา ตอบเป็นภาษาไทย สั้น กระชับ bullet points",
            pr, max_tokens=600)
        return txt
    msgs, _ = rolling_summary.compress(msgs, _compress_fn, room="chat")
```

ปัญหา: เทิร์นที่แชทเกิน 40 ข้อความ ผู้ใช้ต้องรอ **2 LLM calls ต่อกัน** (สรุป → แล้วค่อยตอบ) = ช้าเท่าตัว

## เป้าหมาย
- ผู้ใช้**ไม่ต้องรอการสรุปเลย** — ตอบด้วยประวัติเดิมไปก่อน แล้วสรุปเบื้องหลังเก็บไว้ใช้เทิร์นถัดไป
- คุณภาพสรุป**ดีขึ้น**: เพิ่ม max_tokens 600 → 1200 (ไม่บล็อกผู้ใช้แล้ว จ่ายเวลาได้)

## วิธีทำ

### 2.1 แทนบล็อก compress เดิมด้วย async version

```python
import threading

_compress_locks: dict[str, threading.Lock] = {}
_compress_locks_guard = threading.Lock()

def _get_compress_lock(key: str) -> threading.Lock:
    with _compress_locks_guard:
        if key not in _compress_locks:
            _compress_locks[key] = threading.Lock()
        return _compress_locks[key]

def _compress_in_background(who: str, username: str):
    """สรุปประวัติเบื้องหลัง — โหลดไฟล์ล่าสุด บีบ แล้วบันทึกกลับ"""
    key = f"{username}:{who}"
    lock = _get_compress_lock(key)
    if not lock.acquire(blocking=False):
        return  # มี compress ของห้องนี้กำลังรันอยู่ — ข้าม
    try:
        msgs = _load_chat(who, username)
        if not rolling_summary.should_compress(msgs):
            return
        def _compress_fn(pr):
            txt, _, _ = llm.call_with_fallback(
                "คุณเป็น AI สรุปบทสนทนา ตอบเป็นภาษาไทย กระชับ bullet points "
                "เก็บข้อเท็จจริง ตัวเลข ชื่อคน ชื่อไฟล์ และการตัดสินใจให้ครบ",
                pr, max_tokens=1200)
            return txt
        new_msgs, summary = rolling_summary.compress(msgs, _compress_fn, room="chat")
        if summary:  # บีบสำเร็จเท่านั้นค่อยบันทึก
            # โหลดซ้ำกันเผื่อมีข้อความใหม่เข้ามาระหว่างสรุป
            latest = _load_chat(who, username)
            if len(latest) > len(msgs):
                # มีข้อความใหม่งอกระหว่างสรุป — ต่อท้ายเข้าไป
                new_msgs = new_msgs + latest[len(msgs):]
            _save_chat(who, new_msgs, username)
    except Exception:
        pass  # เบื้องหลังพลาดได้ ไม่กระทบผู้ใช้ — เทิร์นหน้าลองใหม่เอง
    finally:
        lock.release()
```

### 2.2 ในตัว `/api/chat` — ตัดการบีบก่อนตอบออก แล้วยิง thread หลังบันทึกแชท

แทนบล็อกเดิม (บรรทัด ~1618-1625) ด้วย: **ไม่ทำอะไรก่อนตอบ** (ลบ if should_compress ทั้งบล็อก)

แล้วหลัง `_save_chat(who, msgs, username)` (บรรทัด ~1665 ใน flow ตอบเสร็จ) เพิ่ม:

```python
# T5-async: สรุปประวัติเบื้องหลัง — ไม่บล็อกผู้ใช้
if rolling_summary.should_compress(msgs):
    threading.Thread(
        target=_compress_in_background, args=(who, username), daemon=True
    ).start()
```

### 2.3 กันประวัติบวมระหว่างรอสรุป

`_chat_prompt` มี guard `len(hist) > 7000` → ย่ออยู่แล้ว (บรรทัด ~1460) — ไม่ต้องแก้ แค่ยืนยันว่ายังทำงาน

## DoD งาน 2

สร้าง `test_async_summary.py` ใน Council_Lab root:

```python
"""ทดสอบ async rolling summary — mock compress_fn ไม่เรียก LLM จริง"""
import time, threading
import rolling_summary

# 1. should_compress ยังทำงานปกติ
msgs = [{"role": "u", "text": f"msg {i}"} for i in range(45)]
assert rolling_summary.should_compress(msgs) == True
assert rolling_summary.should_compress(msgs[:30]) == False
print("PASS: should_compress")

# 2. compress ด้วย mock fn
def mock_fn(prompt):
    return "สรุป: คุยเรื่องทดสอบ 35 ข้อความ"
new_msgs, summary = rolling_summary.compress(msgs, mock_fn, room="chat")
assert len(new_msgs) == 11  # 1 summary + 10 tail
assert "สรุป" in new_msgs[0]["text"]
print("PASS: compress merges to 11 msgs")

# 3. จำลอง background thread ไม่ throw
result = {}
def bg():
    result["msgs"], result["sum"] = rolling_summary.compress(msgs, mock_fn)
t = threading.Thread(target=bg, daemon=True)
t.start(); t.join(timeout=5)
assert result.get("sum"), "background compress ต้องได้ summary"
print("PASS: background thread compress")
print("ALL PASS")
```

รันแล้วต้องได้:
```
PASS: should_compress
PASS: compress merges to 11 msgs
PASS: background thread compress
ALL PASS
```

และตรวจโค้ดจริง:
- [ ] `/api/chat` ไม่มี compress ก่อน `llm.call_tier` อีกแล้ว
- [ ] thread ยิงหลัง `_save_chat` เท่านั้น
- [ ] lock กันบีบซ้อนต่อห้อง (`username:who`)
- [ ] มีการโหลดซ้ำเช็คข้อความใหม่ก่อนบันทึกทับ (race guard)
- [ ] backup `council_web.py.bak_async_summary` มีจริง

## หมายเหตุสำคัญ
- ⚠️ แก้ `council_web.py` เสร็จต้อง**แจ้งพ่อ restart server** (พอร์ต 8091) ถึงจะเห็นผล
- `rolling_summary.py` ห้ามแก้ — logic บีบเดิมถูกต้องแล้ว เปลี่ยนแค่จังหวะเรียก

---

## ห้ามทำ (ทั้ง 2 งาน)
- ห้ามแตะ `core/*` · `.env` · `rolling_summary.py` · `web/*` · `arc_engine.py` · `arc_llm.py`
- ห้ามลบ `arc_ollama_state.json` เดิม (ผลรอบ qwen3-vl)
- ห้ามลบ backup
- งาน 1 หยุดที่ 3 ข้อ — ห้ามรันเต็ม 203 ข้อเอง
