package main

import (
	"context"
	"database/sql"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// NoopMQTTPublisher provides an in-memory/stub MQTT publisher when a broker is not connected.
type NoopMQTTPublisher struct{}

func (p *NoopMQTTPublisher) Publish(ctx context.Context, topic string, qos byte, retain bool, expiryInterval uint32, payload []byte) error {
	log.Printf("[MQTT NOOP] Publish to %s (qos=%d, retain=%v, expiry=%ds, len=%dB)", topic, qos, retain, expiryInterval, len(payload))
	return nil
}

// BuildServeMux wires REST endpoints for health checks, operational monitoring, TDMA schedules, and realtime WSS.
func BuildServeMux(
	statusStore storage.StatusStorage,
	offlineThreshold time.Duration,
	schedHandler *api.ScheduleHandler,
	wsHandler *api.WebSocketHandler,
) *http.ServeMux {
	mux := http.NewServeMux()

	healthHandler := api.NewHealthHandler()
	healthHandler.RegisterRoutes(mux)

	if statusStore != nil {
		monitoringHandler := api.NewMonitoringHandler(statusStore, offlineThreshold)
		monitoringHandler.RegisterRoutes(mux)
	}

	if schedHandler != nil {
		schedHandler.RegisterRoutes(mux)
		log.Println("Schedule lifecycle REST API registered.")
	}

	if wsHandler != nil {
		wsHandler.RegisterRoutes(mux)
		log.Println("Realtime WebSocket hub endpoint registered at GET /api/v1/ws/realtime.")
	}

	return mux
}

func main() {
	log.Println("Starting LoRa-P2P Hybrid TDMA Go Backend Server...")

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	dbURL := os.Getenv("DATABASE_URL")
	var statusStore storage.StatusStorage
	var scheduleRepo scheduler.ScheduleRepository
	var channelRepo storage.ChannelRepository

	if dbURL != "" {
		db, err := sql.Open("postgres", dbURL)
		if err != nil {
			log.Fatalf("failed to open database connection: %v", err)
		}
		defer db.Close()

		statusStore = storage.NewPostgresStatusStorage(db)
		scheduleRepo = storage.NewPostgresScheduleStorage(db)
		channelRepo = storage.NewPostgresChannelRepository(db)
		log.Println("PostgreSQL persistent storage initialized.")
	} else {
		log.Println("DATABASE_URL not set; initializing thread-safe in-memory storage.")
		scheduleRepo = scheduler.NewMemoryScheduleRepository()
	}

	// Initialize TDMA planner
	validator := scheduler.NewFeasibilityValidator(nil)
	planner := scheduler.NewPlanner(validator)

	// Initialize MQTT Dispatcher
	mqttPub := &NoopMQTTPublisher{}
	dispatcher, err := mqtt.NewScheduleDispatcher(mqttPub)
	if err != nil {
		log.Fatalf("Failed to initialize schedule dispatcher: %v", err)
	}

	var schedHandler *api.ScheduleHandler
	if channelRepo != nil {
		schedHandler = api.NewScheduleHandlerWithDeps(scheduleRepo, channelRepo, planner, dispatcher, nil)
	}

	// Initialize Realtime Hub & WebSocket Handler (Issue #251)
	hub := realtime.NewHub()
	hubCtx, cancelHub := context.WithCancel(context.Background())
	defer cancelHub()
	go hub.Run(hubCtx)

	jwtSecret := os.Getenv("JWT_SECRET_KEY")
	if jwtSecret == "" {
		jwtSecret = "default-mvp-jwt-secret-key-minimum-32-bytes!!"
	}
	jwtService, err := auth.NewJWTService([]byte(jwtSecret))
	if err != nil {
		log.Fatalf("failed to initialize JWT service: %v", err)
	}
	ticketStore := auth.NewTicketStore()

	realtimeHandler := realtime.NewHandler(hub, ticketStore, jwtService,
		realtime.WithAllowEmptyOrigin(true),
	)
	wsHandler := api.NewWebSocketHandler(realtimeHandler)

	mux := BuildServeMux(statusStore, 5*time.Minute, schedHandler, wsHandler)

	srv := &http.Server{
		Addr:         ":" + port,
		Handler:      mux,
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
