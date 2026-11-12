#!/usr/bin/env python3
"""Sync outreach send results into the Supabase Lead Command Center.

The GitHub sender (send_emails.py) records sends in statuses.json. This
script mirrors that truth into the team portal database:

  * every lead marked sent in statuses.json becomes status='sent' in the
    portal, with its queue position cleared
  * leads still in send_queue.json get their portal queue_position
    renumbered to match the queue order (1..N)

It needs the Supabase service key in the SUPABASE_SERVICE_KEY environment
variable (a GitHub Actions secret). Without it, the script prints a skip
message and exits 0, so it can never break the send workflow.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS_FILE = ROOT / "statuses.json"
QUEUE_FILE = ROOT / "send_queue.json"

SUPABASE_URL = "https://zvvbihatmrlgfpwdrpxg.supabase.co"


def api(method, path, key, body=None):
    req = urllib.request.Request(
        SUPABASE_URL + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )
    with urllib.request.urlopen(req) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else []


def main() -> int:
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not key:
        print("Portal sync skipped: SUPABASE_SERVICE_KEY is not set.")
        return 0

    status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    sent_names = {
        name.strip().lower()
        for name, val in status.get("overrides", {}).items()
        if val == "sent"
    }
    bounces = {
        name.strip().lower(): info
        for name, info in status.get("bounces", {}).items()
    }
    queue_order = {q["name"].strip().lower(): i + 1 for i, q in enumerate(queue)}

    try:
        leads = api(
            "GET",
            "/rest/v1/leads?select=id,business_name,status,queue_position&limit=1000",
            key,
        )
    except urllib.error.HTTPError as e:
        print(f"Portal sync failed reading leads: HTTP {e.code} {e.read().decode()[:200]}")
        return 1

    flipped, renumbered, unmatched_sent, bounced_applied = [], [], [], []
    seen_sent = set()
    for lead in leads:
        name_key = lead["business_name"].strip().lower()
        if name_key in bounces:
            info = bounces[name_key]
            patch = {
                "bounce_date": str(info.get("date", "")),
                "bounce_reason": str(info.get("reason", "")),
            }
            if info.get("hard"):
                patch["status"] = "dropped"
                patch["queue_position"] = None
            api("PATCH", f"/rest/v1/leads?id=eq.{lead['id']}", key, patch)
            bounced_applied.append(lead["business_name"])
        if name_key in sent_names:
            seen_sent.add(name_key)
            hard_bounced = name_key in bounces and bounces[name_key].get("hard")
            if lead["status"] != "sent" and not hard_bounced:
                api(
                    "PATCH",
                    f"/rest/v1/leads?id=eq.{lead['id']}",
                    key,
                    {"status": "sent", "queue_position": None},
                )
                flipped.append(lead["business_name"])
        elif name_key in queue_order:
            want = queue_order[name_key]
            if lead.get("queue_position") != want:
                api(
                    "PATCH",
                    f"/rest/v1/leads?id=eq.{lead['id']}",
                    key,
                    {"queue_position": want},
                )
                renumbered.append(f"{lead['business_name']} -> #{want}")

    for name_key in sent_names:
        if name_key not in seen_sent:
            unmatched_sent.append(name_key)

    print(f"Portal sync done. Leads read: {len(leads)}.")
    print(f"Bounce records applied: {len(bounced_applied)} {bounced_applied if bounced_applied else ''}")
    print(f"Marked sent in portal: {len(flipped)} {flipped if flipped else ''}")
    print(f"Queue positions renumbered: {len(renumbered)} {renumbered if renumbered else ''}")
    if unmatched_sent:
        print(f"Sent in statuses.json but not found in portal: {unmatched_sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
