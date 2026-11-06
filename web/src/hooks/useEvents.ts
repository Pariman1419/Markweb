import { useEffect, useState } from 'react';

/** Refetch on an event or reconnection, including events missed during an outage. */
export function useEvents(): number {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let socket: WebSocket | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const connect = () => {
      const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(`${scheme}//${window.location.host}/api/ws/events`);
      socket.onopen = () => setVersion(value => value + 1);
      socket.onmessage = () => setVersion(value => value + 1);
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
