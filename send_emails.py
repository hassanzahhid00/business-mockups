#!/usr/bin/env python3
"""Send queued outreach emails via PurelyMail SMTP.

Reads send_queue.json (list of {name, to, subject, body}) and statuses.json
({overrides, sentCounts, log}) from this folder. Enforces the daily cap of 5
sends per Asia/Karachi day unless --override is passed. On success a lead is
removed from the queue, marked sent in statuses.json, and logged.

Credentials come from environment variables only:
  PURELYMAIL_USER            full email address
  PURELYMAIL_APP_PASSWORD    PurelyMail app password (or account password)

Usage:
  python3 send_emails.py [--lead "Business Name"] [--limit N] [--override] [--dry-run]
"""
import argparse
import html
import imaplib
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUEUE_FILE = HERE / "send_queue.json"
STATUS_FILE = HERE / "statuses.json"
BACKFILL_FILE = HERE / "backfill_queue.json"
SMTP_HOST = "smtp.purelymail.com"
SMTP_PORT = 465
IMAP_HOST = "imap.purelymail.com"
IMAP_PORT = 993
DAILY_CAP = 5
PKT = timezone(timedelta(hours=5))

SIGNATURE_HTML = r"""<table cellpadding="0" cellspacing="0" border="0" role="presentation" style="width:560px;max-width:560px;font-family:Arial,Helvetica,sans-serif;">
  <tr>
    <td style="background-color:#ffffff;border:1px solid #e2e4e8;border-radius:14px;padding:24px 26px;">
      <table cellpadding="0" cellspacing="0" border="0" role="presentation" width="100%">
        <tr>
          <td valign="middle" style="width:124px;">
            <img src="https://raw.githubusercontent.com/hassanzahhid00/email-signature/main/hassan-zahid-profile.jpg" width="112" height="112" alt="Hassan Zahid" style="display:block;width:112px;height:112px;border-radius:50%;border:3px solid #D8232A;object-fit:cover;">
          </td>
          <td valign="middle" style="width:24px;border-left:1px solid #e6e7ea;font-size:0;line-height:0;">&nbsp;</td>
          <td valign="middle" style="width:1px;background-color:#D8232A;font-size:0;line-height:0;">&nbsp;</td>
          <td valign="middle" style="width:24px;font-size:0;line-height:0;">&nbsp;</td>
          <td valign="middle">
            <div style="font-size:24px;line-height:28px;font-weight:700;color:#111114;">Hassan Zahid</div>
            <div style="font-size:12px;line-height:17px;font-weight:700;color:#D8232A;letter-spacing:1.2px;text-transform:uppercase;padding-top:4px;">Business Development Executive</div>
            <div style="font-size:13.5px;line-height:19px;color:#5B6068;padding-top:4px;">Developers Hub (Pvt.) Ltd</div>
            <div style="font-size:13px;line-height:18px;color:#5B6068;">Helping companies scale revenue through strategic B2B outreach</div>
            <div style="padding-top:10px;"><a href="https://developers-hub.com/contact-us/" target="_blank" rel="noopener" style="font-size:13px;font-weight:700;color:#D8232A;text-decoration:none;">Get a Free Proposal &rarr;</a></div>
          </td>
        </tr>
      </table>
      <table cellpadding="0" cellspacing="0" border="0" role="presentation" width="100%" style="margin-top:20px;border-top:1px solid #ececf0;">
        <tr>
          <td valign="middle" style="padding-top:16px;">
            <a href="https://developers-hub.com" target="_blank" rel="noopener" style="text-decoration:none;"><img src="https://developers-hub.com/assets/logo-color.png" width="138" alt="Developers Hub" style="display:block;border:0;"></a>
          </td>
          <td valign="middle" align="right" style="padding-top:16px;">
            <table cellpadding="0" cellspacing="0" border="0" role="presentation" align="right">
              <tr>
                <td><a href="tel:+923245507922" target="_blank" rel="noopener" style="display:block;text-decoration:none;"><img src="https://raw.githubusercontent.com/hassanzahhid00/email-signature/main/phone.png" width="28" height="28" alt="Call +92 324 5507922" style="display:block;border:0;"></a></td>
                <td style="width:6px;font-size:0;">&nbsp;</td>
                <td><a href="https://wa.me/923245507922" target="_blank" rel="noopener" style="display:block;text-decoration:none;"><img src="https://raw.githubusercontent.com/hassanzahhid00/email-signature/main/whatsapp.png" width="28" height="28" alt="WhatsApp" style="display:block;border:0;"></a></td>
                <td style="width:6px;font-size:0;">&nbsp;</td>
                <td><a href="mailto:info@developers-hub.com" target="_blank" rel="noopener" style="display:block;text-decoration:none;"><img src="https://raw.githubusercontent.com/hassanzahhid00/email-signature/main/email.png" width="28" height="28" alt="Email" style="display:block;border:0;"></a></td>
                <td style="width:6px;font-size:0;">&nbsp;</td>
                <td><a href="https://developers-hub.com" target="_blank" rel="noopener" style="display:block;text-decoration:none;"><img src="https://raw.githubusercontent.com/hassanzahhid00/email-signature/main/website.png" width="28" height="28" alt="Website" style="display:block;border:0;"></a></td>
                <td style="width:6px;font-size:0;">&nbsp;</td>
                <td><a href="https://www.linkedin.com/in/hassanzahid00" target="_blank" rel="noopener" style="display:block;text-decoration:none;"><img src="https://raw.githubusercontent.com/hassanzahhid00/email-signature/main/linkedin.png" width="28" height="28" alt="LinkedIn" style="display:block;border:0;"></a></td>
                <td style="width:6px;font-size:0;">&nbsp;</td>
                <td><a href="https://www.facebook.com/developershub.hq" target="_blank" rel="noopener" style="display:block;text-decoration:none;"><img src="https://raw.githubusercontent.com/hassanzahhid00/email-signature/main/facebook.png" width="28" height="28" alt="Facebook" style="display:block;border:0;"></a></td>
                <td style="width:6px;font-size:0;">&nbsp;</td>
                <td><a href="https://www.instagram.com/developershub.hq/" target="_blank" rel="noopener" style="display:block;text-decoration:none;"><img src="https://raw.githubusercontent.com/hassanzahhid00/email-signature/main/instagram.png" width="28" height="28" alt="Instagram" style="display:block;border:0;"></a></td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td colspan="2" style="padding-top:12px;font-size:11px;line-height:15px;color:#8a8f98;">
            <strong style="color:#6b7078;">London Office:</strong> Suite LP64453, 20 Wenlock Road, London N1 7GU &nbsp;·&nbsp; +44 7491 951577
          </td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding:10px 6px 0 6px;font-size:9.5px;line-height:13px;color:#9aa0a8;">
      This email and any attachments are confidential and intended solely for the named recipient. If you have received it in error, please notify the sender and delete it.
    </td>
  </tr>
</table>"""


def body_to_html(plain: str) -> str:
    # The body stays regular text: plain paragraphs with simple line breaks,
    # no fonts, colors or styling of any kind. The ONLY designed HTML in the
    # email is the signature, appended after the body.
    paras = [p.strip() for p in plain.strip().split("\n\n") if p.strip()]
    parts = []
    for p in paras:
        safe = html.escape(p).replace("\n", "<br>")
        parts.append("<p>" + safe + "</p>")
    return "".join(parts) + SIGNATURE_HTML


def build_message(user: str, item: dict, when: datetime) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"Hassan Zahid <{user}>"
    msg["To"] = item["to"]
    msg["Subject"] = item["subject"]
    msg["Date"] = format_datetime(when)
    msg.set_content(item["body"])
    msg.add_alternative(body_to_html(item["body"]), subtype="html")
    return msg


def find_sent_folder(imap: imaplib.IMAP4_SSL) -> str:
    typ, folders = imap.list()
    names = []
    for raw in folders or []:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        m = re.search(r'"([^"]+)"\s*$', line)
        if m:
            names.append(m.group(1))
    for cand in names:
        if cand == "Sent":
            return cand
    for cand in names:
        leaf = cand.replace("\\", "/").split("/")[-1].strip().lower()
        if leaf in ("sent", "sent items", "sent mail"):
            return cand
    return "Sent"


def append_to_sent(user: str, password: str, items: list) -> None:
    """items: list of (raw_message_bytes, datetime_utc, label). Files copies in Sent."""
    if not items:
        return
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context())
    try:
        imap.login(user, password)
        folder = find_sent_folder(imap)
        for raw, when, label in items:
            typ, _ = imap.append(folder, "\\Seen", imaplib.Time2Internaldate(when), raw)
            print(f"Sent copy filed ({folder}): {label} -> {typ}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def run_backfill(user: str, password: str) -> int:
    items = json.loads(BACKFILL_FILE.read_text(encoding="utf-8"))
    if not items:
        print("Backfill queue is empty. Nothing to file.")
        return 0
    prepared = []
    for it in items:
        when = datetime.fromisoformat(it["date"].replace("Z", "+00:00"))
        msg = build_message(user, it, when)
        prepared.append((msg.as_bytes(), when, f"{it['name']} <{it['to']}>"))
    append_to_sent(user, password, prepared)
    BACKFILL_FILE.write_text("[]\n", encoding="utf-8")
    print(f"Backfill done: {len(prepared)} copies filed in Sent.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead", default="", help="Send only this business name")
    ap.add_argument("--limit", type=int, default=DAILY_CAP)
    ap.add_argument("--override", action="store_true", help="Ignore the daily cap")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backfill", action="store_true", help="Only file queued Sent copies via IMAP")
    args = ap.parse_args()

    if args.backfill:
        user = os.environ.get("PURELYMAIL_USER", "")
        password = os.environ.get("PURELYMAIL_APP_PASSWORD", "")
        if not user or not password:
            print("Missing PURELYMAIL_USER or PURELYMAIL_APP_PASSWORD environment variables.", file=sys.stderr)
            return 3
        return run_backfill(user, password)

    queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    status.setdefault("overrides", {})
    status.setdefault("sentCounts", {})
    status.setdefault("log", [])

    today = datetime.now(PKT).strftime("%Y-%m-%d")
    already = int(status["sentCounts"].get(today, 0))

    if not args.dry_run:
        status["lastRunAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        status["lastRunNote"] = (
            f"Send run: lead={args.lead or 'next batch'}, override={args.override}"
        )
        STATUS_FILE.write_text(
            json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if args.lead:
        targets = [q for q in queue if q["name"].lower() == args.lead.strip().lower()]
        if not targets:
            print(f"Lead not found in queue: {args.lead!r}")
            print("Queue:", ", ".join(q["name"] for q in queue) or "(empty)")
            return 2
    else:
        targets = queue[: args.limit]

    if not args.override:
        allowed = max(0, DAILY_CAP - already)
        if allowed == 0:
            print(
                f"Daily cap reached: {already} emails already sent today ({today} PKT). "
                "Nothing sent. Re-run with override to go beyond the cap."
            )
            return 0
        if len(targets) > allowed:
            print(f"Daily cap: only {allowed} more send(s) allowed today. Trimming batch.")
            targets = targets[:allowed]

    print(f"Plan: send {len(targets)} email(s) (already sent today: {already}, cap: {DAILY_CAP}, override: {args.override})")
    for t in targets:
        print(f"  -> {t['name']} <{t['to']}> : {t['subject']}")

    if args.dry_run:
        print("Dry run only. Nothing sent, no files changed.")
        return 0

    user = os.environ.get("PURELYMAIL_USER", "")
    password = os.environ.get("PURELYMAIL_APP_PASSWORD", "")
    if not user or not password:
        print("Missing PURELYMAIL_USER or PURELYMAIL_APP_PASSWORD environment variables.", file=sys.stderr)
        return 3

    sent_names = []
    sent_copies = []
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=60) as smtp:
        smtp.login(user, password)
        for t in targets:
            when = datetime.now(timezone.utc)
            msg = build_message(user, t, when)
            smtp.send_message(msg)
            sent_names.append(t["name"])
            sent_copies.append((msg.as_bytes(), when, f"{t['name']} <{t['to']}>"))
            print(f"Sent: {t['name']} <{t['to']}>")

    if sent_copies:
        try:
            append_to_sent(user, password, sent_copies)
        except Exception as exc:
            print(f"WARNING: emails sent, but filing copies in Sent failed: {exc}")

    if sent_names:
        queue = [q for q in queue if q["name"] not in sent_names]
        QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
        for name in sent_names:
            status["overrides"][name] = "sent"
            entry = next(q for q in targets if q["name"] == name)
            status["log"].append(
                {"name": name, "to": entry["to"], "date": today, "via": "github-actions"}
            )
        status["sentCounts"][today] = already + len(sent_names)
        STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Done. {len(sent_names)} sent. Queue now has {len(queue)} lead(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
