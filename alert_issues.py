#!/usr/bin/env python3
"""Erstellt/aktualisiert GitHub-Issues für vorhergesagte Overwerder-Überflutungen.

Liest die vom Web-Export erzeugte ``data.json`` (Overwerder-Vorhersage, cm über
PNP), erkennt vorhergesagte Events "Wasser auf dem Gelände" (Sturm-Cluster) und
gleicht sie mit den offenen Alarm-Issues ab:

* neues Event  -> Issue anlegen und ``@aaronspring`` erwähnen (ein Issue pro Event),
* Stufen-Änderung (Sturmflut/schwere/...) -> Kommentar mit erneuter Erwähnung,
* nicht mehr auf Gelände / Scheitel vorbei -> Kommentar + Issue schließen.

Läuft im Deploy-Workflow direkt nach ``export_web.py``. Ohne ``--dry-run`` wird
``GITHUB_TOKEN`` (und ``GITHUB_REPOSITORY``) aus der Umgebung benötigt.

    python alert_issues.py --data web/public/data.json
    python alert_issues.py --data web/public/data.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import os

import pandas as pd

from wasserstand_overwerder import alerts
from wasserstand_overwerder.ghissues import GitHubIssues


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="web/public/data.json", help="Pfad zur data.json")
    ap.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/name (Default: $GITHUB_REPOSITORY)",
    )
    ap.add_argument(
        "--mention", default="aaronspring", help="zu erwähnender GitHub-User"
    )
    ap.add_argument("--label", default=alerts.LABEL, help="Label der Alarm-Issues")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="nur anzeigen, was passieren würde (kein Netz, kein Token nötig)",
    )
    args = ap.parse_args()

    data = _load(args.data)
    now = pd.Timestamp(data["now"])
    thresholds = alerts.thresholds_from_payload(data)
    target = alerts.series_from_payload(data)
    gauge_zero = data.get("gauge_zero_m_nhn")

    events = alerts.detect_events(target, now, thresholds)
    print(f"Erkannte Events (auf Gelände, künftig): {len(events)}")
    for ev in events:
        print(f"  {alerts._local(ev.peak_time)}  {ev.stufe}  {ev.peak_cm:.0f} cm PNP")

    gh: GitHubIssues | None = None
    open_issues: list[alerts.OpenIssue] = []
    if not args.dry_run:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN fehlt (oder --dry-run nutzen).")
        gh = GitHubIssues(args.repo, token)
        raw = gh.list_open_issues(args.label)
        for issue in raw:
            parsed = alerts.parse_open_issue(issue["number"], issue.get("body"))
            if parsed is not None:
                open_issues.append(parsed)
    print(f"Offene Alarm-Issues: {len(open_issues)}")

    actions = alerts.plan(events, open_issues, now)
    if not actions:
        print("Nichts zu tun.")
        return

    for action in actions:
        _execute(action, gh, args, gauge_zero)


def _execute(
    action: alerts.PlannedAction,
    gh: GitHubIssues | None,
    args: argparse.Namespace,
    gauge_zero: float | None,
) -> None:
    dry = gh is None
    prefix = "[dry-run] " if dry else ""

    if action.kind == "create":
        ev = action.event
        title = alerts.issue_title(ev)
        body = alerts.issue_body(ev, args.mention, gauge_zero_m_nhn=gauge_zero)
        print(f"{prefix}CREATE  {title}")
        if not dry:
            gh.ensure_label(
                args.label, description="Vorhergesagte Overwerder-Überflutung"
            )
            issue = gh.create_issue(title, body, [args.label])
            print(f"          -> #{issue['number']}")

    elif action.kind == "change":
        ev = action.event
        comment = alerts.change_comment(
            ev, action.prev_stufe, args.mention, gauge_zero_m_nhn=gauge_zero
        )
        body = alerts.issue_body(ev, args.mention, gauge_zero_m_nhn=gauge_zero)
        print(f"{prefix}CHANGE  #{action.number}  {action.prev_stufe} -> {ev.stufe}")
        if not dry:
            gh.update_issue(action.number, body=body)
            gh.comment(action.number, comment)

    elif action.kind == "touch":
        ev = action.event
        body = alerts.issue_body(ev, args.mention, gauge_zero_m_nhn=gauge_zero)
        print(f"{prefix}TOUCH   #{action.number}  (Fenster/Marker aktualisieren)")
        if not dry:
            gh.update_issue(action.number, body=body)

    elif action.kind == "retract":
        print(f"{prefix}RETRACT #{action.number}  (Entwarnung + schließen)")
        if not dry:
            gh.comment(action.number, alerts.retract_comment(args.mention))
            gh.update_issue(action.number, state="closed", state_reason="completed")

    elif action.kind == "passed":
        print(f"{prefix}PASSED  #{action.number}  (Scheitel vorbei + schließen)")
        if not dry:
            gh.comment(action.number, alerts.passed_comment())
            gh.update_issue(action.number, state="closed", state_reason="completed")


if __name__ == "__main__":
    main()
