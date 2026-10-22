package app

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
)

type comparisonReport struct {
	PredictionID string   `json:"prediction_id"`
	ForecastID   string   `json:"forecast_id"`
	Probability  *float64 `json:"matchforge_probability"`
	Agreement    string   `json:"agreement"`
}

func decodeReadReport(payload []byte, digest *string, target any) error {
	if payload == nil || digest == nil {
		return errProductUnavailable
	}
	actual := sha256.Sum256(payload)
	if hex.EncodeToString(actual[:]) != *digest {
		return errors.New("stored read report checksum mismatch")
	}
	return json.Unmarshal(payload, target)
}

func attachComparison(item *ExternalPrediction, forecastID *string, payload []byte, digest *string) error {
	item.Agreement = "UNABLE_TO_EVALUATE"
	if forecastID == nil || payload == nil || digest == nil {
		return nil
	}
	var report comparisonReport
	if err := decodeReadReport(payload, digest, &report); err != nil {
		return err
	}
	if report.PredictionID != item.ID || report.ForecastID != *forecastID {
		return errors.New("stored comparison identity mismatch")
	}
	item.MatchForgeProbability, item.Agreement = report.Probability, report.Agreement
	return nil
}
