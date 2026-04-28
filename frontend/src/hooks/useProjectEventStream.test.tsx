import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useProjectEventStream } from "./useProjectEventStream";

const mocks = vi.hoisted(() => ({
  streamUrl: vi.fn((projectId: string) => `/api/v1/projects/${projectId}/construction/stream?token=abc`),
}));

vi.mock("../../api/construction", () => ({
  constructionApi: {
    streamUrl: mocks.streamUrl,
  },
}));

describe("useProjectEventStream", () => {
  it("subscribes to construction stream url and parses stage events", async () => {
    const { result } = renderHook(() => useProjectEventStream("p1"));

    expect(mocks.streamUrl).toHaveBeenCalledWith("p1");

    const MockEventSource = (globalThis as typeof globalThis & {
      __mockEventSource__: {
        instances: Array<{ url: string; emit: (type: string, data: string) => void }>;
      };
    }).__mockEventSource__;

    expect(MockEventSource.instances[0].url).toBe("/api/v1/projects/p1/construction/stream?token=abc");

    act(() => {
      MockEventSource.instances[0].emit("stage_error", JSON.stringify({ message: "失败" }));
    });

    await waitFor(() => {
      expect(result.current).toEqual({
        event: "stage_error",
        payload: { message: "失败" },
      });
    });
  });
});
