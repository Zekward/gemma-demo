#!/usr/bin/env python3
"""
tenk — 10-K / 10-Q pipeline scoped to the bondsec issuer watchlist.

  python3 tenk.py backfill        # watchlist -> submissions API -> filings_10k10q.jsonl
  python3 tenk.py watch           # subscribe: poll EDGAR's current-filings Atom feed,
                                  # ingest new 10-K/10-Q the moment they're disseminated

Watchlist = distinct (issuer, CIK) from the bondsec tool's outputs
(bonds_clean_enriched.jsonl first, falling back to bonds.jsonl / graph nodes).

Foreign private issuers and sovereigns never file 10-K/10-Q — their annual/interim
equivalents are 20-F / 40-F / 6-K / 18-K. We track those separately instead of
reporting a silent zero.
"""
from __future__ import annotations
import argparse, json, pathlib, re, sys, time, urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import bondsec as B                      # SEC fetch (UA + throttle + retry)

HERE = pathlib.Path(__file__).parent
OUT = HERE / "data"
PRIMARY = ["10-K", "10-Q", "10-K/A", "10-Q/A"]
FOREIGN_EQUIV = ["20-F", "40-F", "6-K", "18-K", "20-F/A", "40-F/A", "18-K/A"]
IPO_DOCS = ["S-1", "S-1/A", "F-1", "F-1/A", "424B4"]   # recent IPOs (e.g. SpaceX): financials live here until the first 10-Q
ATOM = "{http://www.w3.org/2005/Atom}"


# --- watchlist ------------------------------------------------------------------
def watchlist() -> dict[str, str]:
    """{cik(no leading zeros): issuer_name} from the bondsec tool outputs."""
    wl: dict[str, str] = {}

    def add(name, cik):
        name = re.split(r"\s*\(", str(name or ""))[0].strip()
        try:
            cik = str(int(str(cik).strip()))
        except (ValueError, TypeError):
            return
        if name and cik not in wl:
            wl[cik] = name

    for fn in ("bonds_clean_enriched.jsonl", "bonds_clean.jsonl", "bonds.jsonl"):
        p = HERE / fn
        if p.exists():
            for l in p.open():
                try:
                    r = json.loads(l)
                except json.JSONDecodeError:
                    continue
                add(r.get("issuer_name"), r.get("cik"))
            if wl:
                print(f"# watchlist from {fn}: {len(wl)} issuers", file=sys.stderr)
                break
    gp = HERE / "graph/nodes_week1.jsonl"                     # merge graph issuers too
    if gp.exists():
        before = len(wl)
        for l in gp.open():
            m = json.loads(l)["_meta"]
            add(m.get("issuer"), m.get("cik"))
        if len(wl) > before:
            print(f"# + {len(wl)-before} more from graph nodes -> {len(wl)} total", file=sys.stderr)
    return wl


# --- backfill: submissions API per CIK -------------------------------------------
def backfill(limit_per_form: int = 4):
    wl = watchlist()
    OUT.mkdir(exist_ok=True)
    out_path = OUT / "filings_10k10q.jsonl"
    n_rec, have_primary, have_foreign, have_none = 0, [], [], []
    with out_path.open("w") as out:
        for i, (cik, name) in enumerate(sorted(wl.items(), key=lambda kv: kv[1].lower())):
            try:
                sub = json.loads(B.fetch(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"))
            except Exception as e:
                print(f"  !! {name} (CIK {cik}): {str(e)[:80]}", file=sys.stderr)
                continue
            r = sub.get("filings", {}).get("recent", {})
            rows = list(zip(r.get("form", []), r.get("filingDate", []),
                            r.get("accessionNumber", []), r.get("primaryDocument", []),
                            r.get("reportDate", [])))
            got_p = got_f = 0
            has_periodic = any(f in PRIMARY or f in FOREIGN_EQUIV for f, *_ in rows)
            form_sets = [(PRIMARY, "primary"), (FOREIGN_EQUIV, "foreign_equiv")]
            if not has_periodic:
                form_sets.append((IPO_DOCS, "ipo_prospectus"))    # newly-public issuer: surface the S-1/424B4
            for form_set, tag in form_sets:
                per_form: dict[str, int] = {}
                for form, fdate, acc, doc, rdate in rows:
                    if form not in form_set or per_form.get(form, 0) >= limit_per_form:
                        continue
                    per_form[form] = per_form.get(form, 0) + 1
                    rec = {"cik": cik, "issuer": name, "form": form, "kind": tag,
                           "filing_date": fdate, "report_date": rdate, "accession": acc,
                           "doc_url": f"{B.ARCHIVES}/{cik}/{acc.replace('-','')}/{doc}" if doc else None,
                           "entity_name": sub.get("name"), "sic": sub.get("sicDescription")}
                    out.write(json.dumps(rec) + "\n")
                    n_rec += 1
                    if tag == "primary":
                        got_p += 1
                    else:
                        got_f += 1
            (have_primary if got_p else have_foreign if got_f else have_none).append(name)
            if (i + 1) % 25 == 0:
                print(f"  … {i+1}/{len(wl)} issuers, {n_rec} filings", file=sys.stderr)
    print(f"\n# wrote {out_path} ({n_rec} filings)", file=sys.stderr)
    print(f"# issuers with 10-K/10-Q: {len(have_primary)} | foreign-equiv only: {len(have_foreign)}"
          f" | neither: {len(have_none)}", file=sys.stderr)
    if have_foreign:
        print("#   foreign-equiv-only: " + ", ".join(sorted(have_foreign)[:12]) +
              (" …" if len(have_foreign) > 12 else ""), file=sys.stderr)
    if have_none:
        print("#   no periodic reports: " + ", ".join(sorted(have_none)[:12]) +
              (" …" if len(have_none) > 12 else ""), file=sys.stderr)


# --- watch: EDGAR current-filings Atom feed ---------------------------------------
FEED = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
        "&type={form}&company=&dateb=&owner=include&count=40&output=atom")

def _feed_entries(form: str):
    xml = B.fetch(FEED.format(form=urllib.parse.quote(form))).decode("utf-8", "ignore")
    root = ET.fromstring(xml)
    for e in root.findall(f"{ATOM}entry"):
        title = (e.findtext(f"{ATOM}title") or "").strip()
        link = e.find(f"{ATOM}link")
        href = link.get("href") if link is not None else ""
        updated = (e.findtext(f"{ATOM}updated") or "").strip()
        # e.g. /Archives/edgar/data/1709542/000168316826005287/0001683168-26-005287-index.htm
        m = re.search(r"/Archives/edgar/data/(\d+)/(?:\d+/)?([\d-]+)-index", href)
        cik, acc = (m.group(1), m.group(2)) if m else (None, None)
        fm = re.match(r"\s*([\w/-]+)\s+-\s+(.*?)\s*\(", title)
        yield {"form": fm.group(1) if fm else form, "entity": fm.group(2) if fm else title,
               "cik": cik, "accession": acc, "index_url": href, "updated": updated}

def _ingest(entry):
    """New filing -> resolve primary doc -> text -> append to the feed jsonl."""
    cik, acc = entry["cik"], entry["accession"]
    rec = dict(entry)
    try:
        idx = json.loads(B.fetch(f"{B.ARCHIVES}/{cik}/{acc.replace('-','')}/index.json"))
        items = [it for it in idx.get("directory", {}).get("item", [])
                 if it.get("name", "").lower().endswith((".htm", ".html"))
                 and "index" not in it.get("name", "").lower()
                 and not re.match(r"^r\d+\.htm$", it.get("name", "").lower())]  # skip XBRL viewer fragments
        # primary doc looks like "tdsynnex-20260531.htm"; otherwise take the biggest non-exhibit file
        items.sort(key=lambda it: (0 if re.search(r"-\d{8}\.htm", it["name"].lower()) else 1,
                                   "ex" in it["name"].lower(), -int(it.get("size") or 0)))
        docs = [it["name"] for it in items]
        if docs:
            rec["doc_url"] = f"{B.ARCHIVES}/{cik}/{acc.replace('-','')}/{docs[0]}"
            text = B.html_to_text(B.fetch(rec["doc_url"]))
            rec["chars"] = len(text)
            rec["excerpt"] = text[:600]
    except Exception as e:
        rec["ingest_error"] = str(e)[:120]
    with (OUT / "filings_10k10q_feed.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec

def watch(interval: int = 60, only_watchlist: bool = False, once: bool = False):
    OUT.mkdir(exist_ok=True)
    wl = watchlist() if only_watchlist else None
    seen_path = OUT / ".feed_seen.json"
    seen = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
    print(f"# watching EDGAR current-filings feed for 10-K/10-Q every {interval}s "
          f"({'watchlist only' if only_watchlist else 'ALL filers'}); state={seen_path.name}", file=sys.stderr)
    while True:
        new = 0
        for form in ("10-K", "10-Q"):
            try:
                for e in _feed_entries(form):
                    if not e["accession"] or e["accession"] in seen:
                        continue
                    if wl is not None and e["cik"] not in wl:
                        seen.add(e["accession"])          # remember, but don't ingest
                        continue
                    seen.add(e["accession"])
                    rec = _ingest(e)
                    new += 1
                    print(f"  NEW {rec['form']:6s} {rec['entity'][:44]:44s} "
                          f"{rec.get('chars','?'):>8} chars  {rec.get('doc_url','')}", file=sys.stderr)
            except Exception as ex:
                print(f"  feed err ({form}): {str(ex)[:100]}", file=sys.stderr)
        seen_path.write_text(json.dumps(sorted(seen)[-5000:]))
        if once:
            print(f"# single pass done: {new} new filings ingested", file=sys.stderr)
            return
        time.sleep(interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["backfill", "watch"])
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--only-watchlist", action="store_true")
    ap.add_argument("--once", action="store_true", help="watch: one poll cycle then exit")
    ap.add_argument("--limit-per-form", type=int, default=4)
    a = ap.parse_args()
    if a.mode == "backfill":
        backfill(a.limit_per_form)
    else:
        watch(a.interval, a.only_watchlist, a.once)
