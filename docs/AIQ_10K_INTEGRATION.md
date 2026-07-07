# Integrating 10-K/10-Q into AIQ — fast, cheap, near-zero inference

Design for getting issuer financials into AIQ's agent tools **within ~2 minutes of EDGAR
dissemination**, with **no LLM on the hot path**. Grounded in what we verified live in bondsec
(tenk.py, 2026-07-07): the Atom feed detects new filings in seconds, and the filing's own
**inline XBRL** yields the financials deterministically.

## The core insight: the numbers are already structured — don't infer them

A modern 10-K/10-Q is filed as **inline XBRL**. At the moment of dissemination, the accession
already contains:

| Artifact | What it gives you |
|---|---|
| `<primary>.htm` with `<ix:nonFraction name="us-gaap:…">` tags | Every financial-statement number, machine-tagged in place |
| `<ticker>-<date>_htm.xml` | The extracted XBRL instance (same facts, pure XML) |
| `FilingSummary.xml` / `MetaLinks.json` | Statement structure / tag catalog |
| dei tags | Period end, fiscal quarter, shares outstanding — cover-page facts |

**Verified live** on TD SYNNEX's 10-Q filed today: a 30-line stdlib regex over the primary doc
pulled `Revenue 19,574,813` / `NetIncomeLoss 334,088` / `Cash 1,094,181` (thousands) —
deterministic, ~1s, $0 of inference. A tag-whitelist parser (~40 us-gaap concepts: revenue,
net income, cash, **total debt, long-term debt, interest expense**, equity, EBITDA components)
covers what a fixed-income desk needs. `data.sec.gov/api/xbrl/companyfacts` provides the same
facts but on SEC's processing lag; parsing the accession directly is instant and self-contained.

## Pipeline (mapped to AIQ's existing infra)

```
EventBridge rate(1 min)                       [same pattern as the Argilla hourly scraper rule]
  └─> Lambda "edgar-watch" (stdlib, <1s)
        poll getcurrent Atom (10-K,10-Q [,20-F,6-K])   ── ~seconds after dissemination
        dedupe accession vs `filings` table
        (optional) filter to AIQ's issuer universe (CIK watchlist from the CUSIP spine)
  └─> SQS -> job-runner task (or 2nd Lambda) "edgar-extract"  (~1-3s per filing)
        fetch accession index.json -> primary doc (skip R*.htm fragments)
        parse inline-XBRL tag whitelist  ->  facts rows          [ZERO inference]
        regex section boundaries (Item 1A, Item 7, debt footnote) -> store offsets for later
  └─> upsert RDS/Snowflake
        filings(cik, form, accession, filed_at, period_end, doc_url, status)
        issuer_financials(cik, period_end, tag, value, form, accession)   -- time series
  └─> agent surface
        new tool: issuer_financials(cusip|issuer) -> latest Q/K facts + trend + filing link
        headline hook: "new 10-Q: <issuer> — revenue X (±y% q/q)" for issuers held/traded
```

**Latency budget:** detect ≤60s (poll) + fetch/parse 1–3s + upsert <1s → **queryable in the
agent well under 2 minutes**, at ~zero marginal cost. The 10 req/s SEC cap is irrelevant at
this volume (tens of 10-K/Qs per day; hundreds only in peak weeks).

## Where inference IS worth it — and how to keep it tiny

The narrative sections (MD&A, risk factors, debt footnote) are where an LLM adds value. Two
tricks keep it cheap:

1. **Contrastive diff against the issuer's previous filing** (our near-duplicate engine, applied
   in time). Successive 10-Qs are ~90% identical boilerplate. `difflib` the section text vs last
   quarter's → send **only the changed paragraphs** to Gemma for a delta summary
   ("what changed this quarter"). Typical cost: one small call instead of a 180K-char document.
   This runs **async**, minutes later — never on the hot path.
2. **Debt-footnote table extraction** on demand only (when an analyst opens the issuer), not on
   ingest. The XBRL totals are already in the DB; the footnote adds the maturity ladder detail.

## Joining to AIQ's CUSIP spine

- EDGAR is **CIK-keyed**; AIQ is **CUSIP-keyed**. Bridge: issuer master (ticker↔CIK via SEC's
  `company_tickers.json`) + OpenFIGI for CUSIP→issuer. Both already proven in bondsec/enrich.py.
- **SPV shells** (BofA Finance LLC, GS Finance, JPM Chase Financial, …16 found): they file no
  10-K — map each shell → **parent guarantor CIK** in a small static table so notes issued by
  the shell inherit the parent's financials.
- **Foreign issuers** (51 found: Canadian banks, Barclays, DB, sovereigns): subscribe the same
  feed for **20-F / 40-F / 6-K / 18-K** — same pipeline, different form filter; XBRL coverage is
  partial (IFRS tags), fall back to companyfacts.

## Why not alternatives

- **Full-text LLM extraction on ingest**: 100–300-page docs × tokens = slow, costly, and *less*
  accurate than the issuer's own XBRL tags. Use the tags; save the LLM for deltas.
- **Waiting for `companyfacts` API**: convenient but adds SEC's processing lag and a dependency;
  parsing the accession is dissemination-instant.
- **Financial Statement Data Sets (DERA)**: quarterly batch — fine for backfill, useless for "the
  moment it comes out."
- **True push (PDS)**: SEC's paid dissemination line; only needed if 60s polling ever matters.
  Commercial alert services run on the same Atom poll we use.

## Bootstrap

`tenk.py backfill` output (1,883 filings for the 221 bond issuers) is the initial
`filings`/`issuer_financials` load; `tenk.py watch` is the reference implementation of the
watcher (Atom poll → dedupe → primary-doc resolution, incl. the R*.htm and accession-URL
gotchas already fixed).
