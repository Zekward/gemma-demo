"use client";

import { useEffect, useState } from "react";

// The multimodal beat: Gemma reads a prospectus PAGE IMAGE and extracts the
// structured note terms that seed the comparison. Shown as provenance above the
// analysis. Extraction is pre-baked here for a deterministic demo; see
// docs/MULTIMODAL.md to wire it to a live Gemma vision call on Cerebras.

const EXTRACTED = [
  { k: "Issuer", v: "Space Exploration Technologies Corp." },
  { k: "Security", v: "6.00% Senior Secured Notes" },
  { k: "Coupon", v: "6.00%" },
  { k: "Maturity", v: "May 1, 2030" },
  { k: "Spread", v: "+300 bps" },
  { k: "Rating", v: "BB+" },
];

export default function Ingestion({ scanSignal = 0 }: { scanSignal?: number }) {
  const [scanned, setScanned] = useState(false);

  useEffect(() => {
    if (scanSignal > 0) setScanned(true);
  }, [scanSignal]);

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)] p-3 mt-3">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xs font-semibold tracking-wide text-[var(--muted)] uppercase">
          Source · Gemma 31B reads the filing
          <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-[var(--accent)]/15 text-[var(--accent)] tracking-normal normal-case">
            multimodal · vision
          </span>
        </h2>
        <button
          onClick={() => setScanned((s) => !s)}
          className="text-[11px] text-[var(--accent)] hover:underline"
        >
          {scanned ? "reset" : "▸ extract terms"}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[300px_1fr] gap-4 items-center">
        {/* prospectus page */}
        <div className="relative rounded-md overflow-hidden border border-[var(--border)] bg-[#0e1018]">
          <FilingPage scanning={scanned} />
        </div>

        {/* extracted fields */}
        <div>
          <div className="flex items-center gap-2 text-xs text-[var(--muted)] mb-2">
            <span className="mono">424B5 prospectus · p.142</span>
            <span>→</span>
            <span className="text-[var(--good)] mono">structured terms</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {EXTRACTED.map((f, i) => (
              <div
                key={f.k}
                className={`rounded-md border px-2.5 py-1.5 transition-all duration-300 ${
                  scanned
                    ? "border-[var(--good)]/40 bg-[var(--good)]/5 opacity-100 translate-y-0"
                    : "border-[var(--border)] bg-[var(--panel-2)] opacity-40 translate-y-1"
                }`}
                style={{ transitionDelay: scanned ? `${i * 90}ms` : "0ms" }}
              >
                <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{f.k}</div>
                <div className="text-[12px] mono font-semibold text-[var(--foreground)] truncate">{f.v}</div>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-[var(--muted)] mt-2">
            Gemma extracts the note terms straight from the page image — these feed the
            comparison and the Lean-verified facts below.
          </p>
        </div>
      </div>
    </div>
  );
}

function FilingPage({ scanning }: { scanning: boolean }) {
  return (
    <svg viewBox="0 0 300 200" className="w-full block">
      <rect width="300" height="200" fill="#f4f1ea" />
      {/* header */}
      <text x="16" y="22" fontSize="8" fontWeight="700" fill="#1a1a1a">
        SPACE EXPLORATION TECHNOLOGIES CORP.
      </text>
      <text x="16" y="33" fontSize="6.5" fill="#444">
        Offering Memorandum — Senior Secured Notes
      </text>
      <line x1="16" y1="38" x2="284" y2="38" stroke="#bbb" strokeWidth="0.6" />

      {/* body lines */}
      {[48, 56, 64, 72].map((y) => (
        <rect key={y} x="16" y={y} width={y === 72 ? 180 : 268} height="2.4" rx="1" fill="#cfc9bd" />
      ))}

      {/* terms table */}
      <rect x="16" y="86" width="268" height="86" fill="#fff" stroke="#d8d2c4" strokeWidth="0.8" />
      {[
        ["Principal Amount", "$2,000,000,000"],
        ["Interest Rate (Coupon)", "6.00% per annum"],
        ["Maturity Date", "May 1, 2030"],
        ["Spread to Benchmark", "+300 bps"],
        ["Seniority / Rating", "Senior Secured / BB+"],
      ].map((row, i) => {
        const y = 98 + i * 15;
        return (
          <g key={i}>
            <text x="22" y={y} fontSize="6.5" fill="#333">{row[0]}</text>
            <text x="278" y={y} fontSize="6.5" fontWeight="700" textAnchor="end" fill="#111">{row[1]}</text>
            {i < 4 && <line x1="22" y1={y + 4} x2="278" y2={y + 4} stroke="#eee" strokeWidth="0.5" />}
          </g>
        );
      })}

      {/* scan sweep */}
      {scanning && (
        <>
          <rect x="0" y="0" width="300" height="200" fill="url(#scanGrad)" opacity="0.5">
            <animate attributeName="y" from="-200" to="200" dur="1.1s" fill="freeze" />
          </rect>
          <rect x="0" width="300" height="3" fill="#38bdf8">
            <animate attributeName="y" from="0" to="200" dur="1.1s" fill="freeze" />
          </rect>
        </>
      )}
      <defs>
        <linearGradient id="scanGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0" />
          <stop offset="90%" stopColor="#38bdf8" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  );
}
