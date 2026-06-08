// Copy the harness output/ bundles into web/public/output/ so they ship into
// the static build verbatim. Run `npm run sync` before `npm run dev`/`build`.
import { cp, mkdir, rm, access } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../../output");
const dst = resolve(here, "../public/output");

try {
  await access(src);
} catch {
  console.error(`No harness output at ${src}. Generate models first (studio3d gen-script ...).`);
  process.exit(1);
}

await rm(dst, { recursive: true, force: true });
await mkdir(dst, { recursive: true });
await cp(src, dst, { recursive: true });
console.log(`Synced ${src} -> ${dst}`);
