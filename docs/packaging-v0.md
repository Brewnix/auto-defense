# Packaging v0

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this cut  
**License:** MIT  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208) — **do not bump**  
**Extends:** [`docs/slice-9-package.md`](slice-9-package.md) · [`docs/host-install-smoke.md`](host-install-smoke.md) · [`docs/usb-layout.md`](usb-layout.md)

One code home. Platform adapters only. Linux systemd (`deploy/`) is the cottage SoT; Homebrew and USB call that path or document the same contract.

## Locked design (Chris)

| | Rule |
|---|------|
| A | **One code SoT; platform adapters only.** Linux systemd already exists ([`deploy/systemd`](../deploy/systemd), [`deploy/install.sh`](../deploy/install.sh)) — keep it. Homebrew formula + USB role install scripts are adapters that call the existing Linux install path. |
| B | **Orin / Jetson = native systemd on JetPack Ubuntu.** Compose is **not** required for AImmune core. Orin is the same cottage install as any Linux box (`pip` + `deploy/install.sh` + `aimmune.service`). Do **not** add Docker Compose as the primary runtime. |
| C | **Mac = Homebrew tap formula + `brew services` (launchd).** Surface: mock / offline loop + remote-cottage UI defaults. **No** live OPNsense contain path on Mac. Formula (not cask): [`packaging/homebrew/aimmune.rb`](../packaging/homebrew/aimmune.rb) + tap notes ([`packaging/homebrew/README.md`](../packaging/homebrew/README.md), `fyber/homebrew-tap` style — formula lives in-repo as SoT until a separate tap exists). `brew services` via `service do`. Default Mac env: `AIMMUNE_EXEC_MOCK` / plane-down / loopback UI. |
| D | **USB = multi-role Brewnix stick.** [`usb/roles/{gateway-opnsense,hypermesh-host,aimmune-cottage}/`](../usb/roles). Cottage has a real [`install.sh`](../usb/roles/aimmune-cottage/install.sh) that calls `deploy/install.sh` after unpack, plus [`VERSION`](../usb/roles/aimmune-cottage/VERSION) and [`SHA256SUMS`](../usb/roles/aimmune-cottage/SHA256SUMS). Gateway / Host remain pointers to other repos with thin install stubs that say “run that repo’s installer”. **Never** bake `HM_SITE_TOKEN` / `AIMMUNE_UI_TOKEN` onto the stick. |
| E | **This file is the matrix.** Amend host-install-smoke, usb-layout, and slice 9 to point here. Orin = JetPack Ubuntu + systemd, not Compose-primary. |
| F | **Out of scope:** `.deb` / `.rpm` · ISO / image bake · Compose-primary · notarized Mac app · Tailscale · iface pin bump · k8s · Playwright |

Also locked: WireGuard not Tailscale; UI loopback (`AIMMUNE_UI_HOST=0.0.0.0` opt-in only, and not a Mac contain path); state **0700**; secrets **0600** on the box, never on the stick; iface pin unchanged; MIT.

## Packaging matrix

| Surface | Runtime | Adapter | Notes |
|---------|---------|---------|-------|
| Linux cottage | systemd | [`deploy/install.sh`](../deploy/install.sh) + [`deploy/systemd/`](../deploy/systemd/) | **Code SoT.** Units + env example only; does not enable/start. |
| Orin / Jetson | systemd on **JetPack Ubuntu** | same `deploy/` path | Same cottage install. **Not** Compose-primary. |
| Mac | `brew services` / launchd | [`packaging/homebrew/aimmune.rb`](../packaging/homebrew/aimmune.rb) | Mock / offline loop + loopback or remote-cottage UI. **No** live OPNsense contain. |
| USB `aimmune-cottage` | calls Linux SoT | [`usb/roles/aimmune-cottage/install.sh`](../usb/roles/aimmune-cottage/install.sh) | Unpack optional tarball → verify `VERSION` + `SHA256SUMS` → `deploy/install.sh`. |
| USB `gateway-opnsense` | other repo | [`usb/roles/gateway-opnsense/install.sh`](../usb/roles/gateway-opnsense/install.sh) | Pointer: run [`Brewnix/proxmox-firewall`](https://github.com/Brewnix/proxmox-firewall). |
| USB `hypermesh-host` | other repo | [`usb/roles/hypermesh-host/install.sh`](../usb/roles/hypermesh-host/install.sh) | Pointer: run [`FyberLabs/hypermesh-host`](https://github.com/FyberLabs/hypermesh-host). |

## Linux / Orin (systemd SoT)

Orin NX / AGX (and any Jetson on JetPack Ubuntu) is a **normal cottage box**. Use the slice 9 installer. Do not introduce `docker compose up` as the way AImmune runs.

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
cd auto-defense
python3 -m pip install -e .
sudo ./deploy/install.sh
# useradd / chown / chmod — see docs/slice-9-package.md
# edit /etc/aimmune/aimmune.env (0600)
sudo systemctl daemon-reload
sudo systemctl enable --now aimmune.service
aimmune status --json
```

Same path from a USB stick: `sudo ./usb/roles/aimmune-cottage/install.sh` (verifies pin + checksums, then calls `deploy/install.sh`). Bring-up checklist: [`docs/host-install-smoke.md`](host-install-smoke.md).

Compose may exist elsewhere on the site (gateway image, Host). It is **not** the AImmune core runtime.

## Mac (Homebrew)

Formula, not cask. In-repo SoT: [`packaging/homebrew/`](../packaging/homebrew/). Private tap notes (`fyber/homebrew-tap` style): [`packaging/homebrew/README.md`](../packaging/homebrew/README.md).

```bash
brew install --HEAD --formula ./packaging/homebrew/aimmune.rb
brew services start aimmune
aimmune status --json
```

`service do` sets `AIMMUNE_EXEC_MOCK=1`, `AIMMUNE_PLANE_REACHABLE=0`, `AIMMUNE_UI_HOST=127.0.0.1`. Do not point a Mac loop at live `alias_util`. Contain stays on the Linux / Orin cottage.

UI defaults: loopback on this machine, **or** SSH-tunnel the remote cottage (`127.0.0.1:3000`). `AIMMUNE_UI_TOKEN` is required to serve and is minted on the box — never baked into the formula or a stick.

## USB roles

```
usb/roles/
  gateway-opnsense/   # pointer + install.sh stub → proxmox-firewall
  hypermesh-host/     # pointer + install.sh stub → hypermesh-host
  aimmune-cottage/    # VERSION + SHA256SUMS + install.sh → deploy/install.sh
```

Cottage:

```bash
# in-tree checkout
./usb/roles/aimmune-cottage/install.sh --verify
sudo ./usb/roles/aimmune-cottage/install.sh

# stick with a staged tarball (optional)
# place aimmune-cottage.tgz next to install.sh, then:
#   ./install.sh --write-sums    # refresh SHA256SUMS to include the tgz
#   sudo ./install.sh
```

`install.sh --write-sums` refreshes [`SHA256SUMS`](../usb/roles/aimmune-cottage/SHA256SUMS) for `VERSION`, `README.md`, `install.sh`, and an optional tarball. Missing optional files are skipped at verify time.

Gateway / Host stubs exit `2` and print the other repo’s installer. Do not copy those trees into `auto-defense`.

Layout notes: [`docs/usb-layout.md`](usb-layout.md).

## Secrets

| May live on the stick | Must not |
|-----------------------|----------|
| `VERSION` (product / iface pin) | `HM_SITE_TOKEN` |
| `SHA256SUMS` | `AIMMUNE_UI_TOKEN` |
| source tarball / this checkout | filled `aimmune.env` |
| install adapters | OPNsense key / secret, `owner.token` |

Tokens are **0600** on the box after install ([`deploy/aimmune.env.example`](../deploy/aimmune.env.example)). Cottage `install.sh` refuses a role-dir file that assigns a non-empty `HM_SITE_TOKEN` / `AIMMUNE_UI_TOKEN` or bakes an `hm_site_` blob.

## Out of scope

`.deb` / `.rpm` · ISO / USB image / qcow bake · Compose as the AImmune primary runtime · notarized Mac app · Tailscale · iface pin bump · k8s · Playwright · embedding Next in the pip wheel · vendoring Host / OPNsense
