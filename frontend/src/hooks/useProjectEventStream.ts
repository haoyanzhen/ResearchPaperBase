import { constructionApi } from "../../api/construction";
import { useEffect, useState } from "react";

type ProjectEvent = {
  event: string;
  payload: Record<string, unknown>;
} | null;

export function useProjectEventStream(projectId: string | undefined) {
  const [latestEvent, setLatestEvent] = useState<ProjectEvent>(null);

  useEffect(() => {
    if (!projectId) return;
    const source = new EventSource(constructionApi.streamUrl(projectId));

    const listen = (eventName: string) => {
      source.addEventListener(eventName, ((event: MessageEvent) => {
        try {
          setLatestEvent({
            event: eventName,
            payload: JSON.parse(event.data) as Record<string, unknown>,
          });
        } catch {
          setLatestEvent({ event: eventName, payload: { raw: event.data } });
        }
      }) as EventListener);
    };

    ["stage_start", "stage_error", "stage_pause", "turn_complete"].forEach(listen);
    source.onerror = () => source.close();

    return () => source.close();
  }, [projectId]);

  return latestEvent;
}
