# -*- coding: utf-8 -*-
"""
core/applier.py — ตัวแก้ไฟล์จริงในคอมแบบมีเกราะ (สำหรับ "แก้โค้ดในที่")
หลักการ (ตามที่พ่อสั่ง):
  1) ก่อนทับไฟล์ไหน → สำรองไฟล์นั้นไว้ก่อนทุกครั้ง (backups/<โปรเจกต์_เวลา>/)
  2) ถ้าพัง → restore() ย้อนเอาของเดิมกลับมา (ไฟล์ใหม่ที่เพิ่งสร้าง → ลบทิ้ง)
เกราะ:
  - เขียนได้เฉพาะ "ใต้โฟลเดอร์เป้าหมายที่พ่อชี้" เท่านั้น (กัน .. หลุด)
  - เขตต้องห้าม (PROTECTED) — core/บ้าน/.env/.secrets — ปฏิเสธเด็ดขาด แม้พ่อชี้มาก็ไม่แก้
"""
import os
import re
import json
import shutil
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(_BASE, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


def _norm(p):
    return os.path.normcase(os.path.realpath(p))


# ── เขตต้องห้าม: ห้ามแตะเด็ดขาด แม้พ่อจะชี้มา ──
PROTECTED = [_norm(p) for p in [
    os.path.join(_BASE, "core"),
    os.path.join(_BASE, "council_web.py"),
    os.path.join(_BASE, "council_lab.py"),
    os.path.join(_BASE, "council_config.json"),
    os.path.join(_BASE, ".env"),
    os.path.join(_BASE, "chats"),
    os.path.join(_BASE, "backups"),
    r"C:\Inthasap_Guard\Sovereign_Bridge_V5_22",          # ระบบบ้าน
    os.path.join(os.path.expanduser("~"), ".secrets"),     # ความลับ
]]


class GuardError(Exception):
    pass


def _is_protected(path):
    n = _norm(path)
    return any(n == p or n.startswith(p + os.sep) for p in PROTECTED)


def _slug(s):
    return (re.sub(r"[^0-9A-Za-z฀-๿]+", "_", (s or "proj").strip())[:40].strip("_") or "proj")


def validate_target(target_root):
    """ตรวจโฟลเดอร์เป้าหมายว่าแก้ได้ไหม — คืน path ที่ normalize แล้ว"""
    if not target_root or not os.path.isdir(target_root):
        raise GuardError("ไม่พบโฟลเดอร์เป้าหมาย")
    if _is_protected(target_root):
        raise GuardError("โฟลเดอร์นี้เป็นเขตต้องห้าม/ระบบหลัก — แก้ไม่ได้")
    return _norm(target_root)


def apply_files(src_dir, target_root):
    """ก๊อปไฟล์จาก src_dir (workspace) → target_root จริง โดยสำรองของเดิมก่อนทับทุกไฟล์
    คืน manifest (ใช้ย้อนคืน)"""
    troot = validate_target(target_root)
    # หาไฟล์ทุกระดับ (recursive) ไม่ใช่แค่ top-level
    files = []
    for root, dirs, fnames in os.walk(src_dir):
        for fn in fnames:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, src_dir)
            files.append(rel)
    if not files:
        raise GuardError("ไม่มีไฟล์จะส่ง")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(BACKUP_DIR, _slug(os.path.basename(troot)) + "_" + stamp)
    os.makedirs(bdir, exist_ok=True)

    applied = []
    warnings = []
    for f in files:
        dest = os.path.join(troot, f)
        ndest = _norm(dest)
        if not (ndest == troot or ndest.startswith(troot + os.sep)):
            raise GuardError(f"ไฟล์ {f} หลุดนอกโฟลเดอร์เป้าหมาย — ปฏิเสธ")
        if _is_protected(dest):
            raise GuardError(f"ไฟล์ {f} ตกในเขตต้องห้าม — ปฏิเสธ")
        # สร้างโฟลเดอร์ย่อยใน backup ด้วย
        dest_dir = os.path.dirname(os.path.join(bdir, f))
        os.makedirs(dest_dir, exist_ok=True)
        existed = os.path.exists(dest)
        if existed:
            # เก็บของเดิมเป็น backup เสมอ — เพื่อให้กู้คืนได้ถ้าของใหม่เสีย
            shutil.copy2(dest, os.path.join(bdir, f))         # 1) สำรองของเดิมก่อน
            # เช็คคุณภาพ: ถ้าไฟล์ใหม่เล็กกว่าเดิมมาก (<30%) ให้เตือน
            old_size = os.path.getsize(dest)
            new_size = os.path.getsize(os.path.join(src_dir, f))
            if old_size > 0 and new_size < old_size * 0.3:
                warnings.append(f"⚠️ {f}: ไฟล์ใหม่เล็กกว่าเดิมมาก ({new_size} vs {old_size} bytes) — ตรวจสอบว่าไม่ใช่การทำลาย")
        # สร้างโฟลเดอร์ย่อยในปลายทางด้วย
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(os.path.join(src_dir, f), dest)          # 2) ทับด้วยของใหม่
        applied.append({"file": f, "existed": existed, "backup": os.path.join(bdir, f) if existed else None})

    manifest = {"target": troot, "backup_dir": bdir, "time": stamp, "applied": applied, "warnings": warnings}
    with open(os.path.join(bdir, "_manifest.json"), "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)
    return manifest


def restore(backup_id):
    """ย้อนคืน: ไฟล์เดิม→ทับกลับจากแบ็กอัพ, ไฟล์ใหม่ที่เพิ่งสร้าง→ลบทิ้ง"""
    bdir = backup_id if os.path.isabs(backup_id) else os.path.join(BACKUP_DIR, backup_id)
    mpath = os.path.join(bdir, "_manifest.json")
    if not os.path.exists(mpath):
        raise GuardError("ไม่พบแบ็กอัพนี้")
    m = json.load(open(mpath, encoding="utf-8"))
    troot = m["target"]
    restored, removed = [], []
    for item in m["applied"]:
        dest = os.path.join(troot, item["file"])
        if _is_protected(dest):
            continue
        if item["existed"]:
            bkp = os.path.join(bdir, item["file"])
            if os.path.exists(bkp):
                shutil.copy2(bkp, dest)
                restored.append(item["file"])
        elif os.path.exists(dest):
            os.remove(dest)                                   # ไฟล์ใหม่ → ลบ
            removed.append(item["file"])
    return {"target": troot, "restored": restored, "removed": removed}


def list_backups(limit=20):
    out = []
    for d in sorted(os.listdir(BACKUP_DIR), reverse=True)[:limit]:
        mp = os.path.join(BACKUP_DIR, d, "_manifest.json")
        if os.path.exists(mp):
            try:
                m = json.load(open(mp, encoding="utf-8"))
                out.append({"id": d, "target": m.get("target"),
                            "time": m.get("time"), "count": len(m.get("applied", []))})
            except Exception:
                pass
    return out


def restore_file(rel_path, target_root=None):
    """กู้คืนไฟล์เดียวจาก backup ล่าสุดที่มีไฟล์นั้น — หากไฟล์เสียหายจะได้ของเดิมกลับมา"""
    rel_norm = rel_path.replace("\\", "/")
    for d in sorted(os.listdir(BACKUP_DIR), reverse=True):
        mp = os.path.join(BACKUP_DIR, d, "_manifest.json")
        if not os.path.exists(mp):
            continue
        try:
            m = json.load(open(mp, encoding="utf-8"))
        except Exception:
            continue
        for item in m.get("applied", []):
            if item.get("file", "").replace("\\", "/") != rel_norm:
                continue
            if not item.get("existed"):
                continue
            bkp = os.path.join(BACKUP_DIR, d, rel_norm)
            if not os.path.exists(bkp):
                continue
            troot = target_root or m.get("target")
            if not troot:
                continue
            dest = os.path.join(troot, rel_norm)
            if _is_protected(dest):
                raise GuardError(f"ไฟล์ {rel_norm} ตกในเขตต้องห้าม — ปฏิเสธ")
            shutil.copy2(bkp, dest)
            return {"file": rel_norm, "restored_from": d, "target": troot}
    return None
