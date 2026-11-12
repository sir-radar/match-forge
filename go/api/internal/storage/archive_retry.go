package storage

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"time"
)

func reusableArchive(source, destination string, names []string, retain time.Time) (*ArchiveManifest, error) {
	info, err := os.Lstat(destination)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	if !info.IsDir() {
		return nil, errors.New("archive destination is not an owned archive directory")
	}
	if err = VerifyArchive(destination); err != nil {
		return nil, err
	}
	m, err := readArchiveManifest(destination)
	if err != nil {
		return nil, err
	}
	if err = matchesArchiveRequest(m, source, names, retain); err != nil {
		return nil, err
	}
	return &m, nil
}
func matchesArchivedOriginal(root *os.Root, name string, member ArchiveFile) error {
	if name != member.Path {
		return errors.New("archive request binds different paths")
	}
	f, err := archiveInput(root, name)
	if err != nil {
		return err
	}
	defer f.Close()
	hash := sha256.New()
	n, err := io.Copy(hash, f)
	if err != nil {
		return err
	}
	if n != member.Size || hex.EncodeToString(hash.Sum(nil)) != member.SHA256 {
		return errors.New("current original differs from retained archive")
	}
	return nil
}

func matchesArchiveRequest(m ArchiveManifest, source string, names []string, retain time.Time) error {
	if m.SourceRoot != source || len(m.Files) != len(names) || retain.After(m.RetainUntil) {
		return errors.New("existing archive binds different provenance or retention")
	}
	root, err := os.OpenRoot(source)
	if err != nil {
		return err
	}
	defer root.Close()
	for i, name := range names {
		if err = matchesArchivedOriginal(root, name, m.Files[i]); err != nil {
			return err
		}
	}

	return nil
}
