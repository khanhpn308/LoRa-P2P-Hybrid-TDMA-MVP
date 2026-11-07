package api

import (
	"encoding/json"
	"net/http"
)

// HealthResponseDTO matches Health component schema in openapi.yaml.
type HealthResponseDTO struct {
	Status string `json:"status"`
}

// HealthHandler provides the /healthz liveness endpoint.
type HealthHandler struct{}

// NewHealthHandler creates a new HealthHandler.
func NewHealthHandler() *HealthHandler {
	return &HealthHandler{}
}

// RegisterRoutes registers the health endpoint on a ServeMux.
func (h *HealthHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /healthz", h.handleHealthz)
}

func (h *HealthHandler) handleHealthz(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(HealthResponseDTO{Status: "ok"})
}
