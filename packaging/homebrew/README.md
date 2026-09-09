# Homebrew adapter (private tap notes)

**Product:** AImmune  
**Code home:** [`Brewnix/auto-defense`](https://github.com/Brewnix/auto-defense) (MIT)  
**This file:** tap notes until a separate tap exists  
**Formula:** [`aimmune.rb`](aimmune.rb) — **formula, not cask**

Linux / Orin install stays [`deploy/install.sh`](../../deploy/install.sh) + systemd. This directory is a **platform adapter** only.

## Source of truth

[`aimmune.rb`](aimmune.rb) lives **in this repo** until a private tap is created. When [`fyber/homebrew-tap`](https://github.com/fyber/homebrew-tap) (or `FyberLabs/homebrew-tap`) exists, copy this formula to `Formula/aimmune.rb` in that tap and keep this tree as the review SoT — do not grow a second implementation.

HEAD-only until a tagged release. No bottle. No notarized `.app`. No cask.

## Install from this checkout

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
cd auto-defense
brew install --HEAD --formula ./packaging/homebrew/aimmune.rb
brew services start aimmune
aimmune status --json
```

`brew services` is launchd via the formula `service do` block.

## Install from a private tap (when it exists)

```bash
brew tap fyber/homebrew-tap
brew install --HEAD aimmune
brew services start aimmune
```

If the tap lives under a different org, `brew tap <org>/homebrew-tap` is the same shape.

## Mac defaults (locked)

| Knob | Value | Why |
|------|-------|-----|
| `AIMMUNE_EXEC_MOCK` | `1` | No live OPNsense contain path on Mac |
| `AIMMUNE_PLANE_REACHABLE` | `0` | Offline-first laptop / lab |
| `AIMMUNE_UI_HOST` | `127.0.0.1` | Loopback UI; remote cottage via SSH tunnel |

Copy [`aimmune.env.macos.example`](aimmune.env.macos.example) to `$(brew --prefix)/etc/aimmune/aimmune.env` (**0600**). Do not set `AIMMUNE_OPNSENSE_*` on Mac. Do not commit `HM_SITE_TOKEN` / `AIMMUNE_UI_TOKEN`.

Remote-cottage UI: tunnel `127.0.0.1:3000` from the Linux/Orin cottage. Local UI is the sibling `ui/` tree (token required to serve).

## Out of scope

`.deb` / `.rpm` · ISO / image bake · Compose-primary · notarized Mac app · Tailscale · iface pin bump · k8s · Playwright · cask
