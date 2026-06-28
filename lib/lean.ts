import { spawn } from "node:child_process";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { homedir } from "node:os";
import { Claim } from "@/lib/claims";

export type ClaimVerdict = { id: string; leanName: string; verified: boolean };
export type VerifyResult = {
  ok: boolean;
  available: boolean; // is the lean binary present
  verdicts: ClaimVerdict[];
  leanSource: string;
  durationMs: number;
  leanVersion?: string;
  error?: string;
};

// elan installs lean here on macOS; PATH in a Next server process may not have it.
const LEAN_BIN = process.env.LEAN_BIN || join(homedir(), ".elan", "bin", "lean");

function run(bin: string, args: string[], cwd?: string): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(bin, args, { cwd, env: process.env });
    let stdout = "", stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", () => resolve({ code: -1, stdout, stderr: "spawn-error" }));
    child.on("close", (code) => resolve({ code: code ?? -1, stdout, stderr }));
  });
}

export function buildLeanSource(claims: Claim[]): string {
  const header = [
    "-- AIQ formal verification layer",
    "-- Every numeric claim below is proved by Lean's kernel via `decide`.",
    "-- Figures are integers (basis points / tenths) drawn from source data.",
    "",
  ].join("\n");
  return header + claims.map((c) => c.leanStatement).join("\n") + "\n";
}

export async function verifyClaims(claims: Claim[]): Promise<VerifyResult> {
  const start = Date.now();
  const leanSource = buildLeanSource(claims);

  // Probe lean availability.
  const ver = await run(LEAN_BIN, ["--version"]);
  if (ver.code !== 0) {
    return {
      ok: false,
      available: false,
      verdicts: claims.map((c) => ({ id: c.id, leanName: c.leanName, verified: false })),
      leanSource,
      durationMs: Date.now() - start,
      error: "lean binary not found",
    };
  }
  const leanVersion = ver.stdout.trim();

  const dir = await mkdtemp(join(tmpdir(), "aiq-lean-"));
  const file = join(dir, "Claims.lean");
  try {
    await writeFile(file, leanSource, "utf8");
    const res = await run(LEAN_BIN, [file]);
    // exit 0 => the whole file type-checked => every theorem proved.
    // On failure, Lean names the offending declaration in stderr.
    const verdicts: ClaimVerdict[] = claims.map((c) => ({
      id: c.id,
      leanName: c.leanName,
      verified: res.code === 0 ? true : !new RegExp(`\\b${c.leanName}\\b`).test(res.stderr),
    }));
    return {
      ok: res.code === 0,
      available: true,
      verdicts,
      leanSource,
      durationMs: Date.now() - start,
      leanVersion,
      error: res.code === 0 ? undefined : res.stderr.slice(0, 800),
    };
  } finally {
    await rm(dir, { recursive: true, force: true }).catch(() => {});
  }
}
