"""Load the 10-K/10-Q filings + the bond graph issuers into Kuzu (embedded Cypher graph DB).

Model:  (:Issuer)-[:FILED]->(:Filing)      1,883 periodic reports from tenk.py backfill
        (:Issuer)-[:ISSUED]->(:Bond)       the week-1 bond/structured-note nodes, joined by CIK

Same portable-store philosophy as loaders.py: this is just another ~80-line adapter over
the canonical jsonl files. DB lands in graph/kuzu_tenk_db (a directory; delete to rebuild).
"""
from __future__ import annotations
import csv, json, pathlib, re, shutil, sys, tempfile
import kuzu

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
DB = HERE / "kuzu_tenk_db"

def rows(p):
    for l in open(p):
        l = l.strip()
        if l:
            yield json.loads(l)

def build():
    # ---- gather ------------------------------------------------------------
    issuers, filings, filed, bonds, issued = {}, {}, [], {}, []
    for r in rows(ROOT / "data/filings_10k10q.jsonl"):
        cik = str(r["cik"])
        issuers.setdefault(cik, r["issuer"])
        acc = r["accession"]
        if acc not in filings:
            filings[acc] = [acc, r["form"], r["kind"], r["filing_date"] or "",
                            r.get("report_date") or "", r.get("doc_url") or ""]
            filed.append([cik, acc])
    for n in rows(ROOT / "graph/nodes_week1.jsonl"):
        m = n["_meta"]; cik = str(int(m["cik"]))
        issuers.setdefault(cik, re.split(r"\s*\(", m["issuer"])[0].strip())
        bid = m["id"]
        if bid in bonds:
            continue
        tr = n.get("tranches") or [{}]
        t = next((x for x in tr if x.get("coupon_pct") is not None), tr[0])
        bonds[bid] = [bid, m["form"], m["date"],
                      float(t["coupon_pct"]) if t.get("coupon_pct") is not None else None,
                      int(t["maturity_year"]) if t.get("maturity_year") else None,
                      t.get("cusip") or "", m["doc_url"]]
        issued.append([cik, bid])

    # ---- write staging CSVs and COPY into kuzu ------------------------------
    if DB.exists():                                   # kuzu 0.11 = single file (+ .wal), older = dir
        shutil.rmtree(DB) if DB.is_dir() else DB.unlink()
    for w in (DB.parent / (DB.name + ".wal"), DB.parent / (DB.name + ".shadow")):
        w.unlink(missing_ok=True)
    db = kuzu.Database(str(DB)); con = kuzu.Connection(db)
    con.execute("CREATE NODE TABLE Issuer(cik STRING, name STRING, PRIMARY KEY(cik))")
    con.execute("CREATE NODE TABLE Filing(accession STRING, form STRING, kind STRING, "
                "filing_date STRING, report_date STRING, doc_url STRING, PRIMARY KEY(accession))")
    con.execute("CREATE NODE TABLE Bond(id STRING, form STRING, date STRING, coupon DOUBLE, "
                "maturity INT64, cusip STRING, doc_url STRING, PRIMARY KEY(id))")
    con.execute("CREATE REL TABLE FILED(FROM Issuer TO Filing)")
    con.execute("CREATE REL TABLE ISSUED(FROM Issuer TO Bond)")

    tmp = pathlib.Path(tempfile.mkdtemp())
    def stage(name, data):
        p = tmp / f"{name}.csv"
        with p.open("w", newline="") as f:
            csv.writer(f).writerows(data)
        return str(p)

    con.execute(f"COPY Issuer FROM '{stage('issuer', [[k, v] for k, v in issuers.items()])}'")
    con.execute(f"COPY Filing FROM '{stage('filing', list(filings.values()))}'")
    con.execute(f"COPY Bond FROM '{stage('bond', list(bonds.values()))}'")
    con.execute(f"COPY FILED FROM '{stage('filed', filed)}'")
    con.execute(f"COPY ISSUED FROM '{stage('issued', issued)}'")
    shutil.rmtree(tmp)
    return con, dict(issuers=len(issuers), filings=len(filings), bonds=len(bonds),
                     filed=len(filed), issued=len(issued))

def q(con, title, cypher):
    print(f"\n— {title}\n  {cypher.strip()}")
    res = con.execute(cypher)
    cols = res.get_column_names()
    while res.has_next():
        print("   ", dict(zip(cols, res.get_next())))

if __name__ == "__main__":
    con, stats = build()
    print(f"kuzu db built at {DB.name}: {stats}")
    q(con, "counts by node label",
      "MATCH (f:Filing) RETURN f.kind AS kind, f.form AS form, count(*) AS n ORDER BY n DESC LIMIT 6")
    q(con, "issuers with the most periodic reports",
      "MATCH (i:Issuer)-[:FILED]->(f:Filing) RETURN i.name AS issuer, count(*) AS reports "
      "ORDER BY reports DESC LIMIT 5")
    q(con, "THE JOIN — Schwab's bonds AND its 10-K in one Cypher pattern",
      "MATCH (b:Bond)<-[:ISSUED]-(i:Issuer)-[:FILED]->(f:Filing) "
      "WHERE i.name CONTAINS 'SCHWAB' AND f.form = '10-K' "
      "RETURN i.name AS issuer, b.coupon AS bond_coupon, b.maturity AS bond_maturity, "
      "f.filing_date AS tenk_filed, f.doc_url AS tenk_url LIMIT 3")
    q(con, "bond issuers WITHOUT any 10-K/10-Q (foreign filers + SPV shells, straight from the graph)",
      "MATCH (i:Issuer)-[:ISSUED]->(:Bond) WHERE NOT EXISTS "
      "{ MATCH (i)-[:FILED]->(:Filing {kind:'primary'}) } "
      "RETURN DISTINCT i.name AS spv_issuer LIMIT 8")
