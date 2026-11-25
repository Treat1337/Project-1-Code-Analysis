package services

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"net/mail"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode"

	"golang.org/x/crypto/argon2"

	"code-analysis-backend/internal/models"
	"code-analysis-backend/internal/repositories"
)

var (
	ErrInvalidInput       = errors.New("invalid input")
	ErrInvalidCredentials = errors.New("invalid username or password")
	ErrSessionInvalid     = errors.New("invalid or expired session")
	ErrUsernameExists     = repositories.ErrUsernameTaken
)

const (
	argonMemory      uint32 = 64 * 1024 // 64 MiB
	argonIterations  uint32 = 3
	argonParallelism uint8  = 2
	argonSaltLen            = 16
	argonKeyLen      uint32 = 32
	sessionTokenBytes       = 32
)

var usernameRegex = regexp.MustCompile(`^[a-zA-Z0-9_-]{3,32}$`)

type AuthService struct {
	users      *repositories.UserRepository
	sessions   *repositories.SessionRepository
	sessionTTL time.Duration
	pepper     string
	nowFn      func() time.Time
}

func NewAuthService(
	users *repositories.UserRepository,
	sessions *repositories.SessionRepository,
	sessionTTL time.Duration,
	pepper string,
) *AuthService {
	return &AuthService{
		users:      users,
		sessions:   sessions,
		sessionTTL: sessionTTL,
		pepper:     pepper,
		nowFn:      time.Now,
	}
}

// Register validates user input, hashes the password with Argon2id, and creates the user.
func (s *AuthService) Register(ctx context.Context, username, email, password string) (models.UserResponse, error) {
	cleanUsername := strings.TrimSpace(username)
	if !usernameRegex.MatchString(cleanUsername) {
		return models.UserResponse{}, fmt.Errorf("%w: username must be 3-32 characters (letters, digits, _, -)", ErrInvalidInput)
	}

	var emailPtr *string
	cleanEmail := strings.TrimSpace(email)
	if cleanEmail != "" {
		if len(cleanEmail) > 254 {
			return models.UserResponse{}, fmt.Errorf("%w: email is too long", ErrInvalidInput)
		}
		addr, err := mail.ParseAddress(cleanEmail)
		if err != nil || addr.Address != cleanEmail {
			return models.UserResponse{}, fmt.Errorf("%w: invalid email format", ErrInvalidInput)
		}
		emailPtr = &cleanEmail
	}

	if err := validatePassword(password); err != nil {
		return models.UserResponse{}, err
	}

	hash, err := HashPassword(password)
	if err != nil {
		return models.UserResponse{}, fmt.Errorf("hash password: %w", err)
	}

	user, err := s.users.Create(ctx, cleanUsername, emailPtr, hash)
	if err != nil {
		return models.UserResponse{}, err
	}

	return user.ToResponse(), nil
}

// Login verifies credentials (username or email) and creates a new session, returning the user and raw token.
func (s *AuthService) Login(ctx context.Context, identifier, password string) (models.UserResponse, string, time.Time, error) {
	cleanID := strings.TrimSpace(identifier)
	if cleanID == "" || password == "" {
		return models.UserResponse{}, "", time.Time{}, ErrInvalidCredentials
	}

	user, err := s.users.GetByUsernameOrEmail(ctx, cleanID)
	if err != nil {
		if errors.Is(err, repositories.ErrUserNotFound) {
			return models.UserResponse{}, "", time.Time{}, ErrInvalidCredentials
		}
		return models.UserResponse{}, "", time.Time{}, err
	}

	ok, err := VerifyPassword(password, user.PasswordHash)
	if err != nil || !ok {
		return models.UserResponse{}, "", time.Time{}, ErrInvalidCredentials
	}

	rawToken, err := generateRandomToken(sessionTokenBytes)
	if err != nil {
		return models.UserResponse{}, "", time.Time{}, fmt.Errorf("generate session token: %w", err)
	}

	tokenHash := s.HashToken(rawToken)
	expiresAt := s.nowFn().UTC().Add(s.sessionTTL)

	if _, err := s.sessions.Create(ctx, user.ID, tokenHash, expiresAt); err != nil {
		return models.UserResponse{}, "", time.Time{}, err
	}

	return user.ToResponse(), rawToken, expiresAt, nil
}

// ChangePassword verifies currentPassword, validates newPassword, and updates the user's Argon2id hash.
func (s *AuthService) ChangePassword(ctx context.Context, userID int64, currentPassword, newPassword string) error {
	if currentPassword == "" {
		return ErrInvalidCredentials
	}
	if err := validatePassword(newPassword); err != nil {
		return err
	}

	user, err := s.users.GetByID(ctx, userID)
	if err != nil {
		if errors.Is(err, repositories.ErrUserNotFound) {
			return ErrSessionInvalid
		}
		return err
	}

	ok, err := VerifyPassword(currentPassword, user.PasswordHash)
	if err != nil || !ok {
		return ErrInvalidCredentials
	}

	newHash, err := HashPassword(newPassword)
	if err != nil {
		return fmt.Errorf("hash password: %w", err)
	}
	return s.users.UpdatePasswordHash(ctx, userID, newHash)
}

// Logout revokes the session associated with rawToken.
func (s *AuthService) Logout(ctx context.Context, rawToken string) error {
	if strings.TrimSpace(rawToken) == "" {
		return nil
	}
	tokenHash := s.HashToken(rawToken)
	return s.sessions.DeleteByTokenHash(ctx, tokenHash)
}

// Authenticate validates a raw session token and returns the associated user.
func (s *AuthService) Authenticate(ctx context.Context, rawToken string) (models.UserResponse, error) {
	if strings.TrimSpace(rawToken) == "" {
		return models.UserResponse{}, ErrSessionInvalid
	}

	tokenHash := s.HashToken(rawToken)
	sess, err := s.sessions.GetByTokenHash(ctx, tokenHash)
	if err != nil {
		if errors.Is(err, repositories.ErrSessionNotFound) {
			return models.UserResponse{}, ErrSessionInvalid
		}
		return models.UserResponse{}, err
	}

	if !sess.ExpiresAt.After(s.nowFn().UTC()) {
		_ = s.sessions.DeleteByTokenHash(ctx, tokenHash)
		return models.UserResponse{}, ErrSessionInvalid
	}

	user, err := s.users.GetByID(ctx, sess.UserID)
	if err != nil {
		if errors.Is(err, repositories.ErrUserNotFound) {
			return models.UserResponse{}, ErrSessionInvalid
		}
		return models.UserResponse{}, err
	}

	return user.ToResponse(), nil
}

// CleanupExpiredSessions removes expired sessions from SQLite.
func (s *AuthService) CleanupExpiredSessions(ctx context.Context) (int64, error) {
	return s.sessions.DeleteExpired(ctx, s.nowFn().UTC())
}

// HashToken hashes a raw session token using HMAC-SHA256 (if pepper is set) or SHA-256.
func (s *AuthService) HashToken(rawToken string) string {
	if s.pepper != "" {
		mac := hmac.New(sha256.New, []byte(s.pepper))
		mac.Write([]byte(rawToken))
		return hex.EncodeToString(mac.Sum(nil))
	}
	sum := sha256.Sum256([]byte(rawToken))
	return hex.EncodeToString(sum[:])
}

// HashPassword hashes a plaintext password using Argon2id and encodes it in PHC format.
func HashPassword(password string) (string, error) {
	salt := make([]byte, argonSaltLen)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}

	hash := argon2.IDKey([]byte(password), salt, argonIterations, argonMemory, argonParallelism, argonKeyLen)

	b64Salt := base64.RawStdEncoding.EncodeToString(salt)
	b64Hash := base64.RawStdEncoding.EncodeToString(hash)

	return fmt.Sprintf("$argon2id$v=%d$m=%d,t=%d,p=%d$%s$%s",
		argon2.Version, argonMemory, argonIterations, argonParallelism, b64Salt, b64Hash,
	), nil
}

// VerifyPassword compares a plaintext password against a PHC-encoded Argon2id hash.
func VerifyPassword(password, encodedHash string) (bool, error) {
	parts := strings.Split(encodedHash, "$")
	if len(parts) != 6 || parts[1] != "argon2id" {
		return false, errors.New("invalid argon2id hash format")
	}

	var version int
	if _, err := fmt.Sscanf(parts[2], "v=%d", &version); err != nil || version != argon2.Version {
		return false, errors.New("unsupported argon2id version")
	}

	params := strings.Split(parts[3], ",")
	if len(params) != 3 {
		return false, errors.New("invalid argon2id params")
	}
	memory, err := parseParamUint32(params[0], "m=")
	if err != nil {
		return false, err
	}
	iterations, err := parseParamUint32(params[1], "t=")
	if err != nil {
		return false, err
	}
	parallelism64, err := parseParamUint32(params[2], "p=")
	if err != nil {
		return false, err
	}
	parallelism := uint8(parallelism64)

	salt, err := base64.RawStdEncoding.DecodeString(parts[4])
	if err != nil {
		return false, err
	}
	expectedHash, err := base64.RawStdEncoding.DecodeString(parts[5])
	if err != nil {
		return false, err
	}

	computed := argon2.IDKey([]byte(password), salt, iterations, memory, parallelism, uint32(len(expectedHash)))
	return subtle.ConstantTimeCompare(computed, expectedHash) == 1, nil
}

func parseParamUint32(part, prefix string) (uint32, error) {
	if !strings.HasPrefix(part, prefix) {
		return 0, fmt.Errorf("missing prefix %s", prefix)
	}
	v, err := strconv.ParseUint(strings.TrimPrefix(part, prefix), 10, 32)
	if err != nil {
		return 0, err
	}
	return uint32(v), nil
}

func validatePassword(password string) error {
	if len(password) < 8 {
		return fmt.Errorf("%w: password must be at least 8 characters", ErrInvalidInput)
	}
	if len(password) > 128 {
		return fmt.Errorf("%w: password must be at most 128 characters", ErrInvalidInput)
	}

	var hasLetter, hasDigit bool
	for _, r := range password {
		if r == 0 {
			return fmt.Errorf("%w: password contains invalid characters", ErrInvalidInput)
		}
		if unicode.IsLetter(r) {
			hasLetter = true
		} else if unicode.IsDigit(r) {
			hasDigit = true
		}
	}
	if !hasLetter || !hasDigit {
		return fmt.Errorf("%w: password must contain at least one letter and one digit", ErrInvalidInput)
	}
	return nil
}

func generateRandomToken(numBytes int) (string, error) {
	b := make([]byte, numBytes)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}
