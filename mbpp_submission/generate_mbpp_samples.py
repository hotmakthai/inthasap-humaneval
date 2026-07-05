# -*- coding: utf-8 -*-
"""
Generate MBPP+ samples for EvalPlus evaluation.
Outputs: samples_mbpp_raw.jsonl + samples_mbpp_scaffolded.jsonl

Usage:
  1. Start server: python bench_api.py
  2. Run: python mbpp_submission/generate_mbpp_samples.py
  3. Convert to solution format + run EvalPlus:
     python mbpp_submission/convert_to_evalplus.py
     python -m evalplus.evaluate --dataset mbpp --samples mbpp_submission/samples_mbpp_scaffolded_evalplus.jsonl --i-just-wanna-run
"""
import os, sys, re, json, time, subprocess, tempfile, requests

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)

API = "http://localhost:8000/v1/chat/completions"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRESS_FILE = os.path.join(OUT_DIR, "gen_mbpp_progress.json")
SAMPLES_RAW = os.path.join(OUT_DIR, "samples_mbpp_raw.jsonl")
SAMPLES_SC = os.path.join(OUT_DIR, "samples_mbpp_scaffolded.jsonl")
SUMMARY_FILE = os.path.join(OUT_DIR, "mbpp_summary.json")


def strip_non_ascii_comments(code):
    if not code:
        return code
    lines = code.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#") and any(ord(c) > 127 for c in stripped):
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            pass
        inline_comment_idx = -1
        in_string = False
        string_char = None
        for j, c in enumerate(line):
            if c in ('"', "'") and not in_string:
                in_string = True
                string_char = c
            elif c == string_char and in_string:
                in_string = False
                string_char = None
            elif c == '#' and not in_string:
                inline_comment_idx = j
                break
        if inline_comment_idx >= 0:
            comment_part = line[inline_comment_idx:]
            if any(ord(c) > 127 for c in comment_part):
                line = line[:inline_comment_idx].rstrip()
        cleaned.append(line)
    return "\n".join(cleaned)


def extract_code(answer):
    if not answer:
        return ""
    ws_match = re.search(r'\[CODE FROM WORKSPACE\]\s*\n(.*?)(?:\[TRANSCRIPT\]|\Z)', answer, re.DOTALL)
    if ws_match:
        ws_text = ws_match.group(1)
        file_pattern = re.compile(r'# file: (\S+)\n(.*?)(?=# file: |\Z)', re.DOTALL)
        code_parts = []
        for m in file_pattern.finditer(ws_text):
            fname = m.group(1)
            fcontent = m.group(2).strip()
            if "test" in fname.lower():
                continue
            code_parts.append(fcontent)
        if code_parts:
            return "\n\n".join(code_parts)
        file_blocks = re.split(r'# file: \S+\n', ws_text)
        code_parts = [b.strip() for b in file_blocks if b.strip() and "test" not in b.lower()[:50]]
        if code_parts:
            return "\n\n".join(code_parts)
    summary_end = answer.find("[TRANSCRIPT]")
    summary_text = answer[:summary_end] if summary_end > 0 else answer
    blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', summary_text, re.DOTALL)
    if blocks:
        func_blocks = [
            b for b in blocks
            if re.search(r'^\s*(def |class )', b, re.MULTILINE)
            and not re.search(r'(import unittest|^from \w+ import|self\.assert)', b, re.MULTILINE)
        ]
        if func_blocks:
            return "\n\n".join(func_blocks)
    trans_match = re.search(r'\[TRANSCRIPT\]\s*\n(.*)', answer, re.DOTALL)
    if trans_match:
        trans_text = trans_match.group(1)
        blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', trans_text, re.DOTALL)
        if blocks:
            func_blocks = [
                b for b in blocks
                if re.search(r'^\s*(def |class )', b, re.MULTILINE)
                and not re.search(r'(import unittest|^from \w+ import|self\.assert)', b, re.MULTILINE)
            ]
            if func_blocks:
                return "\n\n".join(func_blocks)
    return ""


def call_api(prompt, scaffolding, timeout=600):
    try:
        r = requests.post(API, json={
            "messages": [{"role": "user", "content": prompt}],
            "metadata": {"scaffolding": scaffolding}
        }, timeout=timeout)
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"API_ERROR: {e}"


def build_prompt(problem):
    return problem["prompt"] + "\n\n# Complete the function above and make sure it passes all tests."


def run_mbpp_test(problem, generated_code):
    if not generated_code or not generated_code.strip():
        return False, "no_code_extracted"
    full_code = generated_code.rstrip() + "\n\n" + problem["assertion"] + "\n"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(full_code)
            f.flush()
            fname = f.name
        result = subprocess.run(
            [sys.executable, fname],
            capture_output=True, text=True, timeout=15,
            cwd=tempfile.gettempdir()
        )
        os.unlink(fname)
        if result.returncode == 0:
            return True, ""
        else:
            err = (result.stderr or result.stdout or "")[:300]
            return False, err
    except subprocess.TimeoutExpired:
        try: os.unlink(fname)
        except: pass
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:300]


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_index": 0, "raw_results": [], "sc_results": []}


def save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def write_jsonl(path, samples):
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def main():
    print("=" * 60)
    print("MBPP+ Sample Generator — Council Trinity Lab")
    print("Output: samples_mbpp_raw.jsonl + samples_mbpp_scaffolded.jsonl")
    print("=" * 60)

    try:
        r = requests.get("http://localhost:8000/health", timeout=10)
        if r.status_code != 200:
            print("Server not ready — run: python bench_api.py")
            return
        print("Server OK")
    except:
        print("Cannot connect to server — run: python bench_api.py")
        return

    from evalplus.data import get_mbpp_plus
    problems_dict = get_mbpp_plus()
    problems = []
    for tid in sorted(problems_dict.keys()):
        p = problems_dict[tid]
        problems.append({
            "task_id": tid,
            "prompt": p["prompt"],
            "entry_point": p.get("entry_point", ""),
            "assertion": p.get("assertion", ""),
            "canonical_solution": p.get("canonical_solution", ""),
        })
    total = len(problems)
    print(f"Got {total} MBPP+ problems")

    progress = load_progress()
    start_idx = progress["last_index"]
    raw_samples = progress["raw_results"]
    sc_samples = progress["sc_results"]

    if start_idx > 0:
        print(f"Resuming from problem {start_idx}/{total}")

    for i in range(start_idx, total):
        problem = problems[i]
        pid = problem["task_id"]
        prompt = build_prompt(problem)

        print(f"\n[{i+1}/{total}] {pid}", end="", flush=True)

        # Raw
        raw_answer = call_api(prompt, scaffolding=False)
        raw_code = extract_code(raw_answer)
        if not raw_code:
            if re.search(r'^\s*def\s+', raw_answer, re.MULTILINE):
                lines = raw_answer.split("\n")
                code_lines = []
                in_func = False
                for line in lines:
                    if re.match(r'^\s*def\s+', line):
                        in_func = True
                    if in_func:
                        if line.strip() == "" and code_lines and not code_lines[-1].strip():
                            break
                        if re.match(r'^[A-Z]|^#{2,}|^\*|^---', line) and not re.match(r'^\s+(if|for|while|return|else|elif|try|except|with|assert|print|raise|yield|break|continue|pass)', line):
                            break
                        code_lines.append(line)
                raw_code = "\n".join(code_lines) if code_lines else raw_answer
        if not raw_code or not raw_code.strip():
            print(f" (empty-retry)", end="", flush=True)
            raw_answer = call_api(prompt, scaffolding=False)
            raw_code = extract_code(raw_answer)
        raw_code = strip_non_ascii_comments(raw_code)
        raw_passed, raw_err = run_mbpp_test(problem, raw_code)
        raw_samples.append({
            "task_id": pid,
            "completion": raw_code,
            "passed": raw_passed,
        })
        print(f" Raw={'PASS' if raw_passed else 'FAIL'}", end="", flush=True)

        # Scaffolded
        sc_answer = call_api(prompt, scaffolding=True)
        sc_code = extract_code(sc_answer)
        if not sc_code or not sc_code.strip():
            print(f" (empty-retry)", end="", flush=True)
            sc_answer = call_api(prompt, scaffolding=True)
            sc_code = extract_code(sc_answer)
        sc_code = strip_non_ascii_comments(sc_code)
        sc_passed, sc_err = run_mbpp_test(problem, sc_code)
        sc_samples.append({
            "task_id": pid,
            "completion": sc_code,
            "passed": sc_passed,
        })
        print(f" SC={'PASS' if sc_passed else 'FAIL'}", end="", flush=True)

        progress["raw_results"] = raw_samples
        progress["sc_results"] = sc_samples
        progress["last_index"] = i + 1
        save_progress(progress)

        raw_passes = sum(1 for r in raw_samples if r["passed"])
        sc_passes = sum(1 for s in sc_samples if s["passed"])
        print(f"  | Raw: {raw_passes}/{i+1}  SC: {sc_passes}/{i+1}")

    # Write final JSONL files
    write_jsonl(SAMPLES_RAW, [{"task_id": s["task_id"], "completion": s["completion"]} for s in raw_samples])
    write_jsonl(SAMPLES_SC, [{"task_id": s["task_id"], "completion": s["completion"]} for s in sc_samples])

    # Summary
    raw_passes = sum(1 for r in raw_samples if r["passed"])
    sc_passes = sum(1 for s in sc_samples if s["passed"])
    summary = {
        "model": "Inthasap-Council-Trinity",
        "benchmark": "MBPP+",
        "source": "EvalPlus MBPP+ (378 problems)",
        "date": time.strftime("%Y-%m-%d"),
        "results": {
            "raw": {"pass": raw_passes, "total": total, "pass_at_1": round(raw_passes / total * 100, 1)},
            "scaffolded": {"pass": sc_passes, "total": total, "pass_at_1": round(sc_passes / total * 100, 1)},
        },
        "note": "Raw = base LLM output. Scaffolded = Council Trinity orchestration.",
        "files": {
            "samples_raw": "samples_mbpp_raw.jsonl",
            "samples_scaffolded": "samples_mbpp_scaffolded.jsonl",
        },
    }
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

    print("\n" + "=" * 60)
    print(f"Raw:         {raw_passes}/{total} = {round(raw_passes/total*100,1)}%")
    print(f"Scaffolded:  {sc_passes}/{total} = {round(sc_passes/total*100,1)}%")
    print(f"\nFiles written:")
    print(f"  {SAMPLES_RAW}")
    print(f"  {SAMPLES_SC}")
    print(f"  {SUMMARY_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
