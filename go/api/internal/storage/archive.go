package storage

import (
	"archive/tar"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"syscall"
	"time"
)

type ArchiveFile struct {
	Path     string    `json:"path"`
	SHA256   string    `json:"sha256"`
	Size     int64     `json:"size"`
	Mode     uint32    `json:"mode"`
	Modified time.Time `json:"modified"`
}
type ArchiveManifest struct {
	Version       int           `json:"version"`
	SourceRoot    string        `json:"source_root"`
	Files         []ArchiveFile `json:"files"`
	PayloadSHA256 string        `json:"payload_sha256"`
	LogicalBytes  int64         `json:"logical_bytes"`
	UniqueBytes   int64         `json:"unique_bytes"`
	PackedBytes   int64         `json:"packed_bytes"`
	RetainUntil   time.Time     `json:"retain_until"`
	Protected     bool          `json:"protected"`
}

// Pack publishes a new archive, verifies it through the reader, and leaves every original intact.
func Pack(source, destination string, names []string, retain time.Time) (ArchiveManifest, error) {
	m := ArchiveManifest{Version: 1, SourceRoot: source, Files: []ArchiveFile{}, RetainUntil: retain, Protected: true}
	if len(names) == 0 || !retain.After(time.Now()) {
		return m, errors.New("archive needs explicit members and future retention")
	}
	existing, err := reusableArchive(source, destination, names, retain)
	if err != nil {
		return m, err
	}
	if existing != nil {
		return *existing, nil
	}
	return packNewArchive(source, destination, names, retain)
}
func packNewArchive(source, destination string, names []string, retain time.Time) (ArchiveManifest, error) {
	m := ArchiveManifest{Version: 1, SourceRoot: source, Files: []ArchiveFile{}, RetainUntil: retain, Protected: true}
	root, err := os.OpenRoot(source)
	if err != nil {
		return m, err
	}
	defer root.Close()
	staging, err := os.MkdirTemp(filepath.Dir(destination), ".storage-archive-")
	if err != nil {
		return m, err
	}
	defer os.RemoveAll(staging) // Only this invocation's unpublished staging directory.
	file, err := os.OpenFile(filepath.Join(staging, "payload.tar.gz"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return m, err
	}
	gz := gzip.NewWriter(file)
	gz.Header.ModTime = time.Unix(0, 0)
	tarball := tar.NewWriter(gz)
	err = packMembers(root, names, tarball, &m)
	err = errors.Join(err, closeArchive(tarball, gz, file))
	if err != nil {
		return m, err
	}
	if err = finalizeArchive(staging, destination, &m); err != nil {
		return m, err
	}
	return m, nil
}
func finalizeArchive(staging, destination string, m *ArchiveManifest) error {
	var err error
	m.PayloadSHA256, m.PackedBytes, err = hashPath(filepath.Join(staging, "payload.tar.gz"))
	if err != nil {
		return err
	}
	if m.PackedBytes >= m.UniqueBytes {
		return errors.New("compressed archive would not reduce the representation size; originals retained")
	}
	if err = publishArchiveManifest(staging, *m); err != nil {
		return err
	}
	if err = VerifyArchive(staging); err != nil {
		return err
	}
	if err = syncArchiveDirectory(staging); err != nil {
		return err
	}
	return publishArchive(staging, destination)
}

// The manifest commits publication after the payload is durable. Mkdir and Link
// both refuse existing names, including an empty destination created concurrently.
func publishArchive(staging, destination string) error {
	if err := os.Mkdir(destination, 0o700); err != nil {
		return err
	}
	root, err := os.OpenRoot(filepath.Dir(destination))
	if err != nil {
		return err
	}
	defer root.Close()
	source, target := filepath.Base(staging), filepath.Base(destination)
	if err = root.Link(filepath.Join(source, "payload.tar.gz"), filepath.Join(target, "payload.tar.gz")); err != nil {
		return err
	}
	if err = syncArchiveDirectory(destination); err != nil {
		return err
	}
	if err = root.Link(filepath.Join(source, "manifest.json"), filepath.Join(target, "manifest.json")); err != nil {
		return err
	}
	if err = syncArchiveDirectory(destination); err != nil {
		return err
	}
	return syncArchiveDirectory(filepath.Dir(destination))
}

func packMembers(root *os.Root, names []string, writer *tar.Writer, m *ArchiveManifest) error {
	seenPaths := map[string]bool{}
	seenBlobs := map[string]bool{}
	for _, name := range names {
		if seenPaths[name] {
			return errors.New("duplicate archive pathname")
		}
		seenPaths[name] = true
		f, err := archiveInput(root, name)
		if err != nil {
			return err
		}
		record, err := packMember(name, f, writer, seenBlobs)
		f.Close()
		if err != nil {
			return err
		}
		m.Files = append(m.Files, record)
		m.LogicalBytes += record.Size
		if !seenBlobs[record.SHA256] {
			m.UniqueBytes += record.Size
		}
		seenBlobs[record.SHA256] = true
	}
	return nil
}
func archiveInput(root *os.Root, name string) (*os.File, error) {
	if err := SafeRelative(name); err != nil {
		return nil, err
	}
	// Reject symlinks at every component, even those resolving within the root.
	current := name
	for current != "." {
		stat, err := root.Lstat(current)
		if err != nil {
			return nil, err
		}
		if stat.Mode()&os.ModeSymlink != 0 {
			return nil, errors.New("archive source symlink rejected")
		}
		current = filepath.Dir(current)
	}
	f, err := root.Open(name)
	if err != nil {
		return nil, err
	}
	info, err := f.Stat()
	if err != nil {
		f.Close()
		return nil, err
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !info.Mode().IsRegular() || !ok || stat.Uid != uint32(os.Getuid()) {
		f.Close()
		return nil, errors.New("archive source must be an owned regular file")
	}
	return f, nil
}
func packMember(name string, f *os.File, w *tar.Writer, seen map[string]bool) (ArchiveFile, error) {
	before, err := f.Stat()
	if err != nil {
		return ArchiveFile{}, err
	}
	hash := sha256.New()
	if _, err = io.Copy(hash, f); err != nil {
		return ArchiveFile{}, err
	}
	digest := hex.EncodeToString(hash.Sum(nil))
	r := ArchiveFile{name, digest, before.Size(), uint32(before.Mode().Perm()), before.ModTime()}
	if !seen[digest] {
		if err = writeBlob(f, w, digest, before.Size()); err != nil {
			return r, err
		}
	}
	after, err := f.Stat()
	if err != nil {
		return r, err
	}
	if !os.SameFile(before, after) || before.Size() != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		return r, errors.New("source changed while archiving")
	}
	return r, nil
}
func hashPath(path string) (string, int64, error) {
	f, e := os.Open(path)
	if e != nil {
		return "", 0, e
	}
	defer f.Close()
	h := sha256.New()
	n, e := io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil)), n, e
}

func readArchiveManifest(path string) (ArchiveManifest, error) {
	var m ArchiveManifest
	root, err := os.OpenRoot(path)
	if err != nil {
		return m, err
	}
	defer root.Close()
	f, err := archiveInput(root, "manifest.json")
	if err != nil {
		return m, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return m, err
	}
	if info.Size() > 64<<20 {
		return m, errors.New("archive manifest exceeds bounded reader size")
	}
	decoder := json.NewDecoder(io.LimitReader(f, 64<<20))
	decoder.DisallowUnknownFields()
	if err = decoder.Decode(&m); err != nil {
		return m, err
	}
	if decoder.Decode(new(any)) != io.EOF {
		return m, errors.New("archive manifest must contain one JSON object")
	}
	if m.Version != 1 || !m.Protected || len(m.Files) == 0 {
		return m, errors.New("invalid archive manifest")
	}
	return m, nil
}

// ReadArchive serves exact original bytes; callers select registered paths, never tar paths.
func ReadArchive(path, name string, destination io.Writer) error {
	m, err := readArchiveManifest(path)
	if err != nil {
		return err
	}
	for _, member := range m.Files {
		if member.Path == name {
			return readBlob(path, member, destination)
		}
	}
	return errors.New("evidence path is not in archive manifest")
}
func readBlob(path string, member ArchiveFile, destination io.Writer) error {
	root, err := os.OpenRoot(path)
	if err != nil {
		return err
	}
	defer root.Close()
	f, err := archiveInput(root, "payload.tar.gz")
	if err != nil {
		return err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return err
	}
	defer gz.Close()
	reader := tar.NewReader(gz)
	for {
		header, err := reader.Next()
		if err != nil {
			return err
		}
		if header.Name == member.SHA256 {
			return verifyBlob(header, reader, member, destination)
		}
	}
}
func verifyBlob(header *tar.Header, reader io.Reader, member ArchiveFile, destination io.Writer) error {
	if header.Typeflag != tar.TypeReg || header.Size != member.Size {
		return errors.New("archive member length/type mismatch")
	}
	hash := sha256.New()
	n, err := io.Copy(io.MultiWriter(destination, hash), reader)
	if err != nil {
		return err
	}
	if n != member.Size || hex.EncodeToString(hash.Sum(nil)) != member.SHA256 {
		return errors.New("archive evidence checksum mismatch")
	}
	return nil
}
func closeArchive(t *tar.Writer, g *gzip.Writer, f *os.File) error {
	return errors.Join(t.Close(), g.Close(), f.Sync(), f.Close())
}
func writeBlob(f *os.File, w *tar.Writer, digest string, size int64) error {
	if _, err := f.Seek(0, io.SeekStart); err != nil {
		return err
	}
	if err := w.WriteHeader(&tar.Header{Name: digest, Mode: 0o600, Size: size, ModTime: time.Unix(0, 0), Typeflag: tar.TypeReg}); err != nil {
		return err
	}
	second := sha256.New()
	if _, err := io.Copy(io.MultiWriter(w, second), f); err != nil {
		return err
	}
	if hex.EncodeToString(second.Sum(nil)) != digest {
		return errors.New("source changed while archiving")
	}
	return nil
}
func VerifyArchive(path string) error {
	m, err := readArchiveManifest(path)
	if err != nil {
		return err
	}
	expected, err := manifestMembers(m)
	if err != nil {
		return err
	}
	digest, size, err := hashPath(filepath.Join(path, "payload.tar.gz"))
	if err != nil {
		return err
	}
	if digest != m.PayloadSHA256 || size != m.PackedBytes {
		return errors.New("archive payload checksum/length mismatch")
	}
	err = walkArchive(path, func(header *tar.Header, reader io.Reader) error {
		members, ok := expected[header.Name]
		if !ok {
			return errors.New("unexpected or repeated archive blob")
		}
		if err := verifyBlob(header, reader, members[0], io.Discard); err != nil {
			return err
		}
		delete(expected, header.Name)
		return nil
	})
	if err != nil {
		return err
	}
	if len(expected) != 0 {
		return errors.New("archive is missing registered evidence")
	}
	return nil
}
func manifestMembers(m ArchiveManifest) (map[string][]ArchiveFile, error) {
	expected := map[string][]ArchiveFile{}
	paths := map[string]bool{}
	var logical, unique int64
	for _, member := range m.Files {
		if err := validateMember(member, paths); err != nil {
			return nil, err
		}
		paths[member.Path] = true
		previous := expected[member.SHA256]
		if len(previous) == 0 {
			unique += member.Size
		} else if previous[0].Size != member.Size {
			return nil, errors.New("inconsistent blob lengths")
		}
		logical += member.Size
		expected[member.SHA256] = append(previous, member)
	}
	if logical != m.LogicalBytes || unique != m.UniqueBytes {
		return nil, errors.New("archive accounting mismatch")
	}
	return expected, nil
}
func validateMember(member ArchiveFile, paths map[string]bool) error {
	if err := SafeRelative(member.Path); err != nil {
		return err
	}
	if paths[member.Path] || member.Size < 0 || !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(member.SHA256) {
		return errors.New("invalid archive member metadata")
	}
	return nil
}
func walkArchive(path string, visit func(*tar.Header, io.Reader) error) error {
	root, err := os.OpenRoot(path)
	if err != nil {
		return err
	}
	defer root.Close()
	f, err := archiveInput(root, "payload.tar.gz")
	if err != nil {
		return err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return err
	}
	defer gz.Close()
	reader := tar.NewReader(gz)
	for {
		header, err := reader.Next()
		if err == io.EOF {
			return finishGzip(gz)
		}
		if err != nil {
			return err
		}
		if err = visit(header, reader); err != nil {
			return err
		}
	}
}

// RestoreArchive always creates a new destination; it never replaces operating originals.
func RestoreArchive(path, destination string) error {
	if err := VerifyArchive(path); err != nil {
		return err
	}
	m, err := readArchiveManifest(path)
	if err != nil {
		return err
	}
	expected, err := manifestMembers(m)
	if err != nil {
		return err
	}
	if err = os.Mkdir(destination, 0o700); err != nil {
		return err
	}
	root, err := os.OpenRoot(destination)
	if err != nil {
		return err
	}
	defer root.Close()
	err = walkArchive(path, func(header *tar.Header, reader io.Reader) error {
		members, ok := expected[header.Name]
		if !ok {
			return errors.New("archive changed during restore")
		}
		if err := restoreBlob(root, header, reader, members); err != nil {
			return err
		}
		delete(expected, header.Name)
		return nil
	})
	if err != nil {
		return err
	}
	if len(expected) != 0 {
		return errors.New("archive changed during restore: missing registered evidence")
	}
	return nil
}
func restoreBlob(root *os.Root, header *tar.Header, reader io.Reader, members []ArchiveFile) error {
	first := members[0]
	f, err := createRestoreFile(root, first.Path)
	if err != nil {
		return err
	}
	err = verifyBlob(header, reader, first, f)
	err = errors.Join(err, f.Sync(), f.Close())
	if err != nil {
		return err
	}
	if err = root.Chtimes(first.Path, first.Modified, first.Modified); err != nil {
		return err
	}
	for _, member := range members[1:] {
		if err = copyRestored(root, first.Path, member); err != nil {
			return err
		}
	}
	return nil
}
func createRestoreFile(root *os.Root, name string) (*os.File, error) {
	if err := SafeRelative(name); err != nil {
		return nil, err
	}
	if err := root.MkdirAll(filepath.Dir(name), 0o700); err != nil {
		return nil, err
	}
	return root.OpenFile(name, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
}
func copyRestored(root *os.Root, source string, member ArchiveFile) error {
	input, err := root.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	f, err := createRestoreFile(root, member.Path)
	if err != nil {
		return err
	}
	_, err = io.Copy(f, input)
	err = errors.Join(err, f.Sync(), f.Close())
	if err != nil {
		return err
	}
	return root.Chtimes(member.Path, member.Modified, member.Modified)
}
func publishArchiveManifest(path string, m ArchiveManifest) error {
	payload, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.OpenFile(filepath.Join(path, "manifest.json"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	_, err = f.Write(append(payload, '\n'))
	return errors.Join(err, f.Sync(), f.Close())
}

func syncArchiveDirectory(path string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return f.Sync()
}

func finishGzip(reader *gzip.Reader) error {
	n, err := io.Copy(io.Discard, reader)
	if err != nil {
		return err
	}
	if n != 0 {
		return errors.New("unregistered data after archive end")
	}
	return nil
}
