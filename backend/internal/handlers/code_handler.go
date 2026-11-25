package handlers

import (
	"errors"
	"net/http"

	"code-analysis-backend/internal/middleware"
	"code-analysis-backend/internal/services"
)

type CodeHandler struct {
	codeService *services.CodeService
}

func NewCodeHandler(codeService *services.CodeService) *CodeHandler {
	return &CodeHandler{codeService: codeService}
}

type runCodeRequest struct {
	ProblemID      string `json:"problem_id"`
	Language       string `json:"language"`
	Code           string `json:"code"`
	CustomInput    string `json:"custom_input"`
	ExpectedOutput string `json:"expected_output"`
}

type submitCodeRequest struct {
	ProblemID          string `json:"problem_id"`
	Language           string `json:"language"`
	Code               string `json:"code"`
	CustomInput        string `json:"custom_input"`
	ProblemDescription string `json:"problem_description"`
	SampleInput        string `json:"sample_input"`
	SampleOutput       string `json:"sample_output"`
	RequestID          string `json:"request_id"`
}

// Run handles POST /api/code/run (requires session, does NOT save to submissions).
func (h *CodeHandler) Run(w http.ResponseWriter, r *http.Request) {
	if _, ok := middleware.UserFromContext(r.Context()); !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "authentication required"})
		return
	}

	var req runCodeRequest
	if err := decodeJSONBody(w, r, &req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	res, err := h.codeService.Run(r.Context(), services.CodeRunInput{
		ProblemID:      req.ProblemID,
		Language:       req.Language,
		Code:           req.Code,
		CustomInput:    req.CustomInput,
		ExpectedOutput: req.ExpectedOutput,
	})
	if err != nil {
		switch {
		case errors.Is(err, services.ErrInvalidInput):
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		case errors.Is(err, services.ErrCompilerTimeout):
			writeJSON(w, http.StatusGatewayTimeout, map[string]string{"error": "compiler execution timed out"})
		case errors.Is(err, services.ErrCompilerUnavailable):
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "compiler service unavailable"})
		default:
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to execute code"})
		}
		return
	}

	writeJSON(w, http.StatusOK, res)
}

// Submit handles POST /api/code/submit (requires session, persists submission + analysis).
func (h *CodeHandler) Submit(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.UserFromContext(r.Context())
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "authentication required"})
		return
	}

	var req submitCodeRequest
	if err := decodeJSONBody(w, r, &req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	requestID := req.RequestID
	if requestID == "" {
		requestID = r.Header.Get("Idempotency-Key")
	}

	res, err := h.codeService.Submit(r.Context(), user.ID, services.CodeSubmitInput{
		ProblemID:          req.ProblemID,
		Language:           req.Language,
		Code:               req.Code,
		CustomInput:        req.CustomInput,
		ProblemDescription: req.ProblemDescription,
		SampleInput:        req.SampleInput,
		SampleOutput:       req.SampleOutput,
		RequestID:          requestID,
	})
	if err != nil {
		if errors.Is(err, services.ErrInvalidInput) {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to process submission"})
		return
	}

	writeJSON(w, http.StatusCreated, res)
}
