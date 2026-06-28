import bondsData from "@/data/bonds.json";

export type Bond = {
  id: string;
  issuer: string;
  ticker: string;
  sector: string;
  couponPct: number;
  maturity: string; // ISO date
  ytmPct: number;
  pricePct: number;
  rating: string;
  spreadBps: number;
  amountOutstandingUSDmm: number;
  durationYears: number;
  country: string;
  seniority: string;
};

export const BONDS: Bond[] = bondsData.bonds as Bond[];
export const DATA_META = bondsData.meta;

export function getBond(id: string): Bond | undefined {
  return BONDS.find((b) => b.id === id);
}

export function maturityYear(b: Bond): number {
  return parseInt(b.maturity.slice(0, 4), 10);
}

// Rough credit-rating ordinal (higher = safer) for similarity + graph.
const RATING_ORDER = [
  "D", "C", "CC", "CCC-", "CCC", "CCC+", "B-", "B", "B+",
  "BB-", "BB", "BB+", "BBB-", "BBB", "BBB+", "A-", "A", "A+",
  "AA-", "AA", "AA+", "AAA",
];
export function ratingScore(rating: string): number {
  const i = RATING_ORDER.indexOf(rating);
  return i === -1 ? 9 : i;
}

// Feature vector used for "find similar bonds" (cosine similarity).
function featureVector(b: Bond): number[] {
  return [
    b.ytmPct / 10,
    b.spreadBps / 600,
    b.durationYears / 5,
    ratingScore(b.rating) / 21,
    (maturityYear(b) - 2026) / 6,
    b.couponPct / 10,
  ];
}

function cosine(a: number[], v: number[]): number {
  let dot = 0, na = 0, nv = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * v[i];
    na += a[i] * a[i];
    nv += v[i] * v[i];
  }
  return dot / (Math.sqrt(na) * Math.sqrt(nv) + 1e-9);
}

export function similarBonds(id: string, k = 10): { bond: Bond; score: number }[] {
  const target = getBond(id);
  if (!target) return [];
  const tv = featureVector(target);
  return BONDS.filter((b) => b.id !== id)
    .map((b) => ({ bond: b, score: cosine(tv, featureVector(b)) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}

export type GraphNode = {
  id: string;
  label: string;
  sector: string;
  ytmPct: number;
  spreadBps: number;
  rating: string;
  group: number; // sector index, for coloring
  highlight?: boolean;
};

export type GraphEdge = {
  source: string;
  target: string;
  kind: "issuer" | "sector" | "similar";
  weight: number;
};

export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };

const SECTORS = Array.from(new Set(BONDS.map((b) => b.sector)));

// Build a knowledge graph: same-issuer edges (strong), same-sector edges,
// and top similarity edges. Optionally highlight a focus set (e.g. the two
// bonds being compared).
export function buildGraph(focusIds: string[] = []): Graph {
  const nodes: GraphNode[] = BONDS.map((b) => ({
    id: b.id,
    label: `${b.ticker} '${b.maturity.slice(2, 4)}`,
    sector: b.sector,
    ytmPct: b.ytmPct,
    spreadBps: b.spreadBps,
    rating: b.rating,
    group: SECTORS.indexOf(b.sector),
    highlight: focusIds.includes(b.id),
  }));

  const edges: GraphEdge[] = [];
  const seen = new Set<string>();
  const addEdge = (a: string, b: string, kind: GraphEdge["kind"], weight: number) => {
    const key = [a, b].sort().join("|") + kind;
    if (seen.has(key) || a === b) return;
    seen.add(key);
    edges.push({ source: a, target: b, kind, weight });
  };

  // Same issuer
  for (let i = 0; i < BONDS.length; i++) {
    for (let j = i + 1; j < BONDS.length; j++) {
      if (BONDS[i].ticker === BONDS[j].ticker) {
        addEdge(BONDS[i].id, BONDS[j].id, "issuer", 1);
      }
    }
  }
  // Same sector (sparse: link each bond to nearest-by-spread same-sector peer)
  for (const sector of SECTORS) {
    const inSector = BONDS.filter((b) => b.sector === sector);
    for (const b of inSector) {
      const peer = inSector
        .filter((p) => p.id !== b.id)
        .sort((p, q) => Math.abs(p.spreadBps - b.spreadBps) - Math.abs(q.spreadBps - b.spreadBps))[0];
      if (peer) addEdge(b.id, peer.id, "sector", 0.5);
    }
  }
  // Cross-sector similarity for focus nodes (so the graph "explains" comparisons)
  for (const id of focusIds) {
    for (const { bond, score } of similarBonds(id, 4)) {
      addEdge(id, bond.id, "similar", score);
    }
  }

  return { nodes, edges };
}

export const SECTOR_LIST = SECTORS;
