package models

import "time"

// Submission represents a code submission record (schema prepared for Prompt 2).
type Submission struct {
	ID             int64     `json:"id"`
	UserID         int64     `json:"user_id"`
	SourceCode     string    `json:"source_code"`
	Language       string    `json:"language"`
	ProblemID      string    `json:"problem_id"`
	Status         string    `json:"status"`
	CompileStatus  *string   `json:"compile_status,omitempty"`
	AnalysisResult *string   `json:"analysis_result,omitempty"`
	ErrorSummary   *string   `json:"error_summary,omitempty"`
	ModelVersion   *string   `json:"model_version,omitempty"`
	CreatedAt      time.Time `json:"created_at"`
}
