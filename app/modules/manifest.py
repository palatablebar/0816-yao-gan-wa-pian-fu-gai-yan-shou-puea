from hashlib import sha256

from app.config import rule_version


def source_manifest(data, created, duration_ms=0.0):
    """来源指纹与规则版本，预览和入库批次使用同一套口径。"""
    fingerprint = sha256(data).hexdigest()
    version = rule_version()
    return dict(
        sha256=fingerprint,
        version=version,
        created=created,
        duration_ms=duration_ms,
        bytes=len(data),
        run_id=sha256(f"{version}:{fingerprint}".encode()).hexdigest(),
    )
