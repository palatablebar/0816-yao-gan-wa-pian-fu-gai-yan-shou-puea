import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue
from app.modules import closure as closure_rules

SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT
);"""

PACKAGES = """CREATE TABLE IF NOT EXISTS packages (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, case_key TEXT NOT NULL,
    version TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
    sources TEXT NOT NULL DEFAULT '[]', cells INTEGER NOT NULL, region TEXT NOT NULL,
    rects TEXT NOT NULL, bounds TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
    created TEXT NOT NULL, dispatched TEXT, closed TEXT,
    net_cells INTEGER NOT NULL DEFAULT 0,
    remaining_cells INTEGER NOT NULL DEFAULT 0,
    supersedes TEXT NOT NULL DEFAULT '[]', superseded_by TEXT
);"""

LINKS = """CREATE TABLE IF NOT EXISTS package_runs (
    run_id TEXT NOT NULL, package_id TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(run_id, package_id)
);"""

COVERAGE = """CREATE TABLE IF NOT EXISTS coverage (
    package_id TEXT NOT NULL, seq INTEGER NOT NULL, rects TEXT NOT NULL,
    net_cells INTEGER NOT NULL, remaining_cells INTEGER NOT NULL,
    outside_cells INTEGER NOT NULL, received TEXT NOT NULL,
    PRIMARY KEY(package_id, seq)
);"""

OPEN = ("PENDING", "DISPATCHED")


def _json(value):
    return json.dumps(value, ensure_ascii=False)


def package_view(row, submissions=None):
    record = dict(row)
    record["case"] = record.pop("case_key")
    record["region"] = json.loads(record["region"])
    record["rects"] = json.loads(record["rects"])
    record["bounds"] = json.loads(record["bounds"])
    record["sources"] = json.loads(record["sources"] or "[]")
    record["supersedes"] = json.loads(record["supersedes"])
    record["superseded_by"] = json.loads(record["superseded_by"] or "[]")
    record["submissions"] = [
        {
            "seq": item["seq"],
            "rects": json.loads(item["rects"]),
            "net_cells": item["net_cells"],
            "remaining_cells": item["remaining_cells"],
            "outside_cells": item["outside_cells"],
            "received": item["received"],
        }
        for item in submissions or []
    ]
    return record


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute(SCHEMA)
            db.execute(PACKAGES)
            self._migrate(db)
            db.execute(LINKS)
            self._backfill_links(db)
            db.execute(COVERAGE)
            yield db

    @staticmethod
    def _migrate(db):
        columns = {
            row["name"] for row in db.execute("PRAGMA table_info(packages)").fetchall()
        }
        for name, definition in (
            ("source", "TEXT NOT NULL DEFAULT ''"),
            ("sources", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if name not in columns:
                db.execute(f"ALTER TABLE packages ADD COLUMN {name} {definition}")

    @staticmethod
    def _backfill_links(db):
        """旧库的包还没有批次关联时，按登记批次补回。"""
        db.execute(
            "INSERT INTO package_runs(run_id,package_id,source) "
            "SELECT run_id,id,source FROM packages WHERE 1 "
            "ON CONFLICT(run_id,package_id) DO NOTHING"
        )

    def register(self, run_id, report):
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(id,report,created) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING",
                (run_id, _json(report), report["manifest"]["created"]),
            )
            self._register_packages(db, run_id, report)
        return self.load(run_id)

    def _register_packages(self, db, run_id, report):
        version = report["manifest"]["version"]
        created = report["manifest"]["created"]
        source = report["manifest"]["sha256"]
        new_packages = report.get("packages") or []
        replacements = {case["case"]: [] for case in report.get("cases") or []}
        for package in new_packages:
            cursor = db.execute(
                """INSERT INTO packages(
                       id,run_id,case_key,version,source,sources,cells,region,
                       rects,bounds,created,net_cells,remaining_cells)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?)
                   ON CONFLICT(id) DO NOTHING""",
                (
                    package["id"],
                    run_id,
                    package["case"],
                    version,
                    source,
                    _json([source]),
                    package["cells"],
                    _json(package["region"]),
                    _json(package["rects"]),
                    _json(package["bounds"]),
                    created,
                    package["cells"],
                ),
            )
            if cursor.rowcount == 0:
                # 同一缺口范围在不同来源下仍是同一个包，只登记来源，不重复出车。
                existing = db.execute(
                    "SELECT sources FROM packages WHERE id=?", (package["id"],)
                ).fetchone()
                sources = json.loads(existing["sources"] or "[]")
                if source not in sources:
                    sources.append(source)
                    db.execute(
                        "UPDATE packages SET sources=? WHERE id=?",
                        (_json(sources), package["id"]),
                    )
            db.execute(
                "INSERT INTO package_runs(run_id,package_id,source) VALUES (?,?,?) "
                "ON CONFLICT(run_id,package_id) DO NOTHING",
                (run_id, package["id"], source),
            )
            replacements.setdefault(package["case"], []).append(package["id"])
        self._link_versions(db, version, replacements)

    def _link_versions(self, db, version, replacements):
        """规则版本更新后旧范围失效；已下发和已关闭包保留，并与新包互相标注。"""
        for case, ids in replacements.items():
            old_rows = db.execute(
                "SELECT id,status FROM packages WHERE case_key=? AND version<>? "
                "AND status IN ('PENDING','DISPATCHED','CLOSED')",
                (case, version),
            ).fetchall()
            old_ids = [row["id"] for row in old_rows if row["id"] not in ids]
            if not old_ids:
                continue
            db.executemany(
                "UPDATE packages SET supersedes=? WHERE id=?",
                [(_json(old_ids), new_id) for new_id in ids],
            )
            db.executemany(
                "UPDATE packages SET superseded_by=? WHERE id=?",
                [(_json(ids), old_id) for old_id in old_ids],
            )
            stale = [row["id"] for row in old_rows if row["status"] != "CLOSED"]
            db.executemany(
                "UPDATE packages SET status='SUPERSEDED' WHERE id=?",
                [(old_id,) for old_id in stale],
            )
        # 新版规则下已经不再出现的旧包同样失效，避免残留可派发的旧范围。
        db.execute(
            "UPDATE packages SET status='SUPERSEDED' "
            "WHERE version<>? AND status IN (?,?)",
            (version, *OPEN),
        )

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise DomainIssue("RUN_NOT_FOUND")
        result = dict(row)
        result["report"] = json.loads(result["report"])
        return result

    def list(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,created,status,revision,note FROM runs ORDER BY created DESC,id LIMIT 50"
                )
            ]

    def revise(self, run_id, revision, status, note, now):
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE runs SET status=?,note=?,reviewed=?,revision=revision+1 WHERE id=? AND revision=?",
                (status, note, now, run_id, revision),
            )
            if cursor.rowcount != 1:
                raise DomainIssue("STALE_REVIEW")
        return self.load(run_id)

    # 补测包

    def _package_row(self, db, package_id):
        row = db.execute("SELECT * FROM packages WHERE id=?", (package_id,)).fetchone()
        if row is None:
            raise DomainIssue("PACKAGE_NOT_FOUND")
        return row

    def _submissions(self, db, package_id):
        return db.execute(
            "SELECT * FROM coverage WHERE package_id=? ORDER BY seq", (package_id,)
        ).fetchall()

    def _runs_of(self, db, package_id):
        return [
            row["run_id"]
            for row in db.execute(
                "SELECT run_id FROM package_runs WHERE package_id=? ORDER BY run_id",
                (package_id,),
            )
        ]

    def package(self, package_id):
        with self.connect() as db:
            row = self._package_row(db, package_id)
            view = package_view(row, self._submissions(db, package_id))
            view["runs"] = self._runs_of(db, package_id)
            return view

    def run_packages(self, run_id):
        self.load(run_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT packages.*, package_runs.source AS run_source "
                "FROM packages JOIN package_runs "
                "ON packages.id=package_runs.package_id "
                "WHERE package_runs.run_id=? ORDER BY packages.case_key,packages.id",
                (run_id,),
            ).fetchall()
            items = []
            for row in rows:
                record = dict(row)
                run_source = record.pop("run_source")
                view = package_view(record)
                # 每个批次看到的是本批来源；跨来源复用的包保留全部来源。
                view["source"] = run_source
                items.append(view)
            return items

    def list_packages(self, status=None):
        query = "SELECT * FROM packages"
        params = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        with self.connect() as db:
            return [
                package_view(row)
                for row in db.execute(query + " ORDER BY created DESC,id", params)
            ]

    def dispatch(self, run_id, now):
        from app.modules.dispatch import assess

        run = self.load(run_id)
        verdict = run["report"].get("dispatch") or assess(run["report"])
        if verdict.get("blocked_by"):
            raise DomainIssue("DISPATCH_BLOCKED")
        with self.connect() as db:
            db.execute(
                "UPDATE packages SET status='DISPATCHED', dispatched=? WHERE id IN "
                "(SELECT package_id FROM package_runs WHERE run_id=?) "
                "AND status='PENDING'",
                (now, run_id),
            )
        return self.run_packages(run_id)

    def submit_coverage(self, package_id, rects, now):
        with self.connect() as db:
            row = self._package_row(db, package_id)
            if row["status"] == "SUPERSEDED":
                raise DomainIssue("PACKAGE_SUPERSEDED")
            if row["status"] == "CLOSED":
                raise DomainIssue("PACKAGE_CLOSED")
            if row["status"] == "PENDING":
                raise DomainIssue("PACKAGE_NOT_DISPATCHED")
            db.execute(
                """INSERT INTO coverage(package_id,seq,rects,net_cells,remaining_cells,
                       outside_cells,received)
                   VALUES (?, (SELECT COALESCE(MAX(seq),0)+1 FROM coverage WHERE package_id=?), ?,0,0,0,?)""",
                (package_id, package_id, _json([list(r) for r in rects]), now),
            )
            seq = db.execute(
                "SELECT MAX(seq) AS seq FROM coverage WHERE package_id=?", (package_id,)
            ).fetchone()["seq"]
            result = self._recompute(db, package_id)
            db.execute(
                "UPDATE coverage SET net_cells=?,remaining_cells=?,outside_cells=? "
                "WHERE package_id=? AND seq=?",
                (
                    result["net_cells"],
                    result["remaining_cells"],
                    result["outside_cells"],
                    package_id,
                    seq,
                ),
            )
            if result["complete"]:
                db.execute(
                    "UPDATE packages SET status='CLOSED', closed=?, net_cells=?, "
                    "remaining_cells=0 WHERE id=?",
                    (now, result["net_cells"], package_id),
                )
            else:
                db.execute(
                    "UPDATE packages SET net_cells=?, remaining_cells=? WHERE id=?",
                    (result["net_cells"], result["remaining_cells"], package_id),
                )
            row = self._package_row(db, package_id)
            view = package_view(row, self._submissions(db, package_id))
            view["evaluation"] = self._recompute(db, package_id)
            return view

    def _recompute(self, db, package_id):
        row = self._package_row(db, package_id)
        package = {
            "region": json.loads(row["region"]),
            "rects": json.loads(row["rects"]),
            "cells": row["cells"],
        }
        submissions = [
            json.loads(item["rects"]) for item in self._submissions(db, package_id)
        ]
        return closure_rules.evaluate(package, submissions, row["status"])
