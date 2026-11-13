#!/usr/bin/env python3
"""One-off correction for the DC Roofing LLC portal lead: the research round
placed it in Tyler, TX, but the business behind dcroofingllc.com is Shawn
Dunbar's D.C. Roofing LLC in St. Ann, MO (his own card and flyer on the site).
Runs in GitHub Actions with SUPABASE_SERVICE_KEY; key is never printed."""
import json, os, sys, urllib.request, urllib.parse

URL = "https://zvvbihatmrlgfpwdrpxg.supabase.co"

def api(method, path, key, payload=None):
    req = urllib.request.Request(URL + path, method=method)
    req.add_header("apikey", key); req.add_header("Authorization", f"Bearer {key}")
    data = None
    if payload is not None:
        data = json.dumps(payload).encode(); req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "return=representation")
    with urllib.request.urlopen(req, data=data, timeout=60) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else None

def main():
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not key:
        print("SUPABASE_SERVICE_KEY not set; skipping."); return 0
    name = urllib.parse.quote("DC Roofing LLC", safe="")
    patch = {
        "city": "St. Ann, MO",
        "phone": "(618) 671-2658",
        "rating_text": "",
        "note": ("Owner Shawn Dunbar, St. Ann, MO. Family owned, 34 years experience per his own story, fully insured, "
                 "certified Mule-Hide, Dec Tech and CertainTeed, free estimates. Whole website is one GoDaddy page; key trust "
                 "facts sit inside a flyer image at the bottom that Google cannot read. Email: dcroofing97@gmail.com (own website "
                 "footer). CORRECTION Nov 14: the Tyler, TX listing data (903 phone, 5.0 stars, 16 reviews) was an aggregator "
                 "mix-up and is not trusted. Mockups built by Hassan: devstagings brand guideline, homepage and request-a-quote pages. "
                 "Outreach draft prepared Nov 14, not sent."),
    }
    out = api("PATCH", f"/rest/v1/leads?business_name=eq.{name}", key, patch)
    print("Patched rows:", len(out) if out else 0)
    if out:
        print("Now:", out[0]["business_name"], "|", out[0]["city"], "|", out[0]["phone"])
    return 0

if __name__ == "__main__":
    sys.exit(main())
