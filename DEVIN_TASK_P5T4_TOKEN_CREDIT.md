# DEVIN TASK — P5-T4: Token → เครดิตผู้ใช้

**ไฟล์ที่แก้:** `council_web.py` · `web/terminal.html`
**ห้ามแตะ:** `core/*` · `.env` · `session_store.py` · `near_miss_verifier.py` · `arc_engine.py`
**backup ก่อนแก้:** `council_web.py.bak_P5T4` · `terminal.html.bak_P5T4`

---

## Context

ปัจจุบัน council_web.py มีระบบ credit อยู่แล้วบางส่วน:
- `_has_credit(user)` — ตรวจว่ายังมีเครดิตไหม
- `topup` endpoint — เติมเครดิต
- llm layer คืน usage ต่อ call แล้ว (`input_tokens`, `output_tokens`, `cost_usd`)

งานนี้คือ **ต่อท่อ**: ดึง token usage จริงจาก llm layer → แปลงเป็นบาท → หักเครดิต → โชว์ผู้ใช้

---

## งานที่ต้องทำ

### 1. Helper เครดิต (council_web.py)

เพิ่มถ้ายังไม่มี — อย่าลบ `_has_credit` / `topup` เดิม:

```python
CREDIT_FILE = DATA_DIR / "credits.json"   # {username: balance_thb}
USD_TO_THB = 35.0

def _get_balance(user: str) -> float:
    data = json.loads(CREDIT_FILE.read_text()) if CREDIT_FILE.exists() else {}
    return float(data.get(user, 0.0))

def _deduct_credit(user: str, cost_thb: float) -> float:
    data = json.loads(CREDIT_FILE.read_text()) if CREDIT_FILE.exists() else {}
    data[user] = round(float(data.get(user, 0.0)) - cost_thb, 4)
    CREDIT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data[user]
```

### 2. หักเครดิตหลังงานเสร็จ (council_web.py)

ใน SSE endpoint ของ council/chat — หลัง orchestrator คืนผล ดึง cost_usd จาก usage แล้ว:

```python
cost_thb = round(usage.get("cost_usd", 0.0) * USD_TO_THB, 4)
if cost_thb > 0:
    balance = _deduct_credit(user, cost_thb)
    yield f"event: __credit__\ndata: {json.dumps({'cost_thb': cost_thb, 'balance_thb': balance})}\n\n"
```

### 3. endpoint GET /api/credit (council_web.py)

```python
@app.route("/api/credit")
def api_credit():
    user = session.get("username", "guest")
    return jsonify({"balance_thb": _get_balance(user)})
```

### 4. UI (web/terminal.html)

**ยอดเครดิตมุมขวาบน:**
- โหลดจาก `/api/credit` ตอน DOMContentLoaded
- แสดงข้างชื่อ user: `฿49.93`
- อัปเดตเมื่อรับ SSE `__credit__` event

**pill ค่าใช้จ่ายต่องาน:**
- หลังรับ `__credit__` SSE event แสดง pill `💸 ฿0.07` ต่อจาก usage pill ที่มีอยู่แล้ว

---

## Definition of Done

สร้าง `test_p5t4_credit.py` ใน Council_Lab root แล้วรัน:

```python
import json, tempfile
from pathlib import Path

with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
    json.dump({"testuser": 50.0}, f)
    cfile = Path(f.name)

# simulate _deduct_credit
data = json.loads(cfile.read_text())
data["testuser"] = round(data["testuser"] - 0.07, 4)
cfile.write_text(json.dumps(data))
assert data["testuser"] == 49.93, f"expected 49.93 got {data['testuser']}"
print("PASS: deduct 50.00 - 0.07 = 49.93")

# simulate _get_balance
assert json.loads(cfile.read_text())["testuser"] == 49.93
print("PASS: get_balance = 49.93")

# simulate USD -> THB
cost_thb = round(0.002 * 35.0, 4)
assert cost_thb == 0.07
print("PASS: 0.002 USD * 35 = 0.07 THB")

print("ALL PASS")
```

ผลที่ต้องการ:
```
PASS: deduct 50.00 - 0.07 = 49.93
PASS: get_balance = 49.93
PASS: 0.002 USD * 35 = 0.07 THB
ALL PASS
```

และทดสอบ UI ด้วยตา (restart server ก่อน):
- ยอด `฿` ปรากฏมุมขวาบน ✓
- หลังรันงาน ยอดลดลง ✓
- pill `💸 ฿0.07` ปรากฏท้ายงาน ✓

---

## ห้ามทำ

- ห้ามลบ `_has_credit` / `topup` เดิม
- ห้าม hardcode username — ดึงจาก `session.get("username")`
- ห้ามแตะ `core/*` · `.env` · `session_store.py` · `near_miss_verifier.py` · `arc_engine.py`
- ห้ามลบ backup ที่ตัวเองสร้าง
