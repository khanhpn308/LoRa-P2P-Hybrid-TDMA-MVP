"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  RealtimeEnvelope,
  WsConnectionState,
  AlertTriggeredPayload,
} from "@/types/api";
import { getWsTicket } from "../api/auth.ts";
import { getApiBaseUrl, getStoredToken } from "../api/client.ts";

export type EventListener = (envelope: RealtimeEnvelope) => void;

interface UseWebSocketHubOptions {
  autoConnect?: boolean;
  onAlert?: (payload: AlertTriggeredPayload) => void;
  onEvent?: (envelope: RealtimeEnvelope) => void;
}

/**
 * Resolves the Backend WebSocket URL from environment or API base URL.
 */
export function getWsBaseUrl(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_WS_URL) {
    return process.env.NEXT_PUBLIC_WS_URL.replace(/\/+$/, "");
  }
  const apiBase = getApiBaseUrl();
  return apiBase.replace(/^http/, "ws");
}

export function useWebSocketHub(options: UseWebSocketHubOptions = {}) {
  const { autoConnect = true, onAlert, onEvent } = options;

  const [connectionState, setConnectionState] = useState<WsConnectionState>("DISCONNECTED");
  const [lastEvent, setLastEvent] = useState<RealtimeEnvelope | null>(null);
  const [recentAlerts, setRecentAlerts] = useState<AlertTriggeredPayload[]>([]);
  const [reconnectCount, setReconnectCount] = useState<number>(0);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptRef = useRef<number>(0);
  const listenersRef = useRef<Set<EventListener>>(new Set());
  const isMountedRef = useRef<boolean>(true);

  // Keep callback refs fresh
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const subscribe = useCallback((listener: EventListener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const closeSocket = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (socketRef.current) {
      socketRef.current.onopen = null;
      socketRef.current.onclose = null;
      socketRef.current.onerror = null;
      socketRef.current.onmessage = null;
      socketRef.current.close();
      socketRef.current = null;
    }
  }, []);

  const connect = useCallback(async () => {
    closeSocket();

    const token = getStoredToken();
    if (!token) {
      if (isMountedRef.current) {
        setConnectionState("DISCONNECTED");
      }
      return;
    }

    if (isMountedRef.current) {
      setConnectionState(reconnectAttemptRef.current > 0 ? "RECONNECTING" : "CONNECTING");
    }

    try {
      // Step 1: Request single-use ticket (ADR-0005)
      const ticketResp = await getWsTicket();
      if (!ticketResp || !ticketResp.ticket) {
        throw new Error("Failed to obtain single-use websocket ticket");
      }

      if (!isMountedRef.current) return;

      // Step 2: Open WebSocket using query parameter ticket
      // ZERO SECRET LEAKAGE: strictly avoid console.log of full URL with ticket
      const wsBase = getWsBaseUrl();
      const wsUrl = `${wsBase}/api/v1/ws/realtime?ticket=${encodeURIComponent(ticketResp.ticket)}`;

      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        setConnectionState("CONNECTED");
        reconnectAttemptRef.current = 0;
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        try {
          const envelope: RealtimeEnvelope = JSON.parse(event.data);
          setLastEvent(envelope);

          // Notify global and registered listeners
          if (onEventRef.current) {
            onEventRef.current(envelope);
          }
          listenersRef.current.forEach((listener) => {
            try {
              listener(envelope);
            } catch {
              // Ignore subscriber error
            }
          });

          // Dedicated ALERT_TRIGGERED handling
          if (envelope.type === "ALERT_TRIGGERED") {
            const alertPayload = envelope.payload as AlertTriggeredPayload;
            setRecentAlerts((prev) => [alertPayload, ...prev.slice(0, 49)]);
            if (onAlertRef.current) {
              onAlertRef.current(alertPayload);
            }
          }
        } catch {
          // Received non-JSON or ping message, safely ignore
        }
      };

      ws.onerror = () => {
        // WebSocket error event contains minimal info in browser; let onclose trigger reconnect
      };

      ws.onclose = () => {
        if (!isMountedRef.current) return;
        setConnectionState("RECONNECTING");

        // Step 3: Auto-reconnect with exponential backoff (1s, 2s, 4s, ..., max 30s) + jitter
        const attempt = reconnectAttemptRef.current;
        reconnectAttemptRef.current += 1;
        setReconnectCount(reconnectAttemptRef.current);

        const baseDelay = Math.min(1000 * Math.pow(2, attempt), 30000);
        // Jitter: +/- 20%
        const jitter = baseDelay * (0.8 + Math.random() * 0.4);

        reconnectTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current) {
            connect();
          }
        }, jitter);
      };
    } catch {
      if (!isMountedRef.current) return;
      setConnectionState("RECONNECTING");

      const attempt = reconnectAttemptRef.current;
      reconnectAttemptRef.current += 1;
      setReconnectCount(reconnectAttemptRef.current);

      const baseDelay = Math.min(1000 * Math.pow(2, attempt), 30000);
      reconnectTimeoutRef.current = setTimeout(() => {
        if (isMountedRef.current) {
          connect();
        }
      }, baseDelay);
    }
  }, [closeSocket]);

  useEffect(() => {
    isMountedRef.current = true;

    if (autoConnect) {
      connect();
    }

    return () => {
      isMountedRef.current = false;
      closeSocket();
    };
  }, [autoConnect, connect, closeSocket]);

  return {
    connectionState,
    lastEvent,
    recentAlerts,
    reconnectCount,
    subscribe,
    reconnect: connect,
    disconnect: closeSocket,
  };
}
