from datetime import datetime, timezone
from hashlib import sha256

from app.business import DomainIssue
from app.config import rule_version
from app.intake.service import inspect
from app.modules.calculate import compute
from app.modules.dispatch import assess
from app.modules.gaps import build_packages
from app.modules.grouping import case_groups
from app.modules.manifest import source_manifest
from app.modules.policy import policy
from app.modules.prepare import prepare
from app.modules.reconcile import balance


def evaluate(rows, stage, source):
    case = {
        "case": rows[0]["case"],
        "records": [r["record"] for r in rows],
        "status": "READY",
    }
    try:
        case["prep"], payload = prepare(rows)
        if stage >= 3:
            case["measure"] = compute(payload)
        if stage >= 4:
            case.update(policy(case["measure"]))
            case["region"] = case["prep"]["details"]["region"]
            case["packages"] = build_packages(
                case["case"],
                tuple(case["prep"]["details"]["region"]),
                payload[0],
                rule_version(),
                source,
            )
    except DomainIssue as error:
        case["status"] = error.code
    return case


def run(data, stage=5):
    intake = inspect(data)
    output = {"intake": {k: v for k, v in intake.items() if k != "rows"}}
    if stage == 1:
        return output
    source = sha256(data).hexdigest()
    cases = [evaluate(rows, stage, source) for _, rows in case_groups(intake["rows"])]
    output["cases"] = cases
    if stage >= 4:
        output["packages"] = [
            package for case in cases for package in case.get("packages") or []
        ]
    if stage >= 5:
        output["balance"] = balance(intake, cases)
        created = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        output["manifest"] = source_manifest(data, created)
        output["dispatch"] = assess(output)
    return output
