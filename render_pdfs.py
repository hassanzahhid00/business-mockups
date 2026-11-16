#!/usr/bin/env python3
"""Render redesign pages to single tall-page PDFs with headless Chromium.

Reads pdfs_manifest.json: [{source, out}]. Source is a repo-relative HTML
file or an https URL. Each PDF is one long page (full scroll height, capped)
so the whole homepage design is visible in a single attachment.
Runs in GitHub Actions (prep-pdfs workflow) with Playwright Chromium.
"""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
MAX_H = 12000

def main():
    manifest = json.loads((HERE / "pdfs_manifest.json").read_text())
    todo = [m for m in manifest if (m["source"].startswith("http") or (HERE / m["source"]).exists())]
    skipped = [m["out"] for m in manifest if m not in todo]
    for s in skipped:
        print(f"SKIP (source missing): {s}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for m in todo:
            src = m["source"]
            url = src if src.startswith("http") else (HERE / src).as_uri()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1500)
            h = page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
            h = min(int(h), MAX_H)
            out = HERE / m["out"]
            out.parent.mkdir(parents=True, exist_ok=True)
            page.pdf(path=str(out), width="1280px", height=f"{h}px", print_background=True, page_ranges="1")
            page.close()
            print(f"Rendered {m['out']} ({out.stat().st_size // 1024} KB, height {h}px)")
        browser.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
