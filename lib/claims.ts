import { Bond, getBond, maturityYear } from "@/lib/bonds";

// A Claim is a quantitative statement about the comparison that we ground in
// source data and hand to Lean to *prove* against the figures. The Lean
// statement is closed arithmetic over integers (basis points / tenths) so it
// checks with `decide` and needs no mathlib.
export type Claim = {
  id: string;
  title: string; // short headline shown on the badge
  plainEnglish: string; // the human-readable claim
  leanName: string; // theorem identifier
  leanStatement: string; // full `theorem ... := by decide` line shown on hover
};

const bps = (pct: number) => Math.round(pct * 100);
const tenths = (x: number) => Math.round(x * 10);
const dateInt = (iso: string) => parseInt(iso.replace(/-/g, ""), 10);

export function buildComparisonClaims(aId: string, bId: string): {
  a: Bond;
  b: Bond;
  claims: Claim[];
} | null {
  const a = getBond(aId);
  const b = getBond(bId);
  if (!a || !b) return null;

  // Short disambiguating name, e.g. "SPACEX ’30" — important for same-issuer pairs.
  const nm = (x: Bond) => `${x.ticker} ’${x.maturity.slice(2, 4)}`;

  const claims: Claim[] = [];

  // 1. Yield differential (bps)
  {
    const ya = bps(a.ytmPct), yb = bps(b.ytmPct);
    const hi = ya >= yb ? a : b, lo = ya >= yb ? b : a;
    const diff = Math.abs(ya - yb);
    claims.push({
      id: "yield_spread",
      title: `${nm(hi)} yields +${(diff / 100).toFixed(2)}% vs ${nm(lo)}`,
      plainEnglish: `${nm(hi)} yields ${diff} bps more than ${nm(lo)} (${hi.ytmPct}% vs ${lo.ytmPct}% YTM).`,
      leanName: "yield_differential",
      leanStatement: `theorem yield_differential : (${bps(hi.ytmPct)} : Nat) - ${bps(lo.ytmPct)} = ${diff} := by decide`,
    });
  }

  // 2. Credit-spread differential (bps over treasury)
  {
    const hi = a.spreadBps >= b.spreadBps ? a : b, lo = a.spreadBps >= b.spreadBps ? b : a;
    const diff = Math.abs(a.spreadBps - b.spreadBps);
    claims.push({
      id: "credit_spread",
      title: `${nm(hi)} trades ${diff} bps wider`,
      plainEnglish: `${nm(hi)} trades ${diff} bps wider to the curve than ${nm(lo)} (${hi.spreadBps} vs ${lo.spreadBps} bps).`,
      leanName: "spread_differential",
      leanStatement: `theorem spread_differential : (${hi.spreadBps} : Nat) - ${lo.spreadBps} = ${diff} := by decide`,
    });
  }

  // 3. Coupon ordering
  {
    const hi = a.couponPct >= b.couponPct ? a : b, lo = a.couponPct >= b.couponPct ? b : a;
    claims.push({
      id: "coupon_order",
      title: `${nm(hi)} carries the higher coupon`,
      plainEnglish: `${nm(hi)} pays a ${hi.couponPct}% coupon vs ${nm(lo)}’s ${lo.couponPct}%.`,
      leanName: "coupon_ordering",
      leanStatement: `theorem coupon_ordering : (${bps(lo.couponPct)} : Nat) < ${bps(hi.couponPct)} := by decide`,
    });
  }

  // 4. Maturity ordering
  {
    const first = maturityYear(a) <= maturityYear(b) ? a : b;
    const later = first === a ? b : a;
    claims.push({
      id: "maturity_order",
      title: `${nm(first)} matures first`,
      plainEnglish: `${nm(first)} matures ${first.maturity} — before ${nm(later)} at ${later.maturity}.`,
      leanName: "maturity_ordering",
      leanStatement: `theorem maturity_ordering : (${dateInt(first.maturity)} : Nat) < ${dateInt(later.maturity)} := by decide`,
    });
  }

  // 5. Duration differential (years, to one decimal)
  {
    const hi = a.durationYears >= b.durationYears ? a : b, lo = a.durationYears >= b.durationYears ? b : a;
    const diff = Math.round(Math.abs(a.durationYears - b.durationYears) * 10);
    claims.push({
      id: "duration_gap",
      title: `${diff / 10}y more rate duration in ${nm(hi)}`,
      plainEnglish: `${nm(hi)} carries ${(diff / 10).toFixed(1)} years more modified duration than ${nm(lo)} (${hi.durationYears}y vs ${lo.durationYears}y).`,
      leanName: "duration_differential",
      leanStatement: `theorem duration_differential : (${tenths(hi.durationYears)} : Nat) - ${tenths(lo.durationYears)} = ${diff} := by decide`,
    });
  }

  return { a, b, claims };
}
