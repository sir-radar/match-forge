package storage

import "errors"

// Lease is the producing attempt's original claim, not a fresh lookup at publication.
type Lease struct {
	WorkID     string
	Owner      string
	Token      string
	Generation int64
}

func (l Lease) Validate() error {
	if l.WorkID == "" || l.Owner == "" || l.Token == "" || l.Generation <= 0 {
		return errors.New("storage operation requires the original common work claim")
	}
	return nil
}
