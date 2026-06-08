import { Canvas } from "@react-three/fiber";
import { OrbitControls, Grid, Bounds } from "@react-three/drei";
import { Suspense, type ReactNode } from "react";

// A Z-UP CAD scene that matches our authoring frame and slicer convention:
// the build plate is the XY plane at z=0, Z is up. Models are authored on the
// bed (min-z = 0) so they sit ON the grid. (drei <Stage> is intentionally NOT
// used — it re-centers/re-grounds content and fights our explicit placement.)
export function Scene({ children, bed = 256 }: { children: ReactNode; bed?: number }) {
  const h = bed * 0.55;
  return (
    <Canvas
      shadows
      camera={{ position: [bed * 0.55, -bed * 0.7, h], up: [0, 0, 1], fov: 42, near: 1, far: bed * 12 }}
    >
      <color attach="background" args={["#16171b"]} />
      <hemisphereLight intensity={0.55} groundColor="#0b0c10" />
      <directionalLight position={[bed, -bed * 0.6, bed * 1.2]} intensity={1.6} castShadow />
      <directionalLight position={[-bed * 0.8, bed, bed * 0.5]} intensity={0.5} />

      <Suspense fallback={null}>
        <Bounds fit clip observe margin={1.3}>
          {children}
        </Bounds>
      </Suspense>

      {/* print bed: drei Grid lies in the XZ plane by default; rotate it into
          the XY plane so it sits at z=0 under a Z-up model. */}
      <Grid
        args={[bed, bed]}
        rotation={[Math.PI / 2, 0, 0]}
        cellSize={10}
        cellThickness={0.6}
        cellColor="#34373f"
        sectionSize={50}
        sectionThickness={1}
        sectionColor="#2080ff"
        fadeDistance={bed * 4}
        fadeStrength={1}
        infiniteGrid={false}
      />
      <axesHelper args={[bed * 0.22]} />
      <OrbitControls makeDefault enableDamping target={[0, 0, h * 0.25]} />
    </Canvas>
  );
}
