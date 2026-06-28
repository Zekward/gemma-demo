import { NextRequest } from "next/server";
import { buildComparisonClaims } from "@/lib/claims";
import { verifyClaims } from "@/lib/lean";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const { aId, bId } = (await req.json()) as { aId: string; bId: string };
  const built = buildComparisonClaims(aId, bId);
  if (!built) return new Response("unknown bond", { status: 400 });

  const result = await verifyClaims(built.claims);
  return Response.json({
    claims: built.claims,
    result,
  });
}
