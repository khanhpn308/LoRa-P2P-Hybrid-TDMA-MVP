package app

import (
	"context"
	"database/sql"
	"net/http"

	_ "github.com/lib/pq"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/config"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
)

// Subscriber defines the lifecycle operations required of an event subscriber.
type Subscriber interface {
	Start(ctx context.Context) error
	Stop()
}

// App is the composition root managing backend dependencies and lifecycle.
type App struct {
	cfg        *config.Config
	server     *http.Server
	db         *sql.DB
	hub        *realtime.Hub
	statusSub  *mqtt.GatewayStatusSubscriber
	subscriber Subscriber
}

// Server returns the configured http.Server instance.
func (a *App) Server() *http.Server {
	return a.server
}

// Config returns the active application configuration.
func (a *App) Config() *config.Config {
	return a.cfg
}

// Hub returns the realtime Hub instance.
func (a *App) Hub() *realtime.Hub {
	return a.hub
}

// StatusSub returns the configured GatewayStatusSubscriber instance (or nil if unconfigured).
func (a *App) StatusSub() *mqtt.GatewayStatusSubscriber {
	return a.statusSub
}

// Subscriber returns the active Subscriber lifecycle instance.
func (a *App) Subscriber() Subscriber {
	if a.subscriber != nil {
		return a.subscriber
	}
	if a.statusSub != nil {
		return a.statusSub
	}
	return nil
}

// DB returns the active database connection (or nil in in-memory mode).
func (a *App) DB() *sql.DB {
	return a.db
}
