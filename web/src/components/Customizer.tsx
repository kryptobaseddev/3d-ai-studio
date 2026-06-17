import { useEffect, useMemo, useState } from "react";
import type { ManifestEntry } from "../types";
import { asset } from "../types";

/**
 * The parametric Customizer — the structural moat over Meshy made visible.
 * Every studio3d model ships regenerable SOURCE (model.py) + named knobs
 * (params.json). This panel surfaces those knobs as inputs and emits the exact
 * `studio3d tweak` command that regenerates the model deterministically with the
 * changed value — and the 3D view updates LIVE (the app polls output/). A dead
 * Meshy mesh has no knobs to turn.
 */
export function Customizer({ model, rev }: { model: ManifestEntry | null; rev: number }) {
  const params = model?.parameters ?? {};
  const keys = Object.keys(params);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [showSource, setShowSource] = useState(false);
  const [source, setSource] = useState<string | null>(null);

  // reset local edits when the selected model (or its revision) changes
  useEffect(() => {
    const v: Record<string, string> = {};
    for (const k of keys) v[k] = String(params[k]);
    setVals(v);
    setSource(null);
    setShowSource(false);
  }, [model?.id, rev]);

  useEffect(() => {
    if (!showSource || !model?.files.source) return;
    fetch(asset(`output/${model.id}/${model.files.source}`) + `?v=${rev}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.text() : null))
      .then(setSource)
      .catch(() => setSource(null));
  }, [showSource, model?.id, rev]);

  // which params changed from the baseline → only those go into --set
  const changed = useMemo(() => {
    const out: [string, string][] = [];
    for (const k of keys) {
      if (vals[k] !== undefined && vals[k] !== String(params[k])) out.push([k, vals[k]]);
    }
    return out;
  }, [vals, params]);

  if (!model) return null;
  if (!model.editable && keys.length === 0) {
    return (
      <section className="customizer none">
        <h3>Parametric source</h3>
        <p className="muted">This bundle has no editable source yet. Regenerate with the CSG engine to get a forever-editable model.</p>
      </section>
    );
  }

  const plan = model.files.plan ? `output/${model.id}/${model.files.plan}` : undefined;
  const src = model.files.source ? `output/${model.id}/${model.files.source}` : undefined;
  const setFlags = changed.map(([k, v]) => `--set ${k}=${v}`).join(" ");
  const cmd = plan
    ? `studio3d tweak --plan ${plan} ${setFlags} --script ${src ?? "model.py"}`.replace(/\s+/g, " ").trim()
    : `studio3d gen-script --script ${src ?? "model.py"} --name ${model.id} --params '${JSON.stringify(
        Object.fromEntries(changed.map(([k, v]) => [k, maybeNum(v)]))
      )}'`;

  return (
    <section className="customizer">
      <h3>Customizer {model.editable && <span className="badge real">editable</span>}
        {model.multicolor && <span className="badge real">AMS multicolor</span>}</h3>
      {model.multicolor && model.palette && model.palette.length > 1 && (
        <div className="palette" title="per-face AMS colors on a single CSG union">
          {model.palette.map((c) => (
            <span key={c} className="swatch" style={{ background: c }} title={c} />
          ))}
        </div>
      )}
      {keys.length === 0 && <p className="muted">No named parameters — author with <code>P.get(...)</code> to expose knobs.</p>}
      <div className="knobs">
        {keys.map((k) => (
          <label key={k} className="knob">
            <span>{k}</span>
            {typeof params[k] === "boolean" ? (
              <input type="checkbox" checked={vals[k] === "true"}
                     onChange={(e) => setVals((s) => ({ ...s, [k]: String(e.target.checked) }))} />
            ) : (
              <input type={typeof params[k] === "number" ? "number" : "text"} value={vals[k] ?? ""} step="any"
                     onChange={(e) => setVals((s) => ({ ...s, [k]: e.target.value }))} />
            )}
          </label>
        ))}
      </div>

      {changed.length > 0 && (
        <div className="regen">
          <p className="muted">Regenerate (the 3D view updates live):</p>
          <code className="cmd">{cmd}</code>
          <button onClick={() => navigator.clipboard?.writeText(cmd)}>Copy command</button>
        </div>
      )}

      <div className="src-actions">
        {model.files.source && (
          <button onClick={() => setShowSource((s) => !s)}>{showSource ? "Hide" : "View"} source (model.py)</button>
        )}
        {model.files.certificate && (
          <a href={asset(`output/${model.id}/${model.files.certificate}`)} target="_blank" rel="noreferrer">Certificate ↗</a>
        )}
      </div>
      {showSource && source && <pre className="source">{source}</pre>}
    </section>
  );
}

function maybeNum(v: string): number | string | boolean {
  if (v === "true") return true;
  if (v === "false") return false;
  const n = Number(v);
  return Number.isFinite(n) && v.trim() !== "" ? n : v;
}
