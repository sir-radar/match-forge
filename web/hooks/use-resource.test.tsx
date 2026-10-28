import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useResource } from "@/hooks/use-resource";

function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }

describe("keyed resources", () => {
  it("hides old-key data immediately and ignores reordered, cancelled responses", async () => {
    const first = deferred<string>(), second = deferred<string>(), third = deferred<string>();
    const requests = [first, second, third]; const signals: AbortSignal[] = [];
    const load = (signal: AbortSignal) => { signals.push(signal); return requests[signals.length - 1].promise; };
    const resource = renderHook(({ key }) => useResource(key, load), { initialProps: { key: "day-1" } });
    await act(async () => first.resolve("first day"));
    expect(resource.result.current.data).toBe("first day");
    resource.rerender({ key: "day-2" }); expect(resource.result.current.data).toBeNull();
    resource.rerender({ key: "day-3" }); expect(signals[1].aborted).toBe(true);
    await act(async () => third.resolve("third day"));
    await act(async () => second.resolve("late second day"));
    expect(resource.result.current.data).toBe("third day");
  });
  it("retains data during a same-key refresh and aborts on unmount", async () => {
    const second = deferred<string>(); let calls = 0; let signal!: AbortSignal;
    const load = (value: AbortSignal) => { signal = value; return ++calls === 1 ? Promise.resolve("known") : second.promise; };
    const resource = renderHook(() => useResource("same-day", load));
    await act(async () => { await Promise.resolve(); });
    act(() => resource.result.current.retry());
    await act(async () => { await Promise.resolve(); });
    expect(resource.result.current.data).toBe("known"); expect(resource.result.current.refreshing).toBe(true);
    resource.unmount(); expect(signal.aborted).toBe(true);
    await act(async () => second.resolve("after unmount"));
  });

  it("preserves HTTP status for retryable resource failures", async () => {
    const load = () => Promise.reject(Object.assign(new Error("temporarily unavailable"), { status: 503 }));
    const resource = renderHook(() => useResource("context", load));
    await act(async () => { await Promise.resolve(); });
    expect(resource.result.current.error).toBe("temporarily unavailable");
    expect(resource.result.current.errorStatus).toBe(503);
  });
});
