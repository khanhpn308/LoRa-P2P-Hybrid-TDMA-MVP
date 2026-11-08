package api

import (
	"net/http"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
)

// WebSocketHandler provides route registration for the realtime WebSocket fan-out endpoint.
type WebSocketHandler struct {
	handler *realtime.Handler
}

// NewWebSocketHandler creates a new WebSocketHandler adapter.
func NewWebSocketHandler(handler *realtime.Handler) *WebSocketHandler {
	return &WebSocketHandler{handler: handler}
}

// RegisterRoutes registers GET /api/v1/ws/realtime on http.ServeMux according to openapi.yaml and websocket.md.
func (h *WebSocketHandler) RegisterRoutes(mux *http.ServeMux) {
	if h.handler != nil {
		h.handler.RegisterRoutes(mux)
	}
}

// ServeHTTP delegates incoming HTTP upgrade requests to the underlying realtime handler.
func (h *WebSocketHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if h.handler != nil {
		h.handler.ServeHTTP(w, r)
	} else {
		http.Error(w, "Service Unavailable: realtime handler not configured", http.StatusServiceUnavailable)
	}
}
