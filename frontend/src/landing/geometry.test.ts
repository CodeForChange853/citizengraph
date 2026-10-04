import { describe, expect, it } from "vitest";
import { OFFICE_CELLS, RINGS, TARGET, TRAIL } from "./geometry";

const area = (poly: { x: number; y: number }[]) =>
  Math.abs(poly.reduce((sum, p, i) => sum + p.x * poly[(i + 1) % poly.length]!.y - poly[(i + 1) % poly.length]!.x * p.y, 0)) / 2;

describe("stage geometry", () => {
  it("has four office cells that tile the square", () => {
    expect(OFFICE_CELLS.map((o) => o.id)).toEqual(["BPLO", "LCRO", "CHO", "CSWDO"]);
    expect(OFFICE_CELLS.reduce((sum, o) => sum + area(o.cell), 0)).toBeCloseTo(1, 6);
  });

  it("puts 40 service nodes inside their own office's cell", () => {
    expect(OFFICE_CELLS.map((o) => o.nodes.length)).toEqual([7, 17, 15, 1]);
    for (const office of OFFICE_CELLS) {
      for (const node of office.nodes) {
        const nearest = [...OFFICE_CELLS].sort(
          (a, b) => Math.hypot(a.hub.x - node.x, a.hub.y - node.y) - Math.hypot(b.hub.x - node.x, b.hub.y - node.y),
        )[0]!;
        expect(nearest.id).toBe(office.id);
      }
    }
  });

  it("is the same on every load and ends the trail on the demo service", () => {
    expect(OFFICE_CELLS[0]!.nodes[0]!.x).toMatchInlineSnapshot(`0.22958320332691073`);
    expect(RINGS).toHaveLength(7);
    expect(TRAIL[TRAIL.length - 1]).toEqual(TARGET);
    expect(OFFICE_CELLS[0]!.nodes).toContain(TARGET);
  });
});
