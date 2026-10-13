import { FixtureExplorer } from "@/components/fixture-explorer";

import { displayDay } from "@/lib/display-date";

export const dynamic = "force-dynamic";

export default function Home() {
  return <FixtureExplorer initialDate={displayDay()} />;
}
