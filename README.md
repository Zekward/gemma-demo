# bondsec — SEC EDGAR bond scraper (hackathon stage 1)

Scrape new corporate-bond filings from SEC EDGAR for a date window, extract
per-tranche terms, link each bond to its indenture, and emit a **store-agnostic
normalized record** per bond (the single source of truth for the downstream
RAG / graph-DB / Lean / embedding stages).

```bash
python3 bondsec.py --end 2026-06-28 --forms 424B5 --max-docs 12 --save-raw
# window defaults to the 7 days ending --end (or today). Output: bonds.jsonl
```

No pip install required (stdlib `urllib` only). `edgartools` is the optional
upgrade for the 424B parser; see "next steps".

## Verified EDGAR mechanics (live-confirmed 2026-06-28)

| Surface | URL | Notes |
|---|---|---|
| Full-text search (firehose) | `https://efts.sec.gov/LATEST/search-index?forms=&startdt=&enddt=&q=&from=` | JSON. `forms`-only (empty `q`) works. 100 hits/page, page with `from` (≤9900, 10k cap). **2001+ only.** Intermittent 500 on cold queries → retry. |
| Daily index (complete list) | `…/Archives/edgar/daily-index/{YYYY}/QTR{n}/master.{YYYYMMDD}.idx` | Pipe-delimited `CIK|Company|Form|Date|File`. The authoritative complete set; filter by form. |
| Quarterly index (backfill) | `…/Archives/edgar/full-index/{YYYY}/QTR{n}/master.idx` | 1994-present. |
| Submissions (per issuer) | `https://data.sec.gov/submissions/CIK{cik10}.json` | CIK-keyed filing history. Overflow pages in `filings.files[].name`. |
| Document | `…/Archives/edgar/data/{cik}/{accession_nodashes}/{file}` | `cik` = filer CIK, **leading zeros stripped**; accession **dashes removed**. |
| Accession manifest | `…/{accession_nodashes}/index.json` | Lists files; use to find the EX-4 indenture. (`type` field is an icon name, not exhibit type.) |
| CUSIP enrichment | `POST https://api.openfigi.com/v3/mapping` body `[{"idType":"ID_CUSIP","idValue":"…"}]` | Free, 25 req/60s unauth. Returns issuer, marketSector, coupon+maturity in `securityDescription`. |

## Load-bearing gotchas (each cost real debugging)

1. **User-Agent is mandatory.** Every `*.sec.gov` host 403s a default/empty UA (the
   agent's WebFetch is blocked everywhere). Send `User-Agent: Name email`. Rate cap **10 req/s**.
2. **"All bonds" ≈ structured notes.** 424B2 is ~2,500/week, dominated by bank
   structured/market-linked notes. Clean corporate bonds = **424B5 + FWP** (~50–60 deals/week).
3. **Form type ≠ bond.** 424B5 is also used for **equity** shelf takedowns (ATMs, biotech
   secondaries). Classify by content (`is_bond_like`), not form.
4. **No single filing is complete — JOIN three:**
   - **424B5** = structure / legal supplement (often *preliminary* → coupon & CUSIP blank).
   - **FWP** = priced term sheet → final coupon, maturity, **CUSIP** (and ISIN).
   - **8-K EX-4.x** = the **indenture** (the legal contract; the Lean target).
   Key them together by issuer **CIK + offering date**.
5. **CUSIP ⟂ EDGAR.** EDGAR is CIK-keyed; there is no CUSIP index. Recover CUSIP from the
   **ISIN** in the FWP: US/CA `ISIN = CC + CUSIP(9) + check`, so `CUSIP = ISIN[2:11]`.
6. **EFTS 500s intermittently** on cold/slow queries — retry with backoff.
7. **FTS is 2001+.** Pre-2001 bonds need the submissions/Archives fallback.

## Normalized record (bonds.jsonl) — one JSON object per bond/tranche

```
bond_id, cusips[], isins[], issuer_name, cik, form_type, filing_date, accession,
primary_doc_url, terms{coupons[],maturities[],principal,is_bond_like},
indenture{accession,exhibit_file,url}, raw_text_path, metadata{}, relationships[]
```

`relationships[]` is filled later by the Gemma pairwise-attention pass. From this one
file you load DuckDB, any graph DB (Kuzu/Neo4j/Memgraph), or emit embedding-training pairs —
without re-scraping.

## Next steps
- Pair each 424B5 with the issuer's FWP (CIK+date) to fill CUSIP/coupon; OpenFIGI to backfill metadata.
- Tighten indenture linkage to the **supplemental** indenture / officers' certificate for the exact series.
- Swap the regex extractor for `edgartools`' 424B parser (or a Gemma extraction pass) for robustness.
- Emit the indenture text as the Lean-formalization input.
