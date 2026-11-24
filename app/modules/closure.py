"""补测包的实际新增覆盖登记与最终净覆盖关闭。

只统计落在作业区内、且落在本包范围内的新增像元；作业区外面积和重复报送的
重叠多计量都不计入净覆盖。净覆盖到齐（等于包内缺口像元数）后才关闭。
"""

from app.business import DomainIssue
from app.modules.gaps import (
    cell_area,
    clip,
    intersect_area,
    union_area,
    union_rects,
)


def normalize(values):
    """校验矩形列表；返回整数元组列表。"""
    if values is None:
        raise DomainIssue("COVERAGE_REQUIRED")
    if not isinstance(values, (list, tuple)) or not values:
        raise DomainIssue("COVERAGE_REQUIRED")
    rects = []
    for item in values:
        if isinstance(item, dict):
            try:
                item = [item[key] for key in ("x0", "y0", "x1", "y1")]
            except KeyError as error:
                raise DomainIssue("COVERAGE_INVALID") from error
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            raise DomainIssue("COVERAGE_INVALID")
        if any(type(value) is not int for value in item):
            raise DomainIssue("COVERAGE_INVALID")
        x0, y0, x1, y1 = item
        if x0 >= x1 or y0 >= y1:
            raise DomainIssue("COVERAGE_INVALID")
        rects.append((x0, y0, x1, y1))
    return rects


def _inside(rects, scope):
    pieces = []
    for rect in rects:
        clipped = clip(rect, scope)
        if clipped is not None:
            pieces.append(clipped)
    return union_area(pieces)


def evaluate(package, submissions, state="DISPATCHED"):
    """按累计报送的新增覆盖计算净覆盖与关闭状态。

    派发前的 PENDING 包不接收覆盖登记；已失效（SUPERSEDED）的包只保留
    历史账面，不再累计净覆盖。
    """
    region = tuple(package["region"])
    package_rects = [tuple(rect) for rect in package["rects"]]
    cells = package["cells"]
    flat = [rect for submission in submissions for rect in submission]
    inside_pieces = []
    for rect in flat:
        clipped = clip(rect, region)
        if clipped is None:
            continue
        for x0, y0, x1, y1 in package_rects:
            left, bottom = max(clipped[0], x0), max(clipped[1], y0)
            right, top = min(clipped[2], x1), min(clipped[3], y1)
            if left < right and bottom < top:
                inside_pieces.append((left, bottom, right, top))
    net = min(union_area(inside_pieces), cells)
    union = union_area(flat)
    outside = max(0, union - intersect_area(flat, region))
    in_region = max(0, intersect_area(flat, region) - union_area(inside_pieces))
    remaining = cells - net
    if state == "SUPERSEDED":
        status = "SUPERSEDED"
    elif net == cells:
        status = "CLOSED"
    elif state == "PENDING":
        status = "PENDING"
    else:
        status = "DISPATCHED"
    return {
        "cells": cells,
        "net_cells": net,
        "remaining_cells": remaining,
        "outside_cells": outside,
        "outside_package_cells": in_region,
        "duplicate_cells": max(0, cell_area(flat) - union),
        "covered_rects": [list(rect) for rect in union_rects(inside_pieces)],
        "complete": net == cells,
        "status": status,
    }
