#!/usr/bin/env python3
"""
enrich — backfill bonds.jsonl with authoritative metadata from OpenFIGI.

The scraper extracts CUSIP/ISIN/maturity from the filing text, but coupon often goes missing
(structured notes don't say "Notes due", preliminary 424B5s are blank). OpenFIGI maps each CUSIP ->
issuer name, ticker, marketSector, securityType, and a securityDescription like "AAPL 3 11/13/27"
that carries the canonical ticker / coupon / maturity. We use it to:
  - fill terms.coupons / terms.maturities where the regex missed them,
  - attach an issuer ticker + sector, and
  - flag structured notes (securityType ~ MTN / MEDIUM TERM) so the clean-corporate set is separable.

Free, no key: unauth OpenFIGI allows ~25 requests/min, <=10 jobs/request. Stdlib only.
Run: python3 enrich.py [--in bonds.jsonl] [--out bonds_enriched.jsonl]
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
import urllib.request

FIGI_URL = "https://api.openfigi.com/v3/mapping"
UA = "cutedsl-bondrag alexanderlnanda@gmail.com"
# securityDescription canonical form: "TICKER COUPON M/D/YY"; coupon may be decimal ("3.35"),
# whole ("0"), or a FRACTION FIGI-style ("11 1/4", "21 1/2"). Capture the coupon liberally.
_DESC = re.compile(r"^(\S+)\s+(\d+(?:\s+\d+/\d+)?(?:\.\d+)?)\s+(\d{1,2}/\d{1,2}/\d{2,4})")
# structured-note signals: issued by a finance-SPV / global-markets sub, an MTN/structured type, or a
# tell-tale contingent coupon (0% or an implausibly high "coupon" that's really a payoff multiplier).
# NB: match the SPV SUFFIXES ("Finance LLC", "Financial Company", "Global Markets") — NOT a bare
# "Financial", so real financial-sector issuers (Ally Financial Inc, Capital One Financial Corp) pass.
_STRUCT_ISSUER = re.compile(
    r"FINANCE\s+(LLC|CORP|CO\b|INC|N\.?V|B\.?V)|FINANCIAL\s+(COMPANY|PRODUCTS|CO\b)|"
    r"GLOBAL\s+MARKETS|FUNDING\s+(LLC|CORP|TRUST|INC)|STRUCTURED\s+PRODUCTS", re.I)
_STRUCT_TYPE = re.compile(r"\bMTN\b|MEDIUM[- ]TERM|STRUCTURED|MARKET[- ]LINKED|LINKED", re.I)
JOBS_PER_REQ = 10          # unauth job cap per request
REQ_INTERVAL = 2.6         # stay under 25 req/min unauth


def figi_map(cusips: list[str]) -> dict:
    """CUSIP -> first FIGI data dict (or {} if unmapped). Batched + throttled for unauth limits."""
    out: dict = {}
    uniq = [c for c in dict.fromkeys(cusips) if c]
    for i in range(0, len(uniq), JOBS_PER_REQ):
        batch = uniq[i:i + JOBS_PER_REQ]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c} for c in batch]).encode()
        req = urllib.request.Request(FIGI_URL, data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            print(f"  figi batch error: {e}", file=sys.stderr)
            res = [{} for _ in batch]
        for c, r in zip(batch, res):
            data = (r.get("data") or [{}]) if isinstance(r, dict) else [{}]
            out[c] = data[0] if data else {}
        if i + JOBS_PER_REQ < len(uniq):
            time.sleep(REQ_INTERVAL)
    return out


def _coupon(s: str):
    s = s.strip()
    try:
        if " " in s and "/" in s:                 # FIGI fraction form "11 1/4"
            whole, frac = s.split(" ", 1)
            n, d = frac.split("/")
            return round(float(whole) + float(n) / float(d), 4)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return None


def parse_desc(desc: str | None) -> dict:
    m = _DESC.match(desc or "")
    if not m:
        return {}
    return {"ticker": m.group(1), "coupon": _coupon(m.group(2)), "maturity": m.group(3)}


def is_structured(name: str | None, sec_type: str | None, coupon) -> bool:
    if _STRUCT_ISSUER.search(name or "") or _STRUCT_TYPE.search(sec_type or ""):
        return True
    if coupon is not None and (coupon == 0 or coupon >= 9):   # contingent / payoff-multiplier, not a real coupon
        return True
    return False


def enrich(rec: dict, figi: dict) -> dict:
    cusips = rec.get("cusips") or (rec.get("terms") or {}).get("cusips") or []
    d = next((figi[c] for c in cusips if figi.get(c) and figi[c].get("name")), None)
    if not d:
        return rec
    pd = parse_desc(d.get("securityDescription"))
    rec["figi"] = {"name": d.get("name"), "ticker": d.get("ticker") or pd.get("ticker"),
                   "sector": d.get("marketSector"), "security_type": d.get("securityType"),
                   "exch_code": d.get("exchCode"), "coupon": pd.get("coupon"), "maturity": pd.get("maturity")}
    rec["is_structured_note"] = is_structured(d.get("name"), d.get("securityType"), pd.get("coupon"))
    t = rec.setdefault("terms", {})
    if pd.get("coupon") is not None and not t.get("coupons"):
        t["coupons"] = [pd["coupon"]]
    if pd.get("maturity") and not t.get("maturities"):
        t["maturities"] = [pd["maturity"]]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="bonds.jsonl")
    ap.add_argument("--out", default="bonds_enriched.jsonl")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.inp)]
    all_cusips = [c for r in recs for c in (r.get("cusips") or (r.get("terms") or {}).get("cusips") or [])]
    print(f"# {len(recs)} records, {len(set(all_cusips))} unique CUSIPs -> OpenFIGI", file=sys.stderr)
    figi = figi_map(all_cusips)
    mapped = sum(1 for d in figi.values() if d.get("name"))

    enriched = [enrich(r, figi) for r in recs]
    with open(args.out, "w") as f:
        for r in enriched:
            f.write(json.dumps(r) + "\n")

    has_figi = [r for r in enriched if r.get("figi")]
    struct = sum(1 for r in has_figi if r.get("is_structured_note"))
    coup = sum(1 for r in has_figi if (r.get("terms") or {}).get("coupons"))
    print(f"# CUSIPs mapped by FIGI: {mapped}/{len(set(all_cusips))}", file=sys.stderr)
    print(f"# records enriched: {len(has_figi)}  ·  coupon now present: {coup}  ·  "
          f"structured notes flagged: {struct}  ·  clean corporates: {len(has_figi) - struct}", file=sys.stderr)
    print(f"# wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
