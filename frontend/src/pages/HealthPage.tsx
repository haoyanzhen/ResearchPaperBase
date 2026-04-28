import { Database, HeartPulse, ServerCrash } from "lucide-react";
import { useEffect, useState } from "react";

import { getDbHealth, getDeepHealth, getHealth } from "../../api/inspect";
import { Alert } from "../components/Alert";

export function HealthPage() {
  const [shallow, setShallow] = useState<{ status: string; timestamp: string } | null>(null);
  const [db, setDb] = useState<{ status: string } | null>(null);
  const [deep, setDeep] = useState<Awaited<ReturnType<typeof getDeepHealth>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [health, dbHealth, deepHealth] = await Promise.all([
          getHealth(),
          getDbHealth().catch(() => null),
          getDeepHealth().catch(() => null),
        ]);
        setShallow(health);
        setDb(dbHealth);
        setDeep(deepHealth);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "健康检查加载失败");
      }
    };
    void load();
  }, []);

  return (
    <div className="content">
      <header className="page-header">
        <div>
          <h1>系统健康检查</h1>
          <p>这页主要用来确认 web app 打开后，基础探针、DB 探针和深度依赖探针能否正常访问。</p>
        </div>
      </header>

      {error && <Alert tone="error" message={error} />}

      <div className="health-grid">
        <section className="section-card">
          <div className="section-header">
            <div>
              <h3>基础探针</h3>
              <p>根健康状态与时间戳。</p>
            </div>
            <span className="status-indicator" data-status={shallow?.status ?? "unknown"}>
              <HeartPulse size={16} />
              {shallow?.status ?? "loading"}
            </span>
          </div>
          <div className="stack">
            <div>时间：{shallow?.timestamp ?? "—"}</div>
          </div>
        </section>

        <section className="section-card">
          <div className="section-header">
            <div>
              <h3>数据库探针</h3>
              <p>校验 DB 连接层返回是否健康。</p>
            </div>
            <span className={`status-indicator health-db--${db?.status ?? "unknown"}`} data-status={db?.status ?? "unknown"}>
              <Database size={16} />
              {db?.status ?? "unknown"}
            </span>
          </div>
          {!db && <div className="empty-state">数据库探针当前不可用或返回失败。</div>}
        </section>
      </div>

      <section className="section-card">
        <div className="section-header">
          <div>
            <h3>深度探针</h3>
            <p>聚合 LLM、学术数据库和 SMTP 的依赖状态。</p>
          </div>
          <span
            className={`status-indicator health-status--${deep?.status ?? "unknown"}`}
            data-status={deep?.status ?? "unknown"}
          >
            <ServerCrash size={16} />
            {deep?.status ?? "unknown"}
          </span>
        </div>
        {deep ? (
          <div className="inspector-deps__grid">
            {Object.entries(deep.checks).map(([key, check]) => (
              <div key={key} className={`inspector-dep inspector-dep--${check.status}`}>
                <span>{key}</span>
                <strong>{check.status}</strong>
                <span className="muted">{check.message || check.suggestion || "正常"}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">还没有拿到深度探针结果。</div>
        )}
      </section>
    </div>
  );
}
