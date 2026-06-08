import { useLoader } from "@react-three/fiber";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { useMemo } from "react";
import * as THREE from "three";

// Load the STL (raw mm, Z-up — identical to our authoring frame), then ground it:
// centered in XY over the origin with its base resting on z=0, so it sits ON the
// print-bed grid exactly as it will print. We do NOT call geo.center() (that would
// sink half the model below the bed).
function StlModel({ url, color }: { url: string; color: string }) {
  const geo = useLoader(STLLoader, url);
  const prepared = useMemo(() => {
    const g = geo.clone();
    g.computeVertexNormals();
    g.computeBoundingBox();
    const bb = g.boundingBox!;
    const cx = (bb.min.x + bb.max.x) / 2;
    const cy = (bb.min.y + bb.max.y) / 2;
    g.translate(-cx, -cy, -bb.min.z); // XY-center, base on z=0
    return g;
  }, [geo]);
  return (
    <mesh geometry={prepared} castShadow receiveShadow>
      <meshStandardMaterial color={color} metalness={0.05} roughness={0.6} />
    </mesh>
  );
}

export function ModelViewer({ url, color = "#9aa7b2" }: { url: string; color?: string }) {
  return <StlModel url={url} color={color} />;
}

// preload helper used by the gallery on hover (optional)
export function preloadStl(url: string) {
  useLoader.preload(STLLoader, url);
}

void THREE;
