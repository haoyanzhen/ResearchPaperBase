import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { Alert } from "./Alert";
import { Modal } from "./Modal";

type ProjectModalProps = {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: { name: string; description?: string }) => Promise<void>;
};

export function ProjectModal({ open, onClose, onSubmit }: ProjectModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setName("");
      setDescription("");
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit({ name, description: description || undefined });
      setName("");
      setDescription("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="新建研究项目" open={open} onClose={onClose}>
      <form className="form" onSubmit={handleSubmit}>
        {error && <Alert tone="error" message={error} />}
        <label className="field">
          <span>项目名称</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="例如：医学图像分割综述"
            required
          />
        </label>
        <label className="field">
          <span>项目描述</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={4}
            placeholder="补充研究背景、目标或阶段说明"
          />
        </label>
        <div className="form__actions">
          <button type="button" className="button button--ghost" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="button" disabled={submitting}>
            {submitting ? "创建中..." : "创建项目"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
