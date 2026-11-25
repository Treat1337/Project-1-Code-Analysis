package middleware

import (
	"net"
	"net/http"
	"strconv"
	"sync"
	"time"
)

type rateBucket struct {
	count   int
	resetAt time.Time
}

// RateLimiter provides in-memory sliding/fixed-window rate limiting per client IP.
type RateLimiter struct {
	mu      sync.Mutex
	buckets map[string]rateBucket
	max     int
	window  time.Duration
	nowFn   func() time.Time
}

func NewRateLimiter(maxRequests int, window time.Duration) *RateLimiter {
	rl := &RateLimiter{
		buckets: make(map[string]rateBucket),
		max:     maxRequests,
		window:  window,
		nowFn:   time.Now,
	}
	return rl
}

// Allow checks and records an attempt for key. Returns (allowed, retryAfterSeconds).
func (rl *RateLimiter) Allow(key string) (bool, int) {
	now := rl.nowFn()

	rl.mu.Lock()
	defer rl.mu.Unlock()

	// Opportunistic cleanup to keep memory bounded.
	if len(rl.buckets) > 1000 {
		for k, b := range rl.buckets {
			if !b.resetAt.After(now) {
				delete(rl.buckets, k)
			}
		}
	}

	b, exists := rl.buckets[key]
	if !exists || !b.resetAt.After(now) {
		rl.buckets[key] = rateBucket{
			count:   1,
			resetAt: now.Add(rl.window),
		}
		return true, 0
	}

	if b.count >= rl.max {
		retryAfter := int(b.resetAt.Sub(now).Seconds()) + 1
		if retryAfter < 1 {
			retryAfter = 1
		}
		return false, retryAfter
	}

	b.count++
	rl.buckets[key] = b
	return true, 0
}

// Middleware wraps an http.Handler with per-IP rate limiting.
func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip := extractClientIP(r)
		allowed, retryAfter := rl.Allow(ip)
		if !allowed {
			w.Header().Set("Retry-After", strconv.Itoa(retryAfter))
			writeJSONError(w, http.StatusTooManyRequests, "too many requests, please try again later")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func extractClientIP(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}
