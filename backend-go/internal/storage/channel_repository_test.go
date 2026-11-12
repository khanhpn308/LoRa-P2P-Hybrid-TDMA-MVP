package storage_test

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"fmt"
	"io"
	"regexp"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var (
	driverOnce sync.Once
	wsRegex    = regexp.MustCompile(`\s+`)
)

type mockDriver struct{}

func (d *mockDriver) Open(name string) (driver.Conn, error) {
	return &mockConn{name: name}, nil
}

type mockConn struct {
	name string
}

func (c *mockConn) Prepare(query string) (driver.Stmt, error) {
	return &mockStmt{query: query, conn: c}, nil
}

func (c *mockConn) Close() error {
	return nil
}

func (c *mockConn) Begin() (driver.Tx, error) {
	return &mockTx{}, nil
}

func (c *mockConn) BeginTx(ctx context.Context, opts driver.TxOptions) (driver.Tx, error) {
	return &mockTx{}, nil
}

type mockTx struct{}

func (tx *mockTx) Commit() error   { return nil }
func (tx *mockTx) Rollback() error { return nil }

type mockStmt struct {
	query string
	conn  *mockConn
}

func (s *mockStmt) Close() error  { return nil }
func (s *mockStmt) NumInput() int { return -1 }

var (
	mockExecMu      sync.Mutex
	mockExecQueries []string
)

func (s *mockStmt) Exec(args []driver.Value) (driver.Result, error) {
	mockExecMu.Lock()
	mockExecQueries = append(mockExecQueries, s.query)
	mockExecMu.Unlock()
	return driver.RowsAffected(1), nil
}

func (s *mockStmt) Query(args []driver.Value) (driver.Rows, error) {
	q := wsRegex.ReplaceAllString(strings.ToLower(s.query), " ")
	state := s.conn.name

	// 1. GetChannel
	if strings.Contains(q, "from rf_channels where channel_id = $1") && !strings.Contains(q, "for update") {
		if len(args) > 0 && args[0] == "CH00" {
			return &mockRows{
				columns: []string{"channel_id", "channel_plan_version", "center_frequency_hz", "bandwidth_hz", "is_enabled", "created_at", "updated_at"},
				rows: [][]driver.Value{
					{"CH00", "VN920_V1", int64(920250000), int64(125000), true, time.Now().UTC(), time.Now().UTC()},
				},
			}, nil
		}
		return &mockRows{columns: []string{"channel_id"}, rows: nil}, nil // no rows
	}

	// 2. ListChannels
	if strings.Contains(q, "from rf_channels c") && strings.Contains(q, "left join gateway_channel_allocations") {
		return &mockRows{
			columns: []string{"channel_id", "channel_plan_version", "center_frequency_hz", "bandwidth_hz", "is_enabled", "state"},
			rows: [][]driver.Value{
				{"CH00", "VN920_V1", int64(920250000), int64(125000), true, "AVAILABLE"},
				{"CH01", "VN920_V1", int64(920500000), int64(125000), true, "AVAILABLE"},
			},
		}, nil
	}

	// 3. AllocateChannel subqueries
	if strings.Contains(q, "from gateway_channel_allocations where gateway_id = $1 and request_id = $2") {
		if state == "idempotent" {
			return &mockRows{
				columns: []string{"id", "gateway_id", "channel_id", "status", "request_id", "allocation_generation", "granted_by", "released_by", "release_reason", "created_at", "updated_at", "released_at"},
				rows: [][]driver.Value{
					{int64(1), "gw01", "CH00", "ALLOCATED", "req-idemp", int64(1), "test", nil, nil, time.Now().UTC(), time.Now().UTC(), nil},
				},
			}, nil
		}
		return &mockRows{columns: []string{"id"}, rows: nil}, nil
	}

	if strings.Contains(q, "from gateway_channel_allocations where gateway_id = $1 and status = 'allocated'") {
		if state == "gw_has_allocation" {
			return &mockRows{
				columns: []string{"channel_id"},
				rows:    [][]driver.Value{{"CH02"}},
			}, nil
		}
		return &mockRows{columns: []string{"channel_id"}, rows: nil}, nil
	}

	if strings.Contains(q, "from rf_channels where channel_id = $1 for update") {
		if state == "disabled_channel" {
			return &mockRows{
				columns: []string{"channel_plan_version", "is_enabled"},
				rows:    [][]driver.Value{{"VN920_V1", false}},
			}, nil
		}
		if state == "channel_not_found" {
			return &mockRows{columns: []string{"channel_plan_version", "is_enabled"}, rows: nil}, nil
		}
		return &mockRows{
			columns: []string{"channel_plan_version", "is_enabled"},
			rows:    [][]driver.Value{{"VN920_V1", true}},
		}, nil
	}

	if strings.Contains(q, "from gateway_channel_allocations where channel_id = $1 and status = 'allocated'") {
		if state == "channel_occupied" {
			return &mockRows{
				columns: []string{"gateway_id"},
				rows:    [][]driver.Value{{"gw-other"}},
			}, nil
		}
		return &mockRows{columns: []string{"gateway_id"}, rows: nil}, nil
	}

	if strings.Contains(q, "coalesce(max(allocation_generation), 0) + 1") {
		return &mockRows{
			columns: []string{"gen"},
			rows:    [][]driver.Value{{int64(1)}},
		}, nil
	}

	if strings.Contains(q, "insert into gateway_channel_allocations") {
		return &mockRows{
			columns: []string{"id", "gateway_id", "channel_id", "status", "request_id", "allocation_generation", "granted_by", "created_at", "updated_at"},
			rows: [][]driver.Value{
				{int64(10), "gw01", "CH00", "ALLOCATED", "req-new", int64(1), "test", time.Now().UTC(), time.Now().UTC()},
			},
		}, nil
	}

	// 4. ReleaseChannel subqueries
	if strings.Contains(q, "from gateway_channel_allocations where gateway_id = $1 and channel_id = $2 and status = 'allocated'") {
		if state == "release_ok" {
			return &mockRows{
				columns: []string{"id"},
				rows:    [][]driver.Value{{int64(10)}},
			}, nil
		}
		return &mockRows{columns: []string{"id"}, rows: nil}, nil
	}

	if strings.Contains(q, "update gateway_channel_allocations") {
		now := time.Now().UTC()
		return &mockRows{
			columns: []string{"id", "gateway_id", "channel_id", "status", "request_id", "allocation_generation", "granted_by", "released_by", "release_reason", "created_at", "updated_at", "released_at"},
			rows: [][]driver.Value{
				{int64(10), "gw01", "CH00", "RELEASED", "req-rel", int64(1), "test", "tester", "done", now, now, now},
			},
		}, nil
	}

	// 5. Join Storage Queries
	if strings.Contains(q, "select 1 from devices d join device_generations g") {
		if state == "join_device_not_found" || state == "device_unregistered" {
			return &mockRows{columns: []string{"exists"}, rows: nil}, nil
		}
		return &mockRows{
			columns: []string{"exists"},
			rows:    [][]driver.Value{{1}},
		}, nil
	}

	if strings.Contains(q, "from devices d join device_generations g") {
		if state == "join_device_not_found" {
			return &mockRows{columns: []string{"status", "generation", "k_join_wrapped"}, rows: nil}, nil
		}
		if state == "join_device_revoked" {
			return &mockRows{
				columns: []string{"status", "generation", "k_join_wrapped"},
				rows:    [][]driver.Value{{"REVOKED", int64(1), []byte("wrapped-key-revoked")}},
			}, nil
		}
		return &mockRows{
			columns: []string{"status", "generation", "k_join_wrapped"},
			rows:    [][]driver.Value{{"ACTIVE", int64(1), []byte("wrapped-key-bytes-test-32bytes!")}},
		}, nil
	}

	if strings.Contains(q, "from devices where network_id = $1 and device_mac = $2 for update") {
		if state == "join_device_not_found" {
			return &mockRows{columns: []string{"status"}, rows: nil}, nil
		}
		if state == "join_device_revoked" || state == "provision_device_revoked" {
			return &mockRows{columns: []string{"status"}, rows: [][]driver.Value{{"REVOKED"}}}, nil
		}
		return &mockRows{columns: []string{"status"}, rows: [][]driver.Value{{"ACTIVE"}}}, nil
	}

	if strings.Contains(q, "from device_generations where network_id = $1 and device_mac = $2 and is_active = true for update") {
		if state == "provision_active_conflict" {
			return &mockRows{columns: []string{"generation"}, rows: [][]driver.Value{{1}}}, nil
		}
		return &mockRows{columns: []string{"generation"}, rows: nil}, nil
	}

	if strings.Contains(q, "from device_generations where network_id = $1 and device_mac = $2 and generation = $3") && !strings.Contains(q, "for update") {
		if state == "provision_gen_exists" {
			return &mockRows{columns: []string{"dummy"}, rows: [][]driver.Value{{1}}}, nil
		}
		return &mockRows{columns: []string{"dummy"}, rows: nil}, nil
	}

	if strings.Contains(q, "insert into device_generations") && strings.Contains(q, "returning created_at") {
		return &mockRows{columns: []string{"created_at"}, rows: [][]driver.Value{{time.Now().UTC()}}}, nil
	}

	if strings.Contains(q, "from device_generations where network_id = $1 and device_mac = $2 and generation = $3 for update") {
		if state == "join_gen_inactive" {
			return &mockRows{columns: []string{"is_active"}, rows: [][]driver.Value{{false}}}, nil
		}
		if state == "join_gen_not_found" {
			return &mockRows{columns: []string{"is_active"}, rows: nil}, nil
		}
		return &mockRows{columns: []string{"is_active"}, rows: [][]driver.Value{{true}}}, nil
	}

	if strings.Contains(q, "from device_join_counters where network_id = $1 and device_mac = $2 and generation = $3 for update") {
		if state == "join_first_counter" {
			return &mockRows{columns: []string{"last_join_counter"}, rows: nil}, nil
		}
		if state == "join_advancing_counter" {
			return &mockRows{columns: []string{"last_join_counter"}, rows: [][]driver.Value{{int64(10)}}}, nil
		}
		if state == "join_idempotent_retry" || state == "join_replay_conflict" {
			return &mockRows{columns: []string{"last_join_counter"}, rows: [][]driver.Value{{int64(20)}}}, nil
		}
		if state == "join_stale_counter" {
			return &mockRows{columns: []string{"last_join_counter"}, rows: [][]driver.Value{{int64(50)}}}, nil
		}
		return &mockRows{columns: []string{"last_join_counter"}, rows: [][]driver.Value{{int64(1)}}}, nil
	}

	if strings.Contains(q, "from join_transactions where network_id = $1 and device_mac = $2 and generation = $3 and join_counter = $4") {
		if state == "join_idempotent_retry" {
			return &mockRows{
				columns: []string{"id", "status", "raw_hello_sha256"},
				rows: [][]driver.Value{
					{int64(88), storage.StatusHelloAuthenticatedPendingGrant, []byte("hello-hash-32-bytes-identical!!!")},
				},
			}, nil
		}
		if state == "join_replay_conflict" {
			return &mockRows{
				columns: []string{"id", "status", "raw_hello_sha256"},
				rows: [][]driver.Value{
					{int64(88), storage.StatusHelloAuthenticatedPendingGrant, []byte("hello-hash-different-original!!")},
				},
			}, nil
		}
		return &mockRows{columns: []string{"id", "status", "raw_hello_sha256"}, rows: nil}, nil
	}

	if strings.Contains(q, "insert into join_transactions") {
		return &mockRows{
			columns: []string{"id"},
			rows:    [][]driver.Value{{int64(99)}},
		}, nil
	}

	// 6. Event and Health Storage Queries
	if strings.Contains(q, "from events where gateway_id = $1 and event_id = $2 for update") {
		if state == "event_idempotent_duplicate" {
			h := validStorageEvent().ComputePayloadSHA256()
			return &mockRows{
				columns: []string{"id", "raw_payload_sha256"},
				rows: [][]driver.Value{
					{int64(42), h[:]},
				},
			}, nil
		}
		if state == "event_conflicting_payload" {
			// Mock conflicting hash
			return &mockRows{
				columns: []string{"id", "raw_payload_sha256"},
				rows: [][]driver.Value{
					{int64(42), []byte("conflicting-hash-32-bytes-here!")},
				},
			}, nil
		}
		return &mockRows{columns: []string{"id", "raw_payload_sha256"}, rows: nil}, nil
	}

	if strings.Contains(q, "insert into events") && strings.Contains(q, "returning id") {
		return &mockRows{
			columns: []string{"id"},
			rows:    [][]driver.Value{{int64(101)}},
		}, nil
	}

	if strings.Contains(q, "from events where gateway_id = $1 and event_id = $2") {
		if state == "event_not_found" {
			return &mockRows{columns: []string{"id"}, rows: nil}, nil
		}
		now := time.Now().UTC()
		return &mockRows{
			columns: []string{
				"id", "event_id", "gateway_id", "gateway_epoch", "event_seq", "node_id",
				"superframe_seq", "seq_num", "schedule_version", "severity", "observed_at", "observed_time_source",
				"radio_rx_monotonic_us", "buffered", "radio_ack_sent", "event_ref", "event_code", "event_value",
				"trigger_channel", "trigger_observed_raw", "trigger_threshold_raw",
				"raw_payload_sha256", "ingested_at", "ack_status", "acknowledged_at", "acknowledged_by",
			},
			rows: [][]driver.Value{
				{
					int64(101), "gw01:550e8400-e29b-41d4-a716-446655440000:42", "gw01", "550e8400-e29b-41d4-a716-446655440000", "42", 1,
					int64(100), 5, int64(1), "P1_HIGH", now, "gateway_utc",
					"123456789", false, true, int64(1), 1, 2500,
					1, 2500, 2000,
					[]byte("test-matching-hash-32-bytes!!!"), now, "UNACKNOWLEDGED", nil, nil,
				},
			},
		}, nil
	}

	if strings.Contains(q, "from node_health where gateway_id = $1 and node_id = $2") {
		if state == "health_not_found" {
			return &mockRows{columns: []string{"gateway_id"}, rows: nil}, nil
		}
		now := time.Now().UTC()
		return &mockRows{
			columns: []string{
				"gateway_id", "node_id", "session_sel", "frame_counter", "maint_seq", "status_flags",
				"pending_event_count", "health_status", "updated_at",
			},
			rows: [][]driver.Value{
				{"gw01", 1, 1, int64(100), int64(10), 0, 0, "ONLINE", now},
			},
		}, nil
	}

	if strings.Contains(q, "from events") && strings.Contains(q, "order by id desc limit") {
		if state == "events_empty" {
			return &mockRows{columns: []string{"id"}, rows: nil}, nil
		}
		now := time.Now().UTC()
		return &mockRows{
			columns: []string{
				"id", "event_id", "gateway_id", "gateway_epoch", "event_seq", "node_id",
				"superframe_seq", "seq_num", "schedule_version", "severity", "observed_at", "observed_time_source",
				"radio_rx_monotonic_us", "buffered", "radio_ack_sent", "event_ref", "event_code", "event_value",
				"raw_payload_sha256", "ingested_at", "ack_status", "acknowledged_at", "acknowledged_by",
			},
			rows: [][]driver.Value{
				{
					int64(102), "gw01:550e8400-e29b-41d4-a716-446655440000:43", "gw01", "550e8400-e29b-41d4-a716-446655440000", "43", 2,
					int64(101), 6, int64(1), "P0_EMERGENCY", now, "gateway_utc",
					"123456790", false, true, int64(2), 2, 100,
					[]byte("test-matching-hash-32-bytes!!!"), now, "UNACKNOWLEDGED", nil, nil,
				},
				{
					int64(101), "gw01:550e8400-e29b-41d4-a716-446655440000:42", "gw01", "550e8400-e29b-41d4-a716-446655440000", "42", 1,
					int64(100), 5, int64(1), "P1_HIGH", now, "gateway_utc",
					"123456789", false, true, int64(1), 1, 2500,
					[]byte("test-matching-hash-32-bytes!!!"), now, "UNACKNOWLEDGED", nil, nil,
				},
			},
		}, nil
	}

	if strings.Contains(q, "select ack_status from events where id = $1 for update") {
		if state == "ack_not_found" {
			return &mockRows{columns: []string{"ack_status"}, rows: nil}, nil
		}
		if state == "ack_already_acked" {
			return &mockRows{columns: []string{"ack_status"}, rows: [][]driver.Value{{"ACKNOWLEDGED"}}}, nil
		}
		return &mockRows{columns: []string{"ack_status"}, rows: [][]driver.Value{{"UNACKNOWLEDGED"}}}, nil
	}

	if strings.Contains(q, "from events where id = $1") {
		now := time.Now().UTC()
		return &mockRows{
			columns: []string{
				"id", "event_id", "gateway_id", "gateway_epoch", "event_seq", "node_id",
				"superframe_seq", "seq_num", "schedule_version", "severity", "observed_at", "observed_time_source",
				"radio_rx_monotonic_us", "buffered", "radio_ack_sent", "event_ref", "event_code", "event_value",
				"raw_payload_sha256", "ingested_at", "ack_status", "acknowledged_at", "acknowledged_by",
			},
			rows: [][]driver.Value{
				{
					int64(101), "gw01:550e8400-e29b-41d4-a716-446655440000:42", "gw01", "550e8400-e29b-41d4-a716-446655440000", "42", 1,
					int64(100), 5, int64(1), "P1_HIGH", now, "gateway_utc",
					"123456789", false, true, int64(1), 1, 2500,
					[]byte("test-matching-hash-32-bytes!!!"), now, "ACKNOWLEDGED", now, "operator1",
				},
			},
		}, nil
	}

	if strings.Contains(q, "from node_health") && strings.Contains(q, "order by node_id asc limit") {
		if state == "node_health_empty" {
			return &mockRows{columns: []string{"node_id"}, rows: nil}, nil
		}
		now := time.Now().UTC()
		return &mockRows{
			columns: []string{
				"gateway_id", "node_id", "session_sel", "frame_counter", "maint_seq", "status_flags",
				"pending_event_count", "health_status", "updated_at",
			},
			rows: [][]driver.Value{
				{"gw01", 1, 1, int64(100), int64(10), 0, 0, "ONLINE", now},
				{"gw01", 2, 1, int64(95), int64(10), 0, 0, "ONLINE", now},
			},
		}, nil
	}

	// 7. Join Request Approval Queries
	if strings.Contains(q, "from device_join_requests") && strings.Contains(q, "status in ('pending', 'approved')") {
		if state == "join_req_pending" {
			createdAt := time.Now().Add(-10 * time.Minute).UTC()
			return &mockRows{
				columns: []string{"id", "status", "assigned_node_id", "created_at", "updated_at"},
				rows: [][]driver.Value{
					{int64(10), "PENDING", nil, createdAt, createdAt},
				},
			}, nil
		}
		if state == "join_req_approved" {
			nodeID := 5
			createdAt := time.Now().Add(-1 * time.Hour).UTC()
			return &mockRows{
				columns: []string{"id", "status", "assigned_node_id", "created_at", "updated_at"},
				rows: [][]driver.Value{
					{int64(10), "APPROVED", nodeID, createdAt, createdAt},
				},
			}, nil
		}
		return &mockRows{columns: []string{"id", "status", "assigned_node_id", "created_at", "updated_at"}, rows: nil}, nil
	}

	if strings.Contains(q, "insert into device_join_requests") && strings.Contains(q, "returning id, created_at, updated_at") {
		now := time.Now().UTC()
		return &mockRows{
			columns: []string{"id", "created_at", "updated_at"},
			rows: [][]driver.Value{
				{int64(101), now, now},
			},
		}, nil
	}

	if strings.Contains(q, "update device_join_requests") && strings.Contains(q, "set status = 'rejected'") {
		if state == "join_req_not_found" {
			return &mockRows{columns: []string{"id"}, rows: nil}, nil
		}
		now := time.Now().UTC()
		return &mockRows{
			columns: []string{"id", "device_mac", "gateway_id", "rssi", "snr", "raw_frame_hex", "status", "assigned_node_id", "created_at", "updated_at"},
			rows: [][]driver.Value{
				{int64(10), "001122334455", "gw01", 0, 0.0, "", "REJECTED", nil, now.Add(-time.Hour), now},
			},
		}, nil
	}

	if strings.Contains(q, "from device_join_requests") && strings.Contains(q, "where id = $1") && strings.Contains(q, "for update") {
		if state == "join_req_not_found" {
			return &mockRows{columns: []string{"id"}, rows: nil}, nil
		}
		return &mockRows{
			columns: []string{"id", "device_mac", "gateway_id", "status"},
			rows: [][]driver.Value{
				{int64(10), "001122334455", "gw01", "PENDING"},
			},
		}, nil
	}

	if strings.Contains(q, "from generate_series(1, 254)") {
		if state == "no_slots" {
			return &mockRows{columns: []string{"id"}, rows: nil}, nil
		}
		return &mockRows{
			columns: []string{"id"},
			rows:    [][]driver.Value{{1}},
		}, nil
	}

	if strings.Contains(q, "update device_join_requests") && strings.Contains(q, "returning updated_at") {
		return &mockRows{
			columns: []string{"updated_at"},
			rows:    [][]driver.Value{{time.Now().UTC()}},
		}, nil
	}

	return nil, fmt.Errorf("unhandled query in mock driver: %s", s.query)
}

type mockRows struct {
	columns []string
	rows    [][]driver.Value
	idx     int
}

func (r *mockRows) Columns() []string {
	return r.columns
}

func (r *mockRows) Close() error {
	return nil
}

func (r *mockRows) Next(dest []driver.Value) error {
	if r.idx >= len(r.rows) {
		return io.EOF
	}
	for i, val := range r.rows[r.idx] {
		dest[i] = val
	}
	r.idx++
	return nil
}

func initMockDB(state string) *sql.DB {
	driverOnce.Do(func() {
		sql.Register("mock_postgres", &mockDriver{})
	})
	db, err := sql.Open("mock_postgres", state)
	if err != nil {
		panic(err)
	}
	return db
}

func TestPostgresChannelRepository_GetChannel(t *testing.T) {
	ctx := context.Background()

	t.Run("found channel", func(t *testing.T) {
		db := initMockDB("default")
		repo := storage.NewPostgresChannelRepository(db)
		ch, err := repo.GetChannel(ctx, "CH00")
		if err != nil {
			t.Fatalf("expected channel, got error: %v", err)
		}
		if ch.ChannelID != "CH00" || ch.CenterFrequencyHz != 920250000 {
			t.Errorf("unexpected channel: %+v", ch)
		}
	})

	t.Run("channel not found", func(t *testing.T) {
		db := initMockDB("default")
		repo := storage.NewPostgresChannelRepository(db)
		_, err := repo.GetChannel(ctx, "CH01")
		if !errors.Is(err, domain.ErrChannelNotFound) {
			t.Errorf("expected ErrChannelNotFound, got: %v", err)
		}
	})
}

func TestPostgresChannelRepository_ListChannels(t *testing.T) {
	ctx := context.Background()
	db := initMockDB("default")
	repo := storage.NewPostgresChannelRepository(db)

	channels, err := repo.ListChannels(ctx, domain.ChannelPlanVN920V1)
	if err != nil {
		t.Fatalf("expected channels, got error: %v", err)
	}
	if len(channels) != 2 {
		t.Errorf("expected 2 channels, got %d", len(channels))
	}
}

func TestPostgresChannelRepository_AllocateChannel(t *testing.T) {
	ctx := context.Background()

	t.Run("successful allocation", func(t *testing.T) {
		db := initMockDB("success")
		repo := storage.NewPostgresChannelRepository(db)
		alloc, err := repo.AllocateChannel(ctx, domain.AllocateRequest{
			GatewayID:          "gw01",
			ChannelID:          "CH00",
			ChannelPlanVersion: domain.ChannelPlanVN920V1,
			RequestID:          "req-new",
			GrantedBy:          "test",
		})
		if err != nil {
			t.Fatalf("expected allocation, got: %v", err)
		}
		if alloc.ChannelID != "CH00" || alloc.GatewayID != "gw01" || alloc.Status != domain.StatusAllocated {
			t.Errorf("unexpected allocation: %+v", alloc)
		}
	})

	t.Run("idempotent replay", func(t *testing.T) {
		db := initMockDB("idempotent")
		repo := storage.NewPostgresChannelRepository(db)
		alloc, err := repo.AllocateChannel(ctx, domain.AllocateRequest{
			GatewayID:          "gw01",
			ChannelID:          "CH00",
			ChannelPlanVersion: domain.ChannelPlanVN920V1,
			RequestID:          "req-idemp",
			GrantedBy:          "test",
		})
		if err != nil {
			t.Fatalf("expected idempotent success, got: %v", err)
		}
		if alloc.RequestID != "req-idemp" {
			t.Errorf("unexpected alloc request id: %s", alloc.RequestID)
		}
	})

	t.Run("gateway already has allocation", func(t *testing.T) {
		db := initMockDB("gw_has_allocation")
		repo := storage.NewPostgresChannelRepository(db)
		_, err := repo.AllocateChannel(ctx, domain.AllocateRequest{
			GatewayID:          "gw01",
			ChannelID:          "CH00",
			ChannelPlanVersion: domain.ChannelPlanVN920V1,
			RequestID:          "req-conflict",
			GrantedBy:          "test",
		})
		if !errors.Is(err, domain.ErrGatewayAlreadyAllocated) {
			t.Errorf("expected ErrGatewayAlreadyAllocated, got: %v", err)
		}
	})

	t.Run("channel is occupied", func(t *testing.T) {
		db := initMockDB("channel_occupied")
		repo := storage.NewPostgresChannelRepository(db)
		_, err := repo.AllocateChannel(ctx, domain.AllocateRequest{
			GatewayID:          "gw01",
			ChannelID:          "CH00",
			ChannelPlanVersion: domain.ChannelPlanVN920V1,
			RequestID:          "req-occupied",
			GrantedBy:          "test",
		})
		if !errors.Is(err, domain.ErrChannelInUse) {
			t.Errorf("expected ErrChannelInUse, got: %v", err)
		}
	})

	t.Run("channel is disabled", func(t *testing.T) {
		db := initMockDB("disabled_channel")
		repo := storage.NewPostgresChannelRepository(db)
		_, err := repo.AllocateChannel(ctx, domain.AllocateRequest{
			GatewayID:          "gw01",
			ChannelID:          "CH00",
			ChannelPlanVersion: domain.ChannelPlanVN920V1,
			RequestID:          "req-disabled",
			GrantedBy:          "test",
		})
		if !errors.Is(err, domain.ErrChannelDisabled) {
			t.Errorf("expected ErrChannelDisabled, got: %v", err)
		}
	})
}

func TestPostgresChannelRepository_ReleaseChannel(t *testing.T) {
	ctx := context.Background()

	t.Run("successful release", func(t *testing.T) {
		db := initMockDB("release_ok")
		repo := storage.NewPostgresChannelRepository(db)
		alloc, err := repo.ReleaseChannel(ctx, domain.ReleaseRequest{
			GatewayID:     "gw01",
			ChannelID:     "CH00",
			RequestID:     "req-rel",
			ReleasedBy:    "tester",
			ReleaseReason: "done",
		})
		if err != nil {
			t.Fatalf("expected release, got error: %v", err)
		}
		if alloc.Status != domain.StatusReleased {
			t.Errorf("expected status RELEASED, got %s", alloc.Status)
		}
	})

	t.Run("allocation not found", func(t *testing.T) {
		db := initMockDB("release_not_found")
		repo := storage.NewPostgresChannelRepository(db)
		_, err := repo.ReleaseChannel(ctx, domain.ReleaseRequest{
			GatewayID:     "gw01",
			ChannelID:     "CH00",
			RequestID:     "req-rel-nf",
			ReleasedBy:    "tester",
			ReleaseReason: "done",
		})
		if !errors.Is(err, domain.ErrAllocationNotFound) {
			t.Errorf("expected ErrAllocationNotFound, got: %v", err)
		}
	})
}
