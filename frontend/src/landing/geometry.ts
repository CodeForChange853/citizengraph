// Stage geometry, in a unit square (0..1). Everything is computed once when the landing chunk loads,
// from a fixed seed, so the picture is the same on every visit and no frame does geometry work.
import { OFFICES } from "./demo";

export interface Pt {
  x: number;
  y: number;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** One site per office, placed so the cell areas roughly follow the service counts. */
const SITES: Pt[] = [
  { x: 0.2, y: 0.27 },
  { x: 0.69, y: 0.3 },
  { x: 0.36, y: 0.77 },
  { x: 0.89, y: 0.87 },
];

/** Keep the part of a convex polygon that is nearer to `a` than to `b`. */
function clipNearer(poly: Pt[], a: Pt, b: Pt): Pt[] {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const nx = b.x - a.x;
  const ny = b.y - a.y;
  const side = (p: Pt) => (p.x - mx) * nx + (p.y - my) * ny;
  const out: Pt[] = [];
  poly.forEach((p, i) => {
    const q = poly[(i + 1) % poly.length]!;
    const sp = side(p);
    const sq = side(q);
    if (sp <= 0) out.push(p);
    if (sp < 0 !== sq < 0 && sp !== sq) {
      const k = sp / (sp - sq);
      out.push({ x: p.x + (q.x - p.x) * k, y: p.y + (q.y - p.y) * k });
    }
  });
  return out;
}

function voronoi(sites: Pt[]): Pt[][] {
  const square: Pt[] = [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
    { x: 0, y: 1 },
  ];
  return sites.map((site, i) => sites.reduce((poly, other, j) => (i === j ? poly : clipNearer(poly, site, other)), square));
}

const dist = (a: Pt, b: Pt) => Math.hypot(a.x - b.x, a.y - b.y);

/** Scatter `count` points inside one cell: away from its edges, from its hub and from each other. */
function scatter(index: number, count: number, rand: () => number): Pt[] {
  const site = SITES[index]!;
  const inside = (p: Pt, margin: number) =>
    p.x > margin &&
    p.x < 1 - margin &&
    p.y > margin &&
    p.y < 1 - margin &&
    SITES.every((other, j) => j === index || dist(p, other) - dist(p, site) > margin * 1.6);
  const points: Pt[] = [];
  let gap = 0.085;
  let tries = 0;
  while (points.length < count) {
    const p = { x: rand(), y: rand() };
    if (inside(p, 0.035) && dist(p, site) > 0.06 && points.every((o) => dist(o, p) > gap)) points.push(p);
    else if (++tries % 300 === 0) gap *= 0.9;
  }
  return points;
}

export interface OfficeCell {
  id: string;
  count: number;
  hub: Pt;
  cell: Pt[];
  nodes: Pt[];
}

const rand = mulberry32(11032);
const CELLS = voronoi(SITES);

/** Four office cells holding 40 service nodes (7, 17, 15, 1). */
export const OFFICE_CELLS: OfficeCell[] = OFFICES.map((office, i) => ({
  id: office.id,
  count: office.services,
  hub: SITES[i]!,
  cell: CELLS[i]!,
  nodes: scatter(i, office.services, rand),
}));

/** Topographic contour rings round the middle of the graph: wobbly closed loops, as unit offsets. */
export const RING_SEGMENTS = 96;
export const RINGS: Pt[][] = Array.from({ length: 7 }, (_, k) => {
  const radius = 0.13 + k * 0.105;
  const [a, b, c] = [rand() * 6.28, rand() * 6.28, rand() * 6.28];
  return Array.from({ length: RING_SEGMENTS + 1 }, (_, s) => {
    const angle = (s / RING_SEGMENTS) * Math.PI * 2;
    const r = radius * (1 + 0.07 * Math.sin(3 * angle + a) + 0.045 * Math.sin(5 * angle + b) + 0.025 * Math.sin(8 * angle + c));
    return { x: Math.cos(angle) * r, y: Math.sin(angle) * r * 0.82 };
  });
});

/** The service the demo question is about: the BPLO node closest to its hub. */
const bplo = OFFICE_CELLS[0]!;
export const TARGET: Pt = bplo.nodes.reduce((best, p) => (dist(p, bplo.hub) < dist(best, bplo.hub) ? p : best));

function catmullRom(points: Pt[], perSegment: number): Pt[] {
  const out: Pt[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)]!;
    const p1 = points[i]!;
    const p2 = points[i + 1]!;
    const p3 = points[Math.min(points.length - 1, i + 2)]!;
    for (let s = 0; s < perSegment; s++) {
      const t = s / perSegment;
      const t2 = t * t;
      const t3 = t2 * t;
      out.push({
        x: 0.5 * (2 * p1.x + (p2.x - p0.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (3 * p1.x - p0.x - 3 * p2.x + p3.x) * t3),
        y: 0.5 * (2 * p1.y + (p2.y - p0.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (3 * p1.y - p0.y - 3 * p2.y + p3.y) * t3),
      });
    }
  }
  out.push(points[points.length - 1]!);
  return out;
}

/** The glow trail: in from the edge, through the graph to the office hub, and on to the service. */
export const TRAIL: Pt[] = catmullRom(
  [{ x: 1.06, y: 0.6 }, { x: 0.82, y: 0.66 }, { x: 0.56, y: 0.55 }, { x: 0.4, y: 0.4 }, bplo.hub, TARGET],
  18,
);
