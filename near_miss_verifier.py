# -*- coding: utf-8 -*-
"""
near_miss_verifier.py — ตรวจ prediction ที่ผ่าน train แล้วว่าสอดคล้อง invariant หรือไม่

ใช้ต่อท้าย arc_engine.solve_task() เมื่อ status=solved:
    from near_miss_verifier import check_invariants
    hints = check_invariants(task, predicted_output)
    if hints:
        # มีข้อสงสัย → ส่ง hint กลับ LLM เพื่อ patch
"""
from __future__ import annotations
from typing import Any
from enum import Enum
from dataclasses import dataclass, field

Grid = list[list[int]]


class FailureClass(str, Enum):
    DELTA_MAGNITUDE  = "DELTA_MAGNITUDE"
    COLOR_MAP        = "COLOR_MAP"
    ALIEN_COLOR      = "ALIEN_COLOR"
    BORDER           = "BORDER"
    COLOR_COUNT      = "COLOR_COUNT"
    POSITION         = "POSITION"       # reserved
    SYMMETRY         = "SYMMETRY"       # reserved
    OBJECT_COUNT     = "OBJECT_COUNT"    # reserved
    CONNECTIVITY     = "CONNECTIVITY"    # reserved
    UNKNOWN          = "UNKNOWN"


@dataclass
class FailureReport:
    failure_class: FailureClass
    confidence: float
    hints: list[str] = field(default_factory=list)


def _valid_grid(g: Any) -> bool:
    if not isinstance(g, list) or not g:
        return False
    if not all(isinstance(row, list) and row for row in g):
        return False
    return all(isinstance(c, int) for row in g for c in row)


# ── helpers ────────────────────────────────────────────────────────────────────

def _colors(grid: Grid) -> set[int]:
    return {c for row in grid for c in row}


def _color_map(inp: Grid, out: Grid) -> dict[int, set[int]]:
    """คืน mapping color_in → set(color_out) จาก grid คู่หนึ่ง"""
    mapping: dict[int, set[int]] = {}
    if len(inp) != len(out):
        return mapping
    for r, (ri, ro) in enumerate(zip(inp, out)):
        if len(ri) != len(ro):
            continue
        for ci, co in zip(ri, ro):
            mapping.setdefault(ci, set()).add(co)
    return mapping


def _consistent_color_map(train: list[dict]) -> dict[int, int] | None:
    """
    ถ้า train ทุกคู่มี color mapping input→output แบบ 1-to-1 สม่ำเสมอ
    คืน dict{in_color: out_color}  มิฉะนั้นคืน None
    """
    merged: dict[int, set[int]] = {}
    for pair in train:
        pair_map = _color_map(pair["input"], pair["output"])
        for k, vs in pair_map.items():
            merged.setdefault(k, set()).update(vs)
    # ตรวจว่า 1-to-1
    result: dict[int, int] = {}
    for k, vs in merged.items():
        if len(vs) != 1:
            return None
        result[k] = next(iter(vs))
    return result


def _border_colors(grid: Grid) -> set[int]:
    if not grid:
        return set()
    top = set(grid[0])
    bottom = set(grid[-1])
    left = {row[0] for row in grid}
    right = {row[-1] for row in grid}
    return top | bottom | left | right


# ── invariant checks (แต่ละตัวคืน FailureReport หรือ None) ─────────────────────

def _check_alien_color(train: list[dict], test_input: Grid, pred: Grid) -> FailureReport | None:
    """
    Invariant: สีใน prediction ต้องมาจาก union(train colors ทั้งหมด + test_input colors)
    เท่านั้น ถ้า pred มีสีที่ไม่เคยปรากฏในโจทย์เลย → alien color → น่าสงสัย
    """
    known_colors: set[int] = set()
    for pair in train:
        known_colors.update(_colors(pair["input"]))
        known_colors.update(_colors(pair["output"]))
    known_colors.update(_colors(test_input))

    train_out_colors: set[int] = set()
    for pair in train:
        train_out_colors.update(_colors(pair["output"]))

    pred_colors = _colors(pred)
    # alien = สีที่ไม่เคยอยู่ในโจทย์เลย (ไม่ใช่แค่ไม่อยู่ใน train output)
    alien = pred_colors - known_colors
    if alien:
        return FailureReport(
            failure_class=FailureClass.ALIEN_COLOR,
            confidence=0.90,
            hints=[
                f"ALIEN_COLOR: prediction มีสี {sorted(alien)} "
                f"ซึ่งไม่เคยปรากฏในโจทย์เลย (known colors: {sorted(known_colors)}) "
                f"— น่าจะเป็น hallucinated color"
            ],
        )
    # ถ้า pred มีสีจาก train_input/test_input ที่ไม่เคยอยู่ใน train_output
    # → เช็คว่า train inputs เคย "pass through" สีนั้นไหม
    # ถ้า train ไม่เคยมี input color ไหลเข้า output เลย → suspicious
    input_only_colors = known_colors - train_out_colors
    suspicious = pred_colors & input_only_colors
    if suspicious:
        # แต่ถ้า test_input มีสีเหล่านี้ด้วย → ไม่ flag (อาจ copy from input)
        test_colors = _colors(test_input)
        truly_suspicious = suspicious - test_colors
        if truly_suspicious:
            return FailureReport(
                failure_class=FailureClass.COLOR_MAP,
                confidence=0.70,
                hints=[
                    f"ALIEN_COLOR: prediction มีสี {sorted(truly_suspicious)} "
                    f"ซึ่งอยู่ใน train inputs เท่านั้น ไม่เคยปรากฏใน train outputs "
                    f"(train out colors: {sorted(train_out_colors)}) "
                    f"— น่าจะเป็น input color ที่ควร map เป็น color อื่น"
                ],
            )
    return None


def _check_input_color_preserved(train: list[dict], test_input: Grid, pred: Grid) -> FailureReport | None:
    """
    Invariant: ถ้า train แสดงว่า input colors ทุกตัวยังอยู่ใน output →
    ตรวจ test prediction ว่า input color หายไปไหม

    เปิดใช้เฉพาะเมื่อ train ทุกคู่ทำตาม pattern นี้
    """
    for pair in train:
        in_c = _colors(pair["input"])
        out_c = _colors(pair["output"])
        if not in_c.issubset(out_c):
            return None  # train ไม่ได้ preserve input colors ทุกสี — ข้าม

    # train preserve: ตรวจ test prediction
    test_in_colors = _colors(test_input)
    pred_colors = _colors(pred)
    missing = test_in_colors - pred_colors
    if missing:
        return FailureReport(
            failure_class=FailureClass.COLOR_MAP,
            confidence=0.70,
            hints=[
                f"MISSING_INPUT_COLOR: train แสดงว่า input colors ต้องอยู่ใน output "
                f"แต่ prediction ขาด {sorted(missing)} "
                f"(test_input มี: {sorted(test_in_colors)}, pred มี: {sorted(pred_colors)})"
            ],
        )
    return None


def _check_color_map(train: list[dict], test_input: Grid, pred: Grid) -> FailureReport | None:
    """
    Invariant: ถ้า train มี 1-to-1 color mapping input→output สม่ำเสมอ →
    ตรวจว่า test prediction ทำตาม mapping นั้น
    """
    cmap = _consistent_color_map(train)
    if cmap is None:
        return None  # mapping ไม่ consistent — ข้าม

    violations: list[str] = []
    if len(test_input) != len(pred):
        return None
    for r, (ri, rp) in enumerate(zip(test_input, pred)):
        if len(ri) != len(rp):
            return None
        for c, (ci, cp) in enumerate(zip(ri, rp)):
            expected = cmap.get(ci)
            if expected is not None and cp != expected:
                violations.append(f"row={r} col={c} input_color={ci} pred={cp} expected={expected}")
                if len(violations) >= 5:
                    violations.append("...")
                    break
        if len(violations) >= 6:
            break

    if violations:
        return FailureReport(
            failure_class=FailureClass.COLOR_MAP,
            confidence=0.80,
            hints=[
                f"COLOR_MAP_VIOLATION: train มี consistent color mapping {dict(sorted(cmap.items()))} "
                f"แต่ prediction ผิด {len([v for v in violations if v != '...'])} จุด: "
                + "; ".join(violations[:4])
            ],
        )
    return None


def _check_border_consistency(train: list[dict], pred: Grid) -> FailureReport | None:
    """
    Invariant: ถ้า train outputs มีขอบ (border) เป็น color เดียวกันเสมอ →
    ตรวจ prediction border
    """
    if not train:
        return None

    # เช็คว่า train ทุกคู่มี border color เดียวกัน
    border_colors_list = [_border_colors(pair["output"]) for pair in train]
    common_border = border_colors_list[0]
    for bc in border_colors_list[1:]:
        common_border = common_border & bc

    # ถ้า border เป็นสีเดียว (เช่น 0 ล้วน)
    single_border: set[int] = set()
    for pair in train:
        bc = _border_colors(pair["output"])
        if len(bc) == 1:
            single_border.update(bc)
        else:
            return None  # border ใน train ไม่ single-color — ข้าม

    if len(single_border) != 1:
        return None

    expected_border_color = next(iter(single_border))
    pred_border = _border_colors(pred)
    if expected_border_color not in pred_border or len(pred_border) > 1:
        alien_in_border = pred_border - {expected_border_color}
        if alien_in_border:
            return FailureReport(
                failure_class=FailureClass.BORDER,
                confidence=0.75,
                hints=[
                    f"BORDER_VIOLATION: train outputs มี border เป็น {expected_border_color} ล้วน "
                    f"แต่ prediction border มีสี {sorted(alien_in_border)} ปน"
                ],
            )
    return None


def _check_delta_magnitude(train: list[dict], test_input: Grid, pred: Grid) -> FailureReport | None:
    """
    Invariant: ถ้า train ทุกคู่มี sum(positive delta cells) เท่ากัน (เช่น +3 ทุกคู่)
    → ตรวจ pred ว่าทำตาม magnitude นั้น

    Catch: prediction ที่เปลี่ยนสีถูกทิศแต่น้อยเกินไป (เช่น +1 แทน +3)
    """
    def positive_delta(inp: Grid, out: Grid) -> int:
        cnt_in: dict[int, int] = {}
        cnt_out: dict[int, int] = {}
        for row in inp:
            for c in row:
                cnt_in[c] = cnt_in.get(c, 0) + 1
        for row in out:
            for c in row:
                cnt_out[c] = cnt_out.get(c, 0) + 1
        total = 0
        for k in set(cnt_in) | set(cnt_out):
            delta = cnt_out.get(k, 0) - cnt_in.get(k, 0)
            if delta > 0:
                total += delta
        return total

    magnitudes = [positive_delta(pair["input"], pair["output"]) for pair in train]
    if not magnitudes or len(set(magnitudes)) != 1:
        return None  # ไม่ consistent ข้ามข้าม

    expected_mag = magnitudes[0]
    if expected_mag == 0:
        return None

    pred_mag = positive_delta(test_input, pred)
    if pred_mag != expected_mag:
        return FailureReport(
            failure_class=FailureClass.DELTA_MAGNITUDE,
            confidence=0.85,
            hints=[
                f"DELTA_MAGNITUDE_VIOLATION: train ทุกคู่มี delta = +{expected_mag} cells "
                f"แต่ prediction มี delta = +{pred_mag} cells "
                f"(ขาด {expected_mag - pred_mag} cells จากที่ควรเปลี่ยนสี)"
            ],
        )
    return None


def _check_color_count_conservation(train: list[dict], test_input: Grid, pred: Grid) -> FailureReport | None:
    """
    Invariant: ถ้า train ทุกคู่มี count(color X, input) == count(color X, output) สำหรับทุก X
    → ตรวจ test prediction: count(color X, test_input) ควร == count(color X, pred)

    Catch: prediction ที่มีจำนวน cells ต่อสีผิดแม้สีจะครบชุด
    """
    def count_colors(grid: Grid) -> dict[int, int]:
        counts: dict[int, int] = {}
        for row in grid:
            for c in row:
                counts[c] = counts.get(c, 0) + 1
        return counts

    # ตรวจว่า train ทุกคู่มี count conservation
    for pair in train:
        ic = count_colors(pair["input"])
        oc = count_colors(pair["output"])
        all_colors = set(ic) | set(oc)
        for col in all_colors:
            if ic.get(col, 0) != oc.get(col, 0):
                return None  # train pair นี้ไม่ conservation — ข้าม invariant นี้

    # train ทุกคู่ conservation → ตรวจ test prediction
    test_counts = count_colors(test_input)
    pred_counts = count_colors(pred)
    all_test_colors = set(test_counts) | set(pred_counts)

    violations: list[str] = []
    for col in sorted(all_test_colors):
        tc = test_counts.get(col, 0)
        pc = pred_counts.get(col, 0)
        if tc != pc:
            violations.append(f"color {col}: test_input={tc} pred={pc} delta={pc-tc:+d}")

    if violations:
        return FailureReport(
            failure_class=FailureClass.COLOR_COUNT,
            confidence=0.65,
            hints=[
                f"COLOR_COUNT_VIOLATION: train แสดงว่า count(color) ใน input==output ทุกคู่ "
                f"แต่ prediction ผิด: " + "; ".join(violations[:5])
            ],
        )
    return None


# ── public API ─────────────────────────────────────────────────────────────────

def check_invariants(task: dict, predicted_output: Grid) -> list[FailureReport]:
    """
    ตรวจ predicted_output กับ invariants ที่สกัดจาก task["train"]
    คืน list ของ FailureReport (empty = ผ่านทุก invariant)

    ใช้งาน:
        reports = check_invariants(task, predicted_output)
        if reports:
            # มีข้อสงสัย → ส่ง hints กลับ LLM พร้อม instruction ให้แก้ edge case
    """
    if not predicted_output or not _valid_grid(predicted_output):
        return []
    train = task.get("train", [])
    test_input = task["test"][0]["input"]

    reports: list[FailureReport] = []

    # 1. alien color
    r = _check_alien_color(train, test_input, predicted_output)
    if r:
        reports.append(r)

    # 2. input color preserved
    r = _check_input_color_preserved(train, test_input, predicted_output)
    if r:
        reports.append(r)

    # 3. consistent color map
    r = _check_color_map(train, test_input, predicted_output)
    if r:
        reports.append(r)

    # 4. border consistency
    r = _check_border_consistency(train, predicted_output)
    if r:
        reports.append(r)

    # 5. color count conservation
    r = _check_color_count_conservation(train, test_input, predicted_output)
    if r:
        reports.append(r)

    # 6. delta magnitude consistency
    r = _check_delta_magnitude(train, test_input, predicted_output)
    if r:
        reports.append(r)

    return reports


def cell_accuracy(predicted: Grid, truth: Grid) -> float:
    """คืน accuracy ระดับ cell (0.0-1.0) — ใช้สำหรับ benchmark เท่านั้น (รู้ ground truth)"""
    if predicted is None or truth is None:
        return 0.0
    if len(predicted) != len(truth):
        return 0.0
    total = sum(len(r) for r in truth)
    if total == 0:
        return 0.0
    correct = sum(
        1 for r1, r2 in zip(predicted, truth)
        for c1, c2 in zip(r1, r2) if c1 == c2
    )
    return correct / total
