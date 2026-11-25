package middleware

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"net/http"
)

// CSRFProtect enforces double-submit cookie CSRF validation on state-changing requests
// that carry an active session cookie.
func CSRFProtect(sessionCookieName, csrfCookieName string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if isSafeMethod(r.Method) {
				next.ServeHTTP(w, r)
				return
			}

			// Only enforce when a session cookie is present on the request.
			sessionCookie, err := r.Cookie(sessionCookieName)
			if err != nil || sessionCookie.Value == "" {
				next.ServeHTTP(w, r)
				return
			}

			csrfCookie, err := r.Cookie(csrfCookieName)
			if err != nil || csrfCookie.Value == "" {
				writeJSONError(w, http.StatusForbidden, "missing CSRF token cookie")
				return
			}

			headerToken := r.Header.Get("X-CSRF-Token")
			if headerToken == "" || subtle.ConstantTimeCompare([]byte(headerToken), []byte(csrfCookie.Value)) != 1 {
				writeJSONError(w, http.StatusForbidden, "invalid CSRF token")
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

// GenerateCSRFToken creates a cryptographically random CSRF token.
func GenerateCSRFToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}

func isSafeMethod(method string) bool {
	switch method {
	case http.MethodGet, http.MethodHead, http.MethodOptions, http.MethodTrace:
		return true
	default:
		return false
	}
}
