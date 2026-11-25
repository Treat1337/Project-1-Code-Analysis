package repositories

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"

	"code-analysis-backend/internal/database"
	"code-analysis-backend/internal/models"
)

var (
	ErrUserNotFound  = errors.New("user not found")
	ErrUsernameTaken = errors.New("username already exists")
)

type UserRepository struct {
	db *sql.DB
}

func NewUserRepository(db *sql.DB) *UserRepository {
	return &UserRepository{db: db}
}

// Create inserts a new user inside a transaction and returns the created record.
func (r *UserRepository) Create(ctx context.Context, username string, email *string, passwordHash string) (models.User, error) {
	var created models.User

	err := database.WithTx(ctx, r.db, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(
			ctx,
			`INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)`,
			username, email, passwordHash,
		)
		if err != nil {
			if isUniqueConstraintError(err) {
				return ErrUsernameTaken
			}
			return fmt.Errorf("insert user: %w", err)
		}

		id, err := res.LastInsertId()
		if err != nil {
			return fmt.Errorf("get user last insert id: %w", err)
		}

		var emailVal sql.NullString
		err = tx.QueryRowContext(
			ctx,
			`SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?`,
			id,
		).Scan(&created.ID, &created.Username, &emailVal, &created.PasswordHash, &created.CreatedAt)
		if err != nil {
			return fmt.Errorf("select created user: %w", err)
		}
		if emailVal.Valid {
			e := emailVal.String
			created.Email = &e
		}
		return nil
	})

	return created, err
}

// GetByUsernameOrEmail fetches a user by username or email.
func (r *UserRepository) GetByUsernameOrEmail(ctx context.Context, identifier string) (models.User, error) {
	var user models.User
	var emailVal sql.NullString

	err := r.db.QueryRowContext(
		ctx,
		`SELECT id, username, email, password_hash, created_at FROM users WHERE username = ? OR email = ?`,
		identifier, identifier,
	).Scan(&user.ID, &user.Username, &emailVal, &user.PasswordHash, &user.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return models.User{}, ErrUserNotFound
	}
	if err != nil {
		return models.User{}, fmt.Errorf("query user by username or email: %w", err)
	}
	if emailVal.Valid {
		e := emailVal.String
		user.Email = &e
	}
	return user, nil
}

// UpdatePasswordHash updates a user's password hash inside a transaction.
func (r *UserRepository) UpdatePasswordHash(ctx context.Context, userID int64, newHash string) error {
	return database.WithTx(ctx, r.db, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(ctx, `UPDATE users SET password_hash = ? WHERE id = ?`, newHash, userID)
		if err != nil {
			return fmt.Errorf("update password hash: %w", err)
		}
		affected, _ := res.RowsAffected()
		if affected == 0 {
			return ErrUserNotFound
		}
		return nil
	})
}

// GetByUsername fetches a user by exact username.
func (r *UserRepository) GetByUsername(ctx context.Context, username string) (models.User, error) {
	var user models.User
	var emailVal sql.NullString

	err := r.db.QueryRowContext(
		ctx,
		`SELECT id, username, email, password_hash, created_at FROM users WHERE username = ?`,
		username,
	).Scan(&user.ID, &user.Username, &emailVal, &user.PasswordHash, &user.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return models.User{}, ErrUserNotFound
	}
	if err != nil {
		return models.User{}, fmt.Errorf("query user by username: %w", err)
	}
	if emailVal.Valid {
		e := emailVal.String
		user.Email = &e
	}
	return user, nil
}

// GetByID fetches a user by primary key ID.
func (r *UserRepository) GetByID(ctx context.Context, id int64) (models.User, error) {
	var user models.User
	var emailVal sql.NullString

	err := r.db.QueryRowContext(
		ctx,
		`SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?`,
		id,
	).Scan(&user.ID, &user.Username, &emailVal, &user.PasswordHash, &user.CreatedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return models.User{}, ErrUserNotFound
	}
	if err != nil {
		return models.User{}, fmt.Errorf("query user by id: %w", err)
	}
	if emailVal.Valid {
		e := emailVal.String
		user.Email = &e
	}
	return user, nil
}

func isUniqueConstraintError(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "unique constraint failed") || strings.Contains(msg, "constraint failed: unique")
}
