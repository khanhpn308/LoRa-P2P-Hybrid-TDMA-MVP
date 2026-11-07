package storage_test

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var (
	schedDriverOnce sync.Once
)

type mockSchedConn struct {
	state string
}

func (c *mockSchedConn) Prepare(query string) (driver.Stmt, error) {
	return &mockSchedStmt{conn: c, query: query}, nil
}

func (c *mockSchedConn) Close() error {
	return nil
}

func (c *mockSchedConn) Begin() (driver.Tx, error) {
	return &mockSchedTx{}, nil
}

func (c *mockSchedConn) BeginTx(ctx context.Context, opts driver.TxOptions) (driver.Tx, error) {
	return &mockSchedTx{}, nil
}

type mockSchedTx struct{}

func (t *mockSchedTx) Commit() error {
	return nil
}

func (t *mockSchedTx) Rollback() error {
	return nil
}

type mockSchedStmt struct {
	conn  *mockSchedConn
	query string
}

func (s *mockSchedStmt) Close() error {
	return nil
}

func (s *mockSchedStmt) NumInput() int {
	return -1
}

func (s *mockSchedStmt) Exec(args []driver.Value) (driver.Result, error) {
	q := strings.ToLower(s.query)
	state := s.conn.state

	if state == "exec_error" {
		return nil, errors.New("simulated exec error")
	}

	if strings.Contains(q, "update schedule_migration_transactions") && strings.Contains(q, "set state = $1") {
		if state == "tx_not_found" {
			return driver.RowsAffected(0), nil
		}
		return driver.RowsAffected(1), nil
	}

	if strings.Contains(q, "update schedules") {
		if state == "sched_not_found" {
			return driver.RowsAffected(0), nil
		}
		return driver.RowsAffected(1), nil
	}

	return driver.RowsAffected(1), nil
}

func (s *mockSchedStmt) Query(args []driver.Value) (driver.Rows, error) {
	q := strings.ToLower(s.query)
	state := s.conn.state

	if state == "query_error" {
		return nil, errors.New("simulated query error")
	}

	// 1. SELECT schedules
	if strings.Contains(q, "from schedules") && strings.Contains(q, "where schedule_id = $1") {
		if strings.Contains(q, "review_state, reject_reason") {
			if state == "sched_not_found" {
				return &mockSchedRows{columns: []string{"review_state", "reject_reason"}, rows: nil}, nil
			}
			return &mockSchedRows{
				columns: []string{"review_state", "reject_reason"},
				rows:    [][]driver.Value{{"APPROVED", nil}},
			}, nil
		}

		if strings.Contains(q, "select state") {
			if state == "sched_not_found" {
				return &mockSchedRows{columns: []string{"state"}, rows: nil}, nil
			}
			return &mockSchedRows{
				columns: []string{"state"},
				rows:    [][]driver.Value{{"STAGED"}},
			}, nil
		}

		if state == "sched_not_found" {
			return &mockSchedRows{
				columns: []string{
					"schedule_id", "gateway_id", "network_id", "schedule_version", "schedule_generation",
					"channel_id", "profile_id", "superframe_ms", "created_at", "expires_at",
				},
				rows: nil,
			}, nil
		}

		now := time.Now().UTC()
		return &mockSchedRows{
			columns: []string{
				"schedule_id", "gateway_id", "network_id", "schedule_version", "schedule_generation",
				"channel_id", "profile_id", "superframe_ms", "created_at", "expires_at",
			},
			rows: [][]driver.Value{
				{
					"100", "gw01", int64(1), int64(1), int64(1),
					"CH00", scheduler.ProfileV2VN920Static15N, 9000, now, now.Add(24 * time.Hour),
				},
			},
		}, nil
	}

	// 2. SELECT schedule_slots
	if strings.Contains(q, "from schedule_slots") {
		return &mockSchedRows{
			columns: []string{"slot_id", "node_id", "offset_ms", "duration_ms"},
			rows: [][]driver.Value{
				{1, 1, 50, 500},
				{2, 2, 650, 500},
			},
		}, nil
	}

	// 3. SELECT active_gateway_schedules
	if strings.Contains(q, "from active_gateway_schedules") {
		if state == "no_active" {
			return &mockSchedRows{
				columns: []string{
					"gateway_id", "schedule_id", "schedule_version", "schedule_generation",
					"channel_id", "activated_at", "superframe_seq",
				},
				rows: nil,
			}, nil
		}
		now := time.Now().UTC()
		return &mockSchedRows{
			columns: []string{
				"gateway_id", "schedule_id", "schedule_version", "schedule_generation",
				"channel_id", "activated_at", "superframe_seq",
			},
			rows: [][]driver.Value{
				{"gw01", "100", int64(1), int64(1), "CH00", now, int64(42)},
			},
		}, nil
	}

	// 4. SELECT schedule_migration_transactions
	if strings.Contains(q, "from schedule_migration_transactions") {
		if strings.Contains(q, "select decision_type") {
			if state == "tx_not_found" {
				return &mockSchedRows{columns: []string{"decision_type"}, rows: nil}, nil
			}
			if state == "decision_already_recorded" {
				return &mockSchedRows{
					columns: []string{"decision_type"},
					rows:    [][]driver.Value{{int16(1)}},
				}, nil
			}
			return &mockSchedRows{
				columns: []string{"decision_type"},
				rows:    [][]driver.Value{{nil}},
			}, nil
		}

		if state == "tx_not_found" {
			return &mockSchedRows{
				columns: []string{
					"transaction_id", "gateway_id", "schedule_id", "schedule_generation",
					"k_target", "state", "state_reason", "prepare_digest", "prepare_frame",
					"decision_type", "decision_frame", "affected_nodes", "created_at",
					"updated_at", "expires_at",
				},
				rows: nil,
			}, nil
		}

		now := time.Now().UTC()
		prepDigest := make([]byte, 32)
		prepFrame := make([]byte, 80)
		return &mockSchedRows{
			columns: []string{
				"transaction_id", "gateway_id", "schedule_id", "schedule_generation",
				"k_target", "state", "state_reason", "prepare_digest", "prepare_frame",
				"decision_type", "decision_frame", "affected_nodes", "created_at",
				"updated_at", "expires_at",
			},
			rows: [][]driver.Value{
				{
					"tx-01", "gw01", "100", int64(1),
					int64(10), "PREPARED", "staged", prepDigest, prepFrame,
					nil, nil, "{1,2}", now, now, now.Add(24 * time.Hour),
				},
			},
		}, nil
	}

	return nil, fmt.Errorf("unhandled query in mockSchedStmt: %s", s.query)
}

type mockSchedRows struct {
	columns []string
	rows    [][]driver.Value
	idx     int
}

func (r *mockSchedRows) Columns() []string {
	return r.columns
}

func (r *mockSchedRows) Close() error {
	return nil
}

func (r *mockSchedRows) Next(dest []driver.Value) error {
	if r.idx >= len(r.rows) {
		return io.EOF
	}
	for i, val := range r.rows[r.idx] {
		dest[i] = val
	}
	r.idx++
	return nil
}

type mockSchedDriver struct{}

func (d *mockSchedDriver) Open(name string) (driver.Conn, error) {
	return &mockSchedConn{state: name}, nil
}

func initSchedMockDB(state string) *sql.DB {
	schedDriverOnce.Do(func() {
		sql.Register("mock_schedule_postgres", &mockSchedDriver{})
	})
	db, err := sql.Open("mock_schedule_postgres", state)
	if err != nil {
		panic(err)
	}
	return db
}

func createTestSchedule() *scheduler.Schedule {
	now := time.Now().UTC()
	return &scheduler.Schedule{
		SchemaVersion:          scheduler.DefaultSchemaVersion,
		RequestID:              "550e8400-e29b-41d4-a716-446655440000",
		GatewayID:              "gw01",
		ScheduleID:             "100",
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		CreatedAt:              now,
		ExpiresAt:              now.Add(24 * time.Hour),
		ProfileID:              scheduler.ProfileV2VN920Static15N,
		SuperframeMs:           9000,
		MinAnnounceSuperframes: 3,
		ChannelID:              "CH00",
		NetworkID:              1,
		Slots: []scheduler.SlotConfig{
			{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
			{NodeID: 2, SlotID: 2, OffsetMs: 650, DurationMs: 500},
		},
		AffectedNodeSet: []uint8{1, 2},
	}
}

func TestPostgresScheduleStorage_SaveSchedule_Table(t *testing.T) {
	tests := []struct {
		name    string
		state   string
		sched   *scheduler.Schedule
		wantErr bool
	}{
		{
			name:    "success save schedule",
			state:   "default",
			sched:   createTestSchedule(),
			wantErr: false,
		},
		{
			name:    "nil schedule returns error",
			state:   "default",
			sched:   nil,
			wantErr: true,
		},
		{
			name:  "invalid schedule returns validation error",
			state: "default",
			sched: func() *scheduler.Schedule {
				s := createTestSchedule()
				s.GatewayID = "invalid@gateway!id"
				return s
			}(),
			wantErr: true,
		},
		{
			name:    "database error propagates",
			state:   "exec_error",
			sched:   createTestSchedule(),
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			db := initSchedMockDB(tt.state)
			repo := storage.NewPostgresScheduleStorage(db)
			err := repo.SaveSchedule(context.Background(), tt.sched)
			if (err != nil) != tt.wantErr {
				t.Fatalf("SaveSchedule() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestPostgresScheduleStorage_GetSchedule(t *testing.T) {
	t.Run("found schedule with slots", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		sched, err := repo.GetSchedule(context.Background(), "100")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if sched == nil {
			t.Fatal("expected non-nil schedule")
		}
		if sched.ScheduleID != "100" || sched.GatewayID != "gw01" {
			t.Errorf("unexpected schedule fields: %+v", sched)
		}
		if len(sched.Slots) != 2 {
			t.Fatalf("expected 2 slots, got %d", len(sched.Slots))
		}
		if len(sched.AffectedNodeSet) != 2 {
			t.Errorf("expected 2 affected nodes, got %d", len(sched.AffectedNodeSet))
		}
	})

	t.Run("schedule not found", func(t *testing.T) {
		db := initSchedMockDB("sched_not_found")
		repo := storage.NewPostgresScheduleStorage(db)
		sched, err := repo.GetSchedule(context.Background(), "999")
		if !errors.Is(err, scheduler.ErrScheduleNotFound) {
			t.Fatalf("expected ErrScheduleNotFound, got: %v", err)
		}
		if sched != nil {
			t.Fatal("expected nil schedule on not found")
		}
	})
}

func TestPostgresScheduleStorage_ActiveSchedule(t *testing.T) {
	t.Run("found active schedule", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		act, err := repo.GetActiveScheduleByGateway(context.Background(), "gw01")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if act == nil {
			t.Fatal("expected non-nil active schedule")
		}
		if act.GatewayID != "gw01" || act.ScheduleID != "100" || act.SuperframeSeq != 42 {
			t.Errorf("unexpected active schedule: %+v", act)
		}
	})

	t.Run("no active schedule returns nil", func(t *testing.T) {
		db := initSchedMockDB("no_active")
		repo := storage.NewPostgresScheduleStorage(db)
		act, err := repo.GetActiveScheduleByGateway(context.Background(), "gw01")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if act != nil {
			t.Errorf("expected nil active schedule, got: %+v", act)
		}
	})

	t.Run("set active schedule success", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		act := &scheduler.ActiveGatewaySchedule{
			GatewayID:          "gw01",
			ScheduleID:         "100",
			ScheduleVersion:    1,
			ScheduleGeneration: 1,
			ChannelID:          "CH00",
			ActivatedAt:        time.Now().UTC(),
			SuperframeSeq:      42,
		}
		if err := repo.SetActiveSchedule(context.Background(), act); err != nil {
			t.Fatalf("unexpected error setting active schedule: %v", err)
		}
	})

	t.Run("set active nil returns error", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		if err := repo.SetActiveSchedule(context.Background(), nil); !errors.Is(err, storage.ErrNilActiveSchedule) {
			t.Fatalf("expected ErrNilActiveSchedule, got: %v", err)
		}
	})
}

func TestPostgresScheduleStorage_Transactions(t *testing.T) {
	now := time.Now().UTC()
	tx := &scheduler.MigrationTransaction{
		TransactionID:      "tx-01",
		GatewayID:          "gw01",
		ScheduleID:         "100",
		ScheduleGeneration: 1,
		KTarget:            10,
		State:              scheduler.StatePrepared,
		StateReason:        "staged",
		PrepareDigest:      [32]byte{0xAA},
		PrepareFrame:       [scheduler.BytesDownSchedPrepare]byte{0xBB},
		AffectedNodes:      []uint8{1, 2},
		CreatedAt:          now,
		UpdatedAt:          now,
		ExpiresAt:          now.Add(24 * time.Hour),
	}

	t.Run("create transaction success", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		if err := repo.CreateTransaction(context.Background(), tx); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("create transaction nil error", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		if err := repo.CreateTransaction(context.Background(), nil); !errors.Is(err, storage.ErrNilTransaction) {
			t.Fatalf("expected ErrNilTransaction, got: %v", err)
		}
	})

	t.Run("get transaction success", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		got, err := repo.GetTransaction(context.Background(), "tx-01")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if got.TransactionID != "tx-01" || got.GatewayID != "gw01" || got.State != "PREPARED" {
			t.Errorf("unexpected transaction: %+v", got)
		}
		if len(got.AffectedNodes) != 2 || got.AffectedNodes[0] != 1 || got.AffectedNodes[1] != 2 {
			t.Errorf("unexpected affected nodes: %v", got.AffectedNodes)
		}
	})

	t.Run("get transaction not found", func(t *testing.T) {
		db := initSchedMockDB("tx_not_found")
		repo := storage.NewPostgresScheduleStorage(db)
		got, err := repo.GetTransaction(context.Background(), "tx-missing")
		if !errors.Is(err, scheduler.ErrTransactionNotFound) {
			t.Fatalf("expected ErrTransactionNotFound, got: %v", err)
		}
		if got != nil {
			t.Fatal("expected nil transaction")
		}
	})

	t.Run("update transaction state success", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		if err := repo.UpdateTransactionState(context.Background(), "tx-01", scheduler.StateStaged, "staged acked"); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("update transaction state not found", func(t *testing.T) {
		db := initSchedMockDB("tx_not_found")
		repo := storage.NewPostgresScheduleStorage(db)
		err := repo.UpdateTransactionState(context.Background(), "tx-missing", scheduler.StateStaged, "staged acked")
		if !errors.Is(err, scheduler.ErrTransactionNotFound) {
			t.Fatalf("expected ErrTransactionNotFound, got: %v", err)
		}
	})

	t.Run("record decision success", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		decFrame := [scheduler.BytesDownSchedDecision]byte{0xCC}
		if err := repo.RecordDecision(context.Background(), "tx-01", scheduler.DecisionCommit, decFrame); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	})

	t.Run("record decision already recorded", func(t *testing.T) {
		db := initSchedMockDB("decision_already_recorded")
		repo := storage.NewPostgresScheduleStorage(db)
		decFrame := [scheduler.BytesDownSchedDecision]byte{0xCC}
		err := repo.RecordDecision(context.Background(), "tx-01", scheduler.DecisionCommit, decFrame)
		if err == nil {
			t.Fatal("expected error on already recorded decision, got nil")
		}
	})
}

func TestPostgresScheduleStorage_ReviewAndState(t *testing.T) {
	t.Run("update and get review state", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		if err := repo.UpdateReviewState(context.Background(), "100", "APPROVED", nil); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		st, reason, err := repo.GetReviewState(context.Background(), "100")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if st != "APPROVED" || reason != nil {
			t.Errorf("unexpected review state: %s, reason: %v", st, reason)
		}
	})

	t.Run("update and get schedule state", func(t *testing.T) {
		db := initSchedMockDB("default")
		repo := storage.NewPostgresScheduleStorage(db)
		if err := repo.UpdateScheduleState(context.Background(), "100", "STAGED"); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		st, err := repo.GetScheduleState(context.Background(), "100")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if st != "STAGED" {
			t.Errorf("unexpected state: %s", st)
		}
	})
}
