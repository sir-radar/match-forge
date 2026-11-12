package main

import (
	"context"
	"strings"
	"testing"
)

func TestAllocationAndPublicationRequireOriginalWorkClaim(t *testing.T) {
	for _, action := range []string{"pack", "restore", "review", "rehearse-fixtures"} {
		err := run(context.Background(), options{action: action})
		if err == nil || !strings.Contains(err.Error(), "original common work claim") {
			t.Fatalf("%s bypassed lease admission: %v", action, err)
		}
	}
}
