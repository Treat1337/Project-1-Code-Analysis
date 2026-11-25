package repositories

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"code-analysis-backend/internal/database"
	"code-analysis-backend/internal/models"
)

var ErrSessionNotFound = errors.New("session not found")

type SessionRepository struct {
	db *sql.DB
}

func NewSessionRepository(db *sql.DB) *SessionRepository {
	return &SessionRepository{db: db}
}

// Create stores a new hashed session token in SQLite within a transaction.
func (r *SessionRepository) Create(ctx context.Context, userID int64, tokenHash string, expiresAt time.Time) (models.Session, error) {
	var sess models.Session
	expiresUTC := expiresAt.UTC()

	err := database.WithTx(ctx, r.db, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(
			ctx,
			`INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)`,
			userID, tokenHash, expiresUTC,
		)
		if err != nil {
			return fmt.Errorf("insert session: %w", err)
		}

		id, err := res.LastInsertId()
		if err != nil {
			return fmt.Errorf("get session last insert id: %w", err)
		}

		err = tx.QueryRowContext(
			ctx,
			`SELECT id, user_id, token_hash, expires_at, created_at FROM sessions WHERE id = ?`,
			id,
		).Scan(&sess.ID, &sess.UserID, &sess.TokenHash, &sess.ExpiresAt, &sess.CreatedAt)
		if err != nil {
			return fmt.Errorf("select created session: %w", err)
		}
		return nil
	})

	return sess, err
}

// GetByTokenHash retrieves a session by its hashed token.
func (r *SessionRepository) GetByTokenHash(ctx context.Context, tokenHash string) (models.Session, error) {
	var sess models.Session
	err := r.db.QueryRowContext(
		ctx,
		`SELECT id, user_id, token_hash, expires_at, created_at FROM sessions WHERE token_hash = ?`,
		tokenHash,
	).Scan(&sess.ID, &sess.UserID, &sess.TokenHash, &sess.ExpiresAt, &sess.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return models.Session{}, ErrSessionNotFound
	}
	if err != nil {
		return models.Session{}, fmt.Errorf("query session by token hash: %w", err)
	}
	return sess, nil
}

// DeleteByTokenHash revokes a single session.
func (r *SessionRepository) DeleteByTokenHash(ctx context.Context, tokenHash string) error {
	_, err := r.db.ExecContext(ctx, `DELETE FROM sessions WHERE token_hash = ?`, tokenHash)
	if err != nil {
		return fmt.Errorf("delete session by token hash: %w", err)
	}
	return nil
}

// DeleteExpired removes all expired sessions.
func (r *SessionRepository) DeleteExpired(ctx context.Context, now time.Time) (int64, error) {
	res, err := r.db.ExecContext(ctx, `DELETE FROM sessions WHERE expires_at <= ?`, now.UTC())
	if err != nil {
		return 0, fmt.Errorf("delete expired sessions: %w", err)
	}
	n, _ := res.RowsAffected()
	return n, nil
}
