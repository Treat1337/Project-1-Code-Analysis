package services

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"code-analysis-backend/internal/models"
	"code-analysis-backend/internal/repositories"
)

var problemIDRegex = regexp.MustCompile(`^p\d{5}$`)

type CodeRunInput struct {
	ProblemID      string
	Language       string
	Code           string
	CustomInput    string
	ExpectedOutput string
}

type CodeSubmitInput struct {
	ProblemID          string
	Language           string
	Code               string
	CustomInput        string
	ProblemDescription string
	SampleInput        string
	SampleOutput       string
	RequestID          string
}

type CompilerAnalysisSummary struct {
	Status          string   `json:"status"`
	Verdict         string   `json:"verdict,omitempty"`
	Diagnostics     []string `json:"diagnostics"`
	ExecutionTimeMs int64    `json:"execution_time_ms,omitempty"`
	PassedCount     int      `json:"passed_count,omitempty"`
	TotalCount      int      `json:"total_count,omitempty"`
	Error           string   `json:"error,omitempty"`
}

type ServiceStatusMap struct {
	Compiler string `json:"compiler"`
	AI       string `json:"ai"`
}

type StructuredAnalysisResult struct {
	ASTNN           *ModelPrediction        `json:"astnn,omitempty"`
	CodeBERT        *ModelPrediction        `json:"codebert,omitempty"`
	CodeClassifier  *ModelPrediction        `json:"codeclassifier,omitempty"`
	Compiler        CompilerAnalysisSummary `json:"compiler"`
	ModelVersion    map[string]string       `json:"model_version,omitempty"`
	PipelineVersion string                  `json:"pipeline_version"`
	AnalysisTimeMs  int64                   `json:"analysis_time_ms"`
	ServiceStatus   ServiceStatusMap        `json:"service_status"`
}

type SubmitResponse struct {
	Submission models.Submission        `json:"submission"`
	Analysis   StructuredAnalysisResult `json:"analysis"`
	Compiler   *CompilerResult          `json:"compiler,omitempty"`
}

type CodeService struct {
	compiler        CompilerClient
	ai              AIClient
	submissions     *repositories.SubmissionRepository
	maxCodeBytes    int
	pipelineVersion string
}

func NewCodeService(
	compiler CompilerClient,
	ai AIClient,
	submissions *repositories.SubmissionRepository,
	maxCodeBytes int,
	pipelineVersion string,
) *CodeService {
	return &CodeService{
		compiler:        compiler,
		ai:              ai,
		submissions:     submissions,
		maxCodeBytes:    maxCodeBytes,
		pipelineVersion: pipelineVersion,
	}
}

// Run compiles and executes user code without saving anything to the submissions table.
func (s *CodeService) Run(ctx context.Context, input CodeRunInput) (CompilerResult, error) {
	lang, err := s.validateCodeInput(input.Code, input.Language, input.ProblemID, false)
	if err != nil {
		return CompilerResult{}, err
	}

	return s.compiler.Execute(ctx, CompilerRequest{
		ProblemID:      strings.TrimSpace(input.ProblemID),
		Language:       lang,
		Code:           input.Code,
		CustomInput:    input.CustomInput,
		ExpectedOutput: input.ExpectedOutput,
		RunAll:         false,
	})
}

// Submit creates a processing submission, executes compiler + AI models, and persists the result.
func (s *CodeService) Submit(ctx context.Context, userID int64, input CodeSubmitInput) (SubmitResponse, error) {
	lang, err := s.validateCodeInput(input.Code, input.Language, input.ProblemID, true)
	if err != nil {
		return SubmitResponse{}, err
	}

	problemID := strings.TrimSpace(input.ProblemID)
	requestID := strings.TrimSpace(input.RequestID)
	if requestID != "" {
		existing, err := s.submissions.GetByRequestIDForUser(ctx, userID, requestID)
		if err == nil {
			var parsed StructuredAnalysisResult
			if existing.AnalysisResult != nil {
				_ = json.Unmarshal([]byte(*existing.AnalysisResult), &parsed)
			}
			return SubmitResponse{
				Submission: existing,
				Analysis:   parsed,
			}, nil
		}
	}

	sub, err := s.submissions.CreateProcessing(ctx, userID, input.Code, lang, problemID, requestID)
	if err != nil {
		return SubmitResponse{}, fmt.Errorf("create processing submission: %w", err)
	}

	started := time.Now()
	svcStatus := ServiceStatusMap{Compiler: "ok", AI: "ok"}
	var errParts []string

	// 1. Run Compiler Service
	compRes, compErr := s.compiler.Execute(ctx, CompilerRequest{
		ProblemID:   problemID,
		Language:    lang,
		Code:        input.Code,
		CustomInput: input.CustomInput,
		RunAll:      true,
	})

	var compilerSummary CompilerAnalysisSummary
	var compileStatus string
	var compilerMsg string
	var compPtr *CompilerResult

	if compErr != nil {
		if errors.Is(compErr, ErrCompilerTimeout) {
			svcStatus.Compiler = "timeout"
		} else {
			svcStatus.Compiler = "error"
		}
		compileStatus = "error"
		compilerSummary = CompilerAnalysisSummary{
			Status:      "error",
			Diagnostics: []string{},
			Error:       compErr.Error(),
		}
		errParts = append(errParts, "compiler: "+compErr.Error())
	} else {
		compPtr = &compRes
		compileStatus = compRes.CompileStatus
		compilerMsg = compRes.Stderr
		compilerSummary = CompilerAnalysisSummary{
			Status:          compRes.CompileStatus,
			Verdict:         compRes.Verdict,
			Diagnostics:     compRes.CompileDiagnostics,
			ExecutionTimeMs: compRes.ExecutionTimeMs,
			PassedCount:     compRes.PassedCount,
			TotalCount:      compRes.TotalCount,
		}
		if compRes.CompileStatus == "compile_error" && compRes.Stderr != "" {
			errParts = append(errParts, compRes.Stderr)
		}
	}

	// 2. Run Python AI Service (ASTNN, CodeBERT, CodeClassifier)
	aiRes, aiErr := s.ai.Predict(ctx, AIPredictRequest{
		Code:               input.Code,
		CompilerMessage:    compilerMsg,
		ProblemDescription: input.ProblemDescription,
		SampleInput:        input.SampleInput,
		SampleOutput:       input.SampleOutput,
	})

	analysis := StructuredAnalysisResult{
		Compiler:        compilerSummary,
		PipelineVersion: s.pipelineVersion,
		ServiceStatus:   svcStatus,
	}

	var modelVersionStr string
	if aiErr != nil {
		if errors.Is(aiErr, ErrAIServiceTimeout) {
			analysis.ServiceStatus.AI = "timeout"
		} else {
			analysis.ServiceStatus.AI = "error"
		}
		errParts = append(errParts, "ai: "+aiErr.Error())
	} else {
		analysis.ASTNN = &aiRes.ASTNN
		analysis.CodeBERT = &aiRes.CodeBERT
		analysis.CodeClassifier = &aiRes.CodeClassifier
		analysis.ModelVersion = aiRes.ModelVersion
		if aiRes.PipelineVersion != "" {
			analysis.PipelineVersion = aiRes.PipelineVersion
		}
		mvBytes, _ := json.Marshal(aiRes.ModelVersion)
		modelVersionStr = string(mvBytes)
	}

	analysis.AnalysisTimeMs = time.Since(started).Milliseconds()

	// Determine overall submission status without conflating AI predictions with actual execution verdict.
	overallStatus := "completed"
	switch {
	case compErr != nil && aiErr != nil:
		overallStatus = "failed"
	case compErr != nil || aiErr != nil:
		overallStatus = "partial_error"
	case compileStatus == "compile_error":
		overallStatus = "compile_error"
	}

	analysisJSONBytes, err := json.Marshal(analysis)
	if err != nil {
		return SubmitResponse{}, fmt.Errorf("marshal analysis result: %w", err)
	}
	analysisJSON := string(analysisJSONBytes)

	var errSummaryPtr *string
	if len(errParts) > 0 {
		joined := strings.Join(errParts, " | ")
		if len(joined) > 2000 {
			joined = joined[:2000]
		}
		errSummaryPtr = &joined
	}

	var modelVersionPtr *string
	if modelVersionStr != "" {
		modelVersionPtr = &modelVersionStr
	}

	updatedSub, updateErr := s.submissions.UpdateResult(
		ctx,
		sub.ID,
		userID,
		overallStatus,
		&compileStatus,
		&analysisJSON,
		errSummaryPtr,
		modelVersionPtr,
	)
	if updateErr != nil {
		return SubmitResponse{}, fmt.Errorf("update submission result: %w", updateErr)
	}

	return SubmitResponse{
		Submission: updatedSub,
		Analysis:   analysis,
		Compiler:   compPtr,
	}, nil
}

func (s *CodeService) GetSubmissionStats(ctx context.Context, userID int64) (repositories.SubmissionStats, error) {
	return s.submissions.StatsByUser(ctx, userID)
}

func (s *CodeService) ListSubmissions(
	ctx context.Context,
	userID int64,
	statusFilter string,
	page int,
	limit int,
) ([]models.Submission, int, error) {
	if page < 1 {
		page = 1
	}
	if limit < 1 || limit > 100 {
		limit = 20
	}
	offset := (page - 1) * limit
	return s.submissions.ListByUser(ctx, userID, strings.TrimSpace(statusFilter), limit, offset)
}

func (s *CodeService) GetSubmission(ctx context.Context, submissionID, userID int64) (models.Submission, error) {
	return s.submissions.GetByIDForUser(ctx, submissionID, userID)
}

func (s *CodeService) DeleteSubmission(ctx context.Context, submissionID, userID int64) error {
	return s.submissions.DeleteByIDForUser(ctx, submissionID, userID)
}

func (s *CodeService) validateCodeInput(code, language, problemID string, requireProblemID bool) (string, error) {
	if strings.TrimSpace(code) == "" {
		return "", fmt.Errorf("%w: code must not be empty", ErrInvalidInput)
	}
	if len(code) > s.maxCodeBytes {
		return "", fmt.Errorf("%w: code exceeds maximum size (%d bytes)", ErrInvalidInput, s.maxCodeBytes)
	}

	lang := strings.ToLower(strings.TrimSpace(language))
	if lang == "" {
		lang = "cpp"
	}
	if lang != "cpp" && lang != "c++" {
		return "", fmt.Errorf("%w: unsupported language %q (only cpp is supported)", ErrInvalidInput, language)
	}

	pid := strings.TrimSpace(problemID)
	if requireProblemID && pid == "" {
		return "", fmt.Errorf("%w: problem_id is required", ErrInvalidInput)
	}
	if pid != "" && !problemIDRegex.MatchString(pid) {
		return "", fmt.Errorf("%w: invalid problem_id format (expected pXXXXX)", ErrInvalidInput)
	}

	return "cpp", nil
}
