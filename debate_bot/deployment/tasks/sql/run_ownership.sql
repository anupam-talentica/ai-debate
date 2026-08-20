-- Manual/inspection copy of the table ownership.init_pool() already creates
-- automatically (CREATE TABLE IF NOT EXISTS) at server startup. Useful for
-- poking at the schema by hand during the T3 test procedure.
CREATE TABLE IF NOT EXISTS run_ownership (
    run_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'running'
);
