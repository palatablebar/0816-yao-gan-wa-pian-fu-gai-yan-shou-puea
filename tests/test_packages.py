"""补测包的边界、来源版本、派发对平与关闭谱系。"""

import json

import pytest

import app.config as config
from app.business import DomainIssue
from app.modules.dispatch import assess
from app.modules.gaps import cell_area, union_area
from app.modules.pipeline import run
from app.review.service import execute
from conftest import csv_data


def payload(rows):
    return csv_data(rows)


def packages_of(report, case=None):
    items = report.get("packages") or []
    return [item for item in items if case is None or item["case"] == case]


def gap_rects(report, case):
    item = next(c for c in report["cases"] if c["case"] == case)
    return item["measure"]["evidence"]["gap_cells"]


def test_same_group_adjacent_gaps_form_one_package():
    # 作业区 4x4 只盖住中间一个像元，缺口是一圈，按边相邻应只出一个包。
    data = payload(
        [
            ["R", "01", "region", "0", "0", "4", "4", "15", "作业区"],
            ["A", "01", "tile", "1", "1", "2", "2", "0", "中心"],
        ]
    )
    report = run(data)
    items = packages_of(report, "01")
    assert len(items) == 1
    assert items[0]["cells"] == 15
    assert len(items[0]["rects"]) > 1


def test_disjoint_gaps_in_same_group_are_separate_packages():
    # 中间一条竖带被覆盖，左右两块缺口不连边，应各自成包。
    data = payload(
        [
            ["R", "01", "region", "0", "0", "10", "10", "100", "作业区"],
            ["A", "01", "tile", "4", "0", "6", "10", "0", "竖带"],
        ]
    )
    report = run(data)
    items = packages_of(report, "01")
    assert len(items) == 2
    assert sorted(item["cells"] for item in items) == [40, 40]


def test_cross_group_adjacent_gaps_are_not_merged():
    # 两个业务组的缺口沿 x=4 相邻，但签收责任不同，不能并包。
    data = payload(
        [
            ["RA", "A", "region", "0", "0", "4", "4", "16", "左组"],
            ["TA", "A", "tile", "0", "0", "3", "4", "0", "左组缺最后一列"],
            ["RB", "B", "region", "4", "0", "8", "4", "16", "右组"],
            ["TB", "B", "tile", "5", "0", "8", "4", "0", "右组缺第一列"],
        ]
    )
    report = run(data)
    left = packages_of(report, "A")
    right = packages_of(report, "B")
    assert len(left) == 1 and len(right) == 1
    assert left[0]["bounds"][2] == 4 and right[0]["bounds"][0] == 4
    assert left[0]["id"] != right[0]["id"]


def test_every_uncovered_pixel_enters_exactly_one_package(dirty):
    report = run(dirty)
    rects = [tuple(r) for item in report["packages"] for r in item["rects"]]
    gaps = sum(
        case["measure"]["evidence"]["gap_cells"]
        for case in report["cases"]
        if case.get("measure")
    )
    assert cell_area(rects) == gaps
    assert union_area(rects) == gaps


def test_outside_region_and_overlap_do_not_enter_packages():
    # 瓦片越出作业区、互相重叠，补测只取作业区内真正没盖到的像元。
    data = payload(
        [
            ["R", "01", "region", "0", "0", "4", "4", "16", "作业区"],
            ["A", "01", "tile", "0", "0", "6", "2", "0", "越界并重叠"],
            ["B", "01", "tile", "0", "0", "2", "6", "0", "越界并重叠"],
        ]
    )
    report = run(data)
    items = packages_of(report, "01")
    assert sum(item["cells"] for item in items) == gap_rects(report, "01") == 4
    assert all(
        item["region"] == [0, 0, 4, 4]
        and all(0 <= r[0] and r[2] <= 4 and 0 <= r[1] and r[3] <= 4 for r in item["rects"])
        for item in items
    )


def test_packages_carry_source_and_version(store, clean):
    run_record = execute(store, clean)
    manifest = run_record["report"]["manifest"]
    for item in store.run_packages(run_record["id"]):
        assert item["source"] == manifest["sha256"]
        assert item["version"] == manifest["version"]


def test_isolated_row_ledger_reconciles_and_allows_dispatch():
    data = payload(
        [
            ["R", "01", "region", "0", "0", "2", "2", "4", "作业区"],
            ["A", "01", "tile", "0", "0", "1", "2", "0", "半幅"],
            ["BAD KEY", "01", "tile", "0", "0", "1", "1", "0", "坏键"],
        ]
    )
    report = run(data)
    check = report["dispatch"]["checks"]["isolated"]
    assert check["ok"] and check["value"] == check["expected"] == 1
    # 隔离行已逐项对平，剩余采信行的缺口仍可派发。
    assert report["dispatch"]["dispatchable"]


def test_isolation_ledger_break_blocks_dispatch(clean):
    report = run(clean)
    report["intake"]["isolation"] = [{"line": 2, "reason": "BAD_IDENTIFIER"}]
    report["intake"]["rejected"] = 2
    report["intake"]["reasons"] = {"BAD_IDENTIFIER": 1}
    verdict = assess(report)
    assert "isolated" in verdict["blocked_by"]


def test_tampered_source_blocks_dispatch(clean):
    report = run(clean)
    report["manifest"]["sha256"] = "0" * 64
    verdict = assess(report)
    assert "source" in verdict["blocked_by"]


def test_gap_mismatch_blocks_dispatch(clean):
    report = run(clean)
    report["packages"][0]["cells"] += 1
    verdict = assess(report)
    assert "gap" in verdict["blocked_by"]


def test_accepted_mismatch_blocks_dispatch(clean):
    report = run(clean)
    report["intake"]["accepted"] += 1
    verdict = assess(report)
    assert "accepted" in verdict["blocked_by"]


def test_duplicate_record_keys_block_accepted(clean):
    report = run(clean)
    report["cases"][0]["records"] = report["cases"][0]["records"] * 2
    assert "accepted" in assess(report)["blocked_by"]


def test_failed_case_blocks_dispatch(dirty):
    report = run(dirty)
    assert "gap" in report["dispatch"]["blocked_by"]


def test_clean_batch_is_dispatchable(clean):
    verdict = run(clean)["dispatch"]
    assert verdict["dispatchable"] and verdict["blocked_by"] == []
    assert verdict["packages"] == 1 and verdict["cells"] == 5


def test_balance_stage_reports_dispatch_and_packages(clean, dirty):
    preview = run(dirty, 5)
    assert "dispatch" in preview and "packages" in preview
    assert preview["packages"] and preview["dispatch"]["blocked_by"]
    assert run(clean, 5)["dispatch"]["dispatchable"]


def test_sample_packages_follow_group_gaps(dirty):
    report = run(dirty)
    assert [(item["case"], item["bounds"], item["cells"]) for item in report["packages"]] == [
        ("0002", [0, 0, 1, 5], 5),
        ("0004", [4, 0, 6, 6], 12),
    ]


def test_overlapping_packages_are_blocked(clean):
    report = run(clean)
    extra = dict(report["packages"][0])
    extra["id"] = "another"
    extra["rects"] = [[0, 0, 2, 5]]
    report["packages"].append(extra)
    verdict = assess(report)
    assert "gap" in verdict["blocked_by"]


def test_package_outside_region_is_blocked(clean):
    report = run(clean)
    report["packages"][0]["rects"] = [[0, 0, 1, 5], [-1, 0, 0, 5]]
    assert "gap" in assess(report)["blocked_by"]


def test_release_still_requires_balance(clean):
    assert run(clean)["balance"]["releasable"] is True


def test_dispatch_marks_packages_and_blocks_dirty(store, clean, dirty):
    blocked = execute(store, dirty)
    with pytest.raises(DomainIssue, match="DISPATCH_BLOCKED"):
        store.dispatch(blocked["id"], "2026-01-01T00:00:00Z")
    allowed = execute(store, clean)
    items = store.dispatch(allowed["id"], "2026-01-01T00:00:00Z")
    assert items and all(item["status"] == "DISPATCHED" for item in items)


def test_same_batch_rerun_adds_no_packages_or_coverage(store, clean):
    first = execute(store, clean)
    package = store.run_packages(first["id"])[0]
    store.dispatch(first["id"], "2026-01-01T00:00:00Z")
    store.submit_coverage(package["id"], [(0, 0, 1, 2)], "2026-01-01T00:01:00Z")
    before = store.package(package["id"])
    again = execute(store, clean)
    assert again["id"] == first["id"]
    assert store.package(package["id"]) == before
    assert len(store.list_packages()) == 1


def test_different_source_with_same_gap_scope_reuses_package(store, clean):
    # 重放行让来源字节不同，但缺口范围完全相同：应复用同一个包，不重复出车。
    replay = clean.rstrip(b"\r\n") + (
        b"\r\n000202,0002,tile,1,0,7,5,0,\xe5\xa4\x8d\xe6\xa0\xb8\xe5\xba\x95\xe7\xa8\xbf\r\n"
    )
    first = execute(store, clean)
    second = execute(store, replay)
    assert second["id"] != first["id"]
    first_ids = [item["id"] for item in store.run_packages(first["id"])]
    second_ids = [item["id"] for item in store.run_packages(second["id"])]
    assert first_ids == second_ids
    assert len(store.list_packages()) == 1
    detail = store.package(first_ids[0])
    assert set(detail["sources"]) == {
        first["report"]["manifest"]["sha256"],
        second["report"]["manifest"]["sha256"],
    }
    assert set(detail["runs"]) == {first["id"], second["id"]}


def test_rerun_does_not_reopen_closed_package(store, clean):
    replay = clean.rstrip(b"\r\n") + (
        b"\r\n000202,0002,tile,1,0,7,5,0,\xe5\xa4\x8d\xe6\xa0\xb8\xe5\xba\x95\xe7\xa8\xbf\r\n"
    )
    second = execute(store, replay)
    package = store.run_packages(second["id"])[0]
    store.dispatch(second["id"], "2026-01-01T00:00:00Z")
    store.submit_coverage(package["id"], [(0, 0, 1, 5)], "2026-01-01T00:01:00Z")
    again = execute(store, clean)
    kept = store.package(package["id"])
    assert kept["status"] == "CLOSED" and kept["net_cells"] == 5
    assert [item["status"] for item in store.run_packages(again["id"])] == ["CLOSED"]


def test_closure_waits_for_full_net_coverage(store, clean):
    run_record = execute(store, clean)
    package = store.run_packages(run_record["id"])[0]
    store.dispatch(run_record["id"], "2026-01-01T00:00:00Z")
    partial = store.submit_coverage(package["id"], [(0, 0, 1, 2)], "2026-01-01T00:01:00Z")
    assert partial["status"] == "DISPATCHED"
    assert (partial["net_cells"], partial["remaining_cells"]) == (2, 3)
    done = store.submit_coverage(package["id"], [(0, 2, 1, 5)], "2026-01-01T00:02:00Z")
    assert done["status"] == "CLOSED"
    assert (done["net_cells"], done["remaining_cells"]) == (5, 0)
    assert done["closed"]


def test_replayed_coverage_does_not_close_early(store, clean):
    run_record = execute(store, clean)
    package = store.run_packages(run_record["id"])[0]
    store.dispatch(run_record["id"], "2026-01-01T00:00:00Z")
    for tick in range(3):
        item = store.submit_coverage(
            package["id"], [(0, 0, 1, 3)], f"2026-01-01T00:0{tick}:00Z"
        )
    assert item["status"] == "DISPATCHED"
    assert item["net_cells"] == 3
    assert item["evaluation"]["duplicate_cells"] == 6


def test_outside_area_does_not_contribute_to_closure(store, clean):
    run_record = execute(store, clean)
    package = store.run_packages(run_record["id"])[0]
    store.dispatch(run_record["id"], "2026-01-01T00:00:00Z")
    item = store.submit_coverage(
        package["id"], [(0, 0, 1, 3), (-2, 0, 0, 5)], "2026-01-01T00:01:00Z"
    )
    assert item["status"] == "DISPATCHED"
    assert item["evaluation"]["outside_cells"] == 10
    assert item["net_cells"] == 3


def test_closed_package_rejects_more_coverage(store, clean):
    run_record = execute(store, clean)
    package = store.run_packages(run_record["id"])[0]
    store.dispatch(run_record["id"], "2026-01-01T00:00:00Z")
    store.submit_coverage(package["id"], [(0, 0, 1, 5)], "2026-01-01T00:01:00Z")
    with pytest.raises(DomainIssue, match="PACKAGE_CLOSED"):
        store.submit_coverage(package["id"], [(0, 0, 1, 5)], "2026-01-01T00:02:00Z")


def test_pending_package_cannot_take_coverage(store, clean):
    run_record = execute(store, clean)
    package = store.run_packages(run_record["id"])[0]
    with pytest.raises(DomainIssue, match="PACKAGE_NOT_DISPATCHED"):
        store.submit_coverage(package["id"], [(0, 0, 1, 5)], "2026-01-01T00:00:00Z")


def test_rule_update_supersedes_old_scope_and_keeps_dispatched(
    store, clean, monkeypatch
):
    monkeypatch.setattr(config, "RULE_VERSION", "1.0.0")
    old = execute(store, clean)
    old_package = store.run_packages(old["id"])[0]
    store.dispatch(old["id"], "2026-01-01T00:00:00Z")
    store.submit_coverage(old_package["id"], [(0, 0, 1, 2)], "2026-01-01T00:01:00Z")

    monkeypatch.setattr(config, "RULE_VERSION", "2.0.0")
    fresh = execute(store, clean)
    assert fresh["id"] != old["id"]
    new_package = store.run_packages(fresh["id"])[0]

    superseded = store.package(old_package["id"])
    assert superseded["status"] == "SUPERSEDED"
    assert superseded["superseded_by"] == [new_package["id"]]
    assert superseded["submissions"]  # 历史覆盖报送仍然保留
    assert new_package["supersedes"] == [old_package["id"]]

    with pytest.raises(DomainIssue, match="PACKAGE_SUPERSEDED"):
        store.submit_coverage(old_package["id"], [(0, 2, 1, 5)], "2026-01-01T00:02:00Z")


def test_closed_package_keeps_history_after_rule_update(store, clean, monkeypatch):
    monkeypatch.setattr(config, "RULE_VERSION", "1.0.0")
    old = execute(store, clean)
    package = store.run_packages(old["id"])[0]
    store.dispatch(old["id"], "2026-01-01T00:00:00Z")
    store.submit_coverage(package["id"], [(0, 0, 1, 5)], "2026-01-01T00:01:00Z")
    monkeypatch.setattr(config, "RULE_VERSION", "2.0.0")
    execute(store, clean)
    kept = store.package(package["id"])
    assert kept["status"] == "CLOSED"
    assert kept["net_cells"] == 5 and kept["closed"]


def test_old_scope_disappearing_in_new_version_is_superseded(store, monkeypatch):
    monkeypatch.setattr(config, "RULE_VERSION", "1.0.0")
    gapped = payload(
        [
            ["R", "01", "region", "0", "0", "4", "4", "16", "作业区"],
            ["T", "01", "tile", "0", "0", "2", "4", "0", "半幅"],
        ]
    )
    old = execute(store, gapped)
    package = store.run_packages(old["id"])[0]
    store.dispatch(old["id"], "2026-01-01T00:00:00Z")

    monkeypatch.setattr(config, "RULE_VERSION", "2.0.0")
    filled = payload(
        [
            ["R", "01", "region", "0", "0", "4", "4", "16", "作业区"],
            ["T", "01", "tile", "0", "0", "4", "4", "0", "整幅"],
        ]
    )
    fresh = execute(store, filled)
    assert store.run_packages(fresh["id"]) == []
    assert store.package(package["id"])["status"] == "SUPERSEDED"


def test_http_package_lifecycle(client):
    run_record = client.post("/api/runs", data={"sample": "clean"}).json
    blocked = client.post("/api/runs", data={"sample": "dirty"}).json
    assert client.post(f"/api/runs/{blocked['id']}/dispatch").status_code == 409
    dispatched = client.post(f"/api/runs/{run_record['id']}/dispatch")
    assert dispatched.status_code == 200
    package = dispatched.json["items"][0]
    assert package["status"] == "DISPATCHED"

    response = client.post(
        f"/api/packages/{package['id']}/coverage", json={"rects": [[0, 0, 1, 5]]}
    )
    assert response.status_code == 200
    assert response.json["status"] == "CLOSED"
    listed = client.get("/api/packages").json["items"]
    assert package["id"] in [item["id"] for item in listed]
    assert client.get("/api/runs/" + run_record["id"] + "/packages").json["items"][0][
        "status"
    ] == "CLOSED"


def test_http_coverage_validation(client):
    run_record = client.post("/api/runs", data={"sample": "clean"}).json
    package = client.post(f"/api/runs/{run_record['id']}/dispatch").json["items"][0]
    assert (
        client.post(
            f"/api/packages/{package['id']}/coverage", json={"rects": []}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/packages/{package['id']}/coverage", json={"rects": [[1, 1, 0, 2]]}
        ).status_code
        == 422
    )
    assert client.get("/api/packages/unknown").status_code == 404
    assert client.get("/api/packages?status=BOGUS").status_code == 404


def test_evidence_keeps_dispatch_packages_and_closure(client):
    run_record = client.post("/api/runs", data={"sample": "clean"}).json
    package = client.post(f"/api/runs/{run_record['id']}/dispatch").json["items"][0]
    client.post(f"/api/packages/{package['id']}/coverage", json={"rects": [[0, 0, 1, 5]]})
    packet = client.get(f"/api/runs/{run_record['id']}/evidence").json
    assert packet["dispatch"]["dispatchable"] is True
    assert packet["packages"][0]["status"] == "CLOSED"
    assert packet["packages"][0]["net_cells"] == 5
    assert packet["packages"][0]["source"] == packet["manifest"]["sha256"]
