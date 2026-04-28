import { Save, Shield, SlidersHorizontal, UserRoundCog } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  adminApi,
  type AdminUserItem,
  type CreateSystemLLMRequest,
  type SystemDatabaseConfig,
  type SystemEmailConfig,
  type SystemLLMProvider,
} from "../../api/admin";
import { authApi } from "../../api/auth";
import {
  configApi,
  type DatabasesConfigResponse,
  type EmailConfig,
  type LLMConfig,
} from "../../api/config";
import { Alert } from "../components/Alert";
import { useAuth } from "../contexts/AuthContext";

type SettingsTab =
  | "profile"
  | "llm"
  | "databases"
  | "email"
  | "admin-users"
  | "admin-llm"
  | "admin-databases"
  | "admin-email";

export function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const [activeTab, setActiveTab] = useState<SettingsTab>("profile");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [profileForm, setProfileForm] = useState({ username: "", email: "", password: "" });
  const [llmConfigs, setLlmConfigs] = useState<LLMConfig[]>([]);
  const [dbConfigs, setDbConfigs] = useState<DatabasesConfigResponse | null>(null);
  const [emailConfig, setEmailConfig] = useState<EmailConfig | null>(null);
  const [emailRecipientsText, setEmailRecipientsText] = useState("");
  const [adminUsers, setAdminUsers] = useState<AdminUserItem[]>([]);
  const [systemLlms, setSystemLlms] = useState<SystemLLMProvider[]>([]);
  const [systemDbs, setSystemDbs] = useState<Record<string, SystemDatabaseConfig>>({});
  const [systemEmailConfig, setSystemEmailConfig] = useState<SystemEmailConfig | null>(null);
  const [systemEmailForm, setSystemEmailForm] = useState({
    smtpHost: "",
    smtpPort: "587",
    senderEmail: "",
    senderPassword: "",
  });

  const availableTabs = useMemo(() => {
    const base: Array<{ key: SettingsTab; label: string }> = [
      { key: "profile", label: "个人资料" },
      { key: "llm", label: "LLM 配置" },
      { key: "databases", label: "论文库配置" },
      { key: "email", label: "邮件设置" },
    ];
    if (user?.is_admin) {
      base.push(
        { key: "admin-users", label: "用户管理" },
        { key: "admin-llm", label: "系统 LLM" },
        { key: "admin-databases", label: "系统数据库" },
        { key: "admin-email", label: "系统邮件" },
      );
    }
    return base;
  }, [user?.is_admin]);

  const loadSettings = async () => {
    try {
      const [me, llms, dbs, email] = await Promise.all([
        authApi.me(),
        configApi.getLLMConfigs(),
        configApi.getDatabasesConfig(),
        configApi.getEmailConfig(),
      ]);
      setProfileForm({ username: me.username, email: me.email, password: "" });
      setLlmConfigs(llms);
      setDbConfigs(dbs);
      setEmailConfig(email);
      setEmailRecipientsText((email.recipients ?? []).join("\n"));

      if (user?.is_admin) {
        const [users, systemLlmConfigs, systemDbConfigs, systemEmail] = await Promise.all([
          adminApi.listUsers(),
          adminApi.getSystemLLMConfigs(),
          adminApi.getSystemDatabasesConfig(),
          adminApi.getSystemEmailConfig(),
        ]);
        setAdminUsers(users);
        setSystemLlms(systemLlmConfigs);
        setSystemDbs(systemDbConfigs);
        setSystemEmailConfig(systemEmail);
        setSystemEmailForm({
          smtpHost: systemEmail.smtp_host ?? "",
          smtpPort: systemEmail.smtp_port ? String(systemEmail.smtp_port) : "587",
          senderEmail: systemEmail.sender_email ?? "",
          senderPassword: "",
        });
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载设置失败");
    }
  };

  useEffect(() => {
    void loadSettings();
  }, [user?.is_admin]);

  const updateMessage = (text: string) => {
    setMessage(text);
    setError(null);
  };

  const saveProfile = async () => {
    try {
      await authApi.updateMe({
        username: profileForm.username,
        email: profileForm.email,
        password: profileForm.password || undefined,
      });
      await refreshUser();
      updateMessage("个人资料已更新");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存个人资料失败");
    }
  };

  const saveDatabaseField = async (
    dbName: keyof DatabasesConfigResponse,
    field: keyof DatabasesConfigResponse[keyof DatabasesConfigResponse],
    value: string | number | boolean,
  ) => {
    try {
      await configApi.updateDatabaseConfig(dbName, { [field]: value } as never);
      await loadSettings();
      updateMessage(`${dbName} 配置已更新`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新数据库配置失败");
    }
  };

  const saveSystemDatabaseField = async (
    dbName: string,
    field: keyof SystemDatabaseConfig,
    value: string | number | boolean,
  ) => {
    try {
      await adminApi.updateSystemDatabaseConfig(dbName, { [field]: value });
      await loadSettings();
      updateMessage(`系统 ${dbName} 配置已更新`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新系统数据库配置失败");
    }
  };

  const createUserLlm = async () => {
    try {
      await configApi.addLLMConfig({
        provider: "openai",
        url: "https://api.openai.com/v1",
        api_key: "sk-demo",
        default_model: "gpt-4.1-mini",
      });
      await loadSettings();
      updateMessage("已创建示例个人 LLM 配置");
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建 LLM 配置失败");
    }
  };

  const createSystemLlm = async () => {
    try {
      const payload: CreateSystemLLMRequest = {
        provider: "openai",
        url: "https://api.openai.com/v1",
        api_key: "sk-demo",
        default_model: "gpt-4.1-mini",
      };
      await adminApi.addSystemLLMConfig(payload);
      await loadSettings();
      updateMessage("已创建示例系统 LLM 配置");
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建系统 LLM 配置失败");
    }
  };

  const saveEmailRecipients = async () => {
    try {
      const recipients = emailRecipientsText
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean);
      await configApi.updateEmailConfig({ recipients });
      await loadSettings();
      updateMessage("收件人列表已更新");
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新收件人失败");
    }
  };

  const saveSystemEmailConfig = async () => {
    try {
      await adminApi.updateSystemEmailConfig({
        smtp_host: systemEmailForm.smtpHost.trim() || undefined,
        smtp_port: systemEmailForm.smtpPort.trim()
          ? Number(systemEmailForm.smtpPort)
          : undefined,
        sender_email: systemEmailForm.senderEmail.trim() || undefined,
        sender_password: systemEmailForm.senderPassword.trim() || undefined,
      });
      await loadSettings();
      setSystemEmailForm((prev) => ({ ...prev, senderPassword: "" }));
      updateMessage("系统发件邮箱配置已更新");
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新系统邮件配置失败");
    }
  };

  return (
    <div className="content">
      <header className="page-header">
        <div>
          <h1>设置</h1>
          <p>普通用户配置与管理员配置共用一个工作台，便于一起核对服务层落地情况。</p>
        </div>
        <div className="toolbar">
          <Link className="button button--ghost" to="/settings/health">健康检查</Link>
          <Link className="button button--ghost" to="/projects">返回项目</Link>
        </div>
      </header>

      {message && <Alert tone="success" message={message} />}
      {error && <Alert tone="error" message={error} />}

      <div className="settings-layout">
        <aside className="settings-nav">
          {availableTabs.map((tab) => (
            <button
              key={tab.key}
              className={`settings-nav__item ${activeTab === tab.key ? "settings-nav__item--active" : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </aside>

        <section className="section-card">
          {activeTab === "profile" && (
            <div className="stack">
              <div className="section-header">
                <div>
                  <h3>个人资料</h3>
                  <p>更新用户名、邮箱和密码。</p>
                </div>
              </div>
              <label className="field">
                <span>用户名</span>
                <input value={profileForm.username} onChange={(event) => setProfileForm((prev) => ({ ...prev, username: event.target.value }))} />
              </label>
              <label className="field">
                <span>邮箱</span>
                <input value={profileForm.email} onChange={(event) => setProfileForm((prev) => ({ ...prev, email: event.target.value }))} />
              </label>
              <label className="field">
                <span>新密码</span>
                <input type="password" value={profileForm.password} onChange={(event) => setProfileForm((prev) => ({ ...prev, password: event.target.value }))} />
              </label>
              <div className="form__actions">
                <button className="button" onClick={() => void saveProfile()}>
                  <Save size={16} />
                  保存资料
                </button>
              </div>
            </div>
          )}

          {activeTab === "llm" && (
            <ConfigListSection
              title="个人 LLM 配置"
              description="普通用户优先使用自己的配置；未配置时，后端会回落到管理员系统配置。"
              actionLabel="添加示例配置"
              onAction={() => void createUserLlm()}
              items={llmConfigs.map((item) => (
                <div key={item.provider} className="project-card">
                  <strong>{item.provider}</strong>
                  <div className="muted">{item.default_model}</div>
                  <div className="toolbar">
                    <button className="button button--ghost" onClick={() => void configApi.testLLMConfig(item.provider).then(() => updateMessage(`${item.provider} 测试完成`)).catch((err) => setError(err instanceof Error ? err.message : "测试失败"))}>测试</button>
                    <button className="button button--danger" onClick={() => void configApi.deleteLLMConfig(item.provider).then(loadSettings).catch((err) => setError(err instanceof Error ? err.message : "删除失败"))}>删除</button>
                  </div>
                </div>
              ))}
            />
          )}

          {activeTab === "databases" && dbConfigs && (
            <div className="stack">
              <div className="section-header">
                <div>
                  <h3>个人数据库配置</h3>
                  <p>用于 FR-003。未配置的数据库会回落到管理员系统配置。</p>
                </div>
              </div>
              {Object.entries(dbConfigs).map(([dbName, config]) => (
                <div key={dbName} className="project-card">
                  <div className="section-header">
                    <div>
                      <h3>{dbName}</h3>
                      <p>rate_limit: {config.rate_limit}</p>
                    </div>
                    <select value={config.enabled ? "on" : "off"} onChange={(event) => void saveDatabaseField(dbName as keyof DatabasesConfigResponse, "enabled", event.target.value === "on")}>
                      <option value="on">启用</option>
                      <option value="off">停用</option>
                    </select>
                  </div>
                  <label className="field">
                    <span>Endpoint</span>
                    <input
                      defaultValue={config.endpoint || ""}
                      onBlur={(event) => void saveDatabaseField(dbName as keyof DatabasesConfigResponse, "endpoint", event.target.value)}
                    />
                  </label>
                </div>
              ))}
            </div>
          )}

          {activeTab === "email" && emailConfig && (
            <div className="stack">
              <div className="section-header">
                <div>
                  <h3>邮件配置</h3>
                  <p>这里仅维护当前账号的收件人列表；发件邮箱与 SMTP 服务器由管理员统一维护。</p>
                </div>
              </div>
              <label className="field">
                <span>收件人列表</span>
                <textarea
                  rows={5}
                  value={emailRecipientsText}
                  onChange={(event) => setEmailRecipientsText(event.target.value)}
                  placeholder={"reader@example.com\nteam@example.com"}
                />
              </label>
              <div className="muted">
                {emailConfig.sender_configured
                  ? "系统发件邮箱已配置，可用于阶段 7 推送和密码通知。"
                  : "系统发件邮箱尚未配置，请联系管理员。"}
              </div>
              <div className="form__actions">
                <button className="button" onClick={() => void saveEmailRecipients()}>
                  <Save size={16} />
                  保存收件人
                </button>
              </div>
            </div>
          )}

          {activeTab === "admin-users" && (
            <div className="stack">
              <div className="section-header">
                <div>
                  <h3>用户管理</h3>
                  <p>管理员服务层已经接入：启停、提权、删号和重置密码都可直接调用。</p>
                </div>
                <span className="pill"><Shield size={14} /> Admin</span>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>用户</th>
                    <th>状态</th>
                    <th>角色</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {adminUsers.map((item) => (
                    <tr key={item.user_id}>
                      <td>
                        <div>{item.username}</div>
                        <div className="muted">{item.email}</div>
                      </td>
                      <td>{item.is_active ? "启用" : "禁用"}</td>
                      <td>{item.is_admin ? "管理员" : "普通用户"}</td>
                      <td>
                        <div className="table-actions">
                          <button className="button button--ghost" onClick={() => void adminApi.setUserStatus(item.user_id, !item.is_active).then(loadSettings).then(() => updateMessage("账号状态已更新")).catch((err) => setError(err instanceof Error ? err.message : "更新失败"))}>
                            {item.is_active ? "禁用" : "启用"}
                          </button>
                          <button className="button button--ghost" onClick={() => void adminApi.setUserRole(item.user_id, !item.is_admin).then(loadSettings).then(() => updateMessage("角色已更新")).catch((err) => setError(err instanceof Error ? err.message : "更新失败"))}>
                            {item.is_admin ? "撤销管理员" : "提升管理员"}
                          </button>
                          <button className="button button--ghost" onClick={() => void adminApi.resetPassword(item.user_id).then((resp) => updateMessage(resp.email_sent ? "临时密码邮件已发送" : `已生成临时密码：${resp.temp_password ?? "请查看返回值"}`)).catch((err) => setError(err instanceof Error ? err.message : "重置失败"))}>
                            重置密码
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === "admin-llm" && (
            <ConfigListSection
              title="系统 LLM 配置"
              description="管理员为全体普通用户提供系统级回落模型。"
              actionLabel="创建示例系统配置"
              onAction={() => void createSystemLlm()}
              items={systemLlms.map((item) => (
                <div key={item.provider} className="project-card">
                  <strong>{item.provider}</strong>
                  <div className="muted">{item.default_model}</div>
                  <div className="toolbar">
                    <button className="button button--ghost" onClick={() => void adminApi.testSystemLLMConfig(item.provider).then(() => updateMessage(`${item.provider} 测试完成`)).catch((err) => setError(err instanceof Error ? err.message : "测试失败"))}>测试</button>
                    <button className="button button--danger" onClick={() => void adminApi.deleteSystemLLMConfig(item.provider).then(loadSettings).then(() => updateMessage("系统 LLM 配置已删除")).catch((err) => setError(err instanceof Error ? err.message : "删除失败"))}>删除</button>
                  </div>
                </div>
              ))}
            />
          )}

          {activeTab === "admin-databases" && (
            <div className="stack">
              <div className="section-header">
                <div>
                  <h3>系统数据库配置</h3>
                  <p>管理员为普通用户提供全局回落的论文库 API 配置。</p>
                </div>
                <span className="pill"><SlidersHorizontal size={14} /> FR-029</span>
              </div>
              {Object.entries(systemDbs).map(([dbName, config]) => (
                <div key={dbName} className="project-card">
                  <div className="section-header">
                    <div>
                      <h3>{dbName}</h3>
                      <p>rate_limit: {config.rate_limit}</p>
                    </div>
                    <select value={config.enabled ? "on" : "off"} onChange={(event) => void saveSystemDatabaseField(dbName, "enabled", event.target.value === "on")}>
                      <option value="on">启用</option>
                      <option value="off">停用</option>
                    </select>
                  </div>
                  <label className="field">
                    <span>Endpoint</span>
                    <input
                      defaultValue={config.endpoint || ""}
                      onBlur={(event) => void saveSystemDatabaseField(dbName, "endpoint", event.target.value)}
                    />
                  </label>
                </div>
              ))}
            </div>
          )}

          {activeTab === "admin-email" && systemEmailConfig && (
            <div className="stack">
              <div className="section-header">
                <div>
                  <h3>系统邮件配置</h3>
                  <p>统一维护全体用户共享的发件 SMTP 参数与发件邮箱身份。</p>
                </div>
                <span className="pill"><Shield size={14} /> Admin</span>
              </div>
              <label className="field">
                <span>SMTP Host</span>
                <input
                  value={systemEmailForm.smtpHost}
                  onChange={(event) => setSystemEmailForm((prev) => ({ ...prev, smtpHost: event.target.value }))}
                />
              </label>
              <label className="field">
                <span>SMTP Port</span>
                <input
                  value={systemEmailForm.smtpPort}
                  onChange={(event) => setSystemEmailForm((prev) => ({ ...prev, smtpPort: event.target.value }))}
                />
              </label>
              <label className="field">
                <span>Sender Email</span>
                <input
                  value={systemEmailForm.senderEmail}
                  onChange={(event) => setSystemEmailForm((prev) => ({ ...prev, senderEmail: event.target.value }))}
                />
              </label>
              <label className="field">
                <span>Sender Password</span>
                <input
                  type="password"
                  value={systemEmailForm.senderPassword}
                  onChange={(event) => setSystemEmailForm((prev) => ({ ...prev, senderPassword: event.target.value }))}
                  placeholder={systemEmailConfig.sender_password_configured ? "已保存，留空则不修改" : "输入应用密码或 SMTP 密码"}
                />
              </label>
              <div className="muted">
                {systemEmailConfig.sender_password_configured
                  ? "系统发件密码已保存。"
                  : "尚未保存发件密码。"}
              </div>
              <div className="form__actions">
                <button className="button" onClick={() => void saveSystemEmailConfig()}>
                  <Save size={16} />
                  保存系统邮件
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ConfigListSection({
  title,
  description,
  actionLabel,
  onAction,
  items,
}: {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  items: ReactNode[];
}) {
  return (
    <div className="stack">
      <div className="section-header">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <button className="button" onClick={onAction}>
          <UserRoundCog size={16} />
          {actionLabel}
        </button>
      </div>
      {items.length ? items : <div className="empty-state">还没有配置项。</div>}
    </div>
  );
}
