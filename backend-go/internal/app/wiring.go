package app

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"net/http"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/config"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// New initializes the Composition Root and wires dependencies per application configuration.
func New(cfg *config.Config) (*App, error) {
	if cfg == nil {
		cfg = config.Load()
	}

	var db *sql.DB
	var statusStore storage.StatusStorage
	var channelRepo storage.ChannelRepository
	var userRepo auth.UserRepository
	var provisionRepo storage.ProvisionRepository
	var eventStorage *storage.PostgresEventStorage
	var joinReqStore storage.JoinRequestStorage
	var channelHandler *api.ChannelHandler
	var alertHandler *api.AlertHandler
	var nodeHandler *api.NodeHandler

	if cfg.DatabaseURL != "" {
		openedDB, err := sql.Open("postgres", cfg.DatabaseURL)
		if err != nil {
			return nil, fmt.Errorf("failed to open database connection: %w", err)
		}
		db = openedDB

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

	// Initialize Realtime Hub
	hub := realtime.NewHub()

	// Initialize MQTT Status Subscriber for live gateway tracking
	presenceTracker := presence.NewTracker()

	var statusSub *mqtt.GatewayStatusSubscriber
	if statusStore != nil {
		statusSub = mqtt.NewGatewayStatusSubscriber(cfg.MQTTBrokerURI, statusStore, hub, eventStorage, joinReqStore, presenceTracker)
		if err := statusSub.Start(context.Background()); err != nil {
			log.Printf("Warning: failed to start MQTT status subscriber: %v", err)
		} else {
			log.Printf("MQTT status subscriber initialized on %s", cfg.MQTTBrokerURI)
		}
	}

	var joinReqHandler *api.JoinRequestHandler

	jwtService, err := auth.NewJWTService([]byte(cfg.JWTSecretKey))
	if err != nil {
		if db != nil {
			_ = db.Close()
		}
		return nil, fmt.Errorf("failed to initialize JWT service: %w", err)
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
		keyWrapper := api.NewAESGCMKeyWrapper(cfg.DeviceProvisionMasterKey)
		provisionHandler = api.NewProvisionHandler(provisionRepo, keyWrapper, jwtAuth)
	}

	mux := api.BuildServeMux(
		statusStore,
		cfg.OfflineThreshold,
		wsHandler,
		authHandler,
		channelHandler,
		alertHandler,
		provisionHandler,
		joinReqHandler,
		presenceTracker,
		nodeHandler,
		jwtService,
		jwtAuth,
	)

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      api.CORSMiddleware(mux),
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		IdleTimeout:  cfg.IdleTimeout,
	}

	return &App{
		cfg:       cfg,
		server:    srv,
		db:        db,
		hub:       hub,
		statusSub: statusSub,
	}, nil
}
