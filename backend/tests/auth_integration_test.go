package tests

import (
	"bytes"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/cookiejar"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"code-analysis-backend/internal/config"
	"code-analysis-backend/internal/database"
	"code-analysis-backend/internal/handlers"
	"code-analysis-backend/internal/repositories"
	"code-analysis-backend/internal/routes"
	"code-analysis-backend/internal/services"
	"code-analysis-backend/migrations"
)

type testEnv struct {
	db      *sql.DB
	dbPath  string
	cfg     config.Config
	handler http.Handler
	baseURL string
	closed  bool
}

type handlerTransport struct {
	handler http.Handler
}

func (rt handlerTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	rec := httptest.NewRecorder()
	r := req.Clone(req.Context())
	if r.RemoteAddr == "" {
		r.RemoteAddr = "127.0.0.1:54321"
	}
	rt.handler.ServeHTTP(rec, r)
	return rec.Result(), nil
}

func setupTestServer(t *testing.T, dbPath string, loginMax int) *testEnv {
	t.Helper()

	cfg := config.Config{
		ServerHost:              "127.0.0.1",
		ServerPort:              "0",
		AppEnv:                  "test",
		SQLitePath:              dbPath,
		BackupDir:               filepath.Join(filepath.Dir(dbPath), "backups"),
		BackupInterval:          time.Hour,
		CookieName:              "ca_session",
		CSRFCookieName:          "ca_csrf",
		CookieSecure:            false,
		CookieSameSite:          http.SameSiteLaxMode,
		SessionTTL:              24 * time.Hour,
		AllowedOrigins:          []string{"http://127.0.0.1:8000"},
		LoginRateLimitMax:       loginMax,
		LoginRateLimitWindow:    time.Minute,
		RegisterRateLimitMax:    20,
		RegisterRateLimitWindow: time.Minute,
	}

	db, err := database.OpenSQLite(dbPath)
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := database.Migrate(context.Background(), db, migrations.FS); err != nil {
		_ = db.Close()
		t.Fatalf("migrate: %v", err)
	}

	userRepo := repositories.NewUserRepository(db)
	sessionRepo := repositories.NewSessionRepository(db)
	authService := services.NewAuthService(userRepo, sessionRepo, cfg.SessionTTL, cfg.SessionTokenPepper)
	authHandler := handlers.NewAuthHandler(authService, cfg)
	healthHandler := handlers.NewHealthHandler(db)

	router := routes.NewRouter(routes.Dependencies{
		Config:        cfg,
		AuthService:   authService,
		AuthHandler:   authHandler,
		HealthHandler: healthHandler,
	})

	env := &testEnv{
		db:      db,
		dbPath:  dbPath,
		cfg:     cfg,
		handler: router,
		baseURL: "http://127.0.0.1:8080",
	}
	t.Cleanup(env.close)
	return env
}

func (e *testEnv) close() {
	if e.closed {
		return
	}
	e.closed = true
	_ = e.db.Close()
}

func newCookieClient(t *testing.T, handler http.Handler) *http.Client {
	t.Helper()
	jar, err := cookiejar.New(nil)
	if err != nil {
		t.Fatalf("cookiejar: %v", err)
	}
	return &http.Client{
		Jar:       jar,
		Transport: handlerTransport{handler: handler},
	}
}

func postJSON(t *testing.T, client *http.Client, url string, body any, headers map[string]string) (*http.Response, []byte) {
	t.Helper()
	raw, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(raw))
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()
	var buf bytes.Buffer
	_, _ = buf.ReadFrom(resp.Body)
	return resp, buf.Bytes()
}

func TestAuthLifecycleAndSecurity(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "auth_test.db")
	env := setupTestServer(t, dbPath, 10)
	defer env.close()

	client := newCookieClient(t, env.handler)

	// 1. Access /api/auth/me without session -> 401
	resp, err := client.Get(env.baseURL + "/api/auth/me")
	if err != nil {
		t.Fatalf("GET /api/auth/me: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 without session, got %d", resp.StatusCode)
	}

	// 2. Invalid password -> 400
	for _, badPass := range []string{"short1", "onlyletters", "12345678"} {
		r, b := postJSON(t, client, env.baseURL+"/api/auth/register", map[string]string{
			"username": "alice",
			"email":    "alice@example.com",
			"password": badPass,
		}, nil)
		if r.StatusCode != http.StatusBadRequest {
			t.Fatalf("expected 400 for bad password %q, got %d (%s)", badPass, r.StatusCode, string(b))
		}
	}

	// 3. Successful registration -> 201 and no password_hash exposed
	r, b := postJSON(t, client, env.baseURL+"/api/auth/register", map[string]string{
		"username": "alice",
		"email":    "alice@example.com",
		"password": "StrongPass123",
	}, nil)
	if r.StatusCode != http.StatusCreated {
		t.Fatalf("expected 201 on register, got %d (%s)", r.StatusCode, string(b))
	}
	if strings.Contains(string(b), "password_hash") || strings.Contains(string(b), "StrongPass123") {
		t.Fatalf("response leaked sensitive password data: %s", string(b))
	}

	// Verify Argon2id hash in SQLite
	var storedHash string
	if err := env.db.QueryRow(`SELECT password_hash FROM users WHERE username = ?`, "alice").Scan(&storedHash); err != nil {
		t.Fatalf("query stored user: %v", err)
	}
	if !strings.HasPrefix(storedHash, "$argon2id$") {
		t.Fatalf("expected argon2id hash in DB, got %q", storedHash)
	}

	// 4. Duplicate username -> 409 Conflict
	r, b = postJSON(t, client, env.baseURL+"/api/auth/register", map[string]string{
		"username": "alice",
		"email":    "alice2@example.com",
		"password": "StrongPass123",
	}, nil)
	if r.StatusCode != http.StatusConflict {
		t.Fatalf("expected 409 for duplicate username, got %d (%s)", r.StatusCode, string(b))
	}

	// 5. Wrong password -> 401 Unauthorized
	r, _ = postJSON(t, client, env.baseURL+"/api/auth/login", map[string]string{
		"username": "alice",
		"password": "WrongPassword99",
	}, nil)
	if r.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 on wrong password, got %d", r.StatusCode)
	}

	// 6. Correct login -> 200 OK, HttpOnly session cookie, hashed token in DB
	r, b = postJSON(t, client, env.baseURL+"/api/auth/login", map[string]string{
		"username": "alice",
		"password": "StrongPass123",
	}, nil)
	if r.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 on login, got %d (%s)", r.StatusCode, string(b))
	}

	var loginPayload struct {
		User struct {
			ID       int64  `json:"id"`
			Username string `json:"username"`
		} `json:"user"`
		CSRFToken string `json:"csrf_token"`
	}
	if err := json.Unmarshal(b, &loginPayload); err != nil {
		t.Fatalf("unmarshal login response: %v", err)
	}
	if loginPayload.User.Username != "alice" || loginPayload.CSRFToken == "" {
		t.Fatalf("unexpected login payload: %+v", loginPayload)
	}

	var rawSessionToken string
	for _, c := range r.Cookies() {
		if c.Name == env.cfg.CookieName {
			rawSessionToken = c.Value
			if !c.HttpOnly {
				t.Fatalf("expected session cookie to be HttpOnly")
			}
			if c.SameSite != http.SameSiteLaxMode {
				t.Fatalf("expected session cookie SameSite=Lax, got %v", c.SameSite)
			}
		}
	}
	if rawSessionToken == "" {
		t.Fatalf("session cookie %q not set", env.cfg.CookieName)
	}

	// Verify only token_hash is stored in DB, not rawSessionToken
	sum := sha256.Sum256([]byte(rawSessionToken))
	expectedHash := hex.EncodeToString(sum[:])
	var dbTokenHash string
	if err := env.db.QueryRow(`SELECT token_hash FROM sessions WHERE user_id = ?`, loginPayload.User.ID).Scan(&dbTokenHash); err != nil {
		t.Fatalf("query session: %v", err)
	}
	if dbTokenHash != expectedHash || dbTokenHash == rawSessionToken {
		t.Fatalf("expected sha256 token_hash in DB, got %q", dbTokenHash)
	}

	// 7. GET /api/auth/me with valid session -> 200 OK
	meResp, err := client.Get(env.baseURL + "/api/auth/me")
	if err != nil {
		t.Fatalf("GET /api/auth/me: %v", err)
	}
	meResp.Body.Close()
	if meResp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 on /api/auth/me, got %d", meResp.StatusCode)
	}

	// 8. Logout without CSRF token -> 403 Forbidden
	r, _ = postJSON(t, client, env.baseURL+"/api/auth/logout", map[string]string{}, nil)
	if r.StatusCode != http.StatusForbidden {
		t.Fatalf("expected 403 on logout without CSRF token, got %d", r.StatusCode)
	}

	// 9. Logout with valid CSRF token -> 200 OK, session revoked
	r, _ = postJSON(t, client, env.baseURL+"/api/auth/logout", map[string]string{}, map[string]string{
		"X-CSRF-Token": loginPayload.CSRFToken,
	})
	if r.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 on logout with CSRF token, got %d", r.StatusCode)
	}

	meAfterLogout, err := client.Get(env.baseURL + "/api/auth/me")
	if err != nil {
		t.Fatalf("GET /api/auth/me after logout: %v", err)
	}
	meAfterLogout.Body.Close()
	if meAfterLogout.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 after logout, got %d", meAfterLogout.StatusCode)
	}
}

func TestExpiredSessionAndPersistenceAcrossRestart(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "persist_test.db")

	// Start server 1
	env1 := setupTestServer(t, dbPath, 10)
	client := newCookieClient(t, env1.handler)

	r, b := postJSON(t, client, env1.baseURL+"/api/auth/register", map[string]string{
		"username": "bob",
		"email":    "bob@example.com",
		"password": "BobPassword1",
	}, nil)
	if r.StatusCode != http.StatusCreated {
		t.Fatalf("register bob: %d (%s)", r.StatusCode, string(b))
	}

	r, b = postJSON(t, client, env1.baseURL+"/api/auth/login", map[string]string{
		"username": "bob",
		"password": "BobPassword1",
	}, nil)
	if r.StatusCode != http.StatusOK {
		t.Fatalf("login bob: %d (%s)", r.StatusCode, string(b))
	}

	// Verify WAL mode and backup
	var journalMode string
	if err := env1.db.QueryRow(`PRAGMA journal_mode;`).Scan(&journalMode); err != nil {
		t.Fatalf("check journal_mode: %v", err)
	}
	if strings.ToLower(journalMode) != "wal" {
		t.Fatalf("expected WAL journal_mode, got %q", journalMode)
	}

	backupPath, err := database.Backup(context.Background(), env1.db, env1.cfg.BackupDir)
	if err != nil {
		t.Fatalf("backup sqlite: %v", err)
	}
	if backupPath == "" {
		t.Fatalf("expected non-empty backup path")
	}

	// Capture cookies before shutting down server 1
	var sessionCookie *http.Cookie
	for _, c := range r.Cookies() {
		if c.Name == env1.cfg.CookieName {
			sessionCookie = c
		}
	}
	if sessionCookie == nil {
		t.Fatalf("missing session cookie")
	}

	// Shut down server 1 completely
	env1.close()

	// Start server 2 pointing to the exact same SQLite file
	env2 := setupTestServer(t, dbPath, 10)
	defer env2.close()

	client2 := &http.Client{Transport: handlerTransport{handler: env2.handler}}
	req, _ := http.NewRequest(http.MethodGet, env2.baseURL+"/api/auth/me", nil)
	req.AddCookie(sessionCookie)
	resp, err := client2.Do(req)
	if err != nil {
		t.Fatalf("GET /api/auth/me after restart: %v", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 after server restart, got %d", resp.StatusCode)
	}

	// Force session expiration in DB and verify 401
	if _, err := env2.db.Exec(`UPDATE sessions SET expires_at = ?`, time.Now().UTC().Add(-time.Hour)); err != nil {
		t.Fatalf("expire session: %v", err)
	}

	req2, _ := http.NewRequest(http.MethodGet, env2.baseURL+"/api/auth/me", nil)
	req2.AddCookie(sessionCookie)
	resp2, err := client2.Do(req2)
	if err != nil {
		t.Fatalf("GET /api/auth/me expired: %v", err)
	}
	resp2.Body.Close()
	if resp2.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 for expired session, got %d", resp2.StatusCode)
	}
}

func TestBruteForceRateLimit(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "ratelimit_test.db")
	env := setupTestServer(t, dbPath, 3)
	defer env.close()

	client := newCookieClient(t, env.handler)

	for i := 0; i < 3; i++ {
		r, _ := postJSON(t, client, env.baseURL+"/api/auth/login", map[string]string{
			"username": "nobody",
			"password": "WrongPassword1",
		}, nil)
		if r.StatusCode != http.StatusUnauthorized {
			t.Fatalf("attempt %d: expected 401, got %d", i+1, r.StatusCode)
		}
	}

	// 4th attempt should be rate-limited -> 429
	r, _ := postJSON(t, client, env.baseURL+"/api/auth/login", map[string]string{
		"username": "nobody",
		"password": "WrongPassword1",
	}, nil)
	if r.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("expected 429 on 4th login attempt, got %d", r.StatusCode)
	}
}
