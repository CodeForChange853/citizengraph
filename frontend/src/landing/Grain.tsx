import { useEffect, useRef } from "react";

const SIZE = 128;

/** Static film grain: a small noise tile drawn once and repeated as a background. */
export function Grain() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = SIZE;
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext("2d");
    } catch {
      // no canvas here (tests): the page simply has no grain
    }
    if (!ctx || !ref.current) return;
    const image = ctx.createImageData(SIZE, SIZE);
    // Fixed seed: the same grain every visit, and nothing random at run time.
    let seed = 20261004;
    for (let i = 0; i < image.data.length; i += 4) {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      image.data[i] = image.data[i + 1] = image.data[i + 2] = 255;
      image.data[i + 3] = seed >>> 24;
    }
    ctx.putImageData(image, 0, 0);
    ref.current.style.backgroundImage = `url(${canvas.toDataURL()})`;
  }, []);
  return <div ref={ref} className="lp-grain" aria-hidden="true" />;
}
