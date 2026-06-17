// Shapes that mirror what the studio3d harness writes into output/.

export interface KernelMetrics {
  watertight?: boolean;
  manifold?: boolean;
  genus?: number;
  n_components?: number;
  volume_mm3?: number;
  triangles?: number;
  wall_p05_mm?: number | null;
  min_wall_required_mm?: number;
  steepest_overhang_deg?: number;
  overhang_needs_support?: boolean;
  bed_fit?: boolean;
}

export interface ManifestEntry {
  id: string;
  name: string;
  prompt: string;
  category?: string;
  printer_profile?: string;
  files: {
    stl?: string; "3mf"?: string; glb?: string; thumb?: string;
    source?: string; params?: string; plan?: string; certificate?: string;
  };
  editable?: boolean;
  parameters?: Record<string, number | string | boolean>;
  print_ready?: boolean;
  score?: number;
  bbox_mm?: [number, number, number];
  bed_mm?: [number, number, number];
  est_mass_g?: number;
  kernel_metrics?: KernelMetrics;
  slice?: { pass?: boolean; method?: string; slicer?: string; print_time?: string; filament_g?: number };
  color?: string;
}

export interface Manifest {
  generator: string;
  count: number;
  models: ManifestEntry[];
}

// The full per-model report.json (studio3d.validate.Report.to_dict()).
export interface Report {
  print_ready: boolean;
  score: number;
  dimensions: {
    D1_mesh_integrity: {
      pass: boolean;
      watertight: boolean;
      winding_consistent: boolean;
      is_volume: boolean;
      non_manifold_edges: number;
      self_intersections: number | null;
      euler_number: number;
    };
    D2_slicer_pass: {
      pass: boolean; rationale: string; method?: string; slicer?: string;
      print_time?: string; filament_g?: number; error?: string; slice_note?: string;
    };
    D3_print_geometry: {
      pass: boolean;
      min_wall_required_mm: number;
      bed_fit: boolean;
      bed_mm: number[];
      overhang_needs_support: boolean;
      steepest_overhang_deg: number;
    };
    D4_workflow: { pass: boolean; units: string; recommended_format: string; note: string };
  };
  metrics: Record<string, unknown> & {
    bbox_mm?: number[];
    volume_mm3?: number;
    triangles?: number;
    est_mass_g_solid?: number;
    wall_thickness?: { available: boolean; min?: number; p05?: number; median?: number };
    kernel_metrics?: KernelMetrics;
  };
  issues: string[];
  warnings: string[];
  suggestions: string[];
}

// Resolve any harness-relative path against the deployed base path.
export function asset(path: string): string {
  return import.meta.env.BASE_URL + path.replace(/^\//, "");
}
