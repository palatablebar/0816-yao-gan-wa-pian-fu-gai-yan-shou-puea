import json


def artifact(run, packages=None):
    packet = {
        "schema": "review-evidence/1",
        "manifest": run["report"]["manifest"],
        "balance": run["report"]["balance"],
        "cases": run["report"]["cases"],
        "intake": run["report"]["intake"],
        "review": {key: run[key] for key in ("status", "revision", "note", "reviewed")},
    }
    if packages is not None:
        packet["dispatch"] = run["report"].get("dispatch")
        packet["packages"] = packages
    return (
        json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
