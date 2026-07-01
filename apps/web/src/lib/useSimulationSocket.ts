import { useEffect, useState } from 'react';
import { API_BASE } from './api';
import type { SimulationSnapshot } from './types';

export type SimulationSocketStatus = 'connecting' | 'connected' | 'reconnecting' | 'offline';

const INITIAL_RECONNECT_DELAY_MS = 500;
const MAX_RECONNECT_DELAY_MS = 5000;

export function useSimulationSocket(simulationId: string | null) {
  const [snapshot, setSnapshot] = useState<SimulationSnapshot | null>(null);
  const [status, setStatus] = useState<SimulationSocketStatus>('offline');

  useEffect(() => {
    if (!simulationId) {
      setStatus('offline');
      return;
    }

    let socket: WebSocket | null = null;
    let retryCount = 0;
    let retryTimer: number | undefined;
    let closedByEffect = false;
    const wsBase = API_BASE.replace(/^http/, 'ws');

    const connect = () => {
      setStatus(retryCount === 0 ? 'connecting' : 'reconnecting');
      socket = new WebSocket(`${wsBase}/api/ws/simulations/${simulationId}`);

      socket.onopen = () => {
        retryCount = 0;
        setStatus('connected');
      };

      socket.onmessage = (event) => {
        setSnapshot(JSON.parse(event.data) as SimulationSnapshot);
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = () => {
        if (closedByEffect) {
          setStatus('offline');
          return;
        }
        setStatus('reconnecting');
        const delay = Math.min(
          MAX_RECONNECT_DELAY_MS,
          INITIAL_RECONNECT_DELAY_MS * 2 ** retryCount
        );
        retryCount += 1;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      closedByEffect = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [simulationId]);

  return { snapshot, connected: status === 'connected', status };
}
