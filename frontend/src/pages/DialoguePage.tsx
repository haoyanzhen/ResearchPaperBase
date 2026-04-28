import { Bot, MessageSquarePlus, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { dialoguesApi, type DialogueDetail, type DialogueTurnItem } from "../../api/dialogues";
import { projectsApi, type ProjectDetail, type ProjectSummary } from "../../api/projects";
import { Alert } from "../components/Alert";
import { AppShell } from "../components/AppShell";
import { readSseStream } from "../utils/format";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export function DialoguePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [dialogues, setDialogues] = useState<DialogueDetail[]>([]);
  const [currentDialogueId, setCurrentDialogueId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    if (!projectId) return;
    try {
      const [projectList, detail, dialogueList] = await Promise.all([
        projectsApi.list(),
        projectsApi.get(projectId),
        dialoguesApi.list(projectId),
      ]);
      setProjects(projectList.items);
      setProject(detail);
      let activeId = currentDialogueId;
      const detailList: DialogueDetail[] = [];
      if (!dialogueList.length) {
        const created = await dialoguesApi.create(projectId, { title: "新研究对话" });
        detailList.push(created);
        activeId = created.dialogue_id;
      } else {
        for (const item of dialogueList) {
          detailList.push(item as DialogueDetail);
        }
        activeId = activeId || detailList[0].dialogue_id;
      }
      setDialogues(detailList);
      setCurrentDialogueId(activeId);
      await loadTurns(activeId);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载对话失败");
    }
  };

  const loadTurns = async (dialogueId: string) => {
    if (!projectId || !dialogueId) return;
    const turns = await dialoguesApi.getTurns(projectId, dialogueId);
    setMessages(flattenTurns(turns));
  };

  useEffect(() => {
    void loadData();
  }, [projectId]);

  const activeDialogue = useMemo(
    () => dialogues.find((item) => item.dialogue_id === currentDialogueId) ?? null,
    [currentDialogueId, dialogues],
  );

  const handleSend = async () => {
    if (!projectId || !currentDialogueId || !input.trim()) return;
    const userMessage = { id: crypto.randomUUID(), role: "user" as const, content: input.trim() };
    const assistantId = crypto.randomUUID();
    const assistantMessage = { id: assistantId, role: "assistant" as const, content: "" };
    const minimumMessageCount = messages.length + 2;
    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setSending(true);
    setError(null);

    try {
      const response = await dialoguesApi.sendMessage(projectId, currentDialogueId, {
        user_content: userMessage.content,
        sub_mode: "technical",
      });
      await readSseStream(response, {
        onText: (chunk) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId ? { ...message, content: message.content + chunk } : message,
            ),
          );
        },
      });
      const turns = await dialoguesApi.getTurns(projectId, currentDialogueId);
      const nextMessages = flattenTurns(turns);
      if (nextMessages.length >= minimumMessageCount) {
        setMessages(nextMessages);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "发送失败";
      setError(message);
      setMessages((prev) =>
        prev.map((item) => (item.id === assistantId ? { ...item, content: `请求失败：${message}` } : item)),
      );
    } finally {
      setSending(false);
    }
  };

  const handleModeChange = async (mode: "construction" | "deep_research" | "review") => {
    if (!projectId) return;
    if (mode === "deep_research") return;
    try {
      await projectsApi.switchMode(projectId, { target_mode: mode });
      navigate(mode === "construction" ? `/projects/${projectId}` : `/projects/${projectId}/review`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换模式失败");
    }
  };

  const createDialogue = async () => {
    if (!projectId) return;
    const dialogue = await dialoguesApi.create(projectId, { title: "新研究对话" });
    setDialogues((prev) => [dialogue, ...prev]);
    setCurrentDialogueId(dialogue.dialogue_id);
    setMessages([]);
  };

  return (
    <AppShell
      project={project}
      projects={projects}
      mode="deep_research"
      selectedNav="dialogues"
      getProjectHref={(nextProjectId) => `/projects/${nextProjectId}/dialogue`}
      onModeChange={(mode) => void handleModeChange(mode)}
      sidebarItems={[
        { key: "dialogues", label: "对话列表", icon: <Bot size={16} /> },
        { key: "graph", label: "知识图谱", icon: <MessageSquarePlus size={16} /> },
      ]}
    >
      <header className="page-header">
        <div>
          <h1>{project?.name ?? "深度研究"}</h1>
          <p>对话会话、图谱引用和总结能力已经接上普通用户服务层。</p>
        </div>
        <button className="button" onClick={() => void createDialogue()}>
          <MessageSquarePlus size={16} />
          新建对话
        </button>
      </header>

      {error && <Alert tone="error" message={error} />}

      <div className="chat-layout">
        <aside className="chat-layout__sidebar">
          <div className="section-header">
            <div>
              <h3>对话列表</h3>
              <p>选择一个会话继续追问。</p>
            </div>
          </div>
          <div className="dialogue-list">
            {dialogues.map((dialogue) => (
              <button
                key={dialogue.dialogue_id}
                className={`dialogue-list__item ${dialogue.dialogue_id === currentDialogueId ? "dialogue-list__item--active" : ""}`}
                onClick={() => {
                  setCurrentDialogueId(dialogue.dialogue_id);
                  void loadTurns(dialogue.dialogue_id);
                }}
              >
                <div>{dialogue.title || "未命名对话"}</div>
                <div className="muted">{dialogue.summary ? "已生成摘要" : "进行中"}</div>
              </button>
            ))}
          </div>
        </aside>

        <section className="chat-layout__messages">
          <div className="section-header">
            <div>
              <h3>{activeDialogue?.title || "研究对话"}</h3>
              <p>以 technical 子模式发送问题，前端会实时拼接 SSE 文本流。</p>
            </div>
          </div>

          <div className="messages">
            {messages.map((message) => (
              <div
                key={message.id}
                data-testid={message.role === "user" ? "user-message" : undefined}
                className={`message message--${message.role}`}
              >
                {message.content || (message.role === "assistant" ? "生成中..." : "")}
              </div>
            ))}
            {!messages.length && <div className="empty-state">先抛一个问题进来，我们从这里开始展开。</div>}
          </div>

          <div className="form">
            <textarea
              className="chat-input"
              data-testid="chat-input"
              placeholder="请描述你想继续深挖的问题..."
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
            />
            <div className="form__actions">
              <button className="button" onClick={() => void handleSend()} disabled={sending}>
                <Send size={16} />
                {sending ? "发送中..." : "发送"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function flattenTurns(turns: DialogueTurnItem[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  for (const turn of turns) {
    result.push({ id: `${turn.turn_id}-user`, role: "user", content: turn.user_content });
    result.push({ id: `${turn.turn_id}-assistant`, role: "assistant", content: turn.assistant_content });
  }
  return result;
}
