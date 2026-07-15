"""arc_perception.py — Perception Layer สำหรับ ARC-AGI Engine

หน้าที่: แปลง grid ดิบ (list-of-list ของ int 0-9) เป็น Scene ที่มนุษย์/สภาเข้าใจ
- แยก object ด้วย flood fill 4/8-neighbor
- คำนวณ properties: สี, ขนาด, bbox, centroid, normalized mask
- คำนวณ grid-level: ขนาด, สีพื้นหลัง (most common), สมมาตร, นับสี
- มุมมอง A: object-based · B: grid-as-whole · C: cell-wise mapping

หลัก: ใช้ stdlib ล้วน ไม่แตะ numpy จนกว่าจะวัดที่ P4 แล้ว
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# สีใน ARC-AGI: 0-9 โดย 0 มักแทนสีดำ/พื้นหลัง แต่ไม่เสมอ
ARC_COLORS = set(range(10))


@dataclass(frozen=True)
class ArcObject:
    """object หนึ่งก้อนที่ flood fill แยกได้จาก grid"""
    color: int
    cells: tuple[tuple[int, int], ...] = field(repr=False)
    size: int
    min_r: int
    min_c: int
    max_r: int
    max_c: int
    height: int
    width: int
    centroid: tuple[float, float]
    normalized_mask: frozenset[tuple[int, int]] = field(repr=False)
    shape_signature: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Scene:
    """ภาพรวมของ grid หนึ่งใบ"""
    grid: tuple[tuple[int, ...], ...]
    grid_size: tuple[int, int]  # (rows, cols)
    bg_color: int
    color_counts: dict[int, int]
    objects: tuple[ArcObject, ...]       # 4-neighbor
    objects_8: tuple[ArcObject, ...]     # 8-neighbor
    symmetries: dict[str, bool]
    view_a: dict[str, Any] = field(repr=False)
    view_b: dict[str, Any] = field(repr=False)
    view_c: dict[str, Any] = field(repr=False)


# -----------------------------------------------------------------------------
# ฟังก์ชันพื้นฐาน
# -----------------------------------------------------------------------------

def grid_size(grid: list[list[int]] | tuple[tuple[int, ...], ...]) -> tuple[int, int]:
    """คืน (rows, cols)"""
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    return rows, cols


def _to_immutable(grid: list[list[int]]) -> tuple[tuple[int, ...], ...]:
    """แปลง grid เป็น tuple-of-tuple เพื่อ safety/repr"""
    return tuple(tuple(row) for row in grid)


def color_counts(grid: list[list[int]]) -> dict[int, int]:
    """นับจำนวน cell แยกตามสี"""
    counter: Counter = Counter()
    for row in grid:
        counter.update(row)
    return dict(counter)


def background_color(grid: list[list[int]]) -> int:
    """สีพื้นหลัง = สีที่พบมากที่สุด (ตาม blueprint)"""
    counts = color_counts(grid)
    if not counts:
        return 0
    return max(counts, key=counts.get)  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# Flood fill
# -----------------------------------------------------------------------------

def _neighbors_4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def _neighbors_8(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                out.append((nr, nc))
    return out


def flood_fill(
    grid: list[list[int]] | tuple[tuple[int, ...], ...],
    start: tuple[int, int],
    connectivity: int = 4,
) -> set[tuple[int, int]]:
    """BFS flood fill จากจุด start เก็บ cell ที่มีสีเดียวกัน"""
    rows, cols = grid_size(grid)
    sr, sc = start
    target = grid[sr][sc]
    visited: set[tuple[int, int]] = set()
    stack = [start]
    neigh = _neighbors_4 if connectivity == 4 else _neighbors_8
    while stack:
        r, c = stack.pop()
        if (r, c) in visited:
            continue
        if grid[r][c] != target:
            continue
        visited.add((r, c))
        for nr, nc in neigh(r, c, rows, cols):
            if (nr, nc) not in visited:
                stack.append((nr, nc))
    return visited


def extract_objects(
    grid: list[list[int]],
    bg_color: int | None = None,
    connectivity: int = 4,
) -> list[ArcObject]:
    """แยก object ทั้งหมด (ยกเว้น bg_color) ด้วย flood fill"""
    rows, cols = grid_size(grid)
    if bg_color is None:
        bg_color = background_color(grid)
    seen: set[tuple[int, int]] = set()
    objects: list[ArcObject] = []
    for r in range(rows):
        for c in range(cols):
            if (r, c) in seen:
                continue
            color = grid[r][c]
            if color == bg_color:
                seen.add((r, c))
                continue
            cells = flood_fill(grid, (r, c), connectivity)
            seen.update(cells)
            # properties
            min_r = min(rr for rr, _ in cells)
            min_c = min(cc for _, cc in cells)
            max_r = max(rr for rr, _ in cells)
            max_c = max(cc for _, cc in cells)
            height = max_r - min_r + 1
            width = max_c - min_c + 1
            centroid = (
                round(sum(rr for rr, _ in cells) / len(cells), 2),
                round(sum(cc for _, cc in cells) / len(cells), 2),
            )
            norm = frozenset((rr - min_r, cc - min_c) for rr, cc in cells)
            shape_sig = tuple(sorted(norm))
            obj = ArcObject(
                color=color,
                cells=tuple(sorted(cells)),
                size=len(cells),
                min_r=min_r,
                min_c=min_c,
                max_r=max_r,
                max_c=max_c,
                height=height,
                width=width,
                centroid=centroid,
                normalized_mask=norm,
                shape_signature=shape_sig,
            )
            objects.append(obj)
    return objects


# -----------------------------------------------------------------------------
# สมมาตร
# -----------------------------------------------------------------------------

def _transpose(grid: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    rows, cols = grid_size(grid)
    return tuple(tuple(grid[r][c] for r in range(rows)) for c in range(cols))


def _rotate90(grid: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    rows, cols = grid_size(grid)
    if rows != cols:
        return ()  # ไม่สามารถหมุน 90 ได้ถ้าไม่ใช่จตุรัส
    return tuple(tuple(grid[rows - 1 - c][r] for c in range(cols)) for r in range(rows))


def _rotate180(grid: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    rows, cols = grid_size(grid)
    return tuple(tuple(grid[rows - 1 - r][cols - 1 - c] for c in range(cols)) for r in range(rows))


def _flip_vertical(grid: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    return grid[::-1]


def _flip_horizontal(grid: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(row[::-1]) for row in grid)


def _anti_transpose(grid: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    rows, cols = grid_size(grid)
    if rows != cols:
        return ()
    return tuple(tuple(grid[cols - 1 - c][rows - 1 - r] for c in range(cols)) for r in range(rows))


def compute_symmetries(grid: list[list[int]] | tuple[tuple[int, ...], ...]) -> dict[str, bool]:
    """ตรวจสมมาตรทั้งแนวตั้ง แนวนอน ทแยง หมุน 90/180/270"""
    g = _to_immutable(grid) if isinstance(grid, list) else grid
    rows, cols = grid_size(g)
    sym = {
        "vertical": False,
        "horizontal": False,
        "diagonal_main": False,
        "diagonal_anti": False,
        "rot90": False,
        "rot180": False,
        "rot270": False,
    }
    sym["vertical"] = g == _flip_vertical(g)
    sym["horizontal"] = g == _flip_horizontal(g)
    sym["rot180"] = g == _rotate180(g)
    if rows == cols:
        sym["diagonal_main"] = g == _transpose(g)
        sym["diagonal_anti"] = g == _anti_transpose(g)
        rot90 = _rotate90(g)
        sym["rot90"] = g == rot90
        sym["rot270"] = g == _rotate90(_rotate90(_rotate90(g))) if rot90 else False
    return sym


# -----------------------------------------------------------------------------
# Relations ระหว่าง object
# -----------------------------------------------------------------------------

def is_inside(inner: ArcObject, outer: ArcObject) -> bool:
    """inner อยู่ภายใน bbox ของ outer (ไม่ใช่ outer เอง)"""
    if inner is outer:
        return False
    return (
        inner.min_r >= outer.min_r
        and inner.min_c >= outer.min_c
        and inner.max_r <= outer.max_r
        and inner.max_c <= outer.max_c
    )


def is_adjacent(a: ArcObject, b: ArcObject, connectivity: int = 4) -> bool:
    """object a และ b มี cell ติดกัน (4 หรือ 8 neighbor)"""
    cells_a = set(a.cells)
    cells_b = set(b.cells)
    rows = max(a.max_r, b.max_r) + 1
    cols = max(a.max_c, b.max_c) + 1
    neigh = _neighbors_4 if connectivity == 4 else _neighbors_8
    for r, c in cells_a:
        for nr, nc in neigh(r, c, rows, cols):
            if (nr, nc) in cells_b:
                return True
    return False


def same_row(a: ArcObject, b: ArcObject) -> bool:
    """bbox ของ a และ b ทับแถวกัน"""
    return max(a.min_r, b.min_r) <= min(a.max_r, b.max_r)


def same_col(a: ArcObject, b: ArcObject) -> bool:
    """bbox ของ a และ b ทับคอลัมน์กัน"""
    return max(a.min_c, b.min_c) <= min(a.max_c, b.max_c)


def same_size(a: ArcObject, b: ArcObject) -> bool:
    return a.size == b.size


def same_shape(a: ArcObject, b: ArcObject) -> bool:
    """เปรียบเทียบ shape ด้วย normalized mask"""
    return a.normalized_mask == b.normalized_mask


def same_color(a: ArcObject, b: ArcObject) -> bool:
    return a.color == b.color


def compute_relations(objects: list[ArcObject]) -> list[dict[str, Any]]:
    """คำนวณ relations ทุกคู่ object"""
    rels = []
    for i, a in enumerate(objects):
        for b in objects[i + 1 :]:
            rel = {
                "a": a,
                "b": b,
                "inside": is_inside(a, b) or is_inside(b, a),
                "adjacent_4": is_adjacent(a, b, 4),
                "adjacent_8": is_adjacent(a, b, 8),
                "same_row": same_row(a, b),
                "same_col": same_col(a, b),
                "same_size": same_size(a, b),
                "same_shape": same_shape(a, b),
                "same_color": same_color(a, b),
            }
            rels.append(rel)
    return rels


# -----------------------------------------------------------------------------
# มุมมอง A/B/C
# -----------------------------------------------------------------------------

def view_a(objects: list[ArcObject]) -> dict[str, Any]:
    """มุมมอง A: object-based — รายละเอียด object และ relations"""
    return {
        "type": "object",
        "objects": list(objects),
        "relations": compute_relations(objects),
        "by_color": _group_by_color(objects),
    }


def view_b(scene: Scene) -> dict[str, Any]:
    """มุมมอง B: grid-as-whole — ดูภาพใหญ่ทั้งแผ่น"""
    return {
        "type": "grid",
        "grid_size": scene.grid_size,
        "bg_color": scene.bg_color,
        "color_counts": scene.color_counts,
        "symmetries": scene.symmetries,
    }


def view_c(scene: Scene) -> dict[str, Any]:
    """มุมมอง C: cell-wise mapping — สีต่อตำแหน่ง"""
    rows, cols = scene.grid_size
    pos_to_color = {(r, c): scene.grid[r][c] for r in range(rows) for c in range(cols)}
    color_to_pos: dict[int, list[tuple[int, int]]] = {}
    for r in range(rows):
        for c in range(cols):
            color = scene.grid[r][c]
            color_to_pos.setdefault(color, []).append((r, c))
    return {
        "type": "cell",
        "position_to_color": pos_to_color,
        "color_to_positions": color_to_pos,
    }


def _group_by_color(objects: list[ArcObject]) -> dict[int, list[ArcObject]]:
    by_color: dict[int, list[ArcObject]] = {}
    for obj in objects:
        by_color.setdefault(obj.color, []).append(obj)
    return by_color


# -----------------------------------------------------------------------------
# Scene หลัก
# -----------------------------------------------------------------------------

def analyze_scene(
    grid: list[list[int]],
    bg_color: int | None = None,
) -> Scene:
    """สร้าง Scene จาก grid หนึ่งใบ"""
    g = _to_immutable(grid)
    if bg_color is None:
        bg_color = background_color(grid)
    counts = color_counts(grid)
    objects4 = tuple(extract_objects(grid, bg_color, connectivity=4))
    objects8 = tuple(extract_objects(grid, bg_color, connectivity=8))
    syms = compute_symmetries(grid)
    scene = Scene(
        grid=g,
        grid_size=grid_size(grid),
        bg_color=bg_color,
        color_counts=counts,
        objects=objects4,
        objects_8=objects8,
        symmetries=syms,
        view_a={},
        view_b={},
        view_c={},
    )
    # คำนวณมุมมองหลังสร้าง dataclass เพื่อให้ view ถูกต้อง
    object.__setattr__(scene, "view_a", view_a(list(objects4)))
    object.__setattr__(scene, "view_b", view_b(scene))
    object.__setattr__(scene, "view_c", view_c(scene))
    return scene


# -----------------------------------------------------------------------------
# Helpers สำหรับโหลด ARC JSON
# -----------------------------------------------------------------------------

def load_arc_task(path: str) -> dict[str, Any]:
    """โหลดไฟล์ ARC-AGI JSON (train/test)"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def grid_to_str(grid: list[list[int]] | tuple[tuple[int, ...], ...]) -> str:
    """แปลง grid เป็น string สำหรับ print"""
    return "\n".join(" ".join(str(cell) for cell in row) for row in grid)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python arc_perception.py <arc-json-file>")
        sys.exit(1)
    task = load_arc_task(sys.argv[1])
    for idx, ex in enumerate(task["train"]):
        print(f"--- train {idx} ---")
        print("input:")
        print(grid_to_str(ex["input"]))
        print("output:")
        print(grid_to_str(ex["output"]))
        print()
    for idx, ex in enumerate(task["test"]):
        print(f"--- test {idx} ---")
        print("input:")
        print(grid_to_str(ex["input"]))
        print("output:")
        print(grid_to_str(ex["output"]))
        print()
