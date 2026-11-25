package database

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// OpenSQLite initializes a SQLite database connection with WAL mode, foreign keys,
// and busy timeout enabled.
func OpenSQLite(dbPath string) (*sql.DB, error) {
	if dbPath != ":memory:" && !strings.HasPrefix(dbPath, "file:") {
		dir := filepath.Dir(dbPath)
		if err := os.MkdirAll(dir, 0o750); err != nil {
			return nil, fmt.Errorf("create sqlite directory %q: %w", dir, err)
		}
	}

	dsn := dbPath
	if dbPath != ":memory:" && !strings.Contains(dbPath, "?") {
		dsn = dbPath + "?_pragma=busy_timeout(5000)&_pragma=foreign_keys(ON)&_pragma=journal_mode(WAL)"
	}

	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}

	// SQLite handles concurrent readers well in WAL mode, while a single writer
	// pool or serialized writes avoid SQLITE_BUSY under heavy load.
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	db.SetConnMaxLifetime(0)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("ping sqlite: %w", err)
	}

	pragmas := []string{
		"PRAGMA foreign_keys = ON;",
		"PRAGMA journal_mode = WAL;",
		"PRAGMA synchronous = NORMAL;",
		"PRAGMA busy_timeout = 5000;",
	}
	for _, p := range pragmas {
		if _, err := db.ExecContext(ctx, p); err != nil {
			_ = db.Close()
			return nil, fmt.Errorf("apply pragma %q: %w", p, err)
		}
	}

	return db, nil
}

// WithTx executes fn inside a database transaction, rolling back on error or panic.
func WithTx(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) (err error) {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}

	defer func() {
		if p := recover(); p != nil {
			_ = tx.Rollback()
			panic(p)
		} else if err != nil {
			_ = tx.Rollback()
		}
	}()

	if err = fn(tx); err != nil {
		return err
	}
	if err = tx.Commit(); err != nil {
		return fmt.Errorf("commit tx: %w", err)
	}
	return nil
}

// Backup creates a consistent online snapshot of the SQLite database using VACUUM INTO.
// Returns the path of the created backup file.
func Backup(ctx context.Context, db *sql.DB, backupDir string) (string, error) {
	if err := os.MkdirAll(backupDir, 0o750); err != nil {
		return "", fmt.Errorf("create backup directory %q: %w", backupDir, err)
	}

	filename := fmt.Sprintf("code_analysis_%s.db", time.Now().UTC().Format("20060102_150405.000"))
	destPath := filepath.Join(backupDir, filename)

	// VACUUM INTO creates a clean, consistent, standalone backup even in WAL mode.
	// Note: SQLite VACUUM INTO accepts a string literal or bound parameter in modern SQLite.
	if _, err := db.ExecContext(ctx, "VACUUM INTO ?", destPath); err != nil {
		return "", fmt.Errorf("vacuum into %q: %w", destPath, err)
	}

	return destPath, nil
}
