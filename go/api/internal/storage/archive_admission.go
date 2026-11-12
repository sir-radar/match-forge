package storage

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func managedPath(p Policy, path string) error {
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return err
	}
	absolute, err := filepath.Abs(resolved)
	if err != nil {
		return err
	}
	for _, root := range p.Roots {
		if within(root.Path, absolute) {
			return nil
		}
	}
	return errors.New("archive path is outside explicitly managed storage roots")
}
func AdmitArchive(p Policy, source, destination string, names []string) error {
	peak, err := archivePeak(p, source, names)
	if err != nil {
		return err
	}
	return archiveCapacity(p, destination, peak)
}
func archivePeak(p Policy, source string, names []string) (int64, error) {
	if err := managedPath(p, source); err != nil {
		return 0, err
	}
	root, err := os.OpenRoot(source)
	if err != nil {
		return 0, err
	}
	defer root.Close()
	var logical int64
	for _, name := range names {
		f, err := archiveInput(root, name)
		if err != nil {
			return 0, err
		}
		stat, err := f.Stat()
		f.Close()
		if err != nil {
			return 0, err
		}
		if stat.Size() > (1<<60)-logical {
			return 0, errors.New("archive exceeds representable storage budget")
		}
		logical += stat.Size()
	}
	// Includes a conservative bound for gzip framing, tar padding and the path manifest.
	peak := 2 * (logical + int64(len(names))*4096 + 4096)
	return peak, nil
}

func ReserveArchive(ctx context.Context, pool *pgxpool.Pool, lease Lease, p Policy, source, destination string, names []string) (string, error) {
	peak, err := archivePeak(p, source, names)
	if err != nil {
		return "", err
	}
	return reserveFileBytes(ctx, pool, lease, p, destination, peak)
}
func ReserveRestore(ctx context.Context, pool *pgxpool.Pool, lease Lease, p Policy, source, destination string) (string, error) {
	m, err := readArchiveManifest(source)
	if err != nil {
		return "", err
	}
	return reserveFileBytes(ctx, pool, lease, p, destination, m.LogicalBytes+int64(len(m.Files))*4096+4096)
}
func reserveFileBytes(ctx context.Context, pool *pgxpool.Pool, lease Lease, p Policy, destination string, peak int64) (string, error) {
	parent := filepath.Dir(destination)
	if err := managedPath(p, parent); err != nil {
		return "", err
	}
	capacity, err := DiskCapacity(parent)
	if err != nil {
		return "", err
	}
	id := randomResourceID()
	free := func(context.Context) (int64, error) {
		current, err := DiskCapacity(parent)
		return current.FreeBytes, err
	}
	err = Reserve(ctx, pool, id, lease, "host:"+strconv.FormatUint(capacity.Device, 10), peak, p.ReserveBytes, time.Now().Add(time.Hour), free)
	return id, err
}
func archiveCapacity(p Policy, destination string, peak int64) error {
	if err := managedPath(p, filepath.Dir(destination)); err != nil {
		return err
	}
	capacity, err := DiskCapacity(filepath.Dir(destination))
	if err != nil {
		return err
	}
	return (Reservation{RequestedBytes: peak, FreeBytes: capacity.FreeBytes, ReserveBytes: p.ReserveBytes}).Admit()
}
func RestoreWithPolicy(p Policy, source, destination string) error {
	m, err := readArchiveManifest(source)
	if err != nil {
		return err
	}
	if err = archiveCapacity(p, destination, m.LogicalBytes+int64(len(m.Files))*4096+4096); err != nil {
		return err
	}
	return RestoreArchive(source, destination)
}
