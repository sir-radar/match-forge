-- +goose Up

CREATE TABLE football.provider_request_budgets (
    provider_code text NOT NULL CHECK (provider_code <> ''),
    window_date date NOT NULL,
    requests_used integer NOT NULL DEFAULT 0 CHECK (requests_used >= 0),
    remaining_requests integer CHECK (remaining_requests >= 0),
    exhausted boolean NOT NULL DEFAULT false,
    last_error text,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (provider_code, window_date),
    CHECK (NOT exhausted OR remaining_requests IS NULL OR remaining_requests = 0)
);

-- +goose Down

DROP TABLE football.provider_request_budgets;
