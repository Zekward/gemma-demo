import { warmupProvider } from "@/lib/providers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Warm both engines in parallel so the first *measured* comparison reflects
// steady-state speed, not cold-start. Called once on page load.
export async function POST() {
  const [cerebras, gpu] = await Promise.all([
    warmupProvider("cerebras"),
    warmupProvider("gpu"),
  ]);
  return Response.json({ cerebras, gpu });
}
