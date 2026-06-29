#!/usr/bin/env python3
"""
bondsec — scrape new corporate-bond filings from SEC EDGAR for a date window,
download the documents, extract per-tranche terms (CUSIP / coupon / maturity),
link each bond to its indenture (the EX-4 legal contract), and emit a
store-agnostic normalized record per bond.

Stdlib only (urllib) so it runs with no pip install. SEC requires a descriptive
User-Agent (name + email) on every request or it 403s; we set one and self-throttle
to stay well under SEC's 10 req/s fair-access cap.

Pipeline (matches the verified EDGAR mechanics):
  1. DISCOVER  : EFTS full-text-search firehose, filtered by form + date window.
                 forms=424B5,FWP,424B3 -> clean corporate bonds; 424B2 -> structured-note tail (counted only).
  2. FETCH     : build Archives URL from each hit's {accession}:{file} id, download the doc.
  3. EXTRACT   : strip HTML, regex out CUSIP / ISIN / coupon / maturity / principal per tranche.
  4. LINK      : for each issuer CIK, find the nearby 8-K whose EX-4 exhibit is the indenture.
  5. NORMALIZE : write one JSON record per bond to bonds.jsonl (the single source of truth
                 you load into DuckDB / a graph DB / an embedding-training set later).
"""
from __future__ import annotations
import argparse, gzip, io, json, re, sys, time, urllib.request, urllib.error
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

# --- config ------------------------------------------------------------------
UA = "cutedsl-bondrag alexanderlnanda@gmail.com"   # SEC-mandated: name + contact email
EFTS = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
SUBMISSIONS = "https://data.sec.gov/submissions"
MIN_INTERVAL = 0.18                                 # ~5.5 req/s, safely under the 10 req/s cap
CLEAN_BOND_FORMS = ["424B5", "FWP", "424B3"]        # corporate-bond signal
STRUCTURED_FORMS = ["424B2"]                         # mostly bank structured notes (count only)

_last_req = [0.0]


def _throttle():
    dt = time.time() - _last_req[0]
    if dt < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - dt)
    _last_req[0] = time.time()


def fetch(url: str, tries: int = 4) -> bytes:
    """GET with the SEC UA, gzip, throttle, and retry on 403/429/500 (EFTS cold-starts 500)."""
    for attempt in range(tries):
        _throttle()
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json, text/html, */*",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 500, 503) and attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"failed: {url}")


def efts(q: str = "", forms: str = "", startdt: str = "", enddt: str = "",
         ciks: str = "", frm: int = 0) -> dict:
    parts = [f"q={urllib.parse.quote(q)}"]
    if forms:   parts.append(f"forms={forms}")
    if startdt: parts.append(f"startdt={startdt}")
    if enddt:   parts.append(f"enddt={enddt}")
    if ciks:    parts.append(f"ciks={ciks}")
    if frm:     parts.append(f"from={frm}")
    return json.loads(fetch(f"{EFTS}?{'&'.join(parts)}"))


# --- discovery ---------------------------------------------------------------
@dataclass
class Hit:
    accession: str          # 0001140361-24-040979
    file: str               # ny20035638x10_fwp.htm
    cik: str                # primary filer CIK (no leading zeros)
    form: str
    filing_date: str
    issuer: str

    @property
    def doc_url(self) -> str:
        return f"{ARCHIVES}/{self.cik}/{self.accession.replace('-', '')}/{self.file}"

    @property
    def index_url(self) -> str:
        return f"{ARCHIVES}/{self.cik}/{self.accession.replace('-', '')}/index.json"


def _parse_hits(resp: dict) -> list[Hit]:
    out = []
    for h in resp.get("hits", {}).get("hits", []):
        _id = h.get("_id", "")
        if ":" not in _id:
            continue
        acc, fname = _id.split(":", 1)
        s = h.get("_source", {})
        ciks = s.get("ciks", []) or ["0"]
        names = s.get("display_names", []) or [""]
        out.append(Hit(acc, fname, str(int(ciks[0])), s.get("form", ""),
                       s.get("file_date", ""), names[0]))
    return out


def discover(forms: str, startdt: str, enddt: str, max_pages: int = 50) -> tuple[int, list[Hit]]:
    """Return (total_count, hits[]). Pages through EFTS (100/page) up to max_pages."""
    first = efts(forms=forms, startdt=startdt, enddt=enddt)
    total = first.get("hits", {}).get("total", {}).get("value", 0)
    hits = _parse_hits(first)
    page = 100
    while len(hits) < total and page // 100 < max_pages and page < 10000:
        hits += _parse_hits(efts(forms=forms, startdt=startdt, enddt=enddt, frm=page))
        page += 100
    return total, hits


# --- extraction --------------------------------------------------------------
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t ]+")
# "CUSIP" then, within ~60 chars, a 9-char code (often spaced at offset 6: "42824C BR9")
_CUSIP_NEAR = re.compile(r"CUSIP[^0-9A-Z]{0,60}?([0-9A-Z]{6}[ ]?[0-9A-Z]{2}[ ]?[0-9A-Z])\b")
_ISIN = re.compile(r"\b([A-Z]{2}[0-9A-Z]{9}[0-9])\b")
# coupon: a percentage, optional qualifiers (Fixed-to-Floating Rate, Senior, ...), then "Notes due"
_COUPON = re.compile(r"(\d{1,2}(?:\.\d{1,4})?)\s*%[^.\n]{0,45}?Notes?\s+due", re.I)
_RATE = re.compile(r"Interest\s+Rate[\s:]*(?:of\s+)?([0-9]{1,2}\.[0-9]{1,4})\s*%", re.I)
_MATURITY = re.compile(r"(?:Maturity\s+Date|Notes?\s+due|will\s+mature\s+on)[\s:]*"
                       r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4})", re.I)
_PRINCIPAL = re.compile(r"\$\s?([\d,]{7,})\s+(?:aggregate\s+)?(?:principal\s+amount\s+(?:of\s+)?)?(?:[0-9.]+%\s+)?[\w\- ]{0,40}?Notes?", re.I)


def cusip_from_isin(isin: str) -> str | None:
    """US/CA ISINs embed the 9-char CUSIP: ISIN = CC + CUSIP(9) + check(1)."""
    return isin[2:11] if isin[:2] in ("US", "CA") and len(isin) == 12 else None


def html_to_text(raw: bytes) -> str:
    txt = raw.decode("utf-8", "ignore")
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", txt, flags=re.S | re.I)
    txt = _TAG.sub(" ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&#160;", " ").replace("&#39;", "'").replace("&rsquo;", "'"))
    return _WS.sub(" ", txt)


def extract_terms(text: str) -> dict:
    isins = sorted({m.group(1) for m in _ISIN.finditer(text) if m.group(1)[:2].isalpha()})
    cusips = {m.group(1).replace(" ", "") for m in _CUSIP_NEAR.finditer(text)}
    cusips |= {c for c in (cusip_from_isin(i) for i in isins) if c}   # derive from US/CA ISINs
    cusips = sorted(cusips)
    coupons = sorted({float(m.group(1)) for m in _COUPON.finditer(text)} |
                     {float(m.group(1)) for m in _RATE.finditer(text)})
    mats = [m.group(1) for m in _MATURITY.finditer(text)]
    principal = None
    pm = _PRINCIPAL.search(text)
    if pm:
        principal = int(pm.group(1).replace(",", ""))
    # crude bond classifier: must look like a notes/indenture offering
    is_bond = bool(re.search(r"\b(Senior\s+Notes?|Subordinated\s+Notes?|% Notes? due|Indenture|principal amount)\b", text, re.I))
    return {
        "cusips": cusips,
        "isins": isins[:8],
        "coupons": coupons,
        "maturities": list(dict.fromkeys(mats))[:8],
        "principal": principal,
        "is_bond_like": is_bond,
    }


# --- indenture linkage -------------------------------------------------------
def find_indenture(cik: str, around: str, window_days: int = 45) -> dict | None:
    """Best-effort: find the issuer's 8-K mentioning 'indenture' near the offering date,
    then locate an EX-4 exhibit in that accession (the legal bond contract)."""
    cik10 = cik.zfill(10)
    d = date.fromisoformat(around)
    lo, hi = (d - timedelta(days=window_days)).isoformat(), (d + timedelta(days=7)).isoformat()
    try:
        resp = efts(q='"indenture"', forms="8-K", ciks=cik10, startdt=lo, enddt=hi)
    except Exception:
        return None
    hits = _parse_hits(resp)
    if not hits:
        return None
    h = hits[0]
    try:
        idx = json.loads(fetch(h.index_url))
    except Exception:
        return {"accession": h.accession, "exhibit": "?", "url": h.doc_url, "note": "8-K found, exhibit list unavailable"}
    ex4 = None
    for item in idx.get("directory", {}).get("item", []):
        nm = item.get("name", "")
        if re.search(r"ex-?4|ex4|indenture", nm, re.I):
            ex4 = nm
            break
    base = f"{ARCHIVES}/{h.cik}/{h.accession.replace('-', '')}"
    return {
        "accession": h.accession,
        "filing_date": h.filing_date,
        "exhibit_file": ex4,
        "url": f"{base}/{ex4}" if ex4 else f"{base}/",
        "found_via": 'EFTS 8-K q="indenture"',
    }


# --- normalized record -------------------------------------------------------
@dataclass
class BondRecord:
    bond_id: str
    cusips: list
    isins: list
    issuer_name: str
    cik: str
    form_type: str
    filing_date: str
    accession: str
    primary_doc_url: str
    terms: dict
    indenture: dict | None
    raw_text_path: str | None
    metadata: dict = field(default_factory=dict)
    relationships: list = field(default_factory=list)   # filled later by Gemma pairwise pass


def build_record(h: Hit, save_raw_dir: str | None, link_indenture: bool) -> BondRecord:
    raw_path = None
    terms = {}
    try:
        raw = fetch(h.doc_url)
        text = html_to_text(raw)
        terms = extract_terms(text)
        if save_raw_dir:
            safe = h.file.replace("/", "_")
            raw_path = f"{save_raw_dir}/{h.accession.replace('-', '')}_{safe}"
            with open(raw_path, "wb") as f:
                f.write(raw)
    except Exception as e:
        terms = {"error": str(e)}
    indenture = None
    if link_indenture and terms.get("is_bond_like"):
        indenture = find_indenture(h.cik, h.filing_date)
    bid = (terms.get("cusips") or [f"{h.accession}"])[0]
    return BondRecord(
        bond_id=bid, cusips=terms.get("cusips", []), isins=terms.get("isins", []),
        issuer_name=h.issuer, cik=h.cik, form_type=h.form, filing_date=h.filing_date,
        accession=h.accession, primary_doc_url=h.doc_url, terms=terms,
        indenture=indenture, raw_text_path=raw_path,
        metadata={"discovered_via": f"EFTS forms={h.form}"},
    )


# --- CLI ---------------------------------------------------------------------
def week_window(end: str | None) -> tuple[str, str]:
    e = date.fromisoformat(end) if end else date.today()
    return (e - timedelta(days=6)).isoformat(), e.isoformat()


def main():
    ap = argparse.ArgumentParser(description="Scrape past-week corporate bonds from SEC EDGAR.")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--forms", default=",".join(CLEAN_BOND_FORMS),
                    help="comma list of forms to fully fetch (default: clean corporate bonds)")
    ap.add_argument("--max-docs", type=int, default=8, help="cap doc downloads (politeness/demo)")
    ap.add_argument("--no-indenture", action="store_true", help="skip indenture linkage")
    ap.add_argument("--out", default="bonds.jsonl")
    ap.add_argument("--save-raw", action="store_true")
    args = ap.parse_args()

    if args.start and args.end:
        startdt, enddt = args.start, args.end
    else:
        startdt, enddt = week_window(args.end)

    print(f"# window {startdt} .. {enddt}", file=sys.stderr)
    # cheap counts for the whole bond universe (incl the structured-note tail)
    for f in args.forms.split(",") + STRUCTURED_FORMS:
        try:
            tot = efts(forms=f, startdt=startdt, enddt=enddt).get("hits", {}).get("total", {}).get("value", 0)
            print(f"#   {f:8s} total filings in window: {tot}", file=sys.stderr)
        except Exception as e:
            print(f"#   {f:8s} count error: {e}", file=sys.stderr)

    total, hits = discover(args.forms, startdt, enddt)
    print(f"# discovered {len(hits)} hits across forms={args.forms} (reported total {total})", file=sys.stderr)

    save_dir = "data/raw" if args.save_raw else None
    n = 0
    with open(args.out, "w") as out:
        for h in hits:
            if n >= args.max_docs:
                # still emit a lightweight stub (no download) so the firehose set is complete
                rec = BondRecord(bond_id=h.accession, cusips=[], isins=[], issuer_name=h.issuer,
                                 cik=h.cik, form_type=h.form, filing_date=h.filing_date,
                                 accession=h.accession, primary_doc_url=h.doc_url, terms={"_stub": True},
                                 indenture=None, raw_text_path=None,
                                 metadata={"discovered_via": f"EFTS forms={h.form}", "downloaded": False})
                out.write(json.dumps(asdict(rec)) + "\n")
                continue
            rec = build_record(h, save_dir, link_indenture=not args.no_indenture)
            out.write(json.dumps(asdict(rec)) + "\n")
            t = rec.terms
            print(f"  [{rec.form_type}] {rec.filing_date} {rec.issuer_name[:42]:42s} "
                  f"cusip={t.get('cusips')} coupon={t.get('coupons')} mat={t.get('maturities')} "
                  f"indenture={'Y' if rec.indenture else '-'}", file=sys.stderr)
            n += 1

    print(f"# wrote {args.out} ({len(hits)} records, {n} fully parsed)", file=sys.stderr)


if __name__ == "__main__":
    main()
