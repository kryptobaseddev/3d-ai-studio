import { useEffect, useRef, useState } from "react";
import { Scene } from "./components/Scene";
import { ModelViewer } from "./components/ModelViewer";
import { Gallery } from "./components/Gallery";
import { ReportPanel } from "./components/ReportPanel";
import { Customizer } from "./components/Customizer";
import type { Manifest, ManifestEntry, Report } from "./types";
import { asset } from "./types";

export default function App() {
  const [models, setModels] = useState<ManifestEntry[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rev, setRev] = useState(0); // bumps when output/ changes -> busts caches
  const lastManifest = useRef<string>("");

  const selected = models.find((m) => m.id === selectedId) ?? null;

  // poll the manifest so regenerated models appear LIVE during a design session
  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const r = await fetch(asset("output/manifest.json") + `?t=${Date.now()}`, { cache: "no-store" });
        if (!r.ok) throw new Error(`manifest ${r.status}`);
        const text = await r.text();
        if (text !== lastManifest.current) {
          lastManifest.current = text;
          const m = JSON.parse(text) as Manifest;
          setModels(m.models);
          setRev((v) => v + 1);
          setError(null);
          setSelectedId((cur) => cur ?? (m.models[0]?.id ?? null));
        }
      } catch (e: any) {
        if (!lastManifest.current) setError(`No models yet (${e.message}). Generate one with studio3d, it will appear here live.`);
      }
      if (!stop) setTimeout(poll, 2500);
    }
    poll();
    return () => { stop = true; };
  }, []);

  // fetch the detailed report whenever the selection or revision changes
  useEffect(() => {
    if (!selected) return;
    fetch(asset(`output/${selected.id}/report.json`) + `?v=${rev}`, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Report>) : null))
      .then(setReport)
      .catch(() => setReport(null));
  }, [selectedId, rev]);

  const setSelected = (m: ManifestEntry) => setSelectedId(m.id);

  // Display the STL: raw mm, Z-up — identical to our authoring/slicer frame, so
  // orientation is unambiguous. (GLB/3MF remain available as downloads.)
  const fileName = selected?.files.stl || selected?.files.glb;
  // ?v=rev busts the loader cache so a regenerated model reloads live
  const modelUrl = selected && fileName ? asset(`output/${selected.id}/${fileName}`) + `?v=${rev}` : null;
  const bed = selected?.bed_mm?.[0] ?? (selected?.printer_profile === "resin" ? 218 : 256);
  const color = selected?.color ?? "#9aa7b2";

  return (
    <div className="app">
      <Gallery models={models} selectedId={selected?.id ?? null} onSelect={setSelected} />

      <main className="stage">
        <header>
          <h1>3D Studio</h1>
          <span className="tagline">natural language → print-ready 3D</span>
          {selected && (
            <div className="downloads">
              {selected.files.stl && <a href={asset(`output/${selected.id}/${selected.files.stl}`)} download>STL</a>}
              {selected.files["3mf"] && <a href={asset(`output/${selected.id}/${selected.files["3mf"]}`)} download>3MF</a>}
              {selected.files.glb && <a href={asset(`output/${selected.id}/${selected.files.glb}`)} download>GLB</a>}
            </div>
          )}
        </header>

        <div className="canvas-wrap">
          {error && <div className="overlay">{error}</div>}
          {modelUrl && (
            <Scene bed={bed} key={`${selected!.id}:${rev}`}>
              <ModelViewer url={modelUrl} color={color} />
            </Scene>
          )}
        </div>
        {selected && <p className="prompt">“{selected.prompt}”</p>}
        <Customizer model={selected} rev={rev} />
      </main>

      <ReportPanel report={report} />
    </div>
  );
}
