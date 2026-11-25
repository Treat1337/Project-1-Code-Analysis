package config

import (
	"bufio"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds all runtime configuration loaded from environment variables.
type Config struct {
	ServerHost            string
	ServerPort            string
	AppEnv                string
	SQLitePath            string
	BackupDir             string
	BackupInterval        time.Duration
	CookieName            string
	CSRFCookieName        string
	CookieSecure          bool
	CookieSameSite        http.SameSite
	SessionTTL            time.Duration
	SessionTokenPepper    string
	AllowedOrigins        []string
	LoginRateLimitMax       int
	LoginRateLimitWindow    time.Duration
	RegisterRateLimitMax    int
	RegisterRateLimitWindow time.Duration
	CompilerServiceURL      string
	CompilerRunPath         string
	CompilerTimeout         time.Duration
	AIServiceURL            string
	AIPredictPath           string
	AITimeout               time.Duration
	MaxCodeBytes            int
	PipelineVersion         string
}

// Load reads environment variables (optionally loading a .env file if present)
// and returns a validated Config with safe defaults.
func Load(envFile string) Config {
	if envFile != "" {
		loadDotEnv(envFile)
	}

	appEnv := getEnv("APP_ENV", "development")
	cookieSecure := getEnvBool("COOKIE_SECURE", appEnv == "production")

	return Config{
		ServerHost:              getEnv("SERVER_HOST", "127.0.0.1"),
		ServerPort:              getEnv("SERVER_PORT", "8080"),
		AppEnv:                  appEnv,
		SQLitePath:              getEnv("SQLITE_PATH", "./data/code_analysis.db"),
		BackupDir:               getEnv("BACKUP_DIR", "./backups"),
		BackupInterval:          time.Duration(getEnvInt("BACKUP_INTERVAL_MINUTES", 60)) * time.Minute,
		CookieName:              getEnv("COOKIE_NAME", "ca_session"),
		CSRFCookieName:          getEnv("CSRF_COOKIE_NAME", "ca_csrf"),
		CookieSecure:            cookieSecure,
		CookieSameSite:          parseSameSite(getEnv("COOKIE_SAMESITE", "Lax")),
		SessionTTL:              time.Duration(getEnvInt("SESSION_TTL_HOURS", 24)) * time.Hour,
		SessionTokenPepper:      os.Getenv("SESSION_TOKEN_PEPPER"),
		AllowedOrigins:          parseCSV(getEnv("ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000")),
		LoginRateLimitMax:       getEnvInt("LOGIN_RATE_LIMIT_MAX", 5),
		LoginRateLimitWindow:    time.Duration(getEnvInt("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)) * time.Second,
		RegisterRateLimitMax:    getEnvInt("REGISTER_RATE_LIMIT_MAX", 10),
		RegisterRateLimitWindow: time.Duration(getEnvInt("REGISTER_RATE_LIMIT_WINDOW_SECONDS", 60)) * time.Second,
		CompilerServiceURL:      strings.TrimRight(getEnv("COMPILER_SERVICE_URL", "http://127.0.0.1:8000"), "/"),
		CompilerRunPath:         getEnv("COMPILER_RUN_PATH", "/api/run"),
		CompilerTimeout:         time.Duration(getEnvInt("COMPILER_TIMEOUT_SECONDS", 15)) * time.Second,
		AIServiceURL:            strings.TrimRight(getEnv("AI_SERVICE_URL", "http://127.0.0.1:8001"), "/"),
		AIPredictPath:           getEnv("AI_PREDICT_PATH", "/api/models/predict"),
		AITimeout:               time.Duration(getEnvInt("AI_TIMEOUT_SECONDS", 20)) * time.Second,
		MaxCodeBytes:            getEnvInt("MAX_CODE_BYTES", 65536),
		PipelineVersion:         getEnv("PIPELINE_VERSION", "v1"),
	}
}

// Addr returns the host:port listen address.
func (c Config) Addr() string {
	return c.ServerHost + ":" + c.ServerPort
}

func loadDotEnv(path string) {
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key := strings.TrimSpace(k)
		val := strings.TrimSpace(v)
		val = strings.Trim(val, `"'`)
		if key != "" && os.Getenv(key) == "" {
			_ = os.Setenv(key, val)
		}
	}
}

func getEnv(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil || n <= 0 {
		return fallback
	}
	return n
}

func getEnvBool(key string, fallback bool) bool {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return fallback
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return fallback
	}
	return b
}

func parseSameSite(raw string) http.SameSite {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "strict":
		return http.SameSiteStrictMode
	case "none":
		return http.SameSiteNoneMode
	default:
		return http.SameSiteLaxMode
	}
}

func parseCSV(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		trimmed := strings.TrimSpace(p)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}
