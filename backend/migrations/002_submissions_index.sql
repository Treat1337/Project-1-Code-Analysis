-- 002_submissions_index.sql: Index to optimize filtered & paginated submission history queries.

CREATE INDEX IF NOT EXISTS idx_submissions_user_status_created
    ON submissions(user_id, status, created_at DESC);
