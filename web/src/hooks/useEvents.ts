import { useEffect, useRef, useState } from 'react';

export type MarkEvent = {
  event: 'revision_saved' | 'job_progress' | 'scan_started' | 'scan_completed';
  timestamp: string;
  data: Record<string, unknown>;
};

function isMarkEvent(value: unknown): value is MarkEvent {
  if (!value || typeof value !== 'object') return false;
  const event = value as Record<string, unknown>;
  return typeof event.event === 'string' &&
    ['revision_saved', 'job_progress', 'scan_started', 'scan_completed'].includes(event.event) &&
    typeof event.timestamp === 'string' && !!event.data && typeof event.data === 'object';
}

/** Refetch on an event or reconnection, including events missed during an outage. */
export function useEvents(onEvent?: (event: MarkEvent) => void): number {
  const [version, setVersion] = useState(0);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  useEffect(() => {
    let socket: WebSocket | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const connect = () => {
      const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(`${scheme}//${window.location.host}/api/ws/events`);
      socket.onopen = () => setVersion(value => value + 1);
      socket.onmessage = message => {
        try {
          const event: unknown = JSON.parse(message.data);
          if (isMarkEvent(event)) {
            setVersion(value => value + 1);
            onEventRef.current?.(event);
          }
        } catch {
          // Ignore malformed messages and keep the connection open.
        }
      };
      socket.onclose = () => {
        if (!stopped) timer = setTimeout(connect, 5000);
      };
    };
    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, []);
  return version;
}
