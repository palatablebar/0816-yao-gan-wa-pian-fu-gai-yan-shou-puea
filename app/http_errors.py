from flask import jsonify

LABELS = {
    "FILE_TOO_LARGE": "文件超过 256 KiB",
    "FILE_EMPTY": "文件没有内容",
    "FILE_BLANK": "文件只有空白",
    "HEADER_ONLY": "文件只有标题行",
    "HEADER_MISMATCH": "列名与字段字典不一致",
    "ENCODING_INVALID": "请使用 UTF-8 CSV",
    "CSV_MALFORMED": "CSV 引号或行格式异常",
    "ROW_LIMIT": "文件超过 2000 行",
    "FILE_REQUIRED": "请选择 CSV 文件",
    "RUN_NOT_FOUND": "批次不存在",
    "REVIEW_FIELDS": "请填写 3 至 200 字复核意见",
    "STALE_REVIEW": "批次已更新，请刷新",
    "RUN_FINALIZED": "批次已签发",
    "UNRESOLVED_ISSUES": "存在待处理差异",
    "SAMPLE_UNKNOWN": "样例不存在",
    "STAGE_UNKNOWN": "处理阶段不存在",
    "PACKAGE_NOT_FOUND": "补测包不存在",
    "PACKAGE_NOT_DISPATCHED": "补测包尚未派发",
    "PACKAGE_CLOSED": "补测包已关闭，不能追加覆盖",
    "PACKAGE_SUPERSEDED": "规则版本更新，该补测包已失效",
    "PACKAGE_STATUS_UNKNOWN": "补测包状态不存在",
    "DISPATCH_BLOCKED": "来源、采信、隔离或缺口未对平，不能派发",
    "COVERAGE_REQUIRED": "请提供新增覆盖范围",
    "COVERAGE_INVALID": "覆盖范围必须是 x0<x1、y0<y1 的整数矩形",
}


def response(error):
    code = error.code
    if code in {"RUN_NOT_FOUND", "SAMPLE_UNKNOWN", "STAGE_UNKNOWN", "PACKAGE_NOT_FOUND",
                "PACKAGE_STATUS_UNKNOWN"}:
        status = 404
    elif code in {
        "STALE_REVIEW",
        "RUN_FINALIZED",
        "UNRESOLVED_ISSUES",
        "PACKAGE_CLOSED",
        "PACKAGE_SUPERSEDED",
        "PACKAGE_NOT_DISPATCHED",
        "DISPATCH_BLOCKED",
    }:
        status = 409
    elif code == "FILE_TOO_LARGE":
        status = 413
    else:
        status = 422
    return jsonify(code=code, message=LABELS.get(code, code)), status
