import { NextRequest } from "next/server";
import { PROVIDERS, ProviderId, streamProvider, ChatMessage } from "@/lib/providers";
import { getBond, Bond } from "@/lib/bonds";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function bondFacts(b: Bond): string {
  return [
    `${b.ticker} ${b.maturity.slice(0, 4)} (${b.id})`,
    `  issuer: ${b.issuer}`,
    `  coupon: ${b.couponPct}%   yield-to-maturity: ${b.ytmPct}%   price: ${b.pricePct}`,
    `  spread: ${b.spreadBps} bps over treasury   modified duration: ${b.durationYears}y`,
    `  rating: ${b.rating}   seniority: ${b.seniority}   maturity: ${b.maturity}   outstanding: $${b.amountOutstandingUSDmm}mm`,
  ].join("\n");
}

function buildMessages(a: Bond, b: Bond): ChatMessage[] {
  return [
    {
      role: "system",
      content:
        "You are AIQ, a fixed-income research assistant for institutional credit analysts. " +
        "Answer only from the figures provided. Be concise, decisive, and use exact numbers. " +
        "Never invent data. Structure: a one-line verdict, then the carry/duration/credit trade-off, then who each bond suits.",
    },
    {
      role: "user",
      content:
        `Compare these two bonds and tell me which is the better buy.\n\n${bondFacts(a)}\n\n${bondFacts(b)}\n\n` +
        `Keep it under 180 words.`,
    },
  ];
}

export async function POST(req: NextRequest) {
  const { provider, aId, bId } = (await req.json()) as {
    provider: ProviderId;
    aId: string;
    bId: string;
  };

  if (!PROVIDERS[provider]) {
    return new Response("unknown provider", { status: 400 });
  }
  const a = getBond(aId);
  const b = getBond(bId);
  if (!a || !b) return new Response("unknown bond", { status: 400 });

  const stream = streamProvider(provider, buildMessages(a, b));
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
