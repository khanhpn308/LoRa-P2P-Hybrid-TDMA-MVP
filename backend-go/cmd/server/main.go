package main

import (
	"context"
	"database/sql"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

// BuildServeMux wires REST endpoints for health checks and operational gateway/node monitoring.
func BuildServeMux(statusStore storage.StatusStorage, offlineThreshold time.Duration) *http.ServeMux {
	mux := http.NewServeMux()

	healthHandler := api.NewHealthHandler()
	healthHandler.RegisterRoutes(mux)

	if statusStore != nil {
		monitoringHandler := api.NewMonitoringHandler(statusStore, offlineThreshold)
		monitoringHandler.RegisterRoutes(mux)
	}

	return mux
}

func main() {
	log.Println("LoRa-P2P-Hybrid-TDMA-MVP Go Backend starting...")

	dbURL := os.Getenv("DATABASE_URL")
	var statusStore storage.StatusStorage

	if dbURL != "" {
		db, err := sql.Open("postgres", dbURL)
		if err != nil {
			log.Fatalf("failed to open database connection: %v", err)
		}
		defer db.Close()
		statusStore = storage.NewPostgresStatusStorage(db)
	}

	mux := BuildServeMux(statusStore, 5*time.Minute)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	srv := &http.Server{
		Addr:         ":" + port,
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Printf("HTTP server listening on %s", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	log.Println("shutting down server gracefully...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("forced server shutdown: %v", err)
	}
	log.Println("server stopped")
}
