import type { Report } from "../types";

function Row({ label, ok }: { label: string; ok: boolean | null }) {
  const cls = ok === null ? "dot na" : ok ? "dot pass" : "dot fail";
  return (
    <div className="row">
      <span className={cls} />
      <span>{label}</span>
    </div>
  );
}

export function ReportPanel({ report }: { report: Report | null }) {
  if (!report) return <aside className="report empty">Select a model to see its print-readiness report.</aside>;

  const d1 = report.dimensions.D1_mesh_integrity;
  const d2 = report.dimensions.D2_slicer_pass;
  const d3 = report.dimensions.D3_print_geometry;
  const wall = report.metrics.wall_thickness;
  const km = report.metrics.kernel_metrics;
  const verdict = report.print_ready ? "PRINT-READY" : "NEEDS WORK";
  const d2real = d2.method === "slice";

  return (
    <aside className="report">
      <div className={`verdict ${report.print_ready ? "ok" : "warn"}`}>
        <span className="score">{report.score}</span>
        <span className="label">{verdict}</span>
      </div>

      <h3>D1 · Mesh Integrity</h3>
      <Row label="Watertight" ok={d1.watertight} />
      <Row label="Consistent normals (outward)" ok={d1.winding_consistent} />
      <Row label="Valid manifold volume" ok={d1.is_volume} />
      <Row label={`Non-manifold edges: ${d1.non_manifold_edges}`} ok={d1.non_manifold_edges === 0} />
      {km && (
        <Row label={`${km.n_components} part${km.n_components === 1 ? "" : "s"} · genus ${km.genus}`}
             ok={km.n_components === 1 && (km.genus ?? 0) >= 0} />
      )}

      <h3>D2 · Slicer Pass {d2real ? <span className="badge real">real slice</span> : <span className="badge proxy">proxy</span>}</h3>
      <Row label={d2real ? `Sliced to G-code via ${d2.slicer}` : "Opens cleanly (proxy — install a slicer for a real slice)"} ok={d2.pass} />
      {d2real && (d2.print_time || d2.filament_g != null) && (
        <p className="metric">
          {d2.print_time ? `⏱ ${d2.print_time}` : ""}{d2.print_time && d2.filament_g != null ? " · " : ""}
          {d2.filament_g != null ? `${d2.filament_g} g filament` : ""}
        </p>
      )}

      <h3>D3 · Print Geometry</h3>
      <Row label={`Fits build volume (${(d3.bed_mm || []).join("×")}mm)`} ok={d3.bed_fit} />
      {wall?.available && (() => {
        // p05 = effective minimum wall (robust); the absolute min is a single
        // grazing-ray sample and is not what the validator judges on.
        const effMin = (wall.p05 ?? wall.min) as number;
        return <Row label={`Min wall ${effMin}mm (need ≥${d3.min_wall_required_mm}mm)`} ok={effMin >= d3.min_wall_required_mm * 0.9} />;
      })()}
      <Row label={`Steepest overhang ${d3.steepest_overhang_deg}°`} ok={!d3.overhang_needs_support} />

      <h3>D4 · Workflow</h3>
      <Row label={`Recommended format: ${report.dimensions.D4_workflow.recommended_format.toUpperCase()}`} ok={true} />

      {report.metrics.est_mass_g_solid != null && (
        <p className="metric">
          ~{report.metrics.est_mass_g_solid} g · {report.metrics.triangles} tris ·{" "}
          {report.metrics.bbox_mm?.map((n) => Math.round(n)).join("×")} mm
        </p>
      )}

      {(report.warnings.length > 0 || report.suggestions.length > 0) && (
        <div className="advice">
          {report.warnings.map((w, i) => (
            <p key={`w${i}`} className="warn-line">⚠ {w}</p>
          ))}
          {report.suggestions.map((s, i) => (
            <p key={`s${i}`} className="sug-line">→ {s}</p>
          ))}
        </div>
      )}
    </aside>
  );
}
