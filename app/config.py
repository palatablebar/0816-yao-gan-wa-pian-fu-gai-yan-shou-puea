import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 256 * 1024
MAX_ROWS = 2000
RULE_VERSION = os.getenv("WORKBENCH_RULE_VERSION", "1.0.0")


def rule_version():
    """当前生效的规则版本。规则更新后，旧的补测范围会失效。"""
    return os.getenv("WORKBENCH_RULE_VERSION") or RULE_VERSION
