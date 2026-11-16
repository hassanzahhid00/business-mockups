#!/usr/bin/env python3
"""Render redesign pages to single tall-page PDFs with headless Chromium.

Reads pdfs_manifest.json: [{source, out}]. Source is a repo-relative HTML
file or an https URL. Each PDF is one long page (full scroll height, capped)
so the whole homepage design is visible in a single attachment.
Runs in GitHub Actions (prep-pdfs workflow) with Playwright Chromium.
"""
import json, shutil, subprocess, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
MAX_H = 12000

def compress(pdf: Path) -> None:
    """Downsample images with ghostscript so attachments stay email-sized."""
    gs = shutil.which("gs")
    if not gs:
        print("ghostscript not found, skipping compression")
        return
    tmp = pdf.with_suffix(".tmp.pdf")
    subprocess.run(
        [gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
         "-dPDFSETTINGS=/ebook", "-dNOPAUSE", "-dQUIET", "-dBATCH",
         f"-sOutputFile={tmp}", str(pdf)],
        check=False, timeout=300,
    )
    if tmp.exists() and 0 < tmp.stat().st_size < pdf.stat().st_size:
        tmp.replace(pdf)
    elif tmp.exists():
        tmp.unlink()

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
            # Pages hide sections behind scroll-reveal animations (opacity 0
            # until an IntersectionObserver adds a visible class). A PDF
            # printed without scrolling captures those sections blank, so
            # scroll through the whole page first, then force every reveal
            # element visible before printing.
            page.evaluate(
                """async () => {
                    const step = Math.floor(window.innerHeight * 0.8);
                    const max = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
                    for (let y = 0; y <= max; y += step) {
                        window.scrollTo(0, y);
                        await new Promise(r => setTimeout(r, 120));
                    }
                    window.scrollTo(0, max);
                    await new Promise(r => setTimeout(r, 500));
                    window.scrollTo(0, 0);
                }"""
            )
            page.evaluate("document.querySelectorAll('.reveal').forEach(el => el.classList.add('in'))")
            page.add_style_tag(content=".reveal{opacity:1 !important;transform:none !important;transition:none !important;}")
            page.wait_for_timeout(600)
            h = page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
            h = min(int(h), MAX_H)
            out = HERE / m["out"]
            out.parent.mkdir(parents=True, exist_ok=True)
            page.pdf(path=str(out), width="1280px", height=f"{h}px", print_background=True, page_ranges="1")
            page.close()
            before = out.stat().st_size
            compress(out)
            print(f"Rendered {m['out']} ({before // 1024} KB -> {out.stat().st_size // 1024} KB, height {h}px)")
        browser.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
