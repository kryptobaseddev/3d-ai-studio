import type { ManifestEntry } from "../types";
import { asset } from "../types";

export function Gallery({
  models,
  selectedId,
  onSelect,
}: {
  models: ManifestEntry[];
  selectedId: string | null;
  onSelect: (m: ManifestEntry) => void;
}) {
  return (
    <nav className="gallery">
      <h2>Models <span className="count">{models.length}</span></h2>
      <ul>
        {models.map((m) => (
          <li
            key={m.id}
            className={m.id === selectedId ? "selected" : ""}
            onClick={() => onSelect(m)}
          >
            {m.files.thumb ? (
              <img src={asset(`output/${m.id}/${m.files.thumb}`)} alt={m.name} loading="lazy" />
            ) : (
              <div className="thumb-fallback" />
            )}
            <div className="meta">
              <span className="name">{m.name}</span>
              <span className="sub">
                <span className={`badge ${m.print_ready ? "ok" : "warn"}`}>{m.score ?? "?"}</span>
                {m.category} · {m.bbox_mm?.map((n) => Math.round(n)).join("×")}mm
              </span>
            </div>
          </li>
        ))}
      </ul>
    </nav>
  );
}
