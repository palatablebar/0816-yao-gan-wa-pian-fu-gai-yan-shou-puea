"""补测分包的几何性质：未覆盖像元逐格入包、区内、互不重叠。"""

import random

from app.modules.gaps import (
    build_packages,
    cell_area,
    components,
    disjoint,
    inside,
    uncovered_rects,
    union_area,
)


def cells_of(region, boxes):
    rx0, ry0, rx1, ry1 = region
    covered = set()
    for x0, y0, x1, y1 in boxes:
        for x in range(x0, x1):
            for y in range(y0, y1):
                covered.add((x, y))
    return {(x, y) for x in range(rx0, rx1) for y in range(ry0, ry1)} - covered


def test_uncovered_rects_are_disjoint_and_inside():
    random.seed(11)
    for _ in range(200):
        region = (0, 0, random.randint(1, 8), random.randint(1, 8))
        boxes = []
        for _ in range(random.randint(0, 4)):
            x0 = random.randint(-3, region[2] + 2)
            y0 = random.randint(-3, region[3] + 2)
            boxes.append(
                (x0, y0, random.randint(x0 + 1, region[2] + 3),
                 random.randint(y0 + 1, region[3] + 3))
            )
        rects = uncovered_rects(region, boxes)
        pixels = cells_of(region, boxes)
        assert cell_area(rects) == len(pixels)
        assert union_area(rects) == len(pixels)
        assert disjoint(rects) and inside(rects, region)


def test_components_match_pixel_connectivity():
    random.seed(23)
    for _ in range(200):
        region = (0, 0, random.randint(1, 8), random.randint(1, 8))
        boxes = []
        for _ in range(random.randint(0, 4)):
            x0 = random.randint(-2, region[2] + 1)
            y0 = random.randint(-2, region[3] + 1)
            boxes.append(
                (x0, y0, random.randint(x0 + 1, region[2] + 2),
                 random.randint(y0 + 1, region[3] + 2))
            )
        parts = components(uncovered_rects(region, boxes))
        pixels = cells_of(region, boxes)
        seen, islands = set(), 0
        for cell in pixels:
            if cell in seen:
                continue
            islands += 1
            stack = [cell]
            seen.add(cell)
            while stack:
                x, y = stack.pop()
                for neighbour in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if neighbour in pixels and neighbour not in seen:
                        seen.add(neighbour)
                        stack.append(neighbour)
        assert len(parts) == islands


def test_packages_cover_gap_exactly():
    region = (0, 0, 6, 4)
    boxes = [(-2, 0, 2, 2), (2, 2, 9, 6)]
    packages = build_packages("01", region, boxes, "1.0.0", "source")
    assert sum(item["cells"] for item in packages) == 12
    assert all(item["region"] == list(region) for item in packages)
    again = build_packages("01", region, boxes, "1.0.0", "source")
    assert [item["id"] for item in packages] == [item["id"] for item in again]
