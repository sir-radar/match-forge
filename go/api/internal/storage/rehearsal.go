package storage

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type ownedDatabase struct {
	control      *pgx.Conn
	pool         *pgxpool.Pool
	name, owner  string
	oid          uint32
	reservations []string
}

// RehearseFixtures is only for disposable fixtures/replays, never unique acquisition or
// authoritative evidence. Only its new target is released; old targets are never adopted.
func RehearseFixtures(ctx context.Context, pool *pgxpool.Pool, sourceURL string, lease Lease, p Policy, bytes int64, command []string) (result error) {
	if len(command) == 0 {
		return errors.New("rehearsal requires an explicit child command")
	}
	parsed, err := rehearsalURL(sourceURL)
	if err != nil {
		return err
	}
	owned, err := provisionRehearsal(ctx, pool, sourceURL, lease, p, bytes)
	if err != nil {
		return err
	}
	defer func() { result = errors.Join(result, owned.close()) }()
	parsed.Path = "/" + owned.name
	parsed.RawPath = ""
	child := exec.CommandContext(ctx, command[0], command[1:]...)
	child.Env = databaseEnvironment(os.Environ(), parsed.String())
	child.Stdout = os.Stdout
	child.Stderr = os.Stderr
	child.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	child.Cancel = func() error { return syscall.Kill(-child.Process.Pid, syscall.SIGTERM) }
	child.WaitDelay = 5 * time.Second
	defer func() {
		if child.Process != nil {
			_ = syscall.Kill(-child.Process.Pid, syscall.SIGKILL)
		}
	}()
	return child.Run()
}
func rehearsalURL(source string) (*url.URL, error) {
	parsed, err := url.Parse(source)
	if err != nil {
		return nil, err
	}
	if parsed.Scheme != "postgresql" && parsed.Scheme != "postgres" {
		return nil, errors.New("rehearsals require an explicit PostgreSQL URL")
	}
	if parsed.Host == "" || parsed.User == nil {
		return nil, errors.New("explicit database coordinates required")
	}
	query := parsed.Query()
	for _, key := range []string{"dbname", "database", "service", "servicefile", "options", "host", "hostaddr", "port", "user"} {
		if query.Has(key) {
			return nil, errors.New("database routing overrides are not allowed")
		}
	}
	return parsed, nil
}
func provisionRehearsal(ctx context.Context, pool *pgxpool.Pool, source string, lease Lease, p Policy, bytes int64) (*ownedDatabase, error) {
	control, err := pgx.Connect(ctx, source)
	if err != nil {
		return nil, err
	}
	owned := &ownedDatabase{control: control, pool: pool, owner: lease.Owner}
	owned.name = "football_managed_" + strings.ReplaceAll(randomResourceID(), "-", "")
	owned.reservations, err = reserveRehearsal(ctx, pool, control, lease, p, bytes)
	if err != nil {
		control.Close(ctx)
		return nil, err
	}
	if _, err = control.Exec(ctx, "CREATE DATABASE "+pgx.Identifier{owned.name}.Sanitize()+" TEMPLATE template0"); err != nil {
		return nil, errors.Join(err, owned.close())
	}
	if err = owned.register(ctx); err != nil {
		return nil, errors.Join(err, owned.close())
	}
	return owned, nil
}
func (o *ownedDatabase) register(ctx context.Context) error {
	var cluster string
	if err := o.control.QueryRow(ctx, `SELECT oid,(SELECT system_identifier::text FROM pg_control_system()) FROM pg_database WHERE datname=$1`, o.name).Scan(&o.oid, &cluster); err != nil {
		return err
	}
	if _, err := o.control.Exec(ctx, "ALTER DATABASE "+pgx.Identifier{o.name}.Sanitize()+" SET matchforge.database_role='experimental'"); err != nil {
		return err
	}
	_, err := o.pool.Exec(ctx, `UPDATE football.storage_reservations SET resource_identity=jsonb_build_object('database',$2::text,'oid',$3::bigint,'cluster',$4::text) WHERE resource_id=ANY($1::uuid[]) AND owner_name=$5`, o.reservations, o.name, int64(o.oid), cluster, o.owner)
	return err
}
func (o *ownedDatabase) close() error {
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
	defer cancel()
	defer o.control.Close(ctx)
	if o.oid != 0 {
		if err := dropOwned(ctx, o.control, o.name, o.oid); err != nil {
			return err
		}
	}
	// If identity was unavailable after creation, leave the reservation charged for review.
	var exists bool
	if err := o.control.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)`, o.name).Scan(&exists); err != nil {
		return err
	}
	if exists {
		return errors.New("unverified rehearsal identity; recovery review required")
	}
	for _, id := range o.reservations {
		if err := Release(ctx, o.pool, id, o.owner); err != nil {
			return err
		}
	}
	return nil
}
func randomResourceID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:])
}
func reserveRehearsal(ctx context.Context, pool *pgxpool.Pool, control *pgx.Conn, lease Lease, p Policy, bytes int64) ([]string, error) {
	host, err := DiskCapacity(p.Roots[0].Path)
	if err != nil {
		return nil, err
	}
	var cluster string
	if err = control.QueryRow(ctx, `SELECT system_identifier::text FROM pg_control_system()`).Scan(&cluster); err != nil {
		return nil, err
	}
	ids := []string{}
	devices := []struct {
		key  string
		free func(context.Context) (int64, error)
	}{
		{"host:" + strconv.FormatUint(host.Device, 10), func(context.Context) (int64, error) {
			current, err := DiskCapacity(p.Roots[0].Path)
			return current.FreeBytes, err
		}},
		{"postgres-volume:" + cluster, func(ctx context.Context) (int64, error) { return postgresAdmissionFree(ctx, control, p, cluster) }},
	}
	for _, device := range devices {
		id := randomResourceID()
		if err = Reserve(ctx, pool, id, lease, device.key, bytes, p.ReserveBytes, time.Now().Add(time.Hour), device.free); err != nil {
			for _, reserved := range ids {
				err = errors.Join(err, Release(ctx, pool, reserved, lease.Owner))
			}
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, nil
}
func postgresCapacity(ctx context.Context, cluster string) (int64, error) {
	identity, err := exec.CommandContext(ctx, "docker", "compose", "exec", "-T", "postgres", "psql", "-U", os.Getenv("POSTGRES_USER"), "-d", "postgres", "-tAc", "SELECT system_identifier::text FROM pg_control_system()").Output()
	if err != nil {
		return 0, err
	}
	if strings.TrimSpace(string(identity)) != cluster {
		return 0, errors.New("PostgreSQL volume does not belong to target cluster")
	}
	output, err := exec.CommandContext(ctx, "docker", "compose", "exec", "-T", "postgres", "df", "-Pk", "/var/lib/postgresql").Output()
	if err != nil {
		return 0, err
	}
	lines := strings.Split(strings.TrimSpace(string(output)), "\n")
	fields := strings.Fields(lines[len(lines)-1])
	if len(fields) < 6 {
		return 0, errors.New("PostgreSQL volume capacity unavailable")
	}
	available, err := strconv.ParseInt(fields[3], 10, 64)
	if err != nil {
		return 0, err
	}
	return available * 1024, nil
}
func databaseEnvironment(env []string, url string) []string {
	result := []string{}
	routing := regexp.MustCompile(`^(PG[^=]*|DATABASE_URL|FOOTBALL_DATABASE_URL)=`)
	for _, item := range env {
		if !routing.MatchString(item) {
			result = append(result, item)
		}
	}
	return append(result, "DATABASE_URL="+url, "FOOTBALL_DATABASE_URL="+url)
}
func dropOwned(ctx context.Context, control *pgx.Conn, name string, oid uint32) error {
	if !regexp.MustCompile(`^football_managed_[0-9a-f]{32}$`).MatchString(name) {
		return errors.New("unsafe rehearsal target")
	}
	var current uint32
	var operating bool
	if err := control.QueryRow(ctx, `SELECT oid,datname=current_database() FROM pg_database WHERE datname=$1`, name).Scan(&current, &operating); err != nil {
		return err
	}
	if operating || current != oid {
		return errors.New("rehearsal identity changed; teardown blocked")
	}
	_, err := control.Exec(ctx, "DROP DATABASE "+pgx.Identifier{name}.Sanitize()+" WITH (FORCE)")
	return err
}

func postgresAdmissionFree(ctx context.Context, control *pgx.Conn, p Policy, cluster string) (int64, error) {
	physical, err := postgresCapacity(ctx, cluster)
	if err != nil {
		return 0, err
	}
	var allocated int64
	if err = control.QueryRow(ctx, `SELECT sum(pg_database_size(oid)) FROM pg_database`).Scan(&allocated); err != nil {
		return 0, err
	}
	if allocated >= p.DatabaseCriticalBytes {
		return 0, nil
	}
	if physical <= p.ReserveBytes {
		return physical, nil
	}
	remaining := p.DatabaseCriticalBytes - allocated
	if remaining < physical-p.ReserveBytes {
		return remaining + p.ReserveBytes, nil
	}
	return physical, nil
}
