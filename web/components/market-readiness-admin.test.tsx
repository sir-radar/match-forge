import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import fixture from "@/test-fixtures/market-capability-summary.json";
import { MarketReadinessAdmin } from "@/components/market-readiness-admin";

function inspect(season = fixture.season_id) {
  fireEvent.change(screen.getByLabelText("Competition ID"), { target: { value: fixture.competition_id } });
  fireEvent.change(screen.getByLabelText("Season ID"), { target: { value: season } });
  fireEvent.change(screen.getByLabelText("Knowledge cutoff"), { target: { value: fixture.knowledge_cutoff } });
  fireEvent.click(screen.getByRole("button", { name: "Inspect market readiness" }));
}
describe("MarketReadinessAdmin", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("requires an explicit scope, groups diagnostics, and keeps candidate data separate", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(fixture)));
    vi.stubGlobal("fetch", fetcher);
    render(<MarketReadinessAdmin />);
    expect(fetcher).not.toHaveBeenCalled();
    inspect();
    expect(await screen.findByText(/Model metadata is not target qualification/)).toBeInTheDocument();
    expect(screen.getAllByText("DATA_COLLECTION_REQUIRED", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.queryByText(/No registered candidate/)).not.toBeInTheDocument();
  });
  it("shows local errors and retries without a sync mutation", async () => {
    let fail = true;
    const fetcher = vi.fn(async () => fail ? new Response(JSON.stringify({ error: "Qualification unavailable" }), { status: 503 }) : new Response(JSON.stringify(fixture)));
    vi.stubGlobal("fetch", fetcher);
    render(<MarketReadinessAdmin />); inspect();
    expect(await screen.findByRole("alert")).toHaveTextContent("Qualification unavailable");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Model metadata is not target qualification/)).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("ignores an obsolete scope response even when transport cancellation is ignored", async () => {
    let finishFirst!: (value: Response) => void;
    const laterSeason = "00000000-0000-4000-8000-000000000103";
    let first = true;
    vi.stubGlobal("fetch", vi.fn(async () => {
      if (first) { first = false; return new Promise<Response>((resolve) => { finishFirst = resolve; }); }
      return new Response(JSON.stringify({ ...fixture, season_id: laterSeason, markets: [] }));
    }));
    render(<MarketReadinessAdmin />); inspect();
    await waitFor(() => expect(finishFirst).toBeDefined());
    inspect(laterSeason);
    expect(await screen.findByText("No target definitions returned")).toBeInTheDocument();
    await act(async () => finishFirst(new Response(JSON.stringify(fixture))));
    expect(screen.getByText("No target definitions returned")).toBeInTheDocument();
    expect(screen.queryByText("DATA_COLLECTION_REQUIRED", { exact: true })).not.toBeInTheDocument();
  });
});
