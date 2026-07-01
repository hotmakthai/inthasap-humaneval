# -*- coding: utf-8 -*-
"""
core/checkpoint.py — Undo/Checkpoint (CORE #4)
snapshot โฟลเดอร์ workspace ก่อนแก้แต่ละรอบ → กู้คืนได้
เก็บแยกที่ Council_Lab/checkpoints/ (ไม่ปนใน workspace ที่สภาเขียนโค้ด)
"""
import os
import shutil
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Council_Lab/
WORKSPACE = os.path.join(_BASE, "workspace")
CKPT_DIR  = os.path.join(_BASE, "checkpoints")
KEEP_LAST = 10                      # เก็บล่าสุดกี่ checkpoint (เกินลบเก่าสุด)

os.makedirs(CKPT_DIR, exist_ok=True)


def snapshot(label: str = "") -> str:
    """copy workspace → checkpoints/<ts>_<label>/ คืน path ที่เก็บ"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    safe = "".join(c for c in label if c.isalnum() or c in "_-")[:30]
    dst = os.path.join(CKPT_DIR, f"{ts}_{safe}" if safe else ts)
    if os.path.isdir(WORKSPACE):
        shutil.copytree(WORKSPACE, dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        os.makedirs(dst, exist_ok=True)
    _prune()
    return dst


def list_checkpoints():
    items = sorted([d for d in os.listdir(CKPT_DIR)
                    if os.path.isdir(os.path.join(CKPT_DIR, d))])
    return items


def restore(name: str) -> bool:
    """กู้ checkpoint กลับเข้า workspace (ของเดิมใน workspace ถูกแทนที่)"""
    src = os.path.join(CKPT_DIR, name)
    if not os.path.isdir(src):
        return False
    if os.path.isdir(WORKSPACE):
        shutil.rmtree(WORKSPACE, ignore_errors=True)
    shutil.copytree(src, WORKSPACE)
    return True


def restore_latest() -> str:
    items = list_checkpoints()
    if not items:
        return ""
    restore(items[-1])
    return items[-1]


def _prune():
    items = list_checkpoints()
    for old in items[:-KEEP_LAST]:
        shutil.rmtree(os.path.join(CKPT_DIR, old), ignore_errors=True)
