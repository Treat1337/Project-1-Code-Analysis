package middleware

import (
	"context"
	"encoding/json"
	"net/http"

	"code-analysis-backend/internal/models"
	"code-analysis-backend/internal/services"
)

type contextKey string

const userContextKey contextKey = "authenticated_user"

// UserFromContext retrieves the authenticated user attached by RequireAuth.
func UserFromContext(ctx context.Context) (models.UserResponse, bool) {
	u, ok := ctx.Value(userContextKey).(models.UserResponse)
	return u, ok
}

// RequireAuth validates the session cookie and attaches the user to the request context.
func RequireAuth(authService *services.AuthService, cookieName string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			cookie, err := r.Cookie(cookieName)
			if err != nil || cookie.Value == "" {
				writeJSONError(w, http.StatusUnauthorized, "authentication required")
				return
			}

			user, err := authService.Authenticate(r.Context(), cookie.Value)
			if err != nil {
				writeJSONError(w, http.StatusUnauthorized, "invalid or expired session")
				return
			}

			ctx := context.WithValue(r.Context(), userContextKey, user)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func writeJSONError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}
