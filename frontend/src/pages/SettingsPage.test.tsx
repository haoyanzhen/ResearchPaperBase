import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./SettingsPage";
import { renderWithRouter } from "../test/render";

const mocks = vi.hoisted(() => ({
  currentUser: {
    user_id: "u1",
    username: "admin",
    email: "admin@example.com",
    is_admin: true,
    is_active: true,
    created_at: "2026-04-28T00:00:00Z",
  },
  me: vi.fn(),
  updateMe: vi.fn(),
  getLLMConfigs: vi.fn(),
  getDatabasesConfig: vi.fn(),
  getEmailConfig: vi.fn(),
  updateDatabaseConfig: vi.fn(),
  updateEmailConfig: vi.fn(),
  addLLMConfig: vi.fn(),
  deleteLLMConfig: vi.fn(),
  testLLMConfig: vi.fn(),
  listUsers: vi.fn(),
  getSystemLLMConfigs: vi.fn(),
  getSystemDatabasesConfig: vi.fn(),
  getSystemEmailConfig: vi.fn(),
  setUserStatus: vi.fn(),
  setUserRole: vi.fn(),
  resetPassword: vi.fn(),
  addSystemLLMConfig: vi.fn(),
  testSystemLLMConfig: vi.fn(),
  deleteSystemLLMConfig: vi.fn(),
  updateSystemDatabaseConfig: vi.fn(),
  updateSystemEmailConfig: vi.fn(),
  refreshUser: vi.fn(),
}));

vi.mock("../../api/auth", () => ({
  authApi: {
    me: mocks.me,
    updateMe: mocks.updateMe,
  },
}));

vi.mock("../../api/config", () => ({
  configApi: {
    getLLMConfigs: mocks.getLLMConfigs,
    getDatabasesConfig: mocks.getDatabasesConfig,
    getEmailConfig: mocks.getEmailConfig,
    updateDatabaseConfig: mocks.updateDatabaseConfig,
    updateEmailConfig: mocks.updateEmailConfig,
    addLLMConfig: mocks.addLLMConfig,
    deleteLLMConfig: mocks.deleteLLMConfig,
    testLLMConfig: mocks.testLLMConfig,
  },
}));

vi.mock("../../api/admin", () => ({
  adminApi: {
    listUsers: mocks.listUsers,
    getSystemLLMConfigs: mocks.getSystemLLMConfigs,
    getSystemDatabasesConfig: mocks.getSystemDatabasesConfig,
    getSystemEmailConfig: mocks.getSystemEmailConfig,
    setUserStatus: mocks.setUserStatus,
    setUserRole: mocks.setUserRole,
    resetPassword: mocks.resetPassword,
    addSystemLLMConfig: mocks.addSystemLLMConfig,
    testSystemLLMConfig: mocks.testSystemLLMConfig,
    deleteSystemLLMConfig: mocks.deleteSystemLLMConfig,
    updateSystemDatabaseConfig: mocks.updateSystemDatabaseConfig,
    updateSystemEmailConfig: mocks.updateSystemEmailConfig,
  },
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: mocks.currentUser,
    refreshUser: mocks.refreshUser,
  }),
}));

describe("SettingsPage", () => {
  beforeEach(() => {
    mocks.currentUser = {
      user_id: "u1",
      username: "admin",
      email: "admin@example.com",
      is_admin: true,
      is_active: true,
      created_at: "2026-04-28T00:00:00Z",
    };
    mocks.me.mockResolvedValue({ username: "admin", email: "admin@example.com" });
    mocks.updateMe.mockResolvedValue(undefined);
    mocks.getLLMConfigs.mockResolvedValue([]);
    mocks.getDatabasesConfig.mockResolvedValue({
      arxiv: { enabled: true, endpoint: "https://arxiv.org", rate_limit: 3 },
    });
    mocks.getEmailConfig.mockResolvedValue({
      recipients: ["reader@example.com"],
      sender_configured: true,
    });
    mocks.listUsers.mockResolvedValue([
      { user_id: "u2", username: "user2", email: "u2@example.com", is_active: true, is_admin: false },
    ]);
    mocks.getSystemLLMConfigs.mockResolvedValue([]);
    mocks.getSystemDatabasesConfig.mockResolvedValue({
      openalex: { enabled: true, endpoint: "https://api.openalex.org", rate_limit: 5 },
    });
    mocks.getSystemEmailConfig.mockResolvedValue({
      smtp_host: "smtp.example.com",
      smtp_port: 587,
      sender_email: "bot@example.com",
      sender_password_configured: true,
    });
    mocks.setUserStatus.mockResolvedValue(undefined);
    mocks.setUserRole.mockResolvedValue(undefined);
    mocks.resetPassword.mockResolvedValue({ email_sent: false, temp_password: "Temp1234" });
    mocks.addSystemLLMConfig.mockResolvedValue(undefined);
    mocks.updateSystemDatabaseConfig.mockResolvedValue(undefined);
    mocks.updateSystemEmailConfig.mockResolvedValue(undefined);
  });

  it("loads admin tabs and saves profile", async () => {
    const user = userEvent.setup();

    renderWithRouter(<SettingsPage />);

    expect(await screen.findByText("用户管理")).toBeInTheDocument();

    const username = screen.getByDisplayValue("admin");
    await user.clear(username);
    await user.type(username, "new-admin");
    await user.click(screen.getByRole("button", { name: /保存资料/i }));

    await waitFor(() => {
      expect(mocks.updateMe).toHaveBeenCalledWith({
        username: "new-admin",
        email: "admin@example.com",
        password: undefined,
      });
    });
    expect(mocks.refreshUser).toHaveBeenCalledTimes(1);
  });

  it("executes admin user actions", async () => {
    const user = userEvent.setup();

    renderWithRouter(<SettingsPage />);

    await screen.findByText("用户管理");
    await user.click(screen.getByRole("button", { name: "用户管理" }));
    await user.click(screen.getByRole("button", { name: "禁用" }));
    await user.click(screen.getByRole("button", { name: "重置密码" }));

    await waitFor(() => {
      expect(mocks.setUserStatus).toHaveBeenCalledWith("u2", false);
    });
    expect(mocks.resetPassword).toHaveBeenCalledWith("u2");
  });

  it("shows only recipient email settings for non-admin users", async () => {
    mocks.currentUser = {
      user_id: "u3",
      username: "member",
      email: "member@example.com",
      is_admin: false,
      is_active: true,
      created_at: "2026-04-28T00:00:00Z",
    };
    mocks.me.mockResolvedValue({ username: "member", email: "member@example.com" });

    renderWithRouter(<SettingsPage />);

    expect(await screen.findByRole("button", { name: "邮件设置" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "系统邮件" })).not.toBeInTheDocument();
    expect(mocks.getSystemEmailConfig).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "邮件设置" }));
    expect(await screen.findByText("收件人列表")).toBeInTheDocument();
    expect(screen.queryByText("SMTP Host")).not.toBeInTheDocument();
  });

  it("saves system sender settings from the admin email tab", async () => {
    const user = userEvent.setup();

    renderWithRouter(<SettingsPage />);

    await screen.findByText("系统邮件");
    await user.click(screen.getByRole("button", { name: "系统邮件" }));

    const smtpHost = screen.getByDisplayValue("smtp.example.com");
    await user.clear(smtpHost);
    await user.type(smtpHost, "smtp.mail.example");

    const senderEmail = screen.getByDisplayValue("bot@example.com");
    await user.clear(senderEmail);
    await user.type(senderEmail, "sender@example.com");

    const senderPassword = screen.getByPlaceholderText("已保存，留空则不修改");
    await user.type(senderPassword, "app-pass");
    await user.click(screen.getByRole("button", { name: "保存系统邮件" }));

    await waitFor(() => {
      expect(mocks.updateSystemEmailConfig).toHaveBeenCalledWith({
        smtp_host: "smtp.mail.example",
        smtp_port: 587,
        sender_email: "sender@example.com",
        sender_password: "app-pass",
      });
    });
  });
});
