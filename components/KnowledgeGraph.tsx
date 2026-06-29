"use client";

import { useMemo } from "react";
import type { Graph } from "@/lib/bonds";

const SECTOR_COLORS = [
  "#ff5a1f", "#38bdf8", "#a78bfa", "#2fe6a0", "#f472b6", "#facc15", "#fb7185",
];

type Pos = { x: number; y: number };

export default function KnowledgeGraph({
  graph,
  focusIds = [],
  highlightIds = [],
}: {
  graph: Graph;
  focusIds?: string[];
  highlightIds?: string[];
}) {
  const W = 760, H = 560, cx = W / 2, cy = H / 2;

  const { pos, sectors } = useMemo(() => {
    const sectorMap = new Map<string, string[]>();
    for (const n of graph.nodes) {
      if (!sectorMap.has(n.sector)) sectorMap.set(n.sector, []);
      sectorMap.get(n.sector)!.push(n.id);
    }
    const sectors = Array.from(sectorMap.keys());
    const pos = new Map<string, Pos>();
    const R = 200; // cluster ring radius
    sectors.forEach((sector, si) => {
      const angle = (si / sectors.length) * Math.PI * 2 - Math.PI / 2;
      const clusterX = cx + Math.cos(angle) * R;
      const clusterY = cy + Math.sin(angle) * R;
      const members = sectorMap.get(sector)!;
      members.forEach((id, mi) => {
        if (members.length === 1) {
          pos.set(id, { x: clusterX, y: clusterY });
        } else {
          const a = (mi / members.length) * Math.PI * 2;
          const r = 46 + members.length * 4;
          pos.set(id, { x: clusterX + Math.cos(a) * r, y: clusterY + Math.sin(a) * r });
        }
      });
    });
    return { pos, sectors };
  }, [graph, cx, cy]);

  const focus = new Set(focusIds);
  const highlight = new Set(highlightIds);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full">
      {/* edges */}
      {graph.edges.map((e, i) => {
        const a = pos.get(e.source), b = pos.get(e.target);
        if (!a || !b) return null;
        const isFocus = focus.has(e.source) || focus.has(e.target);
        const isHi =
          (highlight.has(e.source) && highlight.has(e.target)) ||
          (e.kind === "similar" && (focus.has(e.source) || focus.has(e.target)));
        const color = e.kind === "issuer" ? "#ff5a1f" : e.kind === "similar" ? "#38bdf8" : "#2a3142";
        return (
          <line
            key={i}
            x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke={color}
            strokeWidth={e.kind === "issuer" ? 2.4 : isHi ? 1.8 : 1}
            strokeOpacity={isHi || isFocus ? 0.9 : 0.28}
            strokeDasharray={e.kind === "similar" ? "4 3" : undefined}
          />
        );
      })}

      {/* nodes */}
      {graph.nodes.map((n) => {
        const p = pos.get(n.id);
        if (!p) return null;
        const isFocus = focus.has(n.id);
        const isHi = highlight.has(n.id);
        const color = SECTOR_COLORS[n.group % SECTOR_COLORS.length];
        const r = isFocus ? 13 : isHi ? 10 : 7;
        // Place the label above the node, but flip it below when that would
        // clip against the top edge — keeps every label fully on-canvas.
        const aboveY = p.y - r - 5;
        const labelBelow = aboveY < 12;
        const labelY = labelBelow ? p.y + r + 13 : aboveY;
        return (
          <g key={n.id} className={isFocus ? "pulse" : undefined}>
            {(isFocus || isHi) && (
              <circle cx={p.x} cy={p.y} r={r + 7} fill={color} opacity={0.18} />
            )}
            <circle
              cx={p.x} cy={p.y} r={r}
              fill={color}
              stroke={isFocus ? "#fff" : "#0c0e14"}
              strokeWidth={isFocus ? 2 : 1.5}
            />
            <text
              x={p.x} y={labelY}
              textAnchor="middle"
              fontSize={isFocus ? 13 : 10.5}
              fontWeight={isFocus ? 700 : 500}
              fill={isFocus ? "#fff" : "#aeb6c6"}
              className="mono"
              stroke="#0c0e14"
              strokeWidth={3}
              strokeLinejoin="round"
              paintOrder="stroke"
            >
              {n.label}
            </text>
          </g>
        );
      })}

      {/* sector legend */}
      {sectors.map((s, i) => (
        <g key={s} transform={`translate(14, ${20 + i * 18})`}>
          <circle cx={5} cy={-4} r={5} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />
          <text x={16} y={0} fontSize={11} fill="#8b93a7">{s}</text>
        </g>
      ))}
    </svg>
  );
}
