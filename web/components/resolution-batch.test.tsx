import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ResolutionCenter } from "@/components/resolution-center";
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/resolution" }));
afterEach(() => vi.unstubAllGlobals());
it("keeps selected cases across pages and reports per-case failures without optimistic changes", async () => {
  const fetch = vi.fn(async (input: string, options?: RequestInit) => {
    if (input.endsWith("batch-preview")) {
      const requests = JSON.parse(String(options?.body)).requests;
      return new Response(JSON.stringify({ items: requests.map((request: object) => ({ status: "PREVIEWED", case_key: (request as { case_key: string }).case_key, preview: { ...request, allowed: true, detail: { case_key: (request as { case_key: string }).case_key }, evidence_version: "a".repeat(64), qualification: { status: "QUALIFIED", reason: "REVIEW_ONLY" } } })) }));
    }
    if (input.endsWith("batch-apply")) {
      const requests = JSON.parse(String(options?.body)).requests;
      return new Response(JSON.stringify({ items: [{ case_key: requests[0].case_key, status: "SUCCEEDED", event: { ...requests[0], detail: {} } }, { case_key: requests[1].case_key, status: "BLOCKED", error: "Evidence changed; preview again" }], succeeded: 1, blocked: 1 }));
    }
    const page = Number(new URL(input).searchParams.get("page")), key = `team:page-${page}`;
    return new Response(JSON.stringify({ items: [{ case_key: key, name: `Team ${page}`, status: "UNRESOLVED" }], page, page_size: 20, total: 21, counts: { UNRESOLVED: 21 }, groups: [] }));
  });
  vi.stubGlobal("fetch", fetch);
  render(<ResolutionCenter />);
  fireEvent.click(await screen.findByRole("checkbox", { name: "Select team:page-1" }));
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  fireEvent.click(await screen.findByRole("checkbox", { name: "Select team:page-2" }));
  const batch = screen.getByRole("region", { name: "Batch review" });
  expect(within(batch).getByRole("heading", { level: 2 })).toHaveTextContent("2 selected cases");
  fireEvent.change(within(batch).getByLabelText("Batch reason"), { target: { value: "Evidence review for both cases" } });
  fireEvent.click(within(batch).getByRole("button", { name: "Gather evidence and preview batch" }));
  const apply = await within(batch).findByRole("button", { name: "Approve and apply 2 decisions" });
  expect(apply).toBeDisabled();
  fireEvent.change(within(batch).getByLabelText("Batch owner credential"), { target: { value: "owner" } });
  fireEvent.click(within(batch).getByRole("checkbox")); fireEvent.click(apply); fireEvent.click(apply);
  expect(await within(batch).findByRole("status")).toHaveTextContent("Evidence changed; preview again");
  expect(fetch.mock.calls.filter(([url]) => url.endsWith("batch-apply"))).toHaveLength(1);
  expect(screen.getByText("21 cases in this scope.", { exact: false })).toBeInTheDocument();
});
