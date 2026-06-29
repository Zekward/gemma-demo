"use client";

import { useEffect, useMemo, useState } from "react";
import { BONDS, getBond, buildGraph, similarBonds } from "@/lib/bonds";
import KnowledgeGraph from "@/components/KnowledgeGraph";
import Ingestion from "@/components/Ingestion";

type Metrics = {
  provider: "cerebras" | "gpu";
  ttftMs: number | null;
  tokens: number;
  elapsedMs: number;
  tps: number;
  simulated: boolean;
  model: string;
};
type Status = "idle" | "streaming" | "done" | "error";
type Sample = { ms: number; tokens: number };

// Append a {ms, tokens} point, keeping the series monotonic and de-duped on time
// so the throughput chart stays clean under the ~80ms metric cadence.
function appendSample(prev: Sample[], m: Metrics): Sample[] {
  const pt = { ms: m.elapsedMs, tokens: m.tokens };
  const last = prev[prev.length - 1];
  if (last && pt.ms <= last.ms) {
    // same tick: replace with the latest token count
    return [...prev.slice(0, -1), { ms: last.ms, tokens: Math.max(last.tokens, pt.tokens) }];
  }
  return [...prev, pt];
}
type Claim = { id: string; title: string; plainEnglish: string; leanName: string; leanStatement: string };
type Verdict = { id: string; leanName: string; verified: boolean };

export default function Home() {
  const [aId, setAId] = useState("SPACEX-2027");
  const [bId, setBId] = useState("SPACEX-2030");
  const [running, setRunning] = useState(false);

  const [cText, setCText] = useState("");
  const [gText, setGText] = useState("");
  const [cMetrics, setCMetrics] = useState<Metrics | null>(null);
  const [gMetrics, setGMetrics] = useState<Metrics | null>(null);
  // time-series of {ms, tokens} per provider, for the throughput chart
  const [cSamples, setCSamples] = useState<Sample[]>([]);
  const [gSamples, setGSamples] = useState<Sample[]>([]);
  const [cStatus, setCStatus] = useState<Status>("idle");
  const [gStatus, setGStatus] = useState<Status>("idle");
  const [cThinking, setCThinking] = useState(false);
  const [gThinking, setGThinking] = useState(false);

  const [claims, setClaims] = useState<Claim[]>([]);
  const [verdicts, setVerdicts] = useState<Record<string, boolean>>({});
  const [revealed, setRevealed] = useState(0);
  const [leanInfo, setLeanInfo] = useState<{ available: boolean; durationMs: number; version?: string } | null>(null);
  const [verifyState, setVerifyState] = useState<"idle" | "running" | "done">("idle");
  const [showSimilar, setShowSimilar] = useState(false);
  const [scanSignal, setScanSignal] = useState(0);
  const [warm, setWarm] = useState<"warming" | "ready" | "sim">("warming");

  // Pre-warm both engines on load so the first measured race reflects
  // steady-state speed, not cold-start latency.
  useEffect(() => {
    let alive = true;
    fetch("/api/warmup", { method: "POST" })
      .then((r) => r.json())
      .then((d) => { if (alive) setWarm(d?.cerebras?.simulated ? "sim" : "ready"); })
      .catch(() => { if (alive) setWarm("ready"); });
    return () => { alive = false; };
  }, []);

  const a = getBond(aId)!;
  const b = getBond(bId)!;
  const focusIds = [aId, bId];
  const graph = useMemo(() => buildGraph(focusIds), [aId, bId]);
  const similar = useMemo(() => similarBonds(aId, 6), [aId]);

  const reset = () => {
    setCText(""); setGText(""); setCMetrics(null); setGMetrics(null);
    setCSamples([]); setGSamples([]);
    setCStatus("idle"); setGStatus("idle");
    setCThinking(false); setGThinking(false);
    setClaims([]); setVerdicts({}); setRevealed(0); setLeanInfo(null);
    setVerifyState("idle"); setShowSimilar(false);
  };

  async function streamProvider(
    provider: "cerebras" | "gpu",
    onToken: (s: string) => void,
    onMetrics: (m: Metrics) => void,
    setStatus: (s: Status) => void,
    setThinking: (b: boolean) => void,
  ) {
    setStatus("streaming");
    const res = await fetch("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, aId, bId }),
    });
    if (!res.body) { setStatus("error"); return; }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop() || "";
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        try {
          const ev = JSON.parse(line.slice(5).trim());
          if (ev.t === "token") { onToken(ev.v); setThinking(false); }
          else if (ev.t === "status") { if (ev.v === "thinking") setThinking(true); }
          else if (ev.t === "metrics") onMetrics(ev.m);
          else if (ev.t === "done") { onMetrics(ev.m); setStatus("done"); setThinking(false); }
          else if (ev.t === "error") { onToken(`\n[error] ${ev.message}`); setStatus("error"); setThinking(false); }
        } catch { /* skip */ }
      }
    }
  }

  async function runVerify() {
    setVerifyState("running");
    const res = await fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ aId, bId }),
    });
    const data = await res.json();
    setClaims(data.claims);
    setLeanInfo({
      available: data.result.available,
      durationMs: data.result.durationMs,
      version: data.result.leanVersion,
    });
    const vmap: Record<string, boolean> = {};
    for (const v of data.result.verdicts as Verdict[]) vmap[v.id] = v.verified;
    // reveal claims one-by-one for the camera
    setRevealed(0);
    (data.claims as Claim[]).forEach((_, i) => {
      setTimeout(() => {
        setRevealed((r) => Math.max(r, i + 1));
        setVerdicts((prev) => ({ ...prev, [data.claims[i].id]: vmap[data.claims[i].id] }));
      }, 250 * (i + 1));
    });
    setTimeout(() => setVerifyState("done"), 250 * (data.claims.length + 1));
    setTimeout(() => setShowSimilar(true), 250 * (data.claims.length + 2));
  }

  async function run() {
    if (running) return;
    reset();
    setRunning(true);
    setScanSignal((s) => s + 1);
    const onC = (m: Metrics) => { setCMetrics(m); setCSamples((s) => appendSample(s, m)); };
    const onG = (m: Metrics) => { setGMetrics(m); setGSamples((s) => appendSample(s, m)); };
    const cerebras = streamProvider("cerebras", (s) => setCText((t) => t + s), onC, setCStatus, setCThinking);
    const gpu = streamProvider("gpu", (s) => setGText((t) => t + s), onG, setGStatus, setGThinking);
    await cerebras; // Cerebras finishes first -> verify immediately
    await runVerify();
    await gpu; // let the GPU side finish in the background
    setRunning(false);
  }

  const verifiedCount = Object.values(verdicts).filter(Boolean).length;

  // Announce meaningful milestones to screen readers — not every token (which
  // would spam). A single polite live region narrates the demo's key beats.
  const liveMessage = useMemo(() => {
    if (verifyState === "done" && cMetrics) {
      if (leanInfo?.available) {
        const s = ((cMetrics.elapsedMs + leanInfo.durationMs) / 1000).toFixed(1);
        return `Formally verified answer in ${s} seconds. ${verifiedCount} of ${claims.length} numeric facts proved by Lean.`;
      }
      return `Answer delivered in ${(cMetrics.elapsedMs / 1000).toFixed(1)} seconds.`;
    }
    if (cStatus === "done" && cMetrics) {
      return `Cerebras answered in ${(cMetrics.elapsedMs / 1000).toFixed(1)} seconds at ${cMetrics.tps} tokens per second.`;
    }
    if (cStatus === "streaming" || gStatus === "streaming") return "Running comparison.";
    return "";
  }, [cStatus, gStatus, verifyState, cMetrics, leanInfo, verifiedCount, claims.length]);

  return (
    <main className="min-h-screen w-full px-4 sm:px-6 py-5 max-w-[1400px] mx-auto">
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{liveMessage}</p>
      <Header onRun={run} running={running} a={a} b={b} warm={warm} />

      <BondPickers
        aId={aId} bId={bId} setAId={setAId} setBId={setBId}
        running={running} reset={reset}
      />

      <Ingestion scanSignal={scanSignal} />

      <RaceStrip
        c={cMetrics} g={gMetrics}
        cSamples={cSamples} gSamples={gSamples}
        cStatus={cStatus} gStatus={gStatus}
        verifyState={verifyState} verifiedCount={verifiedCount} claimCount={claims.length}
      />

      {verifyState === "done" && (
        <VerifiedAnswerBanner
          cMetrics={cMetrics} gMetrics={gMetrics} gStatus={gStatus}
          leanInfo={leanInfo} verifiedCount={verifiedCount} claimCount={claims.length}
        />
      )}

      {/* SPLIT SCREEN */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        <ProviderPanel
          accent kind="cerebras" title="Cerebras"
          subtitle="Wafer-Scale Inference" text={cText}
          metrics={cMetrics} status={cStatus} thinking={cThinking}
        />
        <ProviderPanel
          kind="gpu" title="GPU Provider"
          subtitle="Conventional cloud host · same Gemma model" text={gText}
          metrics={gMetrics} status={gStatus} thinking={gThinking}
        />
      </section>

      {/* VERIFY + GRAPH */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        <VerifiedFacts
          claims={claims} verdicts={verdicts} revealed={revealed}
          leanInfo={leanInfo} verifyState={verifyState} verifiedCount={verifiedCount}
        />
        <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)] p-4">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-semibold tracking-wide text-[var(--muted)] uppercase">
              Bond Knowledge Graph
            </h2>
            {showSimilar && (
              <span className="text-xs text-[var(--accent)] mono">
                {similar.length} nearest by yield · spread · duration · rating
              </span>
            )}
          </div>
          <div className="h-[460px]">
            <KnowledgeGraph
              graph={graph}
              focusIds={focusIds}
              highlightIds={showSimilar ? similar.map((s) => s.bond.id) : []}
            />
          </div>
        </div>
      </section>

      <footer className="mt-6 text-center text-xs text-[var(--muted)]">
        AIQ · real-time, formally-verified bond intelligence · Cerebras + Gemma ·
        <span className="text-[var(--good)]"> fast enough for mobile, trustworthy enough for the desk</span>
      </footer>
    </main>
  );
}

/* ---------- components ---------- */

// The climax: fuses the two differentiators into one number. Cerebras's answer
// time + Lean's proof time = a *formally-verified* answer delivered while the GPU
// host is typically still drafting its first (unverified) paragraph.
function VerifiedAnswerBanner({
  cMetrics, gMetrics, gStatus, leanInfo, verifiedCount, claimCount,
}: {
  cMetrics: Metrics | null; gMetrics: Metrics | null; gStatus: Status;
  leanInfo: { available: boolean; durationMs: number; version?: string } | null;
  verifiedCount: number; claimCount: number;
}) {
  if (!cMetrics) return null;
  const proved = !!leanInfo?.available;
  const totalMs = cMetrics.elapsedMs + (proved ? leanInfo!.durationMs : 0);
  const totalS = (totalMs / 1000).toFixed(1);
  const gpuDone = gStatus === "done";
  const gpuS = gMetrics ? (gMetrics.elapsedMs / 1000).toFixed(1) : null;

  return (
    <div role="status" className="pop-in mt-4 rounded-xl border border-[var(--good)]/40 bg-[var(--good)]/[0.06] px-4 py-3 flex items-center gap-3 shadow-[0_0_40px_-22px_var(--good)]">
      <span aria-hidden className="grid place-items-center h-9 w-9 shrink-0 rounded-lg bg-[var(--good)]/15 text-[var(--good)] text-lg">✓</span>
      <div className="min-w-0">
        <div className="text-sm sm:text-base font-bold leading-tight">
          {proved ? (
            <>Formally-verified answer in <span className="mono text-[var(--good)]">{totalS}s</span></>
          ) : (
            <>Answer delivered in <span className="mono text-[var(--good)]">{(cMetrics.elapsedMs / 1000).toFixed(1)}s</span></>
          )}
        </div>
        <p className="text-xs text-[var(--muted)] mt-0.5">
          {proved && (
            <span className="text-[var(--foreground)]/80">{verifiedCount}/{claimCount} numeric facts proved by Lean’s kernel</span>
          )}
          {proved && " · "}
          {gpuDone ? (
            <>GPU host answered <span className="text-[var(--foreground)]/70">unverified</span> in {gpuS}s</>
          ) : (
            <span className="text-[var(--cerebras-2)]">GPU host is still generating its first draft</span>
          )}
        </p>
      </div>
    </div>
  );
}

// Overlays both providers' cumulative-token curves on a shared time axis. The
// contrast is the whole point: Cerebras spikes near-vertical at the left while
// the GPU curve crawls along the bottom — fast inference made legible at a glance.
function ThroughputChart({ cSamples, gSamples, idle }: { cSamples: Sample[]; gSamples: Sample[]; idle: boolean }) {
  const W = 100, H = 40, padL = 1.5, padR = 1.5, padT = 3, padB = 2;
  const maxMs = Math.max(1, ...cSamples.map((s) => s.ms), ...gSamples.map((s) => s.ms));
  const maxTok = Math.max(1, ...cSamples.map((s) => s.tokens), ...gSamples.map((s) => s.tokens));
  const xa = (W - padL - padR) / maxMs;
  const ya = (H - padT - padB) / maxTok;
  const X = (ms: number) => padL + ms * xa;
  const Y = (tok: number) => H - padB - tok * ya;
  const path = (s: Sample[]) => s.map((p, i) => `${i === 0 ? "M" : "L"}${X(p.ms).toFixed(2)} ${Y(p.tokens).toFixed(2)}`).join(" ");

  const cLast = cSamples[cSamples.length - 1];
  const gLast = gSamples[gSamples.length - 1];

  const ariaLabel = idle
    ? "Throughput chart — run a comparison to plot cumulative tokens over time for both engines."
    : `Cumulative tokens over time. Cerebras reached ${Math.round(maxTok)} tokens; the GPU host's curve climbs far more slowly over the same window.`;

  // The SVG is stretched to fill (preserveAspectRatio="none") so the time axis
  // spans full width — but that would also squash text and round dots into
  // ellipses, so those are rendered as crisp HTML overlays positioned by
  // percentage (viewBox is 100 wide / H tall, so x → x% and y → y/H%).
  const dot = (s: Sample, color: string, size: number) => ({
    left: `${X(s.ms)}%`,
    top: `${(Y(s.tokens) / H) * 100}%`,
    width: size, height: size, background: color,
  });

  return (
    <div className="relative w-full h-[68px]" role="img" aria-label={ariaLabel}>
      <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 w-full h-full" preserveAspectRatio="none" aria-hidden>
        {/* baseline */}
        <line x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} stroke="var(--border)" strokeWidth={0.3} vectorEffect="non-scaling-stroke" />
        {gSamples.length > 1 && (
          <path d={path(gSamples)} fill="none" stroke="var(--gpu)" strokeWidth={1.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
        )}
        {cSamples.length > 1 && (
          <path d={path(cSamples)} fill="none" stroke="var(--cerebras)" strokeWidth={1.4} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
        )}
      </svg>
      {idle ? (
        <div className="absolute inset-0 grid place-items-center text-[11px] text-[var(--muted)]">
          run a comparison to plot throughput
        </div>
      ) : (
        <>
          {gLast && <span className="absolute rounded-full -translate-x-1/2 -translate-y-1/2" style={dot(gLast, "var(--gpu)", 7)} />}
          {cLast && <span className="absolute rounded-full -translate-x-1/2 -translate-y-1/2 shadow-[0_0_8px_-1px_var(--cerebras)]" style={dot(cLast, "var(--cerebras)", 9)} />}
        </>
      )}
    </div>
  );
}

// The visceral proof: a shared-axis throughput chart (Cerebras spikes, GPU crawls)
// plus a single "Nx faster" readout and the "done & verified before GPU finishes" status.
function RaceStrip({
  c, g, cSamples, gSamples, cStatus, gStatus, verifyState, verifiedCount, claimCount,
}: {
  c: Metrics | null; g: Metrics | null;
  cSamples: Sample[]; gSamples: Sample[];
  cStatus: Status; gStatus: Status;
  verifyState: "idle" | "running" | "done"; verifiedCount: number; claimCount: number;
}) {
  const speedup = c && g && g.tps > 0 ? c.tps / g.tps : null;
  const idle = cStatus === "idle" && gStatus === "idle";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)] px-4 py-3 mt-4 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-5">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Cumulative tokens over time</span>
          <span className="flex items-center gap-3 text-[10px]">
            <span className="flex items-center gap-1 text-[var(--cerebras)]"><span className="h-1.5 w-1.5 rounded-full bg-[var(--cerebras)]" />Cerebras</span>
            <span className="flex items-center gap-1 text-[var(--muted)]"><span className="h-1.5 w-1.5 rounded-full bg-[var(--gpu)]" />GPU host</span>
          </span>
        </div>
        <ThroughputChart cSamples={cSamples} gSamples={gSamples} idle={idle} />
      </div>
      <div className="flex items-center justify-center sm:border-l border-[var(--border)] sm:pl-5 min-w-[150px]">
        {idle ? (
          <span className="text-xs text-[var(--muted)]">Run a comparison to race the engines.</span>
        ) : speedup ? (
          <div className="text-center leading-none">
            <div className="mono font-bold text-2xl text-[var(--cerebras)]">{speedup.toFixed(speedup >= 10 ? 0 : 1)}×</div>
            <div className="text-[10px] uppercase tracking-wide text-[var(--muted)] mt-1">Cerebras throughput</div>
          </div>
        ) : (
          <span className="text-xs text-[var(--muted)] pulse">measuring…</span>
        )}
      </div>
      <div className="sm:border-l border-[var(--border)] sm:pl-5 text-[11px] mono text-right min-w-[140px]">
        {cStatus === "done" && gStatus !== "done" && (
          <span className="text-[var(--good)]">
            Cerebras done{verifyState === "done" ? ` · ${verifiedCount}/${claimCount} proved` : verifyState === "running" ? " · proving…" : ""}
            <br />
            <span className="text-[var(--muted)]">GPU still generating…</span>
          </span>
        )}
        {cStatus === "done" && gStatus === "done" && (
          <span className="text-[var(--muted)]">both complete · Cerebras led</span>
        )}
        {!(cStatus === "done") && !idle && <span className="text-[var(--muted)]">racing…</span>}
      </div>
    </div>
  );
}

function Header({ onRun, running, a, b, warm }: { onRun: () => void; running: boolean; a: any; b: any; warm: "warming" | "ready" | "sim" }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 pb-4 border-b border-[var(--border)]">
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="grid place-items-center h-10 w-10 rounded-xl bg-[var(--cerebras)] text-black font-extrabold text-base tracking-tight shadow-[0_0_22px_-8px_var(--cerebras)]"
        >
          AIQ
        </span>
        <div>
          <h1 className="text-lg sm:text-xl font-bold tracking-tight leading-none">
            Bond Intelligence
          </h1>
          <p className="text-[11px] text-[var(--muted)] mt-1.5">
            Real-time, formally-verified credit research ·{" "}
            <span className="text-[var(--foreground)]/80">Cerebras + Gemma</span>
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="hidden md:block text-right border-r border-[var(--border)] pr-4">
          <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Analyst query</div>
          <div className="text-[13px] mono mt-0.5">
            Compare {a.ticker} ’{a.maturity.slice(2, 4)} vs {b.ticker} ’{b.maturity.slice(2, 4)} — better buy?
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <button
            onClick={onRun}
            disabled={running}
            className="rounded-lg px-5 py-2.5 font-semibold text-sm transition
              bg-[var(--cerebras)] text-black hover:brightness-110 disabled:opacity-50
              disabled:cursor-not-allowed shadow-[0_0_24px_-6px_var(--cerebras)]
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cerebras)]"
          >
            {running ? "Running…" : "Run comparison"}
          </button>
          <WarmBadge warm={warm} />
        </div>
      </div>
    </header>
  );
}

function WarmBadge({ warm }: { warm: "warming" | "ready" | "sim" }) {
  if (warm === "sim") {
    return <span className="text-[10px] text-[var(--muted)] mono">simulated · no warm-up needed</span>;
  }
  if (warm === "warming") {
    return (
      <span className="text-[10px] text-[var(--muted)] mono flex items-center gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--cerebras-2)] pulse" />
        warming engines…
      </span>
    );
  }
  return (
    <span className="text-[10px] text-[var(--good)] mono flex items-center gap-1">
      <span className="h-1.5 w-1.5 rounded-full bg-[var(--good)]" />
      engines warm · steady-state speed
    </span>
  );
}

function BondPickers({
  aId, bId, setAId, setBId, running, reset,
}: {
  aId: string; bId: string;
  setAId: (s: string) => void; setBId: (s: string) => void;
  running: boolean; reset: () => void;
}) {
  const opts = BONDS.map((x) => (
    <option key={x.id} value={x.id}>
      {x.ticker} {x.maturity.slice(0, 4)} · {x.couponPct}% · {x.rating}
    </option>
  ));
  const sel = "bg-[var(--panel-2)] border border-[var(--border)] rounded-md px-2 py-1.5 text-sm mono";
  return (
    <div className="flex flex-wrap items-center gap-2 mt-3 text-sm">
      <span className="text-xs text-[var(--muted)] uppercase tracking-wide">Compare</span>
      <select className={sel} value={aId} disabled={running}
        onChange={(e) => { reset(); setAId(e.target.value); }}>{opts}</select>
      <span className="text-[var(--muted)]">vs</span>
      <select className={sel} value={bId} disabled={running}
        onChange={(e) => { reset(); setBId(e.target.value); }}>{opts}</select>
      <button
        className="text-xs text-[var(--accent)] underline-offset-2 hover:underline disabled:opacity-40"
        disabled={running}
        onClick={() => { reset(); setAId("SPACEX-2027"); setBId("SPACEX-2030"); }}
      >
        reset to SpaceX pair
      </button>
    </div>
  );
}

function MetricStat({ label, value, unit, highlight }: { label: string; value: string; unit?: string; highlight?: boolean }) {
  return (
    <div className="flex-1 min-w-[68px]">
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className={`mono font-bold leading-tight ${highlight ? "text-[var(--good)]" : "text-[var(--foreground)]"} text-lg sm:text-xl`}>
        {value}<span className="text-xs font-normal text-[var(--muted)] ml-0.5">{unit}</span>
      </div>
    </div>
  );
}

function ProviderPanel({
  kind, title, subtitle, text, metrics, status, accent, thinking,
}: {
  kind: "cerebras" | "gpu"; title: string; subtitle: string;
  text: string; metrics: Metrics | null; status: Status; accent?: boolean; thinking?: boolean;
}) {
  const borderC = accent ? "border-[var(--cerebras)]/60" : "border-[var(--border)]";
  const glow = accent ? "shadow-[0_0_40px_-18px_var(--cerebras)]" : "";
  return (
    <div className={`rounded-xl border ${borderC} ${glow} bg-[var(--panel)] p-4 flex flex-col`}>
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${accent ? "bg-[var(--cerebras)]" : "bg-[var(--gpu)]"} ${status === "streaming" ? "pulse" : ""}`} />
            <h2 className="font-bold text-lg">{title}</h2>
            {metrics?.simulated && (
              <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-[var(--panel-2)] text-[var(--muted)] border border-[var(--border)]">
                simulated
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--muted)] mt-0.5">{subtitle}</p>
        </div>
        <div className="text-[10px] mono text-[var(--muted)] text-right">
          {metrics?.model}
        </div>
      </div>

      {/* live metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-2 mt-3 pb-3 border-b border-[var(--border)]">
        <MetricStat label="TTFT" value={metrics?.ttftMs != null ? String(metrics.ttftMs) : "—"} unit="ms" highlight={accent} />
        <MetricStat label="Tokens/s" value={metrics ? String(metrics.tps) : "—"} unit="t/s" highlight={accent} />
        <MetricStat label="Latency" value={metrics ? (metrics.elapsedMs / 1000).toFixed(2) : "—"} unit="s" />
        <MetricStat label="Tokens" value={metrics ? String(metrics.tokens) : "—"} />
      </div>

      {/* streaming text */}
      <div className="mono text-[13px] leading-relaxed text-[var(--foreground)]/90 mt-3 h-[230px] overflow-y-auto scroll-thin whitespace-pre-wrap">
        {text ? (
          <span className={status === "streaming" ? "caret" : ""}>{text}</span>
        ) : thinking ? (
          <span className="inline-flex items-center gap-2 text-[var(--cerebras-2)]">
            <span className="inline-flex gap-1">
              <span className="dot h-1.5 w-1.5 rounded-full bg-current" />
              <span className="dot h-1.5 w-1.5 rounded-full bg-current" style={{ animationDelay: "0.18s" }} />
              <span className="dot h-1.5 w-1.5 rounded-full bg-current" style={{ animationDelay: "0.36s" }} />
            </span>
            <span className="text-xs uppercase tracking-wide">Reasoning</span>
            <span className="text-[var(--muted)] text-xs">— model thinks before it answers</span>
          </span>
        ) : (
          <span className="text-[var(--muted)]">{status === "streaming" ? "…" : "Awaiting query."}</span>
        )}
      </div>
    </div>
  );
}

function VerifiedFacts({
  claims, verdicts, revealed, leanInfo, verifyState, verifiedCount,
}: {
  claims: Claim[]; verdicts: Record<string, boolean>; revealed: number;
  leanInfo: { available: boolean; durationMs: number; version?: string } | null;
  verifyState: "idle" | "running" | "done"; verifiedCount: number;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)] p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide text-[var(--muted)] uppercase">
          Formally Verified Facts
        </h2>
        <div className="text-xs mono">
          {verifyState === "running" && <span className="text-[var(--accent)]">running Lean…</span>}
          {verifyState === "done" && leanInfo?.available && (
            <span className="text-[var(--good)]">
              ✓ {verifiedCount}/{claims.length} proved · {leanInfo.durationMs}ms
            </span>
          )}
          {verifyState === "done" && leanInfo && !leanInfo.available && (
            <span className="text-[var(--cerebras-2)]">Lean not installed — facts unverified</span>
          )}
        </div>
      </div>

      {claims.length === 0 ? (
        <p className="text-sm text-[var(--muted)] mt-6">
          Run a comparison. Each quantitative claim is extracted from source data and
          proved by Lean&apos;s kernel before it is shown — no hallucinated numbers reach the desk.
        </p>
      ) : (
        <ul className="space-y-2 mt-2">
          {claims.slice(0, revealed).map((c) => (
            <ClaimCard key={c.id} claim={c} verified={verdicts[c.id]} />
          ))}
        </ul>
      )}

      {leanInfo?.version && verifyState === "done" && (
        <p className="text-[10px] text-[var(--muted)] mt-3 mono">{leanInfo.version}</p>
      )}
    </div>
  );
}

function ClaimCard({ claim, verified }: { claim: Claim; verified: boolean | undefined }) {
  const [open, setOpen] = useState(false);
  const known = verified !== undefined;
  return (
    <li
      className="pop-in rounded-lg border border-[var(--border)] bg-[var(--panel-2)] p-3 cursor-pointer hover:border-[var(--good)]/50 transition"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <div className="flex items-start gap-2">
        <span className={`mt-0.5 shrink-0 text-sm ${verified ? "text-[var(--good)]" : known ? "text-[var(--cerebras)]" : "text-[var(--muted)]"}`}>
          {verified ? "✓" : known ? "✗" : "…"}
        </span>
        <div className="flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-sm">{claim.title}</span>
            <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 ${verified ? "bg-[var(--good)]/15 text-[var(--good)]" : "bg-[var(--panel)] text-[var(--muted)]"}`}>
              {verified ? "Verified in Lean" : known ? "refuted" : "checking"}
            </span>
          </div>
          <p className="text-xs text-[var(--muted)] mt-1">{claim.plainEnglish}</p>
          {open && (
            <pre className="mt-2 text-[11px] mono bg-black/40 border border-[var(--border)] rounded p-2 overflow-x-auto text-[var(--good)]">
{claim.leanStatement}
            </pre>
          )}
        </div>
      </div>
    </li>
  );
}
