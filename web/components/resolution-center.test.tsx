import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResolutionCenter } from "@/components/resolution-center";
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/resolution" }));
const key = "team:00000000-0000-4000-8000-000000000001";
function page(name = "Retained team") { return { items: [{ case_key: key, name, provider: "api_football", status: "UNRESOLVED", reason: "RETAINED_SOURCE_EVIDENCE_REQUIRED" }], page: 1, page_size: 20, total: 1, counts: { UNRESOLVED: 1 }, groups: [] }; }
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }); }
afterEach(() => vi.unstubAllGlobals());
describe("Resolution Center", () => {
  it("inspects source evidence and exposes no decision controls", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url.includes("/detail?") ? json({ case_key: key, evidence_version: "b".repeat(64), status: "UNRESOLVED", source_snapshot_id: "retained-snapshot" }) : json(page())));
    render(<ResolutionCenter />);
    expect(await screen.findByText("Retained team")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect case 1" }));
    expect(await screen.findByText("retained-snapshot")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Owner credential")).not.toBeInTheDocument();
  });
  it("cancels old filters and ignores responses arriving out of order", async () => {
    let resolveOld!: (response: Response) => void;
    const old = new Promise<Response>((resolve) => { resolveOld = resolve; });
    vi.stubGlobal("fetch", vi.fn((url: string) => url.includes("q=new") ? Promise.resolve(json(page("New selection"))) : old));
    render(<ResolutionCenter />);
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "new" } });
    expect(await screen.findByText("New selection")).toBeInTheDocument();
    await act(async () => resolveOld(json(page("Obsolete selection"))));
    expect(screen.queryByText("Obsolete selection")).not.toBeInTheDocument();
    expect(screen.getByText("New selection")).toBeInTheDocument();
  });
  it("retains valid data during refresh failure, rejects malformed responses and allows retry", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(page())).mockResolvedValueOnce(json({ error: "Storage busy" }, 503)).mockResolvedValueOnce(json({ items: [] })).mockResolvedValueOnce(json({ ...page(), items: [], total: 0, counts: {} }));
    vi.stubGlobal("fetch", fetch);
    render(<ResolutionCenter />);
    expect(await screen.findByText("Retained team")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Recheck current view" }));
    expect(await screen.findByText("Storage busy")).toBeInTheDocument();
    expect(screen.getByText("Retained team")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByText("Storage busy")).not.toBeInTheDocument());
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No cases in this scope")).toBeInTheDocument();
  });
});
