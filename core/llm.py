# -*- coding: utf-8 -*-
"""
core/llm.py — ตัวเรียกโมเดล + Fallback Chain (ชั้น A: กันล่ม)
  DeepSeek → Gemini → Claude (ตาม council_config.json)
  - error/timeout/quota → สลับ tier ถัดไปอัตโนมัติ
  - 429 retry 1 ครั้งก่อน escalate
  - per-tier timeout / budget cap (soft เตือน, hard หยุดขึ้น tier แพง)
  - tier ไหนไม่มี key → ข้าม
อ่านกุญแจจาก Council_Lab/.env เท่านั้น (ไม่ผูกกับบ้าน)
"""
import os
import re
import json as _json
import time
from datetime import datetime
import requests

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Council_Lab/
_ENV_LOADED = False
_CONFIG = None
_BUDGET_WARNED = False

_PLACEHOLDERS = {"", "YOUR_API_KEY_HERE", "YOUR_ANTHROPIC_API_KEY", "PUT_KEY_HERE"}


def _load_env():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    envp = os.path.join(_BASE, ".env")
    if os.path.exists(envp):
        for line in open(envp, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                v = re.sub(r"\s+#.*$", "", v).strip()
                os.environ.setdefault(k.strip(), v.strip())
    _ENV_LOADED = True


def _config():
    global _CONFIG
    if _CONFIG is None:
        try:
            _CONFIG = _json.load(open(os.path.join(_BASE, "council_config.json"), encoding="utf-8"))
        except Exception:
            _CONFIG = {}
    return _CONFIG


def _key_for(tier):
    _load_env()
    name = {"deepseek": "DEEPSEEK_API_KEY", "gemini": "GEMINI_API_KEY",
            "claude": "ANTHROPIC_API_KEY"}.get(tier, "")
    val = os.getenv(name, "").split()[0] if os.getenv(name, "").strip() else ""
    return "" if val in _PLACEHOLDERS else val


# ── Budget (ติดตามค่าใช้จ่ายรายวัน — คิดตาม token จริง + peak/valley) ──
# DeepSeek pricing (USD per 1M tokens):
#   deepseek-chat: input $0.27, output $1.10 (cache miss)
#   cache hit input: $0.07
#   Peak hours (mid-July+): 2x all prices
#   Peak UTC: 1:00–4:00 AM, 6:00–10:00 AM
# Gemini pricing (free tier — $0):
#   gemini-3.5-flash / gemini-3.1-flash-lite: free
#   gemini-3.1-pro-preview: free (preview)
# Claude pricing (USD per 1M tokens):
#   claude-3-5-sonnet: input $3.00, output $15.00

_PRICING = {
    "deepseek": {"input": 0.27, "output": 1.10, "cache_input": 0.07},
    "gemini":  {"input": 0.0,  "output": 0.0,  "cache_input": 0.0},
    "claude":  {"input": 3.00, "output": 15.00, "cache_input": 3.00},
}

# Peak hours in UTC (hour ranges, 0-based)
_PEAK_HOURS_UTC = [(1, 4), (6, 10)]  # 1:00–4:00 AM, 6:00–10:00 AM UTC


def _is_peak_hour():
    """เช็คว่าเวลาปัจจุบัน (UTC) อยู่ใน peak hours หรือไม่"""
    h = datetime.utcnow().hour
    return any(start <= h < end for start, end in _PEAK_HOURS_UTC)


def _budget_file():
    d = os.path.join(_BASE, "logs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"budget_{datetime.now():%Y%m%d}.txt")


def _today_cost():
    try:
        return float(open(_budget_file(), encoding="utf-8").read().strip() or 0)
    except Exception:
        return 0.0


def _calc_cost(tier, input_tokens, output_tokens, cached_tokens=0):
    """คำนวณค่าใช้จ่ายจริงตาม token — คืน (cost_usd, is_peak)"""
    p = _PRICING.get(tier, {"input": 0, "output": 0, "cache_input": 0})
    non_cached_input = max(0, input_tokens - cached_tokens)
    cost = (non_cached_input * p["input"] + cached_tokens * p["cache_input"] + output_tokens * p["output"]) / 1_000_000
    peak = _is_peak_hour()
    if peak and tier == "deepseek":
        cost *= 2.0  # DeepSeek peak pricing = 2x (เริ่มกลางกรกฎาคม)
    return round(cost, 6), peak


def _add_cost(tier, input_tokens=0, output_tokens=0, cached_tokens=0):
    """เพิ่มค่าใช้จ่ายตาม token จริง — คืน total รวม"""
    cost, peak = _calc_cost(tier, input_tokens, output_tokens, cached_tokens)
    if cost == 0:
        # fallback: ใช้ estimate เดิมถ้าไม่มี token info
        cost = _config().get("cost_estimate_per_call_usd", {}).get(tier, 0.0)
    total = _today_cost() + cost
    try:
        open(_budget_file(), "w", encoding="utf-8").write(str(total))
    except Exception:
        pass
    return total


# ── ตัวเรียกแต่ละ provider — คืน (text, ok) ──
def _post_json(url, headers, payload, timeout):
    body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return requests.post(url, headers=headers, data=body, timeout=timeout)


def _call_deepseek(system, user, max_tokens, timeout):
    mdl = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    key = _key_for("deepseek")
    if not key:
        return ("(ไม่มี DEEPSEEK_API_KEY)", False, mdl)
    url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    try:
        r = _post_json(url,
                       {"Authorization": "Bearer " + key, "Content-Type": "application/json; charset=utf-8"},
                       {"model": mdl, "messages": [{"role": "system", "content": system},
                                                   {"role": "user", "content": user}],
                        "temperature": 0.3, "max_tokens": max_tokens}, timeout)
        if r.status_code == 429:
            return ("429", False, mdl)
        if r.status_code != 200:
            return (f"(DeepSeek HTTP {r.status_code})", False, mdl)
        resp = r.json()
        text = resp["choices"][0]["message"]["content"].strip()
        usage = resp.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        cached = usage.get("prompt_cache_hit_tokens", 0)
        cost, peak = _calc_cost("deepseek", in_tok, out_tok, cached)
        return (text, True, mdl, {"tier": "deepseek", "input_tokens": in_tok, "output_tokens": out_tok, "cached_tokens": cached, "cost_usd": cost, "peak": peak})
    except Exception as e:
        return (f"(DeepSeek error: {str(e)[:80]})", False, mdl)


def _gemini_request(models, system, user, max_tokens, timeout, images=None):
    """ยิง Gemini โดยลองทีละรุ่นใน models จนกว่าจะสำเร็จ (กัน 503/429 ของรุ่นใดรุ่นหนึ่ง)"""
    key = _key_for("gemini")
    if not key:
        return ("(ไม่มี GEMINI_API_KEY)", False, "gemini")
    last = "(Gemini error)"
    last_mdl = next((m for m in models if m), "gemini")
    for mdl in [m for m in models if m]:
        last_mdl = mdl
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent?key={key}"
        try:
            parts = [{"text": system + "\n\n" + user}]
            if images:
                for img in images:
                    parts.append({"inline_data": {"mime_type": img.get("mime", "image/png"),
                                                          "data": img.get("data", "")}})
            r = _post_json(url, {"Content-Type": "application/json; charset=utf-8"},
                           {"contents": [{"parts": parts}],
                            "generationConfig": {"maxOutputTokens": max_tokens}}, timeout)
            if r.status_code == 200:
                resp = r.json()
                cand = resp.get("candidates", [{}])[0]
                txt = cand.get("content", {}).get("parts", [{}])[0].get("text", "")
                if txt:
                    usage = resp.get("usageMetadata", {})
                    in_tok = usage.get("promptTokenCount", 0)
                    out_tok = usage.get("candidatesTokenCount", 0)
                    cost, peak = _calc_cost("gemini", in_tok, out_tok, 0)
                    return (txt.strip(), True, mdl, {"tier": "gemini", "input_tokens": in_tok, "output_tokens": out_tok, "cached_tokens": 0, "cost_usd": cost, "peak": peak})
                last = f"(Gemini {mdl} ตอบว่าง)"
            else:
                last = f"(Gemini {mdl} HTTP {r.status_code})"   # 503/429 → ลองรุ่นถัดไป
        except Exception as e:
            last = f"(Gemini {mdl} error: {str(e)[:60]})"
    return (last, False, last_mdl)


def _call_gemini(system, user, max_tokens, timeout, images=None):
    """Gemini — ลอง 3 รุ่น: 3.5-flash → 3.1-pro-preview → 3.1-flash-lite ถ้าหลุดทั้งหมดตกไป deepseek
    ถ้ามี GEMINI_MODEL ใน .env จะ override รุ่นหลักจาก config"""
    cfg = _config()
    primary = os.getenv("GEMINI_MODEL", "").strip()
    if primary:
        return _gemini_request([primary,
                                cfg.get("gemini_fallback", "gemini-3.1-pro-preview"),
                                cfg.get("gemini_fallback2", "gemini-3.1-flash-lite")],
                               system, user, max_tokens, timeout, images)
    return _gemini_request([cfg.get("gemini_model", "gemini-3.5-flash"),
                            cfg.get("gemini_fallback", "gemini-3.1-pro-preview"),
                            cfg.get("gemini_fallback2", "gemini-3.1-flash-lite")],
                           system, user, max_tokens, timeout, images)


def _call_claude(system, user, max_tokens, timeout, images=None):
    mdl = _config().get("claude_model", "claude-3-5-sonnet-20241022")
    key = _key_for("claude")
    if not key:
        return ("(ยังไม่ได้ใส่ ANTHROPIC_API_KEY — ข้าม Claude tier)", False, mdl)
    try:
        content = [{"type": "text", "text": user}]
        if images:
            for img in images:
                content.append({"type": "image", "source": {
                    "type": "base64",
                    "media_type": img.get("mime", "image/png"),
                    "data": img.get("data", "")}})
        r = _post_json("https://api.anthropic.com/v1/messages",
                       {"x-api-key": key, "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json; charset=utf-8"},
                       {"model": mdl, "max_tokens": max_tokens, "system": system,
                        "messages": [{"role": "user", "content": content}]}, timeout)
        if r.status_code == 429:
            return ("429", False, mdl)
        if r.status_code != 200:
            return (f"(Claude HTTP {r.status_code})", False, mdl)
        resp = r.json()
        text = resp["content"][0]["text"].strip()
        usage = resp.get("usage", {})
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        cost, peak = _calc_cost("claude", in_tok, out_tok, 0)
        return (text, True, mdl, {"tier": "claude", "input_tokens": in_tok, "output_tokens": out_tok, "cached_tokens": 0, "cost_usd": cost, "peak": peak})
    except Exception as e:
        return (f"(Claude error: {str(e)[:80]})", False, mdl)


_CALLERS = {"deepseek": _call_deepseek, "gemini": _call_gemini, "claude": _call_claude}


def _call_one(tier, system, user, max_tokens, images=None):
    """เรียก tier เดียว + retry 429 ครั้งเดียว — คืน (text, ok, model, usage_info)"""
    cfg = _config()
    timeout = cfg.get("timeouts_sec", {}).get(tier, 60)
    fn = _CALLERS.get(tier)
    if not fn:
        return (f"(ไม่รู้จัก tier {tier})", False, tier, None)
    kwargs = {"images": images} if images and tier in ("gemini", "claude") else {}
    result = fn(system, user, max_tokens, timeout, **kwargs)
    # ผลลัพธ์: (text, ok, model) หรือ (text, ok, model, usage_info)
    if len(result) == 4:
        text, ok, model, usage = result
    else:
        text, ok, model = result
        usage = None
    if (not ok) and text == "429" and cfg.get("retry_on_429", 1):
        time.sleep(2)
        result = fn(system, user, max_tokens, timeout, **kwargs)
        if len(result) == 4:
            text, ok, model, usage = result
        else:
            text, ok, model = result
            usage = None
    if text == "429":
        text = f"({tier} quota เต็ม 429)"
    return (text, ok, model, usage)


_COST_CALLBACK = None

def set_cost_callback(fn):
    """Register a callback fn(tier, model) called after each successful AI call"""
    global _COST_CALLBACK
    _COST_CALLBACK = fn


def call_with_fallback(system_prompt, user_prompt, max_tokens=3000):
    """ชั้น A: ไล่ tier ตามโหมด — คืน (text, tier_used, note)"""
    global _BUDGET_WARNED
    cfg = _config()
    mode = cfg.get("model_mode", "auto")
    tiers = cfg.get("tier_order", ["deepseek", "gemini", "claude"]) if mode == "auto" else [mode]

    soft = cfg.get("budget", {}).get("soft_cap_usd", 9e9)
    hard = cfg.get("budget", {}).get("hard_cap_usd", 9e9)
    note = ""
    last = ""
    for tier in tiers:
        if not _key_for(tier):
            continue                                   # ไม่มี key → ข้าม
        # งบ hard cap → ห้ามขึ้น tier แพงกว่า deepseek
        if _today_cost() >= hard and tier != "deepseek":
            note = f"⚠️ ถึง hard cap ${hard} — ข้าม {tier}"
            continue
        text, ok, model, usage = _call_one(tier, system_prompt, user_prompt, max_tokens)
        if ok:
            if usage:
                total = _add_cost(tier, usage.get("input_tokens", 0),
                                  usage.get("output_tokens", 0),
                                  usage.get("cached_tokens", 0))
            else:
                total = _add_cost(tier)
            if _COST_CALLBACK:
                try: _COST_CALLBACK(tier, model, usage)
                except: pass
            if total >= soft and not _BUDGET_WARNED:
                note = f"⚠️ ใช้งบวันนี้ ${total:.2f} เกิน soft cap ${soft}"
                _BUDGET_WARNED = True
            return (text, model, note)
        last = text
    return (f"(ทุก tier ล้มเหลว: {last})", "none", note)


def call_tier(preferred_tier, system_prompt, user_prompt, max_tokens=3000, images=None):
    """บังคับใช้ tier ที่ระบุก่อน (เช่น reviewer = claude) — ถ้าไม่มี key/error
    ค่อยไล่ tier ที่เหลือตามลำดับ คืน (text, tier_used, note)"""
    cfg = _config()
    rest = [t for t in cfg.get("tier_order", ["deepseek", "gemini", "claude"])
            if t != preferred_tier]
    chain = [preferred_tier] + rest
    hard = cfg.get("budget", {}).get("hard_cap_usd", 9e9)
    last = ""
    for tier in chain:
        if not _key_for(tier):
            continue
        if _today_cost() >= hard and tier != "deepseek":
            continue
        text, ok, model, usage = _call_one(tier, system_prompt, user_prompt, max_tokens, images)
        if ok:
            if usage:
                _add_cost(tier, usage.get("input_tokens", 0),
                          usage.get("output_tokens", 0),
                          usage.get("cached_tokens", 0))
            else:
                _add_cost(tier)
            if _COST_CALLBACK:
                try: _COST_CALLBACK(tier, model, usage)
                except: pass
            return (text, model, "")
        last = text
    return (f"(ทุก tier ล้มเหลว: {last})", "none", "")


def available_tiers():
    return [t for t in _config().get("tier_order", []) if _key_for(t)]


# ── คงไว้เพื่อความเข้ากันได้เดิม ──
def call(model, system_prompt, user_prompt, max_tokens=3000, temperature=0.3):
    text, _, _ = call_with_fallback(system_prompt, user_prompt, max_tokens)
    return text
