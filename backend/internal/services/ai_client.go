package services

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

var (
	ErrAIServiceUnavailable = errors.New("ai service unavailable")
	ErrAIServiceTimeout     = errors.New("ai service timed out")
)

type AIPredictRequest struct {
	Code               string `json:"code"`
	CompilerMessage    string `json:"compiler_message,omitempty"`
	ProblemDescription string `json:"problem_description,omitempty"`
	SampleInput        string `json:"sample_input,omitempty"`
	SampleOutput       string `json:"sample_output,omitempty"`
}

type ModelPrediction struct {
	Available  bool    `json:"available"`
	Label      string  `json:"label,omitempty"`
	Confidence float64 `json:"confidence,omitempty"`
	Reason     string  `json:"reason,omitempty"`
	Note       string  `json:"note,omitempty"`
}

type AIPredictResult struct {
	ASTNN           ModelPrediction   `json:"astnn"`
	CodeBERT        ModelPrediction   `json:"codebert"`
	CodeClassifier  ModelPrediction   `json:"codeclassifier"`
	ModelVersion    map[string]string `json:"model_version"`
	PipelineVersion string            `json:"pipeline_version"`
	AnalysisTimeMs  int64             `json:"analysis_time_ms"`
}

type AIClient interface {
	Predict(ctx context.Context, req AIPredictRequest) (AIPredictResult, error)
}

type HTTPAIClient struct {
	endpoint string
	client   *http.Client
}

func NewHTTPAIClient(baseURL, predictPath string, timeout time.Duration) *HTTPAIClient {
	return &HTTPAIClient{
		endpoint: strings.TrimRight(baseURL, "/") + "/" + strings.TrimLeft(predictPath, "/"),
		client:   &http.Client{Timeout: timeout},
	}
}

func (c *HTTPAIClient) Predict(ctx context.Context, req AIPredictRequest) (AIPredictResult, error) {
	payload, err := json.Marshal(req)
	if err != nil {
		return AIPredictResult{}, fmt.Errorf("marshal ai request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint, bytes.NewReader(payload))
	if err != nil {
		return AIPredictResult{}, fmt.Errorf("create ai request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		if isTimeoutErr(err) {
			return AIPredictResult{}, fmt.Errorf("%w: %v", ErrAIServiceTimeout, err)
		}
		return AIPredictResult{}, fmt.Errorf("%w: %v", ErrAIServiceUnavailable, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if err != nil {
		return AIPredictResult{}, fmt.Errorf("read ai response: %w", err)
	}

	if resp.StatusCode >= 500 {
		return AIPredictResult{}, fmt.Errorf("%w: status %d", ErrAIServiceUnavailable, resp.StatusCode)
	}
	if resp.StatusCode >= 400 {
		return AIPredictResult{}, fmt.Errorf("ai service rejected request (%d): %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var result AIPredictResult
	if err := json.Unmarshal(body, &result); err != nil {
		return AIPredictResult{}, fmt.Errorf("decode ai response: %w", err)
	}
	return result, nil
}
