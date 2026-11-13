#!/usr/bin/env python3
"""One-off importer: adds the Low Review Batch leads (low_review_import.json)
to the Lead Command Center portal (Supabase).

Runs inside GitHub Actions where SUPABASE_SERVICE_KEY is available as an
environment variable (repo secret). The key is never printed or committed.
Idempotent: leads whose business_name already exists in the portal are
skipped, so re-running never creates duplicates.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

SUPABASE_URL = "https://zvvbihatmrlgfpwdrpxg.supabase.co"
DATA_FILE = Path(__file__).with_name("low_review_import.json")


def api(method, path, key, payload=None, prefer=None):
    req = urllib.request.Request(SUPABASE_URL + path, method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    if prefer:
        req.add_header("Prefer", prefer)
    with urllib.request.urlopen(req, data=data, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else None


def main():
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not key:
        print("SUPABASE_SERVICE_KEY not set; skipping import.")
        return 0

    leads_in = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    profiles = api("GET", "/rest/v1/profiles?select=id,email,full_name,role", key)
    owner = next((p for p in profiles if p.get("role") == "admin"), None)
    if owner is None:
        print("No admin profile found; cannot assign lead ownership.")
        return 1
    print(f"Owner: {owner['full_name']} ({owner['email']})")

    existing = api("GET", "/rest/v1/leads?select=business_name&limit=1000", key)
    existing_names = {row["business_name"].strip().lower() for row in existing}
    print(f"Portal leads before: {len(existing)}")

    to_insert, skipped = [], []
    for lead in leads_in:
        if lead["business_name"].strip().lower() in existing_names:
            skipped.append(lead["business_name"])
        else:
            to_insert.append({**lead, "owner_id": owner["id"]})

    if to_insert:
        api("POST", "/rest/v1/leads", key, to_insert, prefer="return=minimal")
    print(f"Inserted: {len(to_insert)}")
    print(f"Skipped (already present): {len(skipped)} {skipped if skipped else ''}")

    batch = api(
        "GET",
        "/rest/v1/leads?select=id&campaign=eq.Low%20Review%20Batch&limit=1000",
        key,
    )
    total = api("GET", "/rest/v1/leads?select=id&limit=2000", key)
    print(f"Low Review Batch leads in portal now: {len(batch)}")
    print(f"Total portal leads now: {len(total)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
