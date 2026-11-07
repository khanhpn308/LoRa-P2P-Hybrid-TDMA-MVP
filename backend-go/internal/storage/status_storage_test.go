package storage_test

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var statusDriverOnce sync.Once

type mockStatusDriver struct{}

func (d *mockStatusDriver) Open(name string) (driver.Conn, error) {
	return &mockStatusConn{state: name}, nil
}

type mockStatusConn struct {
	state string
}

func (c *mockStatusConn) Prepare(query string) (driver.Stmt, error) {
	return &mockStatusStmt{query: query, state: c.state}, nil
}

func (c *mockStatusConn) Close() error { return nil }
func (c *mockStatusConn) Begin() (driver.Tx, error) {
	return &mockStatusTx{}, nil
}

type mockStatusTx struct{}

func (t *mockStatusTx) Commit() error   { return nil }
func (t *mockStatusTx) Rollback() error { return nil }

type mockStatusStmt struct {
	query string
	state string
}

func (s *mockStatusStmt) Close() error  { return nil }
func (s *mockStatusStmt) NumInput() int { return -1 }

func (s *mockStatusStmt) Exec(args []driver.Value) (driver.Result, error) {
	if s.state == "exec_err" {
		return nil, errors.New("exec error")
	}
	return driver.RowsAffected(1), nil
}

func (s *mockStatusStmt) Query(args []driver.Value) (driver.Rows, error) {
	q := strings.ToLower(s.query)
	if s.state == "query_err" {
		return nil, errors.New("query error")
	}

	// 1. GetGatewayStatus
	if strings.Contains(q, "from gateway_status") && strings.Contains(q, "where gateway_id = $1") {
		if len(args) > 0 && args[0] == "gw-01" {
			ch := "CH02"
			return &mockStatusRows{
				cols: []string{
					"gateway_id", "gateway_epoch", "mode", "active_schedule_version",
					"channel_id", "rf_duty_permille", "node_count", "free_heap_bytes",
					"offline_queue_count", "pending_event_count", "dropped_event_count",
					"last_seen_at", "updated_at",
				},
				data: [][]driver.Value{
					{
						"gw-01", "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "ACTIVE", int64(10),
						ch, 50, 4, int64(200000),
						int64(0), 1, "0",
						time.Now().UTC(), time.Now().UTC(),
					},
				},
			}, nil
		}
		// Not found
		return &mockStatusRows{cols: []string{"gateway_id"}, data: nil}, nil
	}

	// 2. ListNodes
	if strings.Contains(q, "from node_health nh") {
		now := time.Now().UTC()
		if s.state == "empty_nodes" {
			return &mockStatusRows{
				cols: []string{"node_id", "gateway_id", "health_status", "last_seen_at"},
				data: nil,
			}, nil
		}
		if s.state == "paginated_page1" {
			// Return 3 rows when limit=2 (+1 extra to trigger next_cursor)
			return &mockStatusRows{
				cols: []string{"node_id", "gateway_id", "health_status", "last_seen_at"},
				data: [][]driver.Value{
					{1, "gw-01", "ONLINE", now},
					{2, "gw-01", "ONLINE", now},
					{3, "gw-01", "OFFLINE", now},
				},
			}, nil
		}
		if s.state == "last_page" {
			// Return 2 rows when limit=2 (no extra row)
			return &mockStatusRows{
				cols: []string{"node_id", "gateway_id", "health_status", "last_seen_at"},
				data: [][]driver.Value{
					{3, "gw-01", "OFFLINE", now},
					{4, "gw-01", "UNSYNCED", now},
				},
			}, nil
		}

		// Default nodes
		return &mockStatusRows{
			cols: []string{"node_id", "gateway_id", "health_status", "last_seen_at"},
			data: [][]driver.Value{
				{1, "gw-01", "ONLINE", now},
				{2, "gw-01", "OFFLINE", now},
			},
		}, nil
	}

	return &mockStatusRows{cols: []string{"id"}, data: nil}, nil
}

type mockStatusRows struct {
	cols []string
	data [][]driver.Value
	idx  int
}

func (r *mockStatusRows) Columns() []string {
	return r.cols
}

func (r *mockStatusRows) Close() error {
	return nil
}

func (r *mockStatusRows) Next(dest []driver.Value) error {
	if r.idx >= len(r.data) {
		return io.EOF
	}
	row := r.data[r.idx]
	copy(dest, row)
	r.idx++
	return nil
}

func initStatusMockDB(state string) *sql.DB {
	statusDriverOnce.Do(func() {
		sql.Register("mock_status_postgres", &mockStatusDriver{})
	})
	db, err := sql.Open("mock_status_postgres", state)
	if err != nil {
		panic(err)
	}
	return db
}

func TestPostgresStatusStorage_UpsertGatewayStatus(t *testing.T) {
	ctx := context.Background()

	t.Run("nil record error", func(t *testing.T) {
		db := initStatusMockDB("default")
		store := storage.NewPostgresStatusStorage(db)
		err := store.UpsertGatewayStatus(ctx, nil)
		if err == nil {
			t.Fatalf("expected error on nil record")
		}
	})

	t.Run("invalid record validation error", func(t *testing.T) {
		db := initStatusMockDB("default")
		store := storage.NewPostgresStatusStorage(db)
		err := store.UpsertGatewayStatus(ctx, &domain.GatewayStatusRecord{
			GatewayID: "invalid!",
		})
		if err == nil {
			t.Fatalf("expected validation error")
		}
	})

	t.Run("successful upsert", func(t *testing.T) {
		db := initStatusMockDB("default")
		store := storage.NewPostgresStatusStorage(db)
		ch := "CH01"
		rec := &domain.GatewayStatusRecord{
			GatewayID:             "gw-01",
			GatewayEpoch:          "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
			Mode:                  domain.GatewayModeActive,
			ActiveScheduleVersion: 5,
			ChannelID:             &ch,
			RFDutyPermille:        20,
			NodeCount:             2,
			FreeHeapBytes:         120000,
			OfflineQueueCount:     0,
			PendingEventCount:     0,
			DroppedEventCount:     0,
			LastSeenAt:            time.Now().UTC(),
		}
		if err := store.UpsertGatewayStatus(ctx, rec); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("exec error propagates", func(t *testing.T) {
		db := initStatusMockDB("exec_err")
		store := storage.NewPostgresStatusStorage(db)
		rec := &domain.GatewayStatusRecord{
			GatewayID:    "gw-01",
			GatewayEpoch: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
			Mode:         domain.GatewayModeActive,
		}
		if err := store.UpsertGatewayStatus(ctx, rec); err == nil {
			t.Fatalf("expected exec error")
		}
	})
}

func TestPostgresStatusStorage_GetGatewayStatus(t *testing.T) {
	ctx := context.Background()

	t.Run("invalid gateway id", func(t *testing.T) {
		db := initStatusMockDB("default")
		store := storage.NewPostgresStatusStorage(db)
		_, err := store.GetGatewayStatus(ctx, "invalid gateway!")
		if err == nil {
			t.Fatalf("expected invalid gateway id error")
		}
	})

	t.Run("found gateway status", func(t *testing.T) {
		db := initStatusMockDB("default")
		store := storage.NewPostgresStatusStorage(db)
		rec, err := store.GetGatewayStatus(ctx, "gw-01")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if rec.GatewayID != "gw-01" || rec.Mode != domain.GatewayModeActive {
			t.Fatalf("unexpected record: %+v", rec)
		}
	})

	t.Run("not found gateway status", func(t *testing.T) {
		db := initStatusMockDB("default")
		store := storage.NewPostgresStatusStorage(db)
		_, err := store.GetGatewayStatus(ctx, "gw-nonexistent")
		if !errors.Is(err, storage.ErrGatewayStatusNotFound) {
			t.Fatalf("expected ErrGatewayStatusNotFound, got: %v", err)
		}
	})
}

func TestPostgresStatusStorage_ListNodes(t *testing.T) {
	ctx := context.Background()

	t.Run("invalid filter bounds", func(t *testing.T) {
		db := initStatusMockDB("default")
		store := storage.NewPostgresStatusStorage(db)
		_, err := store.ListNodes(ctx, domain.NodeFilter{Limit: 0})
		if err == nil {
			t.Fatalf("expected limit error")
		}
	})

	t.Run("invalid cursor format", func(t *testing.T) {
		db := initStatusMockDB("default")
		store := storage.NewPostgresStatusStorage(db)
		_, err := store.ListNodes(ctx, domain.NodeFilter{Limit: 10, Cursor: "not-a-number"})
		if err == nil {
			t.Fatalf("expected cursor error")
		}
	})

	t.Run("paginated page 1 has next_cursor", func(t *testing.T) {
		db := initStatusMockDB("paginated_page1")
		store := storage.NewPostgresStatusStorage(db)
		page, err := store.ListNodes(ctx, domain.NodeFilter{Limit: 2})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(page.Items) != 2 {
			t.Fatalf("expected 2 items, got %d", len(page.Items))
		}
		if page.NextCursor == nil || *page.NextCursor != "2" {
			t.Fatalf("expected next_cursor='2', got: %v", page.NextCursor)
		}
	})

	t.Run("last page has nil next_cursor", func(t *testing.T) {
		db := initStatusMockDB("last_page")
		store := storage.NewPostgresStatusStorage(db)
		page, err := store.ListNodes(ctx, domain.NodeFilter{Limit: 2, Cursor: "2"})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(page.Items) != 2 {
			t.Fatalf("expected 2 items, got %d", len(page.Items))
		}
		if page.NextCursor != nil {
			t.Fatalf("expected nil next_cursor on last page, got: %v", *page.NextCursor)
		}
	})
}
