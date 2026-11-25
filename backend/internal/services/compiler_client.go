package services

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"time"
)

var (
	ErrCompilerUnavailable = errors.New("compiler service unavailable")
	ErrCompilerTimeout     = errors.New("compiler service timed out")
)

type CompilerRequest struct {
	ProblemID      string `json:"problem_id"`
	Language       string `json:"language"`
	Code           string `json:"code"`
	CustomInput    string `json:"custom_input"`
	ExpectedOutput string `json:"expected_output,omitempty"`
	RunAll         bool   `json:"run_all"`
}

type CompilerTestCaseResult struct {
	Case           int    `json:"case"`
	Name           string `json:"name,omitempty"`
	Status         string `json:"status"`
	Stdout         string `json:"actual_stdout,omitempty"`
	ExpectedStdout string `json:"expected_stdout,omitempty"`
	Stderr         string `json:"stderr,omitempty"`
	DurationMs     int64  `json:"duration_ms,omitempty"`
}

type CompilerResult struct {
	Stdout             string                   `json:"stdout"`
	Stderr             string                   `json:"stderr"`
	ExitCode           int                      `json:"exit_code"`
	CompileDiagnostics []string                 `json:"compile_diagnostics"`
	CompileStatus      string                   `json:"compile_status"`
	ExecutionTimeMs    int64                    `json:"execution_time_ms"`
	ExecutionStatus    string                   `json:"execution_status"`
	Verdict            string                   `json:"verdict"`
	PassedCount        int                      `json:"passed_count,omitempty"`
	TotalCount         int                      `json:"total_count,omitempty"`
	Tests              []CompilerTestCaseResult `json:"tests,omitempty"`
}

type CompilerClient interface {
	Execute(ctx context.Context, req CompilerRequest) (CompilerResult, error)
}

type HTTPCompilerClient struct {
	endpoint string
	client   *http.Client
}

func NewHTTPCompilerClient(baseURL, runPath string, timeout time.Duration) *HTTPCompilerClient {
	return &HTTPCompilerClient{
		endpoint: strings.TrimRight(baseURL, "/") + "/" + strings.TrimLeft(runPath, "/"),
		client:   &http.Client{Timeout: timeout},
	}
}

func (c *HTTPCompilerClient) Execute(ctx context.Context, req CompilerRequest) (CompilerResult, error) {
	payload, err := json.Marshal(req)
	if err != nil {
		return CompilerResult{}, fmt.Errorf("marshal compiler request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint, bytes.NewReader(payload))
	if err != nil {
		return CompilerResult{}, fmt.Errorf("create compiler request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		if isTimeoutErr(err) {
			return CompilerResult{}, fmt.Errorf("%w: %v", ErrCompilerTimeout, err)
		}
		return CompilerResult{}, fmt.Errorf("%w: %v", ErrCompilerUnavailable, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return CompilerResult{}, fmt.Errorf("read compiler response: %w", err)
	}

	if resp.StatusCode >= 500 {
		return CompilerResult{}, fmt.Errorf("%w: status %d", ErrCompilerUnavailable, resp.StatusCode)
	}
	if resp.StatusCode >= 400 {
		return CompilerResult{}, fmt.Errorf("compiler rejected request (%d): %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var raw struct {
		Verdict      string                   `json:"verdict"`
		ActualOutput string                   `json:"actual_output"`
		Stdout       string                   `json:"stdout"`
		Stderr       string                   `json:"stderr"`
		Diagnostic   string                   `json:"diagnostic"`
		DurationMs   int64                    `json:"duration_ms"`
		PassedCount  int                      `json:"passed_count"`
		TotalCount   int                      `json:"total_count"`
		Tests        []CompilerTestCaseResult `json:"tests"`
	}
	if err := json.Unmarshal(body, &raw); err != nil {
		return CompilerResult{}, fmt.Errorf("decode compiler response: %w", err)
	}

	stdout := raw.ActualOutput
	if stdout == "" {
		stdout = raw.Stdout
	}
	stderr := raw.Stderr
	if stderr == "" && raw.Diagnostic != "" {
		stderr = raw.Diagnostic
	}

	verdict := strings.TrimSpace(raw.Verdict)
	if verdict == "" {
		verdict = "Unknown"
	}

	compileStatus := "success"
	diagnostics := []string{}
	exitCode := 0

	lowerVerdict := strings.ToLower(verdict)
	switch {
	case strings.Contains(lowerVerdict, "compile"):
		compileStatus = "compile_error"
		exitCode = 1
		if stderr != "" {
			diagnostics = append(diagnostics, stderr)
		}
	case lowerVerdict == "accepted" || lowerVerdict == "passed":
		exitCode = 0
	default:
		exitCode = 1
	}

	return CompilerResult{
		Stdout:             stdout,
		Stderr:             stderr,
		ExitCode:           exitCode,
		CompileDiagnostics: diagnostics,
		CompileStatus:      compileStatus,
		ExecutionTimeMs:    raw.DurationMs,
		ExecutionStatus:    verdict,
		Verdict:            verdict,
		PassedCount:        raw.PassedCount,
		TotalCount:         raw.TotalCount,
		Tests:              raw.Tests,
	}, nil
}

func isTimeoutErr(err error) bool {
	if errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	var netErr net.Error
	return errors.As(err, &netErr) && netErr.Timeout()
}
