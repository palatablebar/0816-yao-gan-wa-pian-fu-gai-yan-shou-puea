from datetime import datetime, timezone
from time import monotonic

from app.business import DomainIssue
from app.modules.dispatch import assess
from app.modules.manifest import source_manifest
from app.modules.pipeline import run


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def stamp():
    return now()


def execute(store, data):
    start = monotonic()
    manifest = source_manifest(data, now())
    run_id = manifest["run_id"]
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != "RUN_NOT_FOUND":
            raise
    report = run(data)
    manifest["duration_ms"] = round((monotonic() - start) * 1000, 3)
    manifest["created"] = now()
    report["manifest"] = manifest
    report["dispatch"] = assess(report)
    return store.register(run_id, report)


def review(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue("REVIEW_FIELDS")
    revision, status, note = (values.get(key) for key in ("revision", "status", "note"))
    if (
        type(revision) is not int
        or revision < 0
        or status not in ("APPROVED", "HELD")
        or not isinstance(note, str)
        or not (3 <= len(note.strip()) <= 200)
    ):
        raise DomainIssue("REVIEW_FIELDS")
    current = store.load(run_id)
    if revision != current["revision"]:
        raise DomainIssue("STALE_REVIEW")
    if current["status"] == "APPROVED":
        raise DomainIssue("RUN_FINALIZED")
    if status == "APPROVED" and not current["report"]["balance"]["releasable"]:
        raise DomainIssue("UNRESOLVED_ISSUES")
    return store.revise(run_id, revision, status, note.strip(), now())
