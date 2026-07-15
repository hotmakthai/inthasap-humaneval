"""arc_diff.py — Diff Analyzer สรุป input↔output"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from arc_dsl import RULES
from arc_perception import extract_objects

Grid = list[list[int]]


@dataclass
class Invariant:
    name: str
    value: Any


@dataclass
class Change:
    name: str
    value: Any


@dataclass
class DiffReport:
    invariants: list[Invariant] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    size_relation: tuple[int | float, int | float] | None = None
    color_map: dict[int, int] | None = None
    bg_color_in: int | None = None
    bg_color_out: int | None = None
    object_count_in: int | None = None
    object_count_out: int | None = None
    detected_transforms: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return len(self.invariants) == 0


def _size(grid: Grid) -> tuple[int, int]:
    return len(grid), len(grid[0]) if grid else 0


def _obj_count(grid: Grid, bg: int | None) -> int:
    return len(extract_objects(grid, bg_color=bg, connectivity=4))


def _grids_equal(a: Grid, b: Grid) -> bool:
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        if ra != rb:
            return False
    return True


def _color_map(examples: list[dict]) -> dict[int, int] | None:
    mapping: dict[int, set[int]] = {}
    for ex in examples:
        inp, out = ex["input"], ex["output"]
        if _size(inp) != _size(out):
            return None
        for r in range(len(inp)):
            for c in range(len(inp[0])):
                mapping.setdefault(inp[r][c], set()).add(out[r][c])
    for oc in mapping.values():
        if len(oc) > 1:
            return None
    return {ic: next(iter(oc)) for ic, oc in mapping.items()}


def _size_relation(examples: list[dict]) -> tuple[int, int] | None:
    ratios = []
    for ex in examples:
        h_in, w_in = _size(ex["input"])
        h_out, w_out = _size(ex["output"])
        if h_in == 0 or w_in == 0 or h_out % h_in or w_out % w_in:
            return None
        ratios.append((h_out // h_in, w_out // w_in))
    if not ratios:
        return None
    first = ratios[0]
    return first if all(r == first for r in ratios) else None


def _detect_transforms(examples: list[dict]) -> list[str]:
    candidates = [
        "identity", "rotate90", "rotate180", "rotate270",
        "flip_vertical", "flip_horizontal", "transpose", "invert_colors",
    ]
    for f in (2, 3):
        candidates.append(("scale_uniform", {"factor": f}))
        candidates.append(("scale_tile", {"factor": f}))
    found = []
    for cand in candidates:
        name, params = cand if isinstance(cand, tuple) else (cand, {})
        fn = RULES[name]
        ok = True
        for ex in examples:
            try:
                got = fn(ex["input"], **params)
            except Exception:
                ok = False
                break
            if not _grids_equal(got, ex["output"]):
                ok = False
                break
        if ok:
            found.append(f"{name}:{params}" if params else name)
    return found


def analyze_diff(task: dict) -> DiffReport:
    report = DiffReport()
    examples = task.get("train", [])
    if not examples:
        return report

    sr = _size_relation(examples)
    if sr:
        report.size_relation = sr
        if sr == (1, 1):
            report.invariants.append(Invariant("grid_size", (1, 1)))
        else:
            report.changes.append(Change("scale", sr))

    cm = _color_map(examples)
    if cm:
        report.color_map = cm
        if all(v == k for k, v in cm.items()):
            report.invariants.append(Invariant("color_mapping_identity", True))
        else:
            report.changes.append(Change("color_map", cm))

    bgs_in = {ex["input"][0][0] for ex in examples}
    bgs_out = {ex["output"][0][0] for ex in examples}
    if len(bgs_in) == 1:
        report.bg_color_in = bgs_in.pop()
    if len(bgs_out) == 1:
        report.bg_color_out = bgs_out.pop()

    if report.bg_color_in is not None and report.bg_color_in == report.bg_color_out:
        report.invariants.append(Invariant("bg_color", report.bg_color_in))
    elif report.bg_color_in is not None and report.bg_color_out is not None:
        report.changes.append(Change("bg_color", (report.bg_color_in, report.bg_color_out)))

    if report.bg_color_in is not None:
        obj_in = _obj_count(examples[0]["input"], report.bg_color_in)
        ok = all(_obj_count(ex["input"], report.bg_color_in) == obj_in for ex in examples)
        if ok:
            report.object_count_in = obj_in
    if report.bg_color_out is not None:
        obj_out = _obj_count(examples[0]["output"], report.bg_color_out)
        ok = all(_obj_count(ex["output"], report.bg_color_out) == obj_out for ex in examples)
        if ok:
            report.object_count_out = obj_out
    if report.object_count_in is not None and report.object_count_in == report.object_count_out:
        report.invariants.append(Invariant("object_count", report.object_count_in))
    elif report.object_count_in is not None and report.object_count_out is not None:
        report.changes.append(Change("object_count", (report.object_count_in, report.object_count_out)))

    report.detected_transforms = _detect_transforms(examples)
    for t in report.detected_transforms:
        report.invariants.append(Invariant("detected_transform", t))

    return report
