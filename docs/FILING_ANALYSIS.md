# What the 2,503 scraped filings actually are — full report

**Window:** 2026-06-23 → 2026-06-26 (the most-recent business days of week-1)
**Source:** SEC EDGAR `/Archives/edgar/data/...`, all primary documents are **HTML (`.htm`), not PDF** (every one of the 2,503).

## TL;DR
**None are 10-K or 10-Q.** These are **securities-offering documents** — the registered-prospectus family (`424B*`) plus free-writing-prospectus term sheets (`FWP`), and 5 SpaceX `8-K`s. They're filed when an issuer *sells new debt*, not the annual/quarterly financial reports you'd expect from "filings." And **~91% are bank structured notes**, not plain corporate bonds.

## 1. Form type (what kind of SEC filing)

| Form | Count | % | What it is |
|---|---|---|---|
| **424B2** | 2,092 | 83.6% | Prospectus supplement / **pricing supplement** — the per-deal terms for a takedown off a shelf/MTN program. The structured-note workhorse. |
| **FWP** | 342 | 13.7% | **Free Writing Prospectus** (Rule 433) — the short "pricing term sheet" for a specific note (coupon/underlying/CUSIP). |
| **424B3** | 53 | 2.1% | Prospectus supplement (Rule 424(b)(3)) — another prospectus variant. |
| **424B5** | 11 | 0.4% | Prospectus supplement (Rule 424(b)(5)) — single-tranche **plain corporate bond** takedowns (e.g. Schwab). |
| **8-K** | 5 | 0.2% | Current report — **SpaceX's 144A senior notes** (launch/pricing/closing), the only non-prospectus docs. |

**What they are NOT:** zero 10-K (annual report), zero 10-Q (quarterly report), zero S-1/registration statements, zero proxy. The `8-K`s are only the 5 SpaceX bond filings, not earnings 8-Ks.

> Why: the scraper discovered via EDGAR full-text search filtered to `forms=424B2,424B3,424B5,FWP` — i.e. it deliberately pulled **new debt *issuance*** (offering docs), not periodic disclosure. SpaceX was added separately from its 8-Ks because its notes are 144A (no prospectus).

## 2. Instrument type — overwhelmingly structured notes

| Instrument | Count | % |
|---|---|---|
| **Structured / market-linked notes** (auto-callable, contingent-coupon, barrier, "linked to" an index/stock) | 2,280 | **91.1%** |
| Fixed-coupon notes / plain bonds | 107 | 4.3% |
| Other / uncertain | 116 | 4.6% |

So the corpus is **not "corporate bonds" in the vanilla sense** — it's dominated by bank **structured products** (e.g. "Auto-Callable Contingent Coupon Notes linked to the worst of the S&P 500 / Russell 2000 / Nasdaq-100"). That's why only **23% have a fixed `coupon`** (structured notes pay *contingent* coupons) and only **35% carry a CUSIP** in the cover-page text.

## 3. Who's issuing — a handful of bank desks

51 distinct issuers, but the top names dominate (all structured-note shelves):

| Issuer | Filings |
|---|---|
| JPMorgan Chase | 452 |
| UBS AG | 341 |
| Morgan Stanley | 290 |
| Citigroup | 284 |
| Goldman Sachs | 236 |
| Barclays Bank | 173 |
| Bank of Montreal | 146 |
| BofA Finance | 144 |
| Bank of Nova Scotia / HSBC / TD / RBC / Nomura … | rest |

## 4. Sector (SIC-derived)
- **Finance (SIC 60 – banks): 1,822** · **Finance (SIC 62 – broker-dealers): 629** → ~98% financial issuers
- Tiny tails: Transport/Utilities (7), Manufacturing (5, incl. SpaceX SIC 37), Services (5), REITs/holding (a few)

## 5. What this means
- This is a **clean census of one week of U.S. structured-note + bond *issuance*** — exactly the "new debt sold this week" firehose, not corporate disclosure.
- For the **contrastive-graph / near-duplicate** thesis it's ideal: thousands of near-identical bank notes off the same shelves, differing only in underlying/coupon/barrier — the agents surface those deltas.
- If you want **10-K/10-Q/periodic** filings (issuer financials), that's a *different* EDGAR query (`forms=10-K,10-Q` via the submissions API by CIK) — not part of this scrape. Likewise, plain **corporate bonds** (not structured notes) are the ~4% `424B5`/fixed-coupon slice (Schwab, Hertz, SpaceX-class).

*Generated from `graph/nodes_week1.jsonl` (2,498 week-1 + 5 SpaceX).*
