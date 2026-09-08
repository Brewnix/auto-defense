"""Contain / expiry never call SociACL Check (binding 5)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAIN_FILES = [
    ROOT / "src/aimmune/exec/opnsense_alias.py",
    ROOT / "src/aimmune/rules/expiry.py",
    ROOT / "src/aimmune/rules/engine.py",
    ROOT / "src/aimmune/cycle.py",
    ROOT / "src/aimmune/policy.py",
    ROOT / "src/aimmune/ledger/ttl.py",
]
BANNED = ("sociacl", "checkdelegate", "mockcheck", "check_delegate")


def test_contain_path_never_imports_check() -> None:
    for path in CONTAIN_FILES:
        text = path.read_text(encoding="utf-8").lower()
        for needle in BANNED:
            assert needle not in text, f"{path} must not mention {needle}"
