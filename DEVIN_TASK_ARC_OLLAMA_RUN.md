# DEVIN TASK — ARC Ollama Runner (ทาง A)

**สร้างไฟล์ใหม่:** `arc_ollama_run.py` ใน Council_Lab root
**ห้ามแตะ:** `core/*` · `arc_engine.py` · `arc_llm.py` · `council_web.py` · `.env`

---

## Context

- 400 ข้อ ARC-AGI · ถูกแล้ว 197 · ยังผิด 203 (18 มีคำตอบแต่ผิด + 185 ไม่มีคำตอบ)
- Ollama รันอยู่บนเครื่อง `http://localhost:11434`
- โมเดล: `qwen3-vl:8b` (ดาวน์โหลดครบแล้ว)
- ผล baseline อยู่ที่: `t0_pred_b.json` — format `{task_id: [[row,...], ...]}` หรือ `{task_id: [attempt1, attempt2]}`
- ARC dataset: `arc_data/data/training/<task_id>.json`
- ประมาณเวลา: ~160 วินาที/ข้อ × 203 ข้อ ≈ 9 ชั่วโมง → รันข้ามคืน

---

## งานที่ต้องทำ

สร้าง `arc_ollama_run.py` ที่:

### 1. โหลด task ที่ยังผิด

```python
import json
from pathlib import Path

pred_all = json.loads(Path("t0_pred_b.json").read_text(encoding="utf-8"))
training_dir = Path("arc_data/data/training")

def cell_accuracy(pred, truth):
    if not pred or not truth or len(pred) != len(truth): return 0.0
    total = sum(len(r) for r in truth)
    if not total: return 0.0
    correct = sum(1 for r1,r2 in zip(pred,truth) for c1,c2 in zip(r1,r2) if c1==c2)
    return correct / total

# คัด task ที่ยังผิด (acc < 1.0)
unsolved = []
for task_id, p in pred_all.items():
    task_file = training_dir / f"{task_id}.json"
    if not task_file.exists(): continue
    task = json.loads(task_file.read_text(encoding="utf-8"))
    truth = task["test"][0]["output"]
    pred = p[0] if (p and isinstance(p[0], list) and isinstance(p[0][0], list)) else p
    if cell_accuracy(pred, truth) < 1.0:
        unsolved.append(task_id)

print(f"unsolved: {len(unsolved)} tasks")
```

### 2. Prompt สำหรับ qwen3-vl:8b

```python
def build_prompt(task: dict) -> str:
    lines = ["Solve this ARC-AGI puzzle. Output ONLY a valid Python list of lists of integers, nothing else.\n"]
    lines.append("Training examples:")
    for i, ex in enumerate(task["train"]):
        lines.append(f"Input {i+1}: {ex['input']}")
        lines.append(f"Output {i+1}: {ex['output']}")
    lines.append(f"\nTest input: {task['test'][0]['input']}")
    lines.append("\nAnswer (Python list of lists only):")
    return "\n".join(lines)
```

### 3. เรียก Ollama HTTP API

```python
import requests, re, ast

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3-vl:8b"

def ask_ollama(prompt: str, timeout: int = 300) -> str | None:
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 2048}
        }, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as e:
        print(f"  Ollama error: {e}")
        return None

def parse_grid(text: str) -> list | None:
    """สกัด grid จาก response — หา [[...]] ที่ valid"""
    if not text: return None
    # หา list-of-lists ใน text
    matches = re.findall(r'\[\s*\[[\d,\s\[\]]+\]\s*\]', text, re.DOTALL)
    for m in reversed(matches):  # เอา match ท้ายสุด
        try:
            grid = ast.literal_eval(m)
            if (isinstance(grid, list) and grid
                    and all(isinstance(r, list) and r for r in grid)
                    and all(isinstance(c, int) for r in grid for c in r)):
                return grid
        except Exception:
            continue
    return None
```

### 4. Resume mechanism — บันทึกทุกข้อ

```python
STATE_FILE = Path("arc_ollama_state.json")

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"done": {}, "errors": []}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
```

### 5. Main loop

```python
import time

def main():
    state = load_state()
    done = state["done"]  # {task_id: {"pred": grid, "acc": float, "time": float}}

    remaining = [t for t in unsolved if t not in done]
    print(f"เหลือ {len(remaining)}/{len(unsolved)} ข้อ (resume จาก {len(done)} ข้อที่ทำแล้ว)")

    for i, task_id in enumerate(remaining):
        task_file = training_dir / f"{task_id}.json"
        task = json.loads(task_file.read_text(encoding="utf-8"))
        truth = task["test"][0]["output"]

        print(f"[{i+1}/{len(remaining)}] {task_id} ...", end=" ", flush=True)
        t0 = time.time()

        prompt = build_prompt(task)
        raw = ask_ollama(prompt)
        pred = parse_grid(raw) if raw else None
        acc = cell_accuracy(pred, truth) if pred else 0.0
        elapsed = round(time.time() - t0, 1)

        is_correct = (acc == 1.0)
        symbol = "✅" if is_correct else f"❌ acc={acc:.2f}"
        print(f"{symbol} ({elapsed}s)")

        done[task_id] = {"pred": pred, "acc": acc, "time": elapsed, "correct": is_correct}
        save_state({"done": done, "errors": state["errors"]})

    # สรุป
    correct = [t for t,v in done.items() if v.get("correct")]
    print(f"\n=== สรุป ===")
    print(f"Ollama ถูก: {len(correct)}/{len(done)} ข้อ")
    print(f"รวมกับ baseline: {197 + len(correct)}/400 ({(197+len(correct))/4:.1f}%)")

if __name__ == "__main__":
    main()
```

---

## Definition of Done

รันแล้วดูว่า:

```
python arc_ollama_run.py
```

ผลที่ต้องเห็น:
```
unsolved: 203 tasks
เหลือ 203/203 ข้อ (resume จาก 0 ข้อที่ทำแล้ว)
[1/203] 007bbfb7 ... ❌ acc=0.00 (162.3s)
[2/203] 00dbd492 ... ✅ (155.1s)
...
```

- **resume ได้**: ถ้า Ctrl+C แล้วรันใหม่ → ต้องข้ามข้อที่ทำแล้ว (อ่านจาก `arc_ollama_state.json`)
- บันทึกผลทุกข้อทันทีหลังได้คำตอบ (ไม่รอจบ)
- ถ้า Ollama ไม่ตอบ (timeout) → บันทึก `pred: null, acc: 0.0` แล้วข้ามต่อ ไม่หยุด

**ทดสอบด้วย 3 ข้อแรกก่อน** แล้วรายงาน output มาให้ดู — พ่อจะเคาะรัน 203 ข้อเองหลังจากนั้น

---

## ห้ามทำ

- ห้ามแตะ `core/*` · `arc_engine.py` · `arc_llm.py` · `council_web.py` · `.env`
- ห้ามแก้ `t0_pred_b.json` (baseline เดิม ห้ามเขียนทับ)
- ห้าม import จาก `core/` (standalone script เท่านั้น)
