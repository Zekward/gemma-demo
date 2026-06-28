// Two OpenAI-compatible inference backends, streamed side by side.
// `cerebras` is the wafer-scale engine; `gpu` is a conventional GPU host of the
// same Gemma model. We measure time-to-first-token, output tok/s and end-to-end
// latency on the server as tokens arrive, then forward both tokens and live
// metrics to the browser over SSE.

export type ProviderId = "cerebras" | "gpu";

export type ProviderConfig = {
  id: ProviderId;
  label: string;
  baseUrl: string;
  apiKey?: string;
  model: string;
  // tok/s used only by the simulated fallback when no API key is configured
  simTps: number;
  simTtftMs: number;
};

export const PROVIDERS: Record<ProviderId, ProviderConfig> = {
  cerebras: {
    id: "cerebras",
    label: "Cerebras",
    baseUrl: process.env.CEREBRAS_BASE_URL || "https://api.cerebras.ai/v1",
    apiKey: process.env.CEREBRAS_API_KEY,
    model: process.env.CEREBRAS_MODEL || "gemma-3-27b-it",
    simTps: 1100,
    simTtftMs: 90,
  },
  gpu: {
    id: "gpu",
    label: process.env.GPU_LABEL || "GPU (Together)",
    baseUrl: process.env.GPU_BASE_URL || "https://api.together.xyz/v1",
    apiKey: process.env.GPU_API_KEY,
    model: process.env.GPU_MODEL || "google/gemma-3-27b-it",
    simTps: 48,
    simTtftMs: 620,
  },
};

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

export type Metrics = {
  provider: ProviderId;
  ttftMs: number | null;
  tokens: number;
  elapsedMs: number;
  tps: number; // output tokens / second
  simulated: boolean;
  model: string;
};

const enc = new TextEncoder();
const sse = (obj: unknown) => enc.encode(`data: ${JSON.stringify(obj)}\n\n`);

function approxTokens(s: string): number {
  // ~4 chars/token heuristic for a live counter
  return Math.max(1, Math.round(s.length / 4));
}

export function streamProvider(providerId: ProviderId, messages: ChatMessage[]): ReadableStream<Uint8Array> {
  const cfg = PROVIDERS[providerId];
  if (!cfg.apiKey) return simulatedStream(cfg, messages);
  return realStream(cfg, messages);
}

function realStream(cfg: ProviderConfig, messages: ChatMessage[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const start = Date.now();
      let ttftMs: number | null = null;
      let tokens = 0;
      let text = "";

      const emitMetrics = (final = false) => {
        const elapsedMs = Date.now() - start;
        const m: Metrics = {
          provider: cfg.id,
          ttftMs,
          tokens,
          elapsedMs,
          tps: elapsedMs > 0 ? +(tokens / (elapsedMs / 1000)).toFixed(1) : 0,
          simulated: false,
          model: cfg.model,
        };
        controller.enqueue(sse({ t: final ? "done" : "metrics", m }));
      };

      try {
        const res = await fetch(`${cfg.baseUrl}/chat/completions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${cfg.apiKey}`,
          },
          body: JSON.stringify({ model: cfg.model, messages, stream: true, temperature: 0.3, max_tokens: 700 }),
        });

        if (!res.ok || !res.body) {
          const errText = await res.text().catch(() => res.statusText);
          controller.enqueue(sse({ t: "error", message: `${cfg.label} ${res.status}: ${errText.slice(0, 200)}` }));
          controller.close();
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let lastMetric = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const payload = trimmed.slice(5).trim();
            if (payload === "[DONE]") continue;
            try {
              const json = JSON.parse(payload);
              const delta: string = json.choices?.[0]?.delta?.content ?? "";
              if (delta) {
                if (ttftMs === null) ttftMs = Date.now() - start;
                text += delta;
                tokens = approxTokens(text);
                controller.enqueue(sse({ t: "token", v: delta }));
                const now = Date.now();
                if (now - lastMetric > 80) {
                  lastMetric = now;
                  emitMetrics();
                }
              }
            } catch {
              /* ignore keep-alive / partial */
            }
          }
        }
        emitMetrics(true);
        controller.close();
      } catch (e) {
        controller.enqueue(sse({ t: "error", message: `${cfg.label}: ${(e as Error).message}` }));
        controller.close();
      }
    },
  });
}

// Honest fallback: replays a grounded analysis at each engine's characteristic
// speed so the UI is fully functional before API keys are wired in. Clearly
// flagged `simulated: true` on the metrics so it is never mistaken for live.
function simulatedStream(cfg: ProviderConfig, messages: ChatMessage[]): ReadableStream<Uint8Array> {
  const body = SIM_ANALYSIS;
  const words = body.split(/(\s+)/); // keep whitespace tokens
  const msPerWord = 1000 / (cfg.simTps / 1.3); // simTps is tok/s; ~1.3 tok/word

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const start = Date.now();
      let ttftMs: number | null = null;
      let text = "";
      let i = 0;

      await new Promise((r) => setTimeout(r, cfg.simTtftMs));

      const tick = () => {
        if (i >= words.length) {
          const elapsedMs = Date.now() - start;
          controller.enqueue(
            sse({
              t: "done",
              m: {
                provider: cfg.id,
                ttftMs,
                tokens: approxTokens(text),
                elapsedMs,
                tps: +(approxTokens(text) / (elapsedMs / 1000)).toFixed(1),
                simulated: true,
                model: cfg.model,
              } satisfies Metrics,
            }),
          );
          controller.close();
          return;
        }
        if (ttftMs === null) ttftMs = Date.now() - start;
        const w = words[i++];
        text += w;
        controller.enqueue(sse({ t: "token", v: w }));
        const elapsedMs = Date.now() - start;
        controller.enqueue(
          sse({
            t: "metrics",
            m: {
              provider: cfg.id,
              ttftMs,
              tokens: approxTokens(text),
              elapsedMs,
              tps: +(approxTokens(text) / (elapsedMs / 1000)).toFixed(1),
              simulated: true,
              model: cfg.model,
            } satisfies Metrics,
          }),
        );
        setTimeout(tick, msPerWord);
      };
      tick();
    },
  });
}

const SIM_ANALYSIS = `Comparing the two SpaceX senior secured notes, the decision reduces to a classic carry-versus-duration trade-off.

The 2030 note offers 55 bps of additional yield (6.80% vs 6.25%) and a 50 bps wider spread to the curve, compensation for taking 2.2 years of additional modified duration. Both bonds are rated BB+ and sit pari passu on the secured stack, so this is a pure term-premium question rather than a credit-quality one.

For an investor with a 12–24 month horizon or a defensive rate view, the 2027 is the cleaner carry: shorter duration, less mark-to-market sensitivity, and a price closer to par. For total-return mandates expecting the front end of the curve to rally, the 2030 captures more spread and convexity.

Net: the 2030 is the better risk-adjusted buy only if you are paid enough for the extra duration. At 55 bps for 2.2 years, the breakeven is roughly 25 bps of widening per year — a thin cushion, so we lean to the 2027 for buy-and-hold books and the 2030 for tactical duration adds.`;
