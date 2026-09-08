"""Suricata EVE window → redacted fyber.feature_bundle/v0 (no payloads)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any, Iterable

Whitelist = list[Any]


def parse_eve_ts(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
        candidates.append(text[:-1] + "+0000")
    if len(text) >= 5 and (text[-5] in "+-") and text[-3] != ":":
        candidates.append(text[:-2] + ":" + text[-2:])
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    for cand in candidates:
        try:
            dt = datetime.fromisoformat(cand)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def load_whitelist(path: Path | None) -> Whitelist:
    if path is None or not path.is_file():
        return []
    entries: Whitelist = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.split("#", 1)[0].strip()
        if not item:
            continue
        try:
            if "/" in item:
                entries.append(ip_network(item, strict=False))
            else:
                entries.append(ip_address(item))
        except ValueError:
            continue
    return entries


def ip_is_whitelisted(ip: str, whitelist: Whitelist) -> bool:
    try:
        addr = ip_address(ip)
    except ValueError:
        return False
    for entry in whitelist:
        if hasattr(entry, "network_address"):
            if addr in entry:
                return True
        elif addr == entry:
            return True
    return False


def parse_eve_window(
    eve_path: Path | None,
    *,
    now: datetime,
    window_s: int,
) -> list[dict[str, Any]]:
    if eve_path is None or not eve_path.is_file():
        return []
    start = now - timedelta(seconds=window_s)
    events: list[dict[str, Any]] = []
    for line in eve_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = rec.get("event_type")
        if event_type not in (None, "alert") and "alert" not in rec:
            continue
        if "alert" not in rec and event_type != "alert":
            continue
        ts = parse_eve_ts(str(rec.get("timestamp", "")))
        if ts is None or ts < start or ts > now:
            continue
        src = rec.get("src_ip")
        if not src:
            continue
        alert = rec.get("alert") or {}
        sid = alert.get("signature_id")
        events.append(
            {
                "src_ip": str(src),
                "dest_port": rec.get("dest_port"),
                "sid": str(sid) if sid is not None else "",
                "timestamp": ts,
            }
        )
    return events


def stub_health(*, wan_up: bool = True) -> dict[str, Any]:
    return {
        "cpu": 0.0,
        "disk": 0.0,
        "wan_gateways": ["up" if wan_up else "down"],
        "suricata": "unknown",
    }


def build_feature_bundle(
    eve_path: Path | None,
    *,
    now: datetime,
    window_s: int,
    whitelist: Whitelist | None = None,
    prior_blocks: list[dict[str, Any]] | None = None,
    wan_up: bool = True,
    events: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parsed = list(events) if events is not None else parse_eve_window(
        eve_path, now=now, window_s=window_s
    )
    allow = whitelist or []
    by_sid: Counter[str] = Counter()
    by_src: Counter[str] = Counter()
    ports: dict[str, set[int]] = defaultdict(set)
    sids: dict[str, set[str]] = defaultdict(set)
    whitelist_hits = 0

    for ev in parsed:
        src = ev["src_ip"]
        by_src[src] += 1
        sid = ev.get("sid") or ""
        if sid:
            by_sid[sid] += 1
            sids[src].add(sid)
        port = ev.get("dest_port")
        if isinstance(port, int) and 0 <= port <= 65535:
            ports[src].add(port)
        if ip_is_whitelisted(src, allow):
            whitelist_hits += 1

    top: list[dict[str, Any]] = []
    for ip, hits in by_src.most_common(50):
        if hits < 1:
            continue
        item: dict[str, Any] = {"ip": ip, "hits": hits}
        ip_ports = sorted(ports[ip])[:64]
        ip_sids = sorted(sids[ip])[:64]
        if ip_ports:
            item["ports"] = ip_ports
        if ip_sids:
            item["sids"] = ip_sids
        top.append(item)

    return {
        "window_s": window_s,
        "counts": {
            "alert_total": sum(by_src.values()),
            "by_sid": dict(by_sid),
            "by_src": dict(by_src),
        },
        "top_subjects": top,
        "health": stub_health(wan_up=wan_up),
        "whitelist_hits": whitelist_hits,
        "prior_blocks": list(prior_blocks or [])[:100],
    }
