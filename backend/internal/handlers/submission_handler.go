package handlers

import (
	"errors"
	"net/http"
	"strconv"

	"code-analysis-backend/internal/middleware"
	"code-analysis-backend/internal/repositories"
	"code-analysis-backend/internal/services"
)

type SubmissionHandler struct {
	codeService *services.CodeService
}

func NewSubmissionHandler(codeService *services.CodeService) *SubmissionHandler {
	return &SubmissionHandler{codeService: codeService}
}

// Stats handles GET /api/submissions/stats.
func (h *SubmissionHandler) Stats(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.UserFromContext(r.Context())
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "authentication required"})
		return
	}

	stats, err := h.codeService.GetSubmissionStats(r.Context(), user.ID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to load submission stats"})
		return
	}
	writeJSON(w, http.StatusOK, stats)
}

// List handles GET /api/submissions?page=1&limit=20&status=...
func (h *SubmissionHandler) List(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.UserFromContext(r.Context())
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "authentication required"})
		return
	}

	q := r.URL.Query()
	page, _ := strconv.Atoi(q.Get("page"))
	if page < 1 {
		page = 1
	}
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit < 1 || limit > 100 {
		limit = 20
	}
	statusFilter := q.Get("status")

	items, total, err := h.codeService.ListSubmissions(r.Context(), user.ID, statusFilter, page, limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to list submissions"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"submissions": items,
		"page":        page,
		"limit":       limit,
		"total":       total,
	})
}

// GetByID handles GET /api/submissions/{id}.
func (h *SubmissionHandler) GetByID(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.UserFromContext(r.Context())
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "authentication required"})
		return
	}

	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid submission id"})
		return
	}

	sub, err := h.codeService.GetSubmission(r.Context(), id, user.ID)
	if err != nil {
		if errors.Is(err, repositories.ErrSubmissionNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "submission not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to fetch submission"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{"submission": sub})
}

// DeleteByID handles DELETE /api/submissions/{id}.
func (h *SubmissionHandler) DeleteByID(w http.ResponseWriter, r *http.Request) {
	user, ok := middleware.UserFromContext(r.Context())
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "authentication required"})
		return
	}

	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid submission id"})
		return
	}

	if err := h.codeService.DeleteSubmission(r.Context(), id, user.ID); err != nil {
		if errors.Is(err, repositories.ErrSubmissionNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "submission not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "failed to delete submission"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{"message": "submission deleted"})
}
