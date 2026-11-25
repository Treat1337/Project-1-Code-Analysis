package routes

import (
	"net/http"

	"code-analysis-backend/internal/config"
	"code-analysis-backend/internal/handlers"
	"code-analysis-backend/internal/middleware"
	"code-analysis-backend/internal/services"
)

// Dependencies bundles handlers and services needed to build the HTTP router.
type Dependencies struct {
	Config            config.Config
	AuthService       *services.AuthService
	AuthHandler       *handlers.AuthHandler
	HealthHandler     *handlers.HealthHandler
	CodeHandler       *handlers.CodeHandler
	SubmissionHandler *handlers.SubmissionHandler
}

// NewRouter registers all routes and applies global/per-route middleware.
func NewRouter(deps Dependencies) http.Handler {
	mux := http.NewServeMux()

	loginLimiter := middleware.NewRateLimiter(deps.Config.LoginRateLimitMax, deps.Config.LoginRateLimitWindow)
	registerLimiter := middleware.NewRateLimiter(deps.Config.RegisterRateLimitMax, deps.Config.RegisterRateLimitWindow)
	requireAuth := middleware.RequireAuth(deps.AuthService, deps.Config.CookieName)
	csrfProtect := middleware.CSRFProtect(deps.Config.CookieName, deps.Config.CSRFCookieName)

	mux.HandleFunc("GET /healthz", deps.HealthHandler.Healthz)
	mux.HandleFunc("GET /api/auth/csrf", deps.AuthHandler.CSRF)

	mux.Handle("POST /api/auth/register", registerLimiter.Middleware(http.HandlerFunc(deps.AuthHandler.Register)))
	mux.Handle("POST /api/auth/login", loginLimiter.Middleware(http.HandlerFunc(deps.AuthHandler.Login)))
	mux.Handle("POST /api/auth/logout", csrfProtect(http.HandlerFunc(deps.AuthHandler.Logout)))
	mux.Handle("GET /api/auth/me", requireAuth(http.HandlerFunc(deps.AuthHandler.Me)))
	mux.Handle("POST /api/auth/change-password", requireAuth(csrfProtect(http.HandlerFunc(deps.AuthHandler.ChangePassword))))

	if deps.CodeHandler != nil {
		mux.Handle("POST /api/code/run", requireAuth(csrfProtect(http.HandlerFunc(deps.CodeHandler.Run))))
		mux.Handle("POST /api/code/submit", requireAuth(csrfProtect(http.HandlerFunc(deps.CodeHandler.Submit))))
	}
	if deps.SubmissionHandler != nil {
		mux.Handle("GET /api/submissions/stats", requireAuth(http.HandlerFunc(deps.SubmissionHandler.Stats)))
		mux.Handle("GET /api/submissions", requireAuth(http.HandlerFunc(deps.SubmissionHandler.List)))
		mux.Handle("GET /api/submissions/{id}", requireAuth(http.HandlerFunc(deps.SubmissionHandler.GetByID)))
		mux.Handle("DELETE /api/submissions/{id}", requireAuth(csrfProtect(http.HandlerFunc(deps.SubmissionHandler.DeleteByID))))
	}

	// Global middleware chain: Logging -> CORS -> Router
	var handler http.Handler = mux
	handler = middleware.CORS(deps.Config.AllowedOrigins)(handler)
	handler = middleware.Logging(handler)
	return handler
}
