import { FixtureExplorer } from "@/components/fixture-explorer";

export const dynamic = "force-dynamic";

export default function Home() {
  return <FixtureExplorer initialDate={new Date().toISOString().slice(0, 10)} />;
}
