import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/app-shell";

const navigation = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => navigation.pathname }));

describe("AppShell back-to-top control", () => {
  beforeEach(() => {
    navigation.pathname = "/";
    Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
    vi.stubGlobal("scrollTo", vi.fn());
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("appears after 300px on the landing page and returns focus to main", () => {
    const { unmount } = render(<AppShell><p>Landing content</p></AppShell>);
    expect(screen.queryByRole("button", { name: "Back to top" })).not.toBeInTheDocument();

    Object.defineProperty(window, "scrollY", { configurable: true, value: 300 });
    act(() => window.dispatchEvent(new Event("scroll")));
    fireEvent.click(screen.getByRole("button", { name: "Back to top" }));

    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
    expect(document.activeElement).toBe(document.querySelector("main"));
    unmount();
  });

  it("uses instant scrolling for reduced motion and stays off other routes", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
    const landing = render(<AppShell><p>Landing content</p></AppShell>);
    Object.defineProperty(window, "scrollY", { configurable: true, value: 301 });
    act(() => window.dispatchEvent(new Event("scroll")));
    fireEvent.click(screen.getByRole("button", { name: "Back to top" }));
    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "auto" });
    landing.unmount();

    navigation.pathname = "/performance";
    render(<AppShell><p>Performance content</p></AppShell>);
    act(() => window.dispatchEvent(new Event("scroll")));
    expect(screen.queryByRole("button", { name: "Back to top" })).not.toBeInTheDocument();
  });

  it("removes its scroll listener on unmount", () => {
    const removeEventListener = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<AppShell><p>Landing content</p></AppShell>);
    unmount();
    expect(removeEventListener).toHaveBeenCalledWith("scroll", expect.any(Function));
  });
});
