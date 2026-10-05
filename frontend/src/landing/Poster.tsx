import type { ReactNode } from "react";
import type { SceneId } from "./scenes";

// Still pictures of the nine scenes, drawn as lines. They stand in for the 3D picture when WebGL is not
// there and when the device asks for reduced motion. Colours come from the tokens through the classes
// c (Core 1), o (Core 2), w (white line), g (grey line) and their filled forms (landing.css, .lp-posterart).

const range = (n: number) => Array.from({ length: n }, (_, i) => i);

function Core({ x, y, r, kind }: { x: number; y: number; r: number; kind: "c" | "o" }) {
  return (
    <>
      <circle cx={x} cy={y} r={r * 1.9} className={`${kind}f halo`} />
      <circle cx={x} cy={y} r={r} className={`${kind}f`} />
      <circle cx={x - r * 0.3} cy={y - r * 0.3} r={r * 0.28} className="wf shine" />
    </>
  );
}

function Case({ open = 0 }: { open?: number }) {
  return (
    <>
      <rect x={96 - open} y="96" width="104" height="108" rx="22" className="w" />
      <rect x={200 + open} y="96" width="104" height="108" rx="22" className="w" />
    </>
  );
}

/** Dots of one office, laid out on a small spiral so they never overlap. */
function Cluster({ x, y, n }: { x: number; y: number; n: number }) {
  return (
    <>
      {range(n).map((i) => {
        const a = i * 2.4;
        const r = 5 + 5.2 * Math.sqrt(i);
        return <circle key={i} cx={x + Math.cos(a) * r} cy={y + Math.sin(a) * r * 0.7} r="2.2" className="cf" />;
      })}
    </>
  );
}

const ART: Record<SceneId, ReactNode> = {
  title: (
    <>
      <Case />
      <Core x={148} y={150} r={30} kind="c" />
      <Core x={252} y={150} r={30} kind="o" />
    </>
  ),
  question: (
    <>
      {range(6).map((i) => {
        const k = 1 / (1 + i * 0.55);
        return <rect key={i} x={200 - 170 * k} y={150 - 115 * k} width={340 * k} height={230 * k} className="w" opacity={1 - i * 0.13} />;
      })}
      {range(4).map((i) => {
        const k = 1 / (1 + i * 0.6);
        const [x, y] = [200 - 95 * k, 150 + 40 * k];
        return (
          <g key={i} className="g">
            <circle cx={x} cy={y - 62 * k} r={11 * k} />
            <path d={`M${x - 18 * k} ${y + 50 * k} L${x - 16 * k} ${y - 36 * k} Q${x} ${y - 50 * k} ${x + 16 * k} ${y - 36 * k} L${x + 18 * k} ${y + 50 * k}`} />
          </g>
        );
      })}
      {[
        [250, 90, -18],
        [300, 170, 24],
        [118, 70, 12],
      ].map(([x, y, turn], i) => (
        <g key={i} transform={`translate(${x} ${y}) rotate(${turn})`} className="w">
          <rect x="-17" y="-24" width="34" height="48" />
          <path d="M-10 -12H6M-10 -3H10M-10 6H10M-10 15H4" className="g" />
        </g>
      ))}
    </>
  ),
  guide: (
    <>
      <rect x="20" y="96" width="104" height="108" rx="22" className="g" />
      <rect x="276" y="96" width="104" height="108" rx="22" className="g" />
      {[58, 80, 104].map((r, i) => (
        <circle key={r} cx="200" cy="150" r={r} className="c" opacity={0.8 - i * 0.25} />
      ))}
      <Core x={200} y={150} r={38} kind="c" />
    </>
  ),
  journey: (
    <>
      <path d="M200 40 L78 150M200 40 L212 118M200 40 L318 168M200 40 L150 232" className="c beam" />
      <Cluster x={78} y={160} n={7} />
      <Cluster x={214} y={130} n={17} />
      <Cluster x={320} y={178} n={15} />
      <Cluster x={150} y={238} n={1} />
      <circle cx="78" cy="160" r="11" className="w" />
      <Core x={200} y={40} r={13} kind="c" />
    </>
  ),
  answer: (
    <>
      <ellipse cx="118" cy="150" rx="92" ry="24" className="o" />
      <ellipse cx="118" cy="150" rx="70" ry="16" className="o" opacity="0.6" />
      <circle cx="118" cy="150" r="38" className="hole" />
      <circle cx="118" cy="150" r="38" className="o" />
      <rect x="230" y="78" width="150" height="144" rx="12" className="w" />
      {range(4).map((i) => (
        <g key={i}>
          <rect x="244" y={98 + i * 30} width="13" height="13" rx="3" className="cf" />
          <path d={`M268 ${104.5 + i * 30}H${350 - (i % 2) * 22}`} className="g" />
        </g>
      ))}
    </>
  ),
  watch: (
    <>
      <circle cx="200" cy="150" r="104" className="o" />
      {range(60).map((i) => {
        const a = (i / 60) * Math.PI * 2;
        const r0 = i % 5 === 0 ? 88 : 95;
        return <path key={i} d={`M${200 + Math.sin(a) * r0} ${150 - Math.cos(a) * r0}L${200 + Math.sin(a) * 104} ${150 - Math.cos(a) * 104}`} className="w" />;
      })}
      <path d="M200 150 L262 204" className="w hand" />
      <Core x={200} y={150} r={40} kind="o" />
    </>
  ),
  request: (
    <>
      <path d="M52 64 C70 110 84 140 96 150 S150 200 160 196" className="o thread" />
      <path d="M160 196 C190 180 210 140 232 138" className="g thread dash" />
      <path d="M232 138 C262 140 276 180 292 190" className="o thread" />
      <path d="M292 190 C300 196 306 198 316 198" className="o thread hot" />
      <path d="M316 198 C340 196 356 170 372 150" className="g" />
      <path d="M288 178 L296 202" className="w" />
      {[
        [96, 150, "o"],
        [160, 196, "o"],
        [232, 138, "g"],
        [326, 198, "o"],
        [372, 150, "w"],
      ].map(([x, y, kind], i) => (
        <circle key={i} cx={x} cy={y} r="7" className={`${kind} node`} />
      ))}
      <circle cx="316" cy="198" r="20" className="o" opacity="0.5" />
      <circle cx="52" cy="64" r="30" className="o" />
      <Core x={52} y={64} r={15} kind="o" />
    </>
  ),
  together: (
    <>
      <circle cx="148" cy="150" r="62" className="c" opacity="0.5" />
      <circle cx="252" cy="150" r="62" className="o" opacity="0.5" />
      <Case />
      <Core x={148} y={150} r={30} kind="c" />
      <Core x={252} y={150} r={30} kind="o" />
    </>
  ),
  close: (
    <>
      <ellipse cx="200" cy="150" rx="150" ry="34" className="o" opacity="0.7" />
      <ellipse cx="200" cy="150" rx="118" ry="22" className="o" opacity="0.45" />
      <circle cx="200" cy="150" r="66" className="hole" />
      <circle cx="200" cy="150" r="66" className="o" />
      <circle cx="200" cy="150" r="74" className="o" opacity="0.35" />
    </>
  ),
};

export function Poster({ scene, label }: { scene: SceneId; label: string }) {
  return (
    <svg className="lp-posterart" data-poster={scene} viewBox="0 0 400 300" role="img" aria-label={label}>
      {ART[scene]}
    </svg>
  );
}
