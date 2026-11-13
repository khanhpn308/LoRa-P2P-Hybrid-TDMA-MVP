package app

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
)

// Run starts the application background workers and HTTP server, blocking until the context is canceled or a server error occurs.
func (a *App) Run(ctx context.Context) error {
	hubCtx, cancelHub := context.WithCancel(context.Background())
	defer cancelHub()
	go a.hub.Run(hubCtx)

	serverErr := make(chan error, 1)
	go func() {
		log.Printf("HTTP server listening on %s", a.server.Addr)
		if err := a.server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			serverErr <- err
		}
	}()

	select {
	case err := <-serverErr:
		return fmt.Errorf("server error: %w", err)
	case <-ctx.Done():
	}

	log.Println("shutting down server gracefully...")
	if a.statusSub != nil {
		a.statusSub.Stop()
	}

	shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), a.cfg.ShutdownTimeout)
	defer cancelShutdown()

	if err := a.hub.Shutdown(shutdownCtx); err != nil {
		log.Printf("error shutting down realtime hub: %v", err)
	}

	if err := a.server.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("forced server shutdown: %w", err)
	}

	if a.db != nil {
		if err := a.db.Close(); err != nil {
			log.Printf("error closing database connection: %v", err)
		}
	}

	log.Println("server gracefully stopped.")
	return nil
}
