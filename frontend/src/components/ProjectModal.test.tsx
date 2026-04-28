import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProjectModal } from "./ProjectModal";
import { renderWithRouter } from "../test/render";

describe("ProjectModal", () => {
  it("submits project payload and closes on success", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    renderWithRouter(
      <ProjectModal open onClose={onClose} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText("项目名称"), "测试项目");
    await user.type(screen.getByLabelText("项目描述"), "测试描述");
    await user.click(screen.getByRole("button", { name: "创建项目" }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        name: "测试项目",
        description: "测试描述",
      });
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders error when submit fails", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockRejectedValue(new Error("创建失败"));

    renderWithRouter(
      <ProjectModal open onClose={vi.fn()} onSubmit={onSubmit} />,
    );

    await user.type(screen.getByLabelText("项目名称"), "测试项目");
    await user.click(screen.getByRole("button", { name: "创建项目" }));

    expect(await screen.findByText("创建失败")).toBeInTheDocument();
  });
});
