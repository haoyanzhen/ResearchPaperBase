import { Route } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoginPage } from "./LoginPage";
import { renderWithRouter } from "../test/render";

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  register: vi.fn(),
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    login: mocks.login,
    register: mocks.register,
  }),
}));

describe("LoginPage", () => {
  it("submits login form and redirects to target route", async () => {
    const user = userEvent.setup();
    mocks.login.mockResolvedValue(undefined);

    renderWithRouter(<LoginPage />, {
      route: "/login",
      path: "/login",
      extraRoutes: <Route path="/projects" element={<div>项目列表页</div>} />,
    });

    await user.type(screen.getByLabelText("用户名 / 邮箱"), "tester");
    await user.type(screen.getByLabelText("密码"), "secret123");
    await user.click(screen.getAllByRole("button", { name: "登录" })[1]);

    await waitFor(() => {
      expect(mocks.login).toHaveBeenCalledWith({ credential: "tester", password: "secret123" });
    });
    expect(await screen.findByText("项目列表页")).toBeInTheDocument();
  });

  it("switches to register mode and submits registration", async () => {
    const user = userEvent.setup();
    mocks.register.mockResolvedValue(undefined);

    renderWithRouter(<LoginPage />, {
      route: "/login",
      path: "/login",
      extraRoutes: <Route path="/projects" element={<div>项目列表页</div>} />,
    });

    await user.click(screen.getByRole("button", { name: "注册" }));
    await user.type(screen.getByLabelText("用户名"), "new-user");
    await user.type(screen.getByLabelText("邮箱"), "new@example.com");
    await user.type(screen.getByLabelText("密码"), "secret123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    await waitFor(() => {
      expect(mocks.register).toHaveBeenCalledWith({
        username: "new-user",
        email: "new@example.com",
        password: "secret123",
      });
    });
  });

  it("renders authentication error", async () => {
    const user = userEvent.setup();
    mocks.login.mockRejectedValue(new Error("认证失败"));

    renderWithRouter(<LoginPage />, { route: "/login", path: "/login" });

    await user.type(screen.getByLabelText("用户名 / 邮箱"), "tester");
    await user.type(screen.getByLabelText("密码"), "wrong");
    await user.click(screen.getAllByRole("button", { name: "登录" })[1]);

    expect(await screen.findByText("认证失败")).toBeInTheDocument();
  });
});
