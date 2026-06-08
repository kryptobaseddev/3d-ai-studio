import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { createReadStream, existsSync, statSync } from "node:fs";
import { resolve, extname } from "node:path";

// Dev-only: serve the harness output/ folder directly at /output/* so the agent
// can regenerate models and the user sees them LIVE (the app polls manifest.json)
// with no copy/sync step. The production build uses the synced public/output.
function serveOutput(): Plugin {
  const root = resolve(__dirname, "../output");
  const mime: Record<string, string> = {
    ".json": "application/json", ".png": "image/png", ".stl": "model/stl",
    ".glb": "model/gltf-binary", ".3mf": "model/3mf",
  };
  return {
    name: "studio3d-serve-output",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req.url || "").split("?")[0];
        if (!url.startsWith("/output/")) return next();
        const file = resolve(root, decodeURIComponent(url.slice("/output/".length)));
        if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) return next();
        res.setHeader("Content-Type", mime[extname(file)] || "application/octet-stream");
        res.setHeader("Cache-Control", "no-store"); // always fresh for live updates
        createReadStream(file).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serveOutput()],
  base: "./",
  server: { port: 5173 },
});
