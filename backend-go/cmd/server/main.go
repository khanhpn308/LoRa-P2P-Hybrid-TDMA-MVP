package main

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/lib/pq"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// corsMiddleware provides CORS headers and preflight handling for web client integration.
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-Idempotency-Key")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// BuildServeMux wires REST endpoints for health checks, operational monitoring, device provisioning, and realtime WSS.
func BuildServeMux(
	statusStore storage.StatusStorage,
	offlineThreshold time.Duration,
	wsHandler *api.WebSocketHandler,
	authHandler *auth.Handler,
	channelHandler *api.ChannelHandler,
	alertHandler *api.AlertHandler,
	provisionHandler *api.ProvisionHandler,
	joinReqHandler *api.JoinRequestHandler,
	presenceTracker *presence.Tracker,
	nodeHandler *api.NodeHandler,
	jwtService *auth.JWTService,
	authenticators ...api.Authenticator,
) *http.ServeMux {
	rootMux := http.NewServeMux()
	apiMux := http.NewServeMux()

	healthHandler := api.NewHealthHandler()
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
		monitoringHandler := api.NewMonitoringHandler(statusStore, offlineThreshold, presenceTracker, authenticators...)
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
		if ja, ok := authenticators[0].(*api.JWTAuthenticator); ok && ja != nil {
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

func main() {
	log.Println("Starting LoRa-P2P Hybrid TDMA Go Backend Server...")

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	dbURL := os.Getenv("DATABASE_URL")
	var statusStore storage.StatusStorage
	var channelRepo storage.ChannelRepository
	var userRepo auth.UserRepository
	var provisionRepo storage.ProvisionRepository
	var eventStorage *storage.PostgresEventStorage
	var joinReqStore storage.JoinRequestStorage
	var channelHandler *api.ChannelHandler
	var alertHandler *api.AlertHandler
	var nodeHandler *api.NodeHandler

	if dbURL != "" {
		db, err := sql.Open("postgres", dbURL)
		if err != nil {
			log.Fatalf("failed to open database connection: %v", err)
		}
		defer db.Close()

		statusStore = storage.NewPostgresStatusStorage(db)
		channelRepo = storage.NewPostgresChannelRepository(db)
		userRepo = auth.NewPostgresUserRepository(db)
		eventStorage = storage.NewPostgresEventStorage(db)
		joinReqStore = storage.NewPostgresJoinRequestStorage(db)
		nodeHandler = api.NewNodeHandler(eventStorage)
		provisionRepo = storage.NewPostgresProvisionStorage(db)
		log.Println("PostgreSQL persistent storage initialized.")
	} else {
		log.Println("DATABASE_URL not set; initializing thread-safe in-memory storage.")
		userRepo = auth.NewInMemoryUserRepository()
		provisionRepo = storage.NewMemoryProvisionStorage()
		nodeHandler = api.NewNodeHandler(nil)
	}

	// Seed / verify default test accounts (admin, operator01, viewer01)
	if err := auth.SeedDefaultUsers(context.Background(), userRepo); err != nil {
		log.Printf("Warning: failed to seed default users: %v", err)
	} else {
		log.Println("Default user accounts verified/seeded (admin, operator01, viewer01).")
	}

	// Initialize Realtime Hub & WebSocket Handler (Issue #251)
	hub := realtime.NewHub()
	hubCtx, cancelHub := context.WithCancel(context.Background())
	defer cancelHub()
	go hub.Run(hubCtx)

	// Initialize MQTT Status Subscriber for live gateway tracking
	presenceTracker := presence.NewTracker()

	var statusSub *mqtt.GatewayStatusSubscriber
	if statusStore != nil {
		mqttHost := os.Getenv("MQTT_HOST")
		mqttPort := os.Getenv("MQTT_PORT")
		if mqttPort == "" {
			mqttPort = "1883"
		}
		resolvedHost := mqttHost
		if resolvedHost == "" || resolvedHost == "localhost" {
			resolvedHost = "127.0.0.1"
		} else if resolvedHost == "mqtt-dev" {
			if _, err := net.LookupHost("mqtt-dev"); err != nil {
				if _, err2 := net.LookupHost("deploy-mqtt-dev-1"); err2 == nil {
					resolvedHost = "deploy-mqtt-dev-1"
				} else {
					resolvedHost = "192.168.88.113"
				}
			}
		}
		brokerURI := fmt.Sprintf("tcp://%s:%s", resolvedHost, mqttPort)
		statusSub = mqtt.NewGatewayStatusSubscriber(brokerURI, statusStore, hub, eventStorage, joinReqStore, presenceTracker)
		if err := statusSub.Start(context.Background()); err != nil {
			log.Printf("Warning: failed to start MQTT status subscriber: %v", err)
		} else {
			log.Printf("MQTT status subscriber initialized on %s", brokerURI)
		}
	}

	var joinReqHandler *api.JoinRequestHandler

	jwtSecret := os.Getenv("JWT_SECRET_KEY")
	if len(jwtSecret) < 32 {
		jwtSecret = "default-mvp-jwt-secret-key-minimum-32-bytes!!"
	}
	jwtService, err := auth.NewJWTService([]byte(jwtSecret))
	if err != nil {
		log.Fatalf("failed to initialize JWT service: %v", err)
	}
	ticketStore := auth.NewTicketStore()
	authService := auth.NewService(userRepo, jwtService, ticketStore)
	authHandler := auth.NewHandler(authService)

	realtimeHandler := realtime.NewHandler(hub, ticketStore, jwtService,
		realtime.WithAllowEmptyOrigin(true),
	)
	wsHandler := api.NewWebSocketHandler(realtimeHandler)

	jwtAuth := api.NewJWTAuthenticator(jwtService)

	if channelRepo != nil {
		channelHandler = api.NewChannelHandler(channelRepo, jwtAuth)
	}
	if eventStorage != nil {
		alertHandler = api.NewAlertHandler(eventStorage, jwtAuth)
	}
	if joinReqStore != nil {
		joinReqHandler = api.NewJoinRequestHandler(joinReqStore, statusSub, jwtAuth)
	}

	var provisionHandler *api.ProvisionHandler
	if provisionRepo != nil {
		var masterKey [32]byte
		provisionKeyEnv := os.Getenv("DEVICE_PROVISION_MASTER_KEY")
		if len(provisionKeyEnv) == 64 {
			decoded, err := hex.DecodeString(provisionKeyEnv)
			if err == nil && len(decoded) == 32 {
				copy(masterKey[:], decoded)
			}
		} else if len(provisionKeyEnv) >= 32 {
			copy(masterKey[:], []byte(provisionKeyEnv[:32]))
		}
		if masterKey == [32]byte{} {
			h := sha256.Sum256([]byte(jwtSecret + ":provision:master:key"))
			copy(masterKey[:], h[:])
		}
		keyWrapper := api.NewAESGCMKeyWrapper(masterKey)
		provisionHandler = api.NewProvisionHandler(provisionRepo, keyWrapper, jwtAuth)
	}

	mux := BuildServeMux(statusStore, 5*time.Minute, wsHandler, authHandler, channelHandler, alertHandler, provisionHandler, joinReqHandler, presenceTracker, nodeHandler, jwtService, jwtAuth)

	srv := &http.Server{
		Addr:         ":" + port,
		Handler:      corsMiddleware(mux),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Printf("HTTP server listening on %s", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	log.Println("shutting down server gracefully...")
	if statusSub != nil {
		statusSub.Stop()
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := hub.Shutdown(ctx); err != nil {
		log.Printf("error shutting down realtime hub: %v", err)
	}

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("forced server shutdown: %v", err)
	}
	log.Println("server gracefully stopped.")
}
