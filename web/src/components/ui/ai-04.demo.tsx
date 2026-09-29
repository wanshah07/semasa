import Ai04 from "@/components/ui/ai-04";

export default function Ai04Demo() {
  return (
    <div className="flex w-full items-center justify-center p-8">
      <Ai04 onSubmit={(prompt) => console.log(prompt)} />
    </div>
  );
}
