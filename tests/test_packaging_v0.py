"""Packaging v0 adapters — docs matrix, Homebrew formula, USB cottage, no secrets."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IFACE_PIN = "3621849bbf7c368b1d709356c465883144300208"
COTTAGE = REPO / "usb" / "roles" / "aimmune-cottage"
GATEWAY = REPO / "usb" / "roles" / "gateway-opnsense"
HOST = REPO / "usb" / "roles" / "hypermesh-host"
FORMULA = REPO / "packaging" / "homebrew" / "aimmune.rb"
TAP_README = REPO / "packaging" / "homebrew" / "README.md"
PACKAGING_DOC = REPO / "docs" / "packaging-v0.md"


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, **kwargs)


def test_packaging_doc_matches_locked_scope() -> None:
    text = PACKAGING_DOC.read_text(encoding="utf-8")
    assert "AImmune" in text
    assert "One code SoT" in text or "one code SoT" in text.lower()
    for letter in "ABCDEF":
        assert f"| {letter} |" in text
    assert "JetPack Ubuntu" in text
    assert "Compose" in text
    assert "packaging/homebrew/aimmune.rb" in text
    assert "service do" in text
    assert "AIMMUNE_EXEC_MOCK" in text
    assert "fyber/homebrew-tap" in text
    assert "usb/roles/aimmune-cottage/install.sh" in text
    assert "VERSION" in text and "SHA256SUMS" in text
    assert "HM_SITE_TOKEN" in text and "AIMMUNE_UI_TOKEN" in text
    for phrase in (".deb", ".rpm", "Playwright", "Tailscale", "k8s", "notarized"):
        assert phrase in text
    assert IFACE_PIN in text


def test_amended_docs_point_at_packaging_v0() -> None:
    for rel in (
        "docs/host-install-smoke.md",
        "docs/usb-layout.md",
        "docs/slice-9-package.md",
    ):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "packaging-v0.md" in text, rel
        assert "JetPack" in text or "packaging-v0" in text


def test_homebrew_formula_is_formula_not_cask() -> None:
    text = FORMULA.read_text(encoding="utf-8")
    assert "class Aimmune < Formula" in text
    assert "class Aimmune < Cask" not in text
    assert "not cask" in text.lower()
    assert "service do" in text
    assert 'AIMMUNE_EXEC_MOCK:        "1"' in text or 'AIMMUNE_EXEC_MOCK:' in text
    assert "AIMMUNE_PLANE_REACHABLE" in text
    assert 'AIMMUNE_UI_HOST:' in text or "AIMMUNE_UI_HOST" in text
    assert 'license "MIT"' in text
    assert "head " in text
    assert TAP_README.is_file()
    tap = TAP_README.read_text(encoding="utf-8")
    assert "fyber/homebrew-tap" in tap
    assert "brew services" in tap
    assert "AIMMUNE_EXEC_MOCK" in tap
    mac_env = (REPO / "packaging" / "homebrew" / "aimmune.env.macos.example").read_text(
        encoding="utf-8"
    )
    assert "AIMMUNE_EXEC_MOCK=1" in mac_env
    assert "AIMMUNE_PLANE_REACHABLE=0" in mac_env
    assert "AIMMUNE_UI_HOST=127.0.0.1" in mac_env
    assert "NO live OPNsense" in mac_env or "No live OPNsense" in mac_env


def test_usb_cottage_install_is_executable_and_verifies() -> None:
    script = COTTAGE / "install.sh"
    assert script.is_file()
    assert script.stat().st_mode & stat.S_IXUSR
    assert (COTTAGE / "VERSION").is_file()
    assert (COTTAGE / "SHA256SUMS").is_file()
    version = (COTTAGE / "VERSION").read_text(encoding="utf-8")
    assert f"IFACE_PIN={IFACE_PIN}" in version
    assert "PRODUCT=AImmune" in version
    proc = _run([str(script), "--verify"])
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "USB cottage verify ok" in proc.stdout


def test_usb_cottage_install_calls_deploy(tmp_path: Path) -> None:
    dest_systemd = tmp_path / "systemd"
    dest_env = tmp_path / "env"
    dest_state = tmp_path / "state"
    env = os.environ.copy()
    env.update(
        {
            "DEST_SYSTEMD": str(dest_systemd),
            "DEST_ENV_DIR": str(dest_env),
            "DEST_STATE_DIR": str(dest_state),
            "AIMMUNE_REPO_ROOT": str(REPO),
            "AIMMUNE_USB_SKIP_PIP": "1",
        }
    )
    proc = _run([str(COTTAGE / "install.sh")], env=env)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "calling Linux SoT" in proc.stdout
    assert (dest_systemd / "aimmune.service").is_file()
    assert (dest_systemd / "aimmune-ui.service").is_file()
    assert (dest_env / "aimmune.env.example").is_file()
    assert (dest_env / "aimmune.env").is_file()
    assert (dest_state).is_dir()


def test_usb_cottage_unpack_tarball_then_install(tmp_path: Path) -> None:
    role = tmp_path / "role"
    role.mkdir()
    for name in ("install.sh", "VERSION", "README.md"):
        data = (COTTAGE / name).read_bytes()
        (role / name).write_bytes(data)
    (role / "install.sh").chmod(0o755)

    payload = tmp_path / "payload" / "auto-defense"
    (payload / "deploy" / "systemd").mkdir(parents=True)
    for rel in (
        "deploy/install.sh",
        "deploy/aimmune.env.example",
        "deploy/systemd/aimmune.service",
        "deploy/systemd/aimmune-ui.service",
    ):
        src = REPO / rel
        dest = payload / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
    (payload / "deploy" / "install.sh").chmod(0o755)

    tarball = role / "aimmune-cottage.tgz"
    with tarfile.open(tarball, "w:gz") as tf:
        tf.add(payload, arcname="auto-defense")

    write = _run([str(role / "install.sh"), "--write-sums"])
    assert write.returncode == 0, write.stderr + write.stdout

    dest_systemd = tmp_path / "systemd"
    env = os.environ.copy()
    env.update(
        {
            "DEST_SYSTEMD": str(dest_systemd),
            "DEST_ENV_DIR": str(tmp_path / "env"),
            "DEST_STATE_DIR": str(tmp_path / "state"),
            "AIMMUNE_USB_SKIP_PIP": "1",
            "AIMMUNE_UNPACK_DIR": str(tmp_path / "unpack"),
        }
    )
    env.pop("AIMMUNE_REPO_ROOT", None)
    proc = _run([str(role / "install.sh")], env=env, cwd=str(role))
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "unpacking" in proc.stdout + proc.stderr
    assert (dest_systemd / "aimmune.service").is_file()


def test_usb_gateway_and_host_are_pointer_stubs() -> None:
    for script, needle in (
        (GATEWAY / "install.sh", "proxmox-firewall"),
        (HOST / "install.sh", "hypermesh-host"),
    ):
        assert script.is_file()
        assert script.stat().st_mode & stat.S_IXUSR
        proc = _run([str(script)])
        assert proc.returncode == 2, proc.stderr + proc.stdout
        assert needle in proc.stdout
        assert "deploy/install.sh" not in script.read_text(encoding="utf-8")


def test_deploy_install_behavior_unchanged(tmp_path: Path) -> None:
    dest_systemd = tmp_path / "systemd"
    dest_env = tmp_path / "env"
    dest_state = tmp_path / "state"
    env = os.environ.copy()
    env.update(
        {
            "DEST_SYSTEMD": str(dest_systemd),
            "DEST_ENV_DIR": str(dest_env),
            "DEST_STATE_DIR": str(dest_state),
        }
    )
    proc = _run([str(REPO / "deploy" / "install.sh")], env=env)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "AImmune slice 9 installer" in proc.stdout
    unit = (dest_systemd / "aimmune.service").read_text(encoding="utf-8")
    assert "ExecStart=/usr/local/bin/aimmune loop" in unit
    env_path = dest_env / "aimmune.env"
    env_path.write_text("SITE_ID=keep-me\n", encoding="utf-8")
    proc2 = _run([str(REPO / "deploy" / "install.sh")], env=env)
    assert proc2.returncode == 0, proc2.stderr + proc2.stdout
    assert "left existing" in proc2.stdout
    assert env_path.read_text(encoding="utf-8") == "SITE_ID=keep-me\n"


def test_no_secrets_in_usb_or_packaging_tree() -> None:
    roots = [REPO / "usb", REPO / "packaging"]
    assign = re.compile(r"^(HM_SITE_TOKEN|AIMMUNE_UI_TOKEN)=(\S+)", re.M)
    baked = re.compile(r"hm_site_[A-Za-z0-9]{8,}")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for match in assign.finditer(text):
                assert match.group(2) in {"", "#"}, f"secret assignment in {path}"
            assert not baked.search(text), f"baked hm_site_ token in {path}"


def test_inference_iface_pin_unchanged() -> None:
    gitmodules = (REPO / ".gitmodules").read_text(encoding="utf-8")
    assert "vendor/inference-iface" in gitmodules
    assert "Brewnix/inference-iface" in gitmodules
    proc = _run(["git", "ls-tree", "HEAD", "vendor/inference-iface"], cwd=str(REPO))
    assert proc.returncode == 0, proc.stderr
    assert IFACE_PIN in proc.stdout
    version = (COTTAGE / "VERSION").read_text(encoding="utf-8")
    assert IFACE_PIN in version
