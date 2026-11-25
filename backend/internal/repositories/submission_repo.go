package repositories

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"code-analysis-backend/internal/database"
	"code-analysis-backend/internal/models"
)

var ErrSubmissionNotFound = errors.New("submission not found")

type SubmissionRepository struct {
	db *sql.DB
}

func NewSubmissionRepository(db *sql.DB) *SubmissionRepository {
	return &SubmissionRepository{db: db}
}

// GetByRequestIDForUser returns an existing submission for (userID, requestID) if present.
func (r *SubmissionRepository) GetByRequestIDForUser(ctx context.Context, userID int64, requestID string) (models.Submission, error) {
	sub, err := scanSubmissionRow(r.db.QueryRowContext(
		ctx,
		`SELECT id, user_id, source_code, language, problem_id, status,
		        compile_status, analysis_result, error_summary, model_version, created_at
		 FROM submissions
		 WHERE user_id = ? AND request_id = ?`,
		userID, requestID,
	))
	if errors.Is(err, sql.ErrNoRows) {
		return models.Submission{}, ErrSubmissionNotFound
	}
	if err != nil {
		return models.Submission{}, fmt.Errorf("get submission by request_id: %w", err)
	}
	return sub, nil
}

// CreateProcessing inserts a new submission row with status='processing' inside a transaction.
func (r *SubmissionRepository) CreateProcessing(
	ctx context.Context,
	userID int64,
	sourceCode string,
	language string,
	problemID string,
	requestID string,
) (models.Submission, error) {
	var sub models.Submission
	var reqIDPtr *string
	if requestID != "" {
		reqIDPtr = &requestID
	}

	err := database.WithTx(ctx, r.db, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(
			ctx,
			`INSERT INTO submissions (user_id, source_code, language, problem_id, status, request_id)
			 VALUES (?, ?, ?, ?, 'processing', ?)`,
			userID, sourceCode, language, problemID, reqIDPtr,
		)
		if err != nil {
			return fmt.Errorf("insert submission: %w", err)
		}

		id, err := res.LastInsertId()
		if err != nil {
			return fmt.Errorf("submission last insert id: %w", err)
		}

		sub, err = scanSubmissionRow(tx.QueryRowContext(
			ctx,
			`SELECT id, user_id, source_code, language, problem_id, status,
			        compile_status, analysis_result, error_summary, model_version, created_at
			 FROM submissions WHERE id = ?`,
			id,
		))
		return err
	})

	return sub, err
}

// UpdateResult updates an existing submission owned by userID inside a transaction.
func (r *SubmissionRepository) UpdateResult(
	ctx context.Context,
	submissionID int64,
	userID int64,
	status string,
	compileStatus *string,
	analysisResult *string,
	errorSummary *string,
	modelVersion *string,
) (models.Submission, error) {
	var sub models.Submission

	err := database.WithTx(ctx, r.db, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(
			ctx,
			`UPDATE submissions
			 SET status = ?, compile_status = ?, analysis_result = ?, error_summary = ?, model_version = ?
			 WHERE id = ? AND user_id = ?`,
			status, compileStatus, analysisResult, errorSummary, modelVersion, submissionID, userID,
		)
		if err != nil {
			return fmt.Errorf("update submission: %w", err)
		}
		affected, _ := res.RowsAffected()
		if affected == 0 {
			return ErrSubmissionNotFound
		}

		sub, err = scanSubmissionRow(tx.QueryRowContext(
			ctx,
			`SELECT id, user_id, source_code, language, problem_id, status,
			        compile_status, analysis_result, error_summary, model_version, created_at
			 FROM submissions WHERE id = ? AND user_id = ?`,
			submissionID, userID,
		))
		return err
	})

	return sub, err
}

// SubmissionStats holds verified submission counts derived strictly from compiler/execution verdicts.
type SubmissionStats struct {
	Total         int `json:"total"`
	Accepted      int `json:"accepted"`
	Incorrect     int `json:"incorrect"`
	CompileErrors int `json:"compile_errors"`
}

// StatsByUser computes submission overview counts from SQLite for userID.
func (r *SubmissionRepository) StatsByUser(ctx context.Context, userID int64) (SubmissionStats, error) {
	var stats SubmissionStats
	err := r.db.QueryRowContext(
		ctx,
		`SELECT
			COUNT(1) AS total,
			COALESCE(SUM(CASE WHEN LOWER(COALESCE(json_extract(analysis_result, '$.compiler.verdict'), '')) = 'accepted' THEN 1 ELSE 0 END), 0) AS accepted,
			COALESCE(SUM(CASE
				WHEN compile_status = 'compile_error' OR status = 'compile_error' THEN 1
				ELSE 0
			END), 0) AS compile_errors,
			COALESCE(SUM(CASE
				WHEN compile_status != 'compile_error'
				 AND status != 'compile_error'
				 AND LOWER(COALESCE(json_extract(analysis_result, '$.compiler.verdict'), '')) NOT IN ('', 'accepted')
				THEN 1 ELSE 0
			END), 0) AS incorrect
		 FROM submissions
		 WHERE user_id = ?`,
		userID,
	).Scan(&stats.Total, &stats.Accepted, &stats.CompileErrors, &stats.Incorrect)
	if err != nil {
		return SubmissionStats{}, fmt.Errorf("query submission stats: %w", err)
	}
	return stats, nil
}

// ListByUser returns paginated submissions for userID ordered by created_at, optionally filtered by status and search query.
func (r *SubmissionRepository) ListByUser(
	ctx context.Context,
	userID int64,
	statusFilter string,
	limit int,
	offset int,
) ([]models.Submission, int, error) {
	var total int
	var countErr error
	if statusFilter != "" {
		countErr = r.db.QueryRowContext(
			ctx,
			`SELECT COUNT(1) FROM submissions WHERE user_id = ? AND status = ?`,
			userID, statusFilter,
		).Scan(&total)
	} else {
		countErr = r.db.QueryRowContext(
			ctx,
			`SELECT COUNT(1) FROM submissions WHERE user_id = ?`,
			userID,
		).Scan(&total)
	}
	if countErr != nil {
		return nil, 0, fmt.Errorf("count submissions: %w", countErr)
	}

	var rows *sql.Rows
	var queryErr error
	if statusFilter != "" {
		rows, queryErr = r.db.QueryContext(
			ctx,
			`SELECT id, user_id, source_code, language, problem_id, status,
			        compile_status, analysis_result, error_summary, model_version, created_at
			 FROM submissions
			 WHERE user_id = ? AND status = ?
			 ORDER BY created_at DESC, id DESC
			 LIMIT ? OFFSET ?`,
			userID, statusFilter, limit, offset,
		)
	} else {
		rows, queryErr = r.db.QueryContext(
			ctx,
			`SELECT id, user_id, source_code, language, problem_id, status,
			        compile_status, analysis_result, error_summary, model_version, created_at
			 FROM submissions
			 WHERE user_id = ?
			 ORDER BY created_at DESC, id DESC
			 LIMIT ? OFFSET ?`,
			userID, limit, offset,
		)
	}
	if queryErr != nil {
		return nil, 0, fmt.Errorf("list submissions: %w", queryErr)
	}
	defer rows.Close()

	items := make([]models.Submission, 0)
	for rows.Next() {
		sub, err := scanSubmissionRow(rows)
		if err != nil {
			return nil, 0, err
		}
		items = append(items, sub)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("iterate submissions: %w", err)
	}
	return items, total, nil
}

// GetByIDForUser fetches a single submission only if it belongs to userID.
func (r *SubmissionRepository) GetByIDForUser(ctx context.Context, submissionID, userID int64) (models.Submission, error) {
	sub, err := scanSubmissionRow(r.db.QueryRowContext(
		ctx,
		`SELECT id, user_id, source_code, language, problem_id, status,
		        compile_status, analysis_result, error_summary, model_version, created_at
		 FROM submissions
		 WHERE id = ? AND user_id = ?`,
		submissionID, userID,
	))
	if errors.Is(err, sql.ErrNoRows) {
		return models.Submission{}, ErrSubmissionNotFound
	}
	if err != nil {
		return models.Submission{}, fmt.Errorf("get submission: %w", err)
	}
	return sub, nil
}

// DeleteByIDForUser deletes a submission only if it belongs to userID.
func (r *SubmissionRepository) DeleteByIDForUser(ctx context.Context, submissionID, userID int64) error {
	res, err := r.db.ExecContext(
		ctx,
		`DELETE FROM submissions WHERE id = ? AND user_id = ?`,
		submissionID, userID,
	)
	if err != nil {
		return fmt.Errorf("delete submission: %w", err)
	}
	affected, _ := res.RowsAffected()
	if affected == 0 {
		return ErrSubmissionNotFound
	}
	return nil
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanSubmissionRow(s rowScanner) (models.Submission, error) {
	var sub models.Submission
	var compileStatus, analysisResult, errorSummary, modelVersion sql.NullString

	err := s.Scan(
		&sub.ID,
		&sub.UserID,
		&sub.SourceCode,
		&sub.Language,
		&sub.ProblemID,
		&sub.Status,
		&compileStatus,
		&analysisResult,
		&errorSummary,
		&modelVersion,
		&sub.CreatedAt,
	)
	if err != nil {
		return models.Submission{}, err
	}

	if compileStatus.Valid {
		v := compileStatus.String
		sub.CompileStatus = &v
	}
	if analysisResult.Valid {
		v := analysisResult.String
		sub.AnalysisResult = &v
	}
	if errorSummary.Valid {
		v := errorSummary.String
		sub.ErrorSummary = &v
	}
	if modelVersion.Valid {
		v := modelVersion.String
		sub.ModelVersion = &v
	}
	return sub, nil
}
