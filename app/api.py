from flask import Blueprint, Response, current_app, jsonify, request

from app.business import DomainIssue
from app.evidence.render import artifact
from app.inputs import read_input
from app.modules import closure
from app.modules.pipeline import run
from app.review.service import execute, review, stamp

api = Blueprint("api", __name__, url_prefix="/api")
STAGES = {"intake": 1, "prepare": 2, "calculate": 3, "policy": 4, "balance": 5}


@api.post("/stages/<stage>")
def preview(stage):
    if stage not in STAGES:
        raise DomainIssue("STAGE_UNKNOWN")
    return jsonify(run(read_input(), STAGES[stage]))


@api.route("/runs", methods=["GET", "POST"])
def runs():
    store = current_app.extensions["runs"]
    if request.method == "GET":
        return jsonify(items=store.list())
    return jsonify(execute(store, read_input()))


@api.route("/runs/<run_id>", methods=["GET", "PATCH"])
def batch(run_id):
    store = current_app.extensions["runs"]
    if request.method == "GET":
        return jsonify(store.load(run_id))
    return jsonify(review(store, run_id, request.get_json(silent=True)))


@api.get("/runs/<run_id>/packages")
def run_packages(run_id):
    return jsonify(items=current_app.extensions["runs"].run_packages(run_id))


@api.post("/runs/<run_id>/dispatch")
def dispatch(run_id):
    store = current_app.extensions["runs"]
    return jsonify(items=store.dispatch(run_id, stamp()))


@api.get("/packages")
def packages():
    status = request.args.get("status")
    if status not in (None, "PENDING", "DISPATCHED", "CLOSED", "SUPERSEDED"):
        raise DomainIssue("PACKAGE_STATUS_UNKNOWN")
    return jsonify(items=current_app.extensions["runs"].list_packages(status))


@api.get("/packages/<package_id>")
def package(package_id):
    return jsonify(current_app.extensions["runs"].package(package_id))


@api.post("/packages/<package_id>/coverage")
def coverage(package_id):
    store = current_app.extensions["runs"]
    values = request.get_json(silent=True)
    if not isinstance(values, dict) or "rects" not in values:
        raise DomainIssue("COVERAGE_INVALID")
    rects = closure.normalize(values["rects"])
    return jsonify(store.submit_coverage(package_id, rects, stamp()))


@api.get("/runs/<run_id>/evidence")
def export(run_id):
    store = current_app.extensions["runs"]
    report = store.load(run_id)
    return Response(
        artifact(report, store.run_packages(run_id)),
        mimetype="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="review-{report["id"][:12]}.json"',
            "Cache-Control": "no-store",
        },
    )
