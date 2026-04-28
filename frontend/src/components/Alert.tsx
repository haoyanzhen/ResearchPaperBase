import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";

import { classNames } from "../utils/format";

type AlertProps = {
  tone?: "error" | "success" | "warning" | "info";
  message: string;
};

const ICONS = {
  error: AlertCircle,
  success: CheckCircle2,
  warning: TriangleAlert,
  info: Info,
};

export function Alert({ tone = "info", message }: AlertProps) {
  const Icon = ICONS[tone];
  return (
    <div className={classNames("alert", `alert--${tone}`)} role="alert">
      <Icon size={16} />
      <span>{message}</span>
    </div>
  );
}
