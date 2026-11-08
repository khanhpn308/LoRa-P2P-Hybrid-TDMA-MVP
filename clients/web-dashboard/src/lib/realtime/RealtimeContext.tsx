"use client";

import React, { createContext, useContext } from "react";
import {
  RealtimeEnvelope,
  WsConnectionState,
  AlertTriggeredPayload,
} from "@/types/api";
import { useWebSocketHub, EventListener } from "./useWebSocketHub";
import { useAuth } from "@/lib/auth/AuthContext";

interface RealtimeContextType {
  connectionState: WsConnectionState;
  lastEvent: RealtimeEnvelope | null;
  recentAlerts: AlertTriggeredPayload[];
  reconnectCount: number;
  subscribe: (listener: EventListener) => () => void;
  reconnect: () => void;
  disconnect: () => void;
}

const RealtimeContext = createContext<RealtimeContextType | undefined>(undefined);

export const RealtimeProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { isAuthenticated } = useAuth();

  const wsHub = useWebSocketHub({
    autoConnect: isAuthenticated,
  });

  return (
    <RealtimeContext.Provider value={wsHub}>
      {children}
    </RealtimeContext.Provider>
  );
};

export function useRealtime(): RealtimeContextType {
  const context = useContext(RealtimeContext);
  if (!context) {
    throw new Error("useRealtime must be used within a RealtimeProvider");
  }
  return context;
}
