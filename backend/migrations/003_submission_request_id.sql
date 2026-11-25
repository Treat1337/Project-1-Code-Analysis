-- 003_submission_request_id.sql: Optional idempotency request_id per user to prevent duplicate submissions on retries.

ALTER TABLE submissions ADD COLUMN request_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_user_request_id
    ON submissions(user_id, request_id)
    WHERE request_id IS NOT NULL AND request_id != '';
