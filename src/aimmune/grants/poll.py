"""Cycle-end grant poll. Short timeout; never blocks contain."""

from __future__ import annotations

from typing import Any

from aimmune.grants.client import GrantError
from aimmune.grants.store import is_active


class GrantPollResult:
    def __init__(self) -> None:
        self.listed = 0
        self.upserted = 0
        self.expired: list[str] = []
        self.errors: list[str] = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "listed": self.listed,
            "upserted": self.upserted,
            "expired": list(self.expired),
            "errors": list(self.errors),
        }


def sync_incident_flags(rt: Any, now=None) -> None:
    """Attach grant ids and flip ``flags.grant_active`` from the cache."""
    clock = now if now is not None else rt.clock.now()
    seen: set[str] = set()
    for grant in rt.grants.list():
        iid = grant.get("incident_id")
        if not iid:
            continue
        seen.add(str(iid))
    for rec in rt.incidents.list_incidents():
        seen.add(str(rec.get("incident_id") or ""))
    for iid in seen:
        if not iid:
            continue
        active = rt.grants.active_for_incident(iid, clock)
        if active:
            rt.incidents.attach_grant(
                iid,
                str(active["grant_id"]),
                active_until=active.get("active_until"),
                now=clock,
            )
            continue
        rec = rt.incidents.get(iid)
        if rec and (rec.get("flags") or {}).get("grant_active"):
            rt.incidents.set_grant_active(iid, False)


def poll_grants(rt: Any) -> dict[str, Any]:
    """Refresh the site cache from plane list/get. Fail-open."""
    result = GrantPollResult()
    now = rt.clock.now()
    try:
        result.expired = rt.grants.expire_local(now)
    except Exception as exc:  # noqa: BLE001 — never block contain
        result.errors.append(f"expire_local: {exc}")

    plane_up = bool(rt.config.plane_reachable) and rt.grant_client is not None
    if plane_up:
        incident_ids: set[str] = set()
        try:
            for rec in rt.incidents.find_open(rt.config.site_id):
                iid = rec.get("incident_id")
                if iid:
                    incident_ids.add(str(iid))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"open incidents: {exc}")
        try:
            for grant in rt.grants.find_proposed():
                iid = grant.get("incident_id")
                if iid:
                    incident_ids.add(str(iid))
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"proposed cache: {exc}")

        for iid in incident_ids:
            for status in ("approved", "proposed"):
                try:
                    rows = rt.grant_client.list_grants(status=status, incident_id=iid)
                except GrantError as exc:
                    result.errors.append(str(exc))
                    continue
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"list {status} {iid}: {exc}")
                    continue
                result.listed += len(rows)
                for row in rows:
                    try:
                        rt.grants.upsert(row)
                        result.upserted += 1
                    except Exception as exc:  # noqa: BLE001
                        result.errors.append(str(exc))

        # Refresh cached proposed rows (terminal GET is allowed).
        try:
            pending = list(rt.grants.find_proposed())
        except Exception:
            pending = []
        for grant in pending:
            gid = grant.get("grant_id")
            if not gid:
                continue
            try:
                fresh = rt.grant_client.get_grant(str(gid))
                rt.grants.upsert(fresh)
                result.upserted += 1
            except GrantError as exc:
                result.errors.append(str(exc))
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"get {gid}: {exc}")

    try:
        sync_incident_flags(rt, now)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"sync flags: {exc}")
    _ = is_active  # keep helper imported for readers
    return result.as_dict()
