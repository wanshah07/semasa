/* The component's own demo, as pasted. Not mounted in Semasa. */
import {
  StripedProgress,
  GradientProgress,
  GlowProgress,
  SegmentedProgress,
  ShimmerProgress,
} from "@/components/ui/progress-styled";

export default function ProgressStyledDemo() {
  return (
    <div className="flex w-full flex-col items-center justify-center gap-6 p-10">
      <StripedProgress value={60} />
      <GradientProgress value={60} />
      <GlowProgress value={60} />
      <SegmentedProgress value={60} />
      <ShimmerProgress />
    </div>
  );
}
