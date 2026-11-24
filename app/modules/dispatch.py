"""派发前的逐项对平：来源、采信、隔离和缺口。

补测包只有在四项全部相符时才可派发，任一项不符都会给出阻止原因。
"""

from hashlib import sha256

from app.modules.gaps import bounds, disjoint, inside

CHECKS = (
    ("source", "来源"),
    ("accepted", "采信"),
    ("isolated", "隔离"),
    ("gap", "缺口"),
)


def _check(key, label, ok, value, expected, **extra):
    return dict(key=key, label=label, ok=ok, value=value, expected=expected, **extra)


def source_check(report):
    intake = report.get("intake") or {}
    manifest = report.get("manifest") or {}
    accounted = (
        intake.get("accepted", 0)
        + intake.get("rejected", 0)
        + intake.get("blank", 0)
        + intake.get("repeated", 0)
    )
    rows_ok = accounted == intake.get("input") and intake.get("input", 0) > 0
    digest = manifest.get("sha256") or ""
    version = manifest.get("version") or ""
    run_id = manifest.get("run_id") or ""
    digest_ok = (
        len(digest) == 64
        and int(manifest.get("bytes", 0)) > 0
        and sha256(f"{version}:{digest}".encode()).hexdigest() == run_id
    )
    return _check(
        "source",
        "来源",
        bool(manifest) and rows_ok and digest_ok,
        intake.get("input", 0),
        accounted,
        manifest=bool(manifest),
        rows_ok=rows_ok,
        digest_ok=digest_ok,
        sha256=digest,
        version=version,
        bytes=manifest.get("bytes", 0),
    )


def accepted_check(report):
    intake = report.get("intake") or {}
    cases = report.get("cases") or []
    observed = sum(len(case.get("records") or []) for case in cases)
    keys = [key for case in cases for key in case.get("records") or []]
    unique = len(set(keys)) == len(keys)
    return _check(
        "accepted",
        "采信",
        observed == intake.get("accepted") and unique,
        observed,
        intake.get("accepted", 0),
        unique=unique,
    )


def isolated_check(report):
    intake = report.get("intake") or {}
    isolation = intake.get("isolation") or []
    reasons = intake.get("reasons") or {}
    listed = len(isolation)
    counted = sum(reasons.values())
    lines = [row.get("line") for row in isolation]
    well_formed = (
        all(isinstance(line, int) and line > 1 for line in lines)
        and len(set(lines)) == len(lines)
    )
    rejected = intake.get("rejected", 0)
    ledger = listed == rejected and counted == rejected and well_formed
    return _check(
        "isolated",
        "隔离",
        ledger,
        listed,
        rejected,
        reasons=counted,
        unique_lines=well_formed,
    )


def _case_gap(case):
    measure = case.get("measure")
    packages = case.get("packages") or []
    region = (case.get("prep") or {}).get("details", {}).get("region")
    covered = measure["value"] if measure else None
    gap = measure["evidence"].get("gap_cells") if measure else None
    region_cells = (case.get("prep") or {}).get("details", {}).get("region_cells")
    cells = sum(package["cells"] for package in packages)
    ok = (
        measure is not None
        and region is not None
        and gap is not None
        and cells == gap
        and all(inside([tuple(r) for r in p["rects"]], tuple(region)) for p in packages)
        and all(disjoint([tuple(r) for r in p["rects"]]) for p in packages)
        and covered + gap == region_cells
    )
    return {
        "case": case["case"],
        "status": case.get("status"),
        "region_cells": region_cells,
        "covered": covered,
        "gap": gap,
        "package_cells": cells,
        "packages": len(packages),
        "bounds": [bounds([tuple(r) for r in p["rects"]]) for p in packages],
        "ok": ok,
    }


def gap_check(report):
    cases = report.get("cases") or []
    details = [_case_gap(case) for case in cases]
    packages = report.get("packages") or []
    expected = sum(item["gap"] or 0 for item in details)
    total = sum(item["package_cells"] for item in details)
    ids = [package["id"] for package in packages]
    unique = len(set(ids)) == len(ids)
    every_measured = bool(cases) and all(
        item["covered"] is not None for item in details
    )
    ok = (
        every_measured
        and all(item["ok"] for item in details)
        and unique
        and total == expected
        and len(packages) == sum(item["packages"] for item in details)
    )
    return _check(
        "gap",
        "缺口",
        ok,
        total,
        expected,
        packages=len(packages),
        cases=details,
        failed_cases=[item["case"] for item in details if item["covered"] is None],
        unique_packages=unique,
        measured=sum(1 for item in details if item["covered"] is not None),
    )


def assess(report):
    """四项逐项对平；任一不符即阻止派发。"""
    checks = {
        "source": source_check(report),
        "accepted": accepted_check(report),
        "isolated": isolated_check(report),
        "gap": gap_check(report),
    }
    blocked = [key for key, _ in CHECKS if not checks[key]["ok"]]
    packages = report.get("packages") or []
    return {
        "checks": checks,
        "blocked_by": blocked,
        "balanced": not blocked,
        "dispatchable": not blocked,
        "packages": len(packages),
        "cells": sum(package["cells"] for package in packages),
    }
