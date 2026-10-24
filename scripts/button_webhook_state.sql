-- Apply once to a dedicated D1 binding named WHATCHIMP_BUTTON_STATE.
-- Only keyed hashes, counters and expirations: no phone numbers or bearer tokens.
CREATE TABLE IF NOT EXISTS button_webhook_rate (
  state_key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS button_webhook_claims (
  state_key TEXT PRIMARY KEY, expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS button_claim_expiry ON button_webhook_claims(expires_at);
-- Periodic maintenance after retention expires:
-- DELETE FROM button_webhook_claims WHERE expires_at < unixepoch();
-- DELETE FROM button_webhook_rate WHERE expires_at < unixepoch();
