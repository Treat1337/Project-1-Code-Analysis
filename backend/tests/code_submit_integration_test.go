package tests

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
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

type stubCompilerClient struct {
	fn func(ctx context.Context, req services.CompilerRequest) (services.CompilerResult, error)
}

func (s stubCompilerClient) Execute(ctx context.Context, req services.CompilerRequest) (services.CompilerResult, error) {
	return s.fn(ctx, req)
}

type stubAIClient struct {
	fn func(ctx context.Context, req services.AIPredictRequest) (services.AIPredictResult, error)
}

func (s stubAIClient) Predict(ctx context.Context, req services.AIPredictRequest) (services.AIPredictResult, error) {
	return s.fn(ctx, req)
}

func setupCodeTestEnv(t *testing.T, comp services.CompilerClient, ai services.AIClient) (*testEnv, *sql.DB) {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "code_submit_test.db")

	cfg := config.Config{
		ServerHost:              "127.0.0.1",
		ServerPort:              "0",
		AppEnv:                  "test",
		SQLitePath:              dbPath,
		BackupDir:               filepath.Join(tmpDir, "backups"),
		BackupInterval:          time.Hour,
		CookieName:              "ca_session",
		CSRFCookieName:          "ca_csrf",
		CookieSecure:            false,
		CookieSameSite:          http.SameSiteLaxMode,
		SessionTTL:              24 * time.Hour,
		AllowedOrigins:          []string{"http://127.0.0.1:8000"},
		LoginRateLimitMax:       50,
		LoginRateLimitWindow:    time.Minute,
		RegisterRateLimitMax:    50,
		RegisterRateLimitWindow: time.Minute,
		MaxCodeBytes:            65536,
		PipelineVersion:         "v1",
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
	submissionRepo := repositories.NewSubmissionRepository(db)
	authService := services.NewAuthService(userRepo, sessionRepo, cfg.SessionTTL, cfg.SessionTokenPepper)
	codeService := services.NewCodeService(comp, ai, submissionRepo, cfg.MaxCodeBytes, cfg.PipelineVersion)

	router := routes.NewRouter(routes.Dependencies{
		Config:            cfg,
		AuthService:       authService,
		AuthHandler:       handlers.NewAuthHandler(authService, cfg),
		HealthHandler:     handlers.NewHealthHandler(db),
		CodeHandler:       handlers.NewCodeHandler(codeService),
		SubmissionHandler: handlers.NewSubmissionHandler(codeService),
	})

	env := &testEnv{
		db:      db,
		dbPath:  dbPath,
		cfg:     cfg,
		handler: router,
		baseURL: "http://127.0.0.1:8080",
	}
	t.Cleanup(env.close)
	return env, db
}

func registerAndLogin(t *testing.T, env *testEnv, username string) (*http.Client, string) {
	t.Helper()
	client := newCookieClient(t, env.handler)

	r, b := postJSON(t, client, env.baseURL+"/api/auth/register", map[string]string{
		"username": username,
		"password": "Password123",
	}, nil)
	if r.StatusCode != http.StatusCreated {
		t.Fatalf("register %s: %d (%s)", username, r.StatusCode, string(b))
	}

	r, b = postJSON(t, client, env.baseURL+"/api/auth/login", map[string]string{
		"username": username,
		"password": "Password123",
	}, nil)
	if r.StatusCode != http.StatusOK {
		t.Fatalf("login %s: %d (%s)", username, r.StatusCode, string(b))
	}

	var payload struct {
		CSRFToken string `json:"csrf_token"`
	}
	if err := json.Unmarshal(b, &payload); err != nil {
		t.Fatalf("unmarshal login: %v", err)
	}
	return client, payload.CSRFToken
}

func defaultWorkingCompiler() services.CompilerClient {
	return stubCompilerClient{
		fn: func(ctx context.Context, req services.CompilerRequest) (services.CompilerResult, error) {
			return services.CompilerResult{
				Stdout:             "42\n",
				Stderr:             "",
				ExitCode:           0,
				CompileDiagnostics: []string{},
				CompileStatus:      "success",
				ExecutionTimeMs:    12,
				ExecutionStatus:    "Accepted",
				Verdict:            "Accepted",
				PassedCount:        2,
				TotalCount:         2,
			}, nil
		},
	}
}

func defaultWorkingAI() services.AIClient {
	return stubAIClient{
		fn: func(ctx context.Context, req services.AIPredictRequest) (services.AIPredictResult, error) {
			return services.AIPredictResult{
				ASTNN:           services.ModelPrediction{Available: true, Label: "Correct", Confidence: 0.91},
				CodeBERT:        services.ModelPrediction{Available: true, Label: "Correct", Confidence: 0.87},
				CodeClassifier:  services.ModelPrediction{Available: true, Label: "Correct", Confidence: 0.78},
				ModelVersion:    map[string]string{"astnn": "astnn-v1", "codebert": "codebert-base-v1", "codeclassifier": "tfidf-logreg-v1"},
				PipelineVersion: "v1",
				AnalysisTimeMs:  35,
			}, nil
		},
	}
}

func TestRunAndSubmitWorkflows(t *testing.T) {
	env, db := setupCodeTestEnv(t, defaultWorkingCompiler(), defaultWorkingAI())

	// 1. Run & Submit without login -> 401
	anonClient := newCookieClient(t, env.handler)
	r, _ := postJSON(t, anonClient, env.baseURL+"/api/code/run", map[string]any{
		"problem_id": "p00000",
		"language":   "cpp",
		"code":       "int main(){return 0;}",
	}, nil)
	if r.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 on unauthenticated run, got %d", r.StatusCode)
	}

	r, _ = postJSON(t, anonClient, env.baseURL+"/api/code/submit", map[string]any{
		"problem_id": "p00000",
		"language":   "cpp",
		"code":       "int main(){return 0;}",
	}, nil)
	if r.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 on unauthenticated submit, got %d", r.StatusCode)
	}

	// 2. Login as user1
	client1, csrf1 := registerAndLogin(t, env, "user1")

	// 3. Authenticated Run -> 200 and MUST NOT create any row in submissions
	r, b := postJSON(t, client1, env.baseURL+"/api/code/run", map[string]any{
		"problem_id":   "p00000",
		"language":     "cpp",
		"code":         "#include <iostream>\nint main(){ std::cout << 42; return 0; }",
		"custom_input": "",
	}, map[string]string{"X-CSRF-Token": csrf1})
	if r.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 on run, got %d (%s)", r.StatusCode, string(b))
	}

	var subCount int
	if err := db.QueryRow(`SELECT COUNT(1) FROM submissions`).Scan(&subCount); err != nil {
		t.Fatalf("count submissions: %v", err)
	}
	if subCount != 0 {
		t.Fatalf("expected 0 submissions after Run, got %d", subCount)
	}

	// 4. Authenticated Submit twice -> creates 2 separate rows, never overwrites
	var firstSubID int64
	for i := 1; i <= 2; i++ {
		r, b = postJSON(t, client1, env.baseURL+"/api/code/submit", map[string]any{
			"problem_id": "p00000",
			"language":   "cpp",
			"code":       fmt.Sprintf("#include <iostream>\nint main(){ std::cout << %d; return 0; }", i),
		}, map[string]string{"X-CSRF-Token": csrf1})
		if r.StatusCode != http.StatusCreated {
			t.Fatalf("submit #%d: expected 201, got %d (%s)", i, r.StatusCode, string(b))
		}
		var resp services.SubmitResponse
		if err := json.Unmarshal(b, &resp); err != nil {
			t.Fatalf("unmarshal submit #%d: %v", i, err)
		}
		if i == 1 {
			firstSubID = resp.Submission.ID
		}
		if resp.Analysis.ASTNN == nil || resp.Analysis.CodeBERT == nil || resp.Analysis.CodeClassifier == nil {
			t.Fatalf("missing AI model results in submit #%d: %+v", i, resp.Analysis)
		}
		if resp.Analysis.ServiceStatus.Compiler != "ok" || resp.Analysis.ServiceStatus.AI != "ok" {
			t.Fatalf("unexpected service status: %+v", resp.Analysis.ServiceStatus)
		}
	}

	if err := db.QueryRow(`SELECT COUNT(1) FROM submissions`).Scan(&subCount); err != nil {
		t.Fatalf("count submissions: %v", err)
	}
	if subCount != 2 {
		t.Fatalf("expected 2 separate submission rows, got %d", subCount)
	}

	// 5. List submissions with pagination & status filter
	listResp, err := client1.Get(env.baseURL + "/api/submissions?page=1&limit=1&status=completed")
	if err != nil {
		t.Fatalf("GET /api/submissions: %v", err)
	}
	var listBody struct {
		Submissions []json.RawMessage `json:"submissions"`
		Total       int               `json:"total"`
	}
	_ = json.NewDecoder(listResp.Body).Decode(&listBody)
	listResp.Body.Close()
	if listResp.StatusCode != http.StatusOK || listBody.Total != 2 || len(listBody.Submissions) != 1 {
		t.Fatalf("unexpected paginated list: status=%d total=%d len=%d", listResp.StatusCode, listBody.Total, len(listBody.Submissions))
	}

	// 6. Another user cannot access or delete user1's submission
	client2, csrf2 := registerAndLogin(t, env, "user2")
	otherGet, err := client2.Get(fmt.Sprintf("%s/api/submissions/%d", env.baseURL, firstSubID))
	if err != nil {
		t.Fatalf("user2 GET submission: %v", err)
	}
	otherGet.Body.Close()
	if otherGet.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 when accessing another user's submission, got %d", otherGet.StatusCode)
	}

	delReq, _ := http.NewRequest(http.MethodDelete, fmt.Sprintf("%s/api/submissions/%d", env.baseURL, firstSubID), nil)
	delReq.Header.Set("X-CSRF-Token", csrf2)
	otherDel, err := client2.Do(delReq)
	if err != nil {
		t.Fatalf("user2 DELETE submission: %v", err)
	}
	otherDel.Body.Close()
	if otherDel.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 when deleting another user's submission, got %d", otherDel.StatusCode)
	}

	// 7. Submission stats endpoint returns verified counts
	statsResp, err := client1.Get(env.baseURL + "/api/submissions/stats")
	if err != nil {
		t.Fatalf("GET /api/submissions/stats: %v", err)
	}
	var statsBody repositories.SubmissionStats
	_ = json.NewDecoder(statsResp.Body).Decode(&statsBody)
	statsResp.Body.Close()
	if statsResp.StatusCode != http.StatusOK || statsBody.Total != 2 || statsBody.Accepted != 2 {
		t.Fatalf("unexpected stats: status=%d body=%+v", statsResp.StatusCode, statsBody)
	}

	// 8. Change password and login with new password
	r, b = postJSON(t, client1, env.baseURL+"/api/auth/change-password", map[string]string{
		"current_password": "Password123",
		"new_password":     "NewStrongPass456",
	}, map[string]string{"X-CSRF-Token": csrf1})
	if r.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 on change-password, got %d (%s)", r.StatusCode, string(b))
	}

	r, _ = postJSON(t, newCookieClient(t, env.handler), env.baseURL+"/api/auth/login", map[string]string{
		"username": "user1",
		"password": "NewStrongPass456",
	}, nil)
	if r.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 logging in with new password, got %d", r.StatusCode)
	}

	// 9. Submit idempotency: duplicate request_id returns existing submission without creating a duplicate row
	idemReq := map[string]any{
		"problem_id": "p00000",
		"language":   "cpp",
		"code":       "int main(){ return 0; }",
		"request_id": "req-idem-001",
	}
	r1, b1 := postJSON(t, client1, env.baseURL+"/api/code/submit", idemReq, map[string]string{"X-CSRF-Token": csrf1})
	r2, b2 := postJSON(t, client1, env.baseURL+"/api/code/submit", idemReq, map[string]string{"X-CSRF-Token": csrf1})
	if r1.StatusCode != http.StatusCreated || r2.StatusCode != http.StatusCreated {
		t.Fatalf("idempotency submits failed: %d / %d", r1.StatusCode, r2.StatusCode)
	}
	var sr1, sr2 services.SubmitResponse
	_ = json.Unmarshal(b1, &sr1)
	_ = json.Unmarshal(b2, &sr2)
	if sr1.Submission.ID != sr2.Submission.ID {
		t.Fatalf("expected identical submission ID for duplicate request_id, got %d vs %d", sr1.Submission.ID, sr2.Submission.ID)
	}
}

func TestSubmitCompileErrorAIServiceFailureTimeoutAndDBError(t *testing.T) {
	// Case A: Compile Error -> submission is saved with compile_status='compile_error'
	compileErrComp := stubCompilerClient{
		fn: func(ctx context.Context, req services.CompilerRequest) (services.CompilerResult, error) {
			return services.CompilerResult{
				Stderr:             "main.cpp:2:5: error: expected ';' before 'return'",
				ExitCode:           1,
				CompileDiagnostics: []string{"main.cpp:2:5: error: expected ';' before 'return'"},
				CompileStatus:      "compile_error",
				ExecutionTimeMs:    5,
				ExecutionStatus:    "Compilation Error",
				Verdict:            "Compilation Error",
			}, nil
		},
	}
	envA, _ := setupCodeTestEnv(t, compileErrComp, defaultWorkingAI())
	cA, csrfA := registerAndLogin(t, envA, "compile_user")

	r, b := postJSON(t, cA, envA.baseURL+"/api/code/submit", map[string]any{
		"problem_id": "p00001",
		"language":   "cpp",
		"code":       "int main(){ return 0 }",
	}, map[string]string{"X-CSRF-Token": csrfA})
	if r.StatusCode != http.StatusCreated {
		t.Fatalf("expected 201 on compile error submit, got %d (%s)", r.StatusCode, string(b))
	}
	var respA services.SubmitResponse
	_ = json.Unmarshal(b, &respA)
	if respA.Submission.Status != "compile_error" || respA.Submission.CompileStatus == nil || *respA.Submission.CompileStatus != "compile_error" {
		t.Fatalf("expected compile_error status persisted, got %+v", respA.Submission)
	}

	// Case B: AI Service fails -> submission still saved with status='partial_error' and service_status.ai='error'
	failingAI := stubAIClient{
		fn: func(ctx context.Context, req services.AIPredictRequest) (services.AIPredictResult, error) {
			return services.AIPredictResult{}, fmt.Errorf("%w: connection refused", services.ErrAIServiceUnavailable)
		},
	}
	envB, dbB := setupCodeTestEnv(t, defaultWorkingCompiler(), failingAI)
	cB, csrfB := registerAndLogin(t, envB, "ai_fail_user")

	r, b = postJSON(t, cB, envB.baseURL+"/api/code/submit", map[string]any{
		"problem_id": "p00001",
		"language":   "cpp",
		"code":       "int main(){ return 0; }",
	}, map[string]string{"X-CSRF-Token": csrfB})
	if r.StatusCode != http.StatusCreated {
		t.Fatalf("expected 201 when AI fails, got %d (%s)", r.StatusCode, string(b))
	}
	var respB services.SubmitResponse
	_ = json.Unmarshal(b, &respB)
	if respB.Submission.Status != "partial_error" || respB.Analysis.ServiceStatus.AI != "error" {
		t.Fatalf("expected partial_error + ai=error, got sub=%s ai=%s", respB.Submission.Status, respB.Analysis.ServiceStatus.AI)
	}
	var countB int
	_ = dbB.QueryRow(`SELECT COUNT(1) FROM submissions`).Scan(&countB)
	if countB != 1 {
		t.Fatalf("expected submission preserved on AI error, got %d", countB)
	}

	// Case C: Compiler Timeout on Run -> 504 Gateway Timeout; on Submit -> saved with compiler='timeout'
	timeoutComp := stubCompilerClient{
		fn: func(ctx context.Context, req services.CompilerRequest) (services.CompilerResult, error) {
			return services.CompilerResult{}, fmt.Errorf("%w: exceeded 15s", services.ErrCompilerTimeout)
		},
	}
	envC, _ := setupCodeTestEnv(t, timeoutComp, defaultWorkingAI())
	cC, csrfC := registerAndLogin(t, envC, "timeout_user")

	r, _ = postJSON(t, cC, envC.baseURL+"/api/code/run", map[string]any{
		"problem_id": "p00001",
		"language":   "cpp",
		"code":       "int main(){ while(true){} }",
	}, map[string]string{"X-CSRF-Token": csrfC})
	if r.StatusCode != http.StatusGatewayTimeout {
		t.Fatalf("expected 504 on compiler timeout during Run, got %d", r.StatusCode)
	}

	r, b = postJSON(t, cC, envC.baseURL+"/api/code/submit", map[string]any{
		"problem_id": "p00001",
		"language":   "cpp",
		"code":       "int main(){ while(true){} }",
	}, map[string]string{"X-CSRF-Token": csrfC})
	if r.StatusCode != http.StatusCreated {
		t.Fatalf("expected 201 on compiler timeout during Submit, got %d", r.StatusCode)
	}
	var respC services.SubmitResponse
	_ = json.Unmarshal(b, &respC)
	if respC.Analysis.ServiceStatus.Compiler != "timeout" || respC.Submission.Status != "partial_error" {
		t.Fatalf("expected compiler=timeout & partial_error, got %+v", respC.Analysis.ServiceStatus)
	}

	// Case D: Database error during Submit -> 500 Internal Server Error
	envD, dbD := setupCodeTestEnv(t, defaultWorkingCompiler(), defaultWorkingAI())
	cD, csrfD := registerAndLogin(t, envD, "dberr_user")
	// Drop submissions table to simulate a database error during Submit
	if _, err := dbD.Exec(`DROP TABLE submissions;`); err != nil {
		t.Fatalf("drop submissions: %v", err)
	}
	r, b = postJSON(t, cD, envD.baseURL+"/api/code/submit", map[string]any{
		"problem_id": "p00001",
		"language":   "cpp",
		"code":       "int main(){ return 0; }",
	}, map[string]string{"X-CSRF-Token": csrfD})
	if r.StatusCode != http.StatusInternalServerError {
		t.Fatalf("expected 500 on DB error, got %d (%s)", r.StatusCode, string(b))
	}
	if !bytes.Contains(b, []byte("failed to process submission")) {
		t.Fatalf("unexpected error body: %s", string(b))
	}
	if strings.Contains(string(b), "DROP TABLE") {
		t.Fatalf("leaked internal SQL error: %s", string(b))
	}
}

// Keep unused import check happy if errors is used
var _ = errors.New
