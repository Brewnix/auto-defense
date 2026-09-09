# frozen_string_literal: true

# AImmune Homebrew formula (adapter — not a second code home).
# Source of truth until a private tap exists: this file in Brewnix/auto-defense.
# Copy into fyber/homebrew-tap Formula/aimmune.rb when that tap is created.
# Formula (not cask). HEAD-only until a tagged release. See README.md.

class Aimmune < Formula
  include Language::Python::Virtualenv

  desc "AImmune site executor — detect → act → receipt (Mac mock/offline)"
  homepage "https://github.com/Brewnix/auto-defense"
  license "MIT"
  head "https://github.com/Brewnix/auto-defense.git", branch: "main"

  depends_on "python@3.12"

  def install
    system "git", "submodule", "update", "--init", "--recursive"

    venv = virtualenv_create(libexec, "python3.12")
    venv.pip_install buildpath

    (etc/"aimmune").mkpath
    (etc/"aimmune").install "packaging/homebrew/aimmune.env.macos.example" => "aimmune.env.example"
    (var/"lib/aimmune").mkpath
    (var/"log").mkpath
  end

  def caveats
    <<~EOS
      Mac surface is mock / offline loop + loopback (or remote-cottage) UI.
      There is NO live OPNsense contain path on macOS. Cottage contain stays
      on Linux / Orin (JetPack Ubuntu + systemd). See docs/packaging-v0.md.

      brew services / launchd defaults:
        AIMMUNE_EXEC_MOCK=1
        AIMMUNE_PLANE_REACHABLE=0
        AIMMUNE_UI_HOST=127.0.0.1

      Copy the example env (do not commit tokens):
        cp #{etc}/aimmune/aimmune.env.example #{etc}/aimmune/aimmune.env
        chmod 600 #{etc}/aimmune/aimmune.env

      Start the mock loop:
        brew services start aimmune
        aimmune status --json

      Remote-cottage UI: SSH-tunnel the cottage loopback (127.0.0.1:3000).
      Local UI: sibling ui/ + AIMMUNE_UI_TOKEN (required to serve).
    EOS
  end

  service do
    run [opt_bin/"aimmune", "loop"]
    keep_alive true
    require_root false
    working_dir var/"lib/aimmune"
    log_path var/"log/aimmune.log"
    error_log_path var/"log/aimmune.error.log"
    environment_variables AIMMUNE_EXEC_MOCK:        "1",
                          AIMMUNE_PLANE_REACHABLE:  "0",
                          AIMMUNE_WAN_UP:           "0",
                          AIMMUNE_UI_HOST:          "127.0.0.1",
                          AIMMUNE_UI_PORT:          "3000",
                          AIMMUNE_SIWE_DOMAIN:      "127.0.0.1",
                          AIMMUNE_STATE_DIR:        "#{var}/lib/aimmune"
  end

  test do
    assert_match(/status|loop|cycle/i, shell_output("#{bin}/aimmune --help"))
    ENV["AIMMUNE_EXEC_MOCK"] = "1"
    ENV["AIMMUNE_PLANE_REACHABLE"] = "0"
    ENV["AIMMUNE_STATE_DIR"] = testpath/"state"
    ENV["AIMMUNE_SITE_ID"] = "net-tn-cottage"
    assert_match "net-tn-cottage", shell_output("#{bin}/aimmune status --json")
  end
end
