// Renders the placeholder app icons (plain blue rounded square with a "CG" monogram) to PNG.
// Run once after changing public/icon.svg or public/icon-maskable.svg:  npm run icons
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const out = (name) => fileURLToPath(new URL(`../public/${name}`, import.meta.url));
const jobs = [
  ["icon.svg", "pwa-192x192.png", 192],
  ["icon.svg", "pwa-512x512.png", 512],
  ["icon-maskable.svg", "maskable-512x512.png", 512],
  ["icon-maskable.svg", "apple-touch-icon.png", 180],
];

for (const [src, dest, size] of jobs) {
  await sharp(out(src), { density: 384 }).resize(size, size).png().toFile(out(dest));
  console.log(`${dest} ${size}x${size}`);
}
