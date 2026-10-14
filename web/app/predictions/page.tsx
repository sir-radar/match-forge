import { PredictionsPage } from "@/components/predictions-page";
import { displayDay } from "@/lib/display-date";

export const dynamic = "force-dynamic";
export default function Page() { return <PredictionsPage initialDate={displayDay()} />; }
