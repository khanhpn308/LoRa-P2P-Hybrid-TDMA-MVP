package api

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// BuildServeMux wires REST endpoints for health checks, operational monitoring, device provisioning, and realtime WSS.
func BuildServeMux(
	statusStore storage.StatusStorage,
	offlineThreshold time.Duration,
	wsHandler *WebSocketHandler,
	authHandler *auth.Handler,
	channelHandler *ChannelHandler,
	alertHandler *AlertHandler,
	provisionHandler *ProvisionHandler,
	joinReqHandler *JoinRequestHandler,
	presenceTracker *presence.Tracker,
	nodeHandler *NodeHandler,
	jwtService *auth.JWTService,
	authenticators ...Authenticator,
) *http.ServeMux {
	rootMux := http.NewServeMux()
	apiMux := http.NewServeMux()

	healthHandler := NewHealthHandler()
	healthHandler.RegisterRoutes(rootMux)

	if wsHandler != nil {
		wsHandler.RegisterRoutes(rootMux)
		log.Println("Realtime WebSocket hub endpoint registered at GET /api/v1/ws/realtime.")
	}

	if authHandler != nil {
		authHandler.RegisterRoutes(rootMux)
		log.Println("Auth REST API registered.")
	}

	if statusStore != nil {
		monitoringHandler := NewMonitoringHandler(statusStore, offlineThreshold, presenceTracker, authenticators...)
		monitoringHandler.RegisterRoutes(apiMux)
	}

	if nodeHandler != nil {
		nodeHandler.RegisterRoutes(apiMux)
		log.Println("Node REST API registered at GET /api/v1/nodes/{node_id}/telemetry.")
	}

	if channelHandler != nil {
		channelHandler.RegisterRoutes(apiMux)
		log.Println("Channel registry REST API registered.")
	}

	if alertHandler != nil {
		alertHandler.RegisterRoutes(apiMux)
		log.Println("Alerts REST API registered.")
	}

	if provisionHandler != nil {
		provisionHandler.RegisterRoutes(apiMux)
		log.Println("Device provisioning REST API registered at POST /api/v1/devices/provision.")
	}

	if joinReqHandler != nil {
		joinReqHandler.RegisterRoutes(apiMux)
		log.Println("Device join request approval REST API registered at /api/v1/devices/requests.")
	}

	if jwtService == nil && len(authenticators) > 0 {
		if ja, ok := authenticators[0].(*JWTAuthenticator); ok && ja != nil {
			jwtService = ja.JWTService()
		}
	}

	var authMw func(http.Handler) http.Handler
	if jwtService != nil {
		authMw = auth.AuthMiddleware(jwtService)
	} else {
		authMw = func(next http.Handler) http.Handler {
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				_ = json.NewEncoder(w).Encode(map[string]string{
					"error":   "UNAUTHORIZED",
					"message": "missing or malformed bearer token",
				})
			})
		}
	}

	wrappedAuthMw := func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			authMw(next).ServeHTTP(w, r)
		})
	}
	rootMux.Handle("/api/v1/", wrappedAuthMw(apiMux))

	return rootMux
}
