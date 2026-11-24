"""把作业区内的未覆盖像元拆成可派发的补测包。

未覆盖像元只在作业区内计算；作业区外和覆盖交叠多计的面积不会进入补测范围。
同一个业务组内按边相邻的未覆盖像元连成一个包，不同业务组即使几何相邻也分开。
"""

from hashlib import sha256
import json

from app.business import intervals, subtract


def _edges(region, boxes):
    """只在作业区内取 X 断点，越界的瓦片边界先夹到区内。"""
    rx0, _, rx1, _ = region
    values = {rx0, rx1}
    for x0, _, x1, _ in boxes:
        values.add(min(max(x0, rx0), rx1))
        values.add(min(max(x1, rx0), rx1))
    return sorted(values)


def uncovered_rects(region, boxes):
    """返回作业区内未覆盖像元的矩形分解，每个像元最多出现一次。"""
    rx0, ry0, rx1, ry1 = region
    rects = []
    edges = _edges(region, boxes)
    for left, right in zip(edges, edges[1:]):
        covered = intervals(
            (max(ry0, y0), min(ry1, y1))
            for x0, y0, x1, y1 in boxes
            if x0 <= left and right <= x1
        )
        for y0, y1 in subtract([(ry0, ry1)], covered):
            rects.append((left, y0, right, y1))
    return coalesce(rects)


def coalesce(rects):
    """把同一条带上的相邻矩形合并，像元数保持不变。"""
    merged = []
    for rect in sorted(rects):
        if merged:
            last = merged[-1]
            if last[1] == rect[1] and last[3] == rect[3] and last[2] == rect[0]:
                merged[-1] = (last[0], last[1], rect[2], last[3])
                continue
        merged.append(rect)
    merged.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    result = []
    for rect in merged:
        if result:
            last = result[-1]
            if last[0] == rect[0] and last[2] == rect[2] and last[3] == rect[1]:
                result[-1] = (last[0], last[1], last[2], rect[3])
                continue
        result.append(rect)
    return sorted(result)


def _overlap_length(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def _link(lefts, rights, rects, begin, end, union):
    lefts = sorted(lefts, key=lambda i: (rects[i][begin], rects[i][end]))
    rights = sorted(rights, key=lambda i: (rects[i][begin], rects[i][end]))
    i = j = 0
    while i < len(lefts) and j < len(rights):
        a, b = lefts[i], rights[j]
        a0, a1 = rects[a][begin], rects[a][end]
        b0, b1 = rects[b][begin], rects[b][end]
        if a1 <= b0:
            i += 1
        elif b1 <= a0:
            j += 1
        else:
            union(a, b)
            if a1 <= b1:
                i += 1
            else:
                j += 1


def components(rects):
    """按边相邻（四邻域）求连通分量。角接触不算相邻。"""
    rects = list(rects)
    count = len(rects)
    parent = list(range(count))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    starts_x, ends_x = {}, {}
    starts_y, ends_y = {}, {}
    for index, (x0, y0, x1, y1) in enumerate(rects):
        starts_x.setdefault(x0, []).append(index)
        ends_x.setdefault(x1, []).append(index)
        starts_y.setdefault(y0, []).append(index)
        ends_y.setdefault(y1, []).append(index)

    for boundary, rights in starts_x.items():
        _link(ends_x.get(boundary, []), rights, rects, 1, 3, union)
    for boundary, rights in starts_y.items():
        _link(ends_y.get(boundary, []), rights, rects, 0, 2, union)

    grouped = {}
    for index in range(count):
        grouped.setdefault(find(index), []).append(rects[index])
    return [coalesce(members) for members in grouped.values()]


def cell_area(rects):
    return sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects)


def bounds(rects):
    return [
        min(r[0] for r in rects),
        min(r[1] for r in rects),
        max(r[2] for r in rects),
        max(r[3] for r in rects),
    ]


def package_id(case, version, region, rects):
    """同一业务组、同一规则版本下的同一缺口范围只有一个包，避免重复出车。"""
    payload = json.dumps(
        {
            "case": case,
            "version": version,
            "region": list(region),
            "rects": [list(r) for r in rects],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(payload.encode()).hexdigest()[:16]


def build_packages(case, region, boxes, version, source):
    """为一个业务组生成补测包；作业区外和覆盖多计的面积不进入结果。"""
    rects = uncovered_rects(region, boxes)
    return [
        {
            "id": package_id(case, version, region, component),
            "case": case,
            "version": version,
            "source": source,
            "cells": cell_area(component),
            "bounds": bounds(component),
            "rects": [list(rect) for rect in component],
            "region": list(region),
        }
        for component in sorted(components(rects), key=bounds)
    ]


def clip(rect, region):
    x0, y0, x1, y1 = rect
    rx0, ry0, rx1, ry1 = region
    left, bottom = max(x0, rx0), max(y0, ry0)
    right, top = min(x1, rx1), min(y1, ry1)
    if left < right and bottom < top:
        return (left, bottom, right, top)
    return None


def union_area(rects):
    """矩形并集面积，用来发现重复计入的像元。"""
    if not rects:
        return 0
    xs = sorted({x for x0, _, x1, _ in rects for x in (x0, x1)})
    total = 0
    for left, right in zip(xs, xs[1:]):
        spans = intervals(
            (y0, y1) for x0, y0, x1, y1 in rects if x0 <= left and right <= x1
        )
        total += (right - left) * sum(y1 - y0 for y0, y1 in spans)
    return total


def union_rects(rects):
    """矩形并集的非重叠分解，重复报送不会重复计面积。"""
    if not rects:
        return []
    xs = sorted({x for x0, _, x1, _ in rects for x in (x0, x1)})
    pieces = []
    for left, right in zip(xs, xs[1:]):
        spans = intervals(
            (y0, y1) for x0, y0, x1, y1 in rects if x0 <= left and right <= x1
        )
        pieces.extend((left, y0, right, y1) for y0, y1 in spans)
    return coalesce(pieces)


def intersect_area(rects, region):
    """矩形与作业区交集的并集面积。"""
    pieces = [clip(rect, region) for rect in rects]
    return union_area([piece for piece in pieces if piece is not None])


def outside_area(rects, region):
    """矩形并集落在作业区外的面积。"""
    return union_area(rects) - intersect_area(rects, region)


def disjoint(rects):
    return union_area(rects) == cell_area(rects)


def inside(rects, region):
    rx0, ry0, rx1, ry1 = region
    return all(
        rx0 <= x0 and ry0 <= y0 and x1 <= rx1 and y1 <= ry1
        for x0, y0, x1, y1 in rects
    )
