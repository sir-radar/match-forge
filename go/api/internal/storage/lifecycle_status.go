package storage

import (
	"context"
	"encoding/json"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

// LifecycleStatus is the Storage Management view of the five-hour policy.
type LifecycleStatus struct {
	ObservedAt   time.Time          `json:"observed_at"`
	Deployed     bool               `json:"deployed"`
	Policy       *LifecyclePolicy   `json:"policy"`
	Resources    []LifecycleRecord  `json:"resources"`
	Events       []LifecycleEvent   `json:"events"`
	Unregistered []UnregisteredTest `json:"unregistered_test_databases"`
	Reclaimed    int64              `json:"reclaimed_bytes"`
}

type LifecycleEvent struct {
	IdentityKey string          `json:"identity_key"`
	Event       string          `json:"event"`
	Detail      json.RawMessage `json:"detail"`
	RecordedAt  time.Time       `json:"recorded_at"`
}

// UnregisteredTest is a database carrying a test marker without a creation
// record. It is never deleted automatically; the owner must dispose of it.
type UnregisteredTest struct {
	Name  string `json:"name"`
	OID   int64  `json:"oid"`
	Bytes int64  `json:"bytes"`
}

func (m *Manager) LifecycleStatus(ctx context.Context) (LifecycleStatus, error) {
	s := LifecycleStatus{ObservedAt: m.now(), Resources: []LifecycleRecord{}, Events: []LifecycleEvent{}, Unregistered: []UnregisteredTest{}}
	if m.Policy != nil {
		s.Policy = m.Policy.LifecycleCleanup
	}
	if err := m.Pool.QueryRow(ctx, `SELECT to_regclass('football.storage_lifecycle_resources') IS NOT NULL`).Scan(&s.Deployed); err != nil || !s.Deployed {
		return s, err
	}
	rows, err := m.Pool.Query(ctx, `SELECT `+lifecycleColumns+` FROM football.storage_lifecycle_resources
 WHERE state NOT IN ('DELETED','ABSENT') OR checked_at>$1 ORDER BY registered_at DESC LIMIT 200`, s.ObservedAt.Add(-14*24*time.Hour))
	if err != nil {
		return s, err
	}
	if s.Resources, err = pgx.CollectRows(rows, scanLifecycle); err != nil {
		return s, err
	}
	rows, err = m.Pool.Query(ctx, `SELECT identity_key,event,detail,recorded_at FROM football.storage_lifecycle_events
 ORDER BY recorded_at DESC, event_id DESC LIMIT 100`)
	if err != nil {
		return s, err
	}
	s.Events, err = pgx.CollectRows(rows, func(row pgx.CollectableRow) (LifecycleEvent, error) {
		var e LifecycleEvent
		return e, row.Scan(&e.IdentityKey, &e.Event, &e.Detail, &e.RecordedAt)
	})
	if err != nil {
		return s, err
	}
	if err = m.Pool.QueryRow(ctx, `SELECT coalesce(sum(reclaimed_bytes),0)::bigint FROM football.storage_lifecycle_resources
 WHERE state='DELETED'`).Scan(&s.Reclaimed); err != nil {
		return s, err
	}
	s.Unregistered, err = m.unregisteredTests(ctx)
	return s, err
}

func (m *Manager) unregisteredTests(ctx context.Context) ([]UnregisteredTest, error) {
	databases, err := readDatabases(ctx, m.Pool)
	if err != nil {
		return nil, err
	}
	tracked, err := lifecycleRecords(ctx, m.Pool, `backend='postgres' AND state NOT IN ('DELETED','ABSENT')`)
	if err != nil {
		return nil, err
	}
	oids := map[int64]bool{}
	for _, r := range tracked {
		if oid, err := identityOID(r.Identity); err == nil {
			oids[oid] = true
		}
	}
	result := []UnregisteredTest{}
	for _, d := range databases {
		marked := strings.HasPrefix(d.comment, disposableMarkerPrefix) || strings.HasPrefix(d.comment, ownedMarkerPrefix)
		if marked && !oids[d.oid] {
			result = append(result, UnregisteredTest{Name: d.name, OID: d.oid, Bytes: d.size})
		}
	}
	return result, nil
}
