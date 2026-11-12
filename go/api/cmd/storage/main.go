package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"syscall"
	"time"

	"football-forecasting/go/api/internal/storage"
	"github.com/jackc/pgx/v5/pgxpool"
)

type options struct {
	action, policy, source, destination, workID, owner, retain, files string
	estimate                                                          int64
	token                                                             string
	generation                                                        int64
}

func arguments() options {
	var o options
	flag.StringVar(&o.action, "action", "review", "review, pack, read, verify, restore or rehearse-fixtures")
	flag.StringVar(&o.policy, "policy", "", "explicit capacity policy")
	flag.StringVar(&o.source, "source", "", "archive source root")
	flag.StringVar(&o.destination, "destination", "", "new archive/restore destination")
	flag.StringVar(&o.workID, "work-id", "", "existing common work identity")
	flag.StringVar(&o.owner, "owner", "", "existing common work lease owner")
	flag.StringVar(&o.token, "lease-token", "", "original producing claim token")
	flag.Int64Var(&o.generation, "generation", 0, "original producing claim generation")
	flag.Int64Var(&o.estimate, "estimated-bytes", 0, "peak additional storage")
	flag.StringVar(&o.retain, "retain-until", "", "RFC3339 archive retention deadline")
	flag.StringVar(&o.files, "file-list", "", "JSON array of original relative paths for bounded archive batches")
	flag.Parse()
	return o
}
func run(ctx context.Context, o options) error {
	switch o.action {
	case "read":
		return o.read()
	case "verify":
		return storage.VerifyArchive(o.source)
	case "restore", "pack":
		return o.fileAction(ctx)
	case "review", "rehearse-fixtures":
		return o.databaseAction(ctx)
	default:
		return errors.New("unsupported storage action")
	}
}
func (o options) fileAction(ctx context.Context) (result error) {
	if err := o.lease().Validate(); err != nil {
		return err
	}
	policy, err := storage.LoadPolicy(o.policy)
	if err != nil {
		return err
	}
	names, err := o.archiveNames()
	if err != nil {
		return err
	}
	pool, err := pgxpool.New(ctx, os.Getenv("DATABASE_URL"))
	if err != nil {
		return err
	}
	defer pool.Close()
	id, err := o.reserveFiles(ctx, pool, policy, names)
	if err != nil {
		return err
	}
	defer func() {
		cleanup, cancel := context.WithTimeout(context.Background(), time.Minute)
		defer cancel()
		result = errors.Join(result, storage.Release(cleanup, pool, id, o.owner))
	}()
	if o.action == "restore" {
		return storage.RestoreWithPolicy(policy, o.source, o.destination)
	}
	return o.pack(ctx, pool, policy, names)
}
func (o options) reserveFiles(ctx context.Context, pool *pgxpool.Pool, policy storage.Policy, names []string) (string, error) {
	if o.action == "restore" {
		return storage.ReserveRestore(ctx, pool, o.lease(), policy, o.source, o.destination)
	}
	return storage.ReserveArchive(ctx, pool, o.lease(), policy, o.source, o.destination, names)
}
func (o options) pack(ctx context.Context, pool *pgxpool.Pool, policy storage.Policy, names []string) error {
	until, err := time.Parse(time.RFC3339, o.retain)
	if err != nil {
		return err
	}
	if err = storage.AdmitArchive(policy, o.source, o.destination, names); err != nil {
		return err
	}
	manifest, err := storage.Pack(o.source, o.destination, names, until)
	if err != nil {
		return err
	}
	if err = storage.RecordArchive(ctx, pool, o.lease(), o.destination, manifest); err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(manifest)
}
func (o options) databaseAction(ctx context.Context) error {
	if err := o.lease().Validate(); err != nil {
		return err
	}
	policy, err := storage.LoadPolicy(o.policy)
	if err != nil {
		return err
	}
	pool, err := pgxpool.New(ctx, os.Getenv("DATABASE_URL"))
	if err != nil {
		return err
	}
	defer pool.Close()
	if o.action == "rehearse-fixtures" {
		return storage.RehearseFixtures(ctx, pool, os.Getenv("DATABASE_URL"), o.lease(), policy, o.estimate, flag.Args())
	}
	return o.review(ctx, pool, policy)
}
func (o options) review(ctx context.Context, pool *pgxpool.Pool, policy storage.Policy) error {
	if err := o.lease().Validate(); err != nil {
		return errors.New("review publication requires common work ownership")
	}
	repository, err := os.Getwd()
	if err != nil {
		return err
	}
	review, err := storage.Collect(ctx, policy, pool, repository)
	if err != nil {
		return err
	}
	if err = storage.Publish(ctx, pool, o.lease(), review); err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "SUCCEEDED", "dry_run": true, "resources": len(review.Resources), "alerts": review.Alerts, "reclaimed_bytes": 0})
}
func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	if err := run(ctx, arguments()); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func (o options) read() error {
	if len(flag.Args()) != 1 {
		return errors.New("read requires one registered archive member")
	}
	return storage.ReadArchive(o.source, flag.Args()[0], os.Stdout)
}

func (o options) archiveNames() ([]string, error) {
	if o.files == "" {
		return flag.Args(), nil
	}
	if len(flag.Args()) != 0 {
		return nil, errors.New("choose file-list or explicit members")
	}
	f, err := os.Open(o.files)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var names []string
	d := json.NewDecoder(io.LimitReader(f, 64<<20))
	if err = d.Decode(&names); err != nil {
		return nil, err
	}
	if d.Decode(new(any)) != io.EOF {
		return nil, errors.New("file-list requires one JSON array")
	}
	return names, nil
}

func (o options) lease() storage.Lease {
	return storage.Lease{WorkID: o.workID, Owner: o.owner, Token: o.token, Generation: o.generation}
}
