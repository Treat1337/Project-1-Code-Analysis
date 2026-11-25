package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"code-analysis-backend/internal/config"
	"code-analysis-backend/internal/database"
	"code-analysis-backend/internal/handlers"
	"code-analysis-backend/internal/repositories"
	"code-analysis-backend/internal/routes"
	"code-analysis-backend/internal/services"
	"code-analysis-backend/migrations"
)

func main() {
	cfg := config.Load(".env")

	db, err := database.OpenSQLite(cfg.SQLitePath)
	if err != nil {
		log.Fatalf("failed to open sqlite: %v", err)
	}
	defer db.Close()

	initCtx, cancelInit := context.WithTimeout(context.Background(), 15*time.Second)
	if err := database.Migrate(initCtx, db, migrations.FS); err != nil {
		cancelInit()
		log.Fatalf("failed to run migrations: %v", err)
	}
	cancelInit()

	userRepo := repositories.NewUserRepository(db)
	sessionRepo := repositories.NewSessionRepository(db)
	submissionRepo := repositories.NewSubmissionRepository(db)
	authService := services.NewAuthService(userRepo, sessionRepo, cfg.SessionTTL, cfg.SessionTokenPepper)

	compilerClient := services.NewHTTPCompilerClient(cfg.CompilerServiceURL, cfg.CompilerRunPath, cfg.CompilerTimeout)
	aiClient := services.NewHTTPAIClient(cfg.AIServiceURL, cfg.AIPredictPath, cfg.AITimeout)
	codeService := services.NewCodeService(compilerClient, aiClient, submissionRepo, cfg.MaxCodeBytes, cfg.PipelineVersion)

	authHandler := handlers.NewAuthHandler(authService, cfg)
	healthHandler := handlers.NewHealthHandler(db)
	codeHandler := handlers.NewCodeHandler(codeService)
	submissionHandler := handlers.NewSubmissionHandler(codeService)

	router := routes.NewRouter(routes.Dependencies{
		Config:            cfg,
		AuthService:       authService,
		AuthHandler:       authHandler,
		HealthHandler:     healthHandler,
		CodeHandler:       codeHandler,
		SubmissionHandler: submissionHandler,
	})

	srv := &http.Server{
		Addr:              cfg.Addr(),
		Handler:           router,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	bgCtx, stopBg := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stopBg()

	// Background maintenance: clean expired sessions & run periodic SQLite backups.
	go func() {
		cleanupTicker := time.NewTicker(15 * time.Minute)
		backupTicker := time.NewTicker(cfg.BackupInterval)
		defer cleanupTicker.Stop()
		defer backupTicker.Stop()

		for {
			select {
			case <-bgCtx.Done():
				return
			case <-cleanupTicker.C:
				ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
				if removed, err := authService.CleanupExpiredSessions(ctx); err != nil {
					log.Printf("session cleanup error: %v", err)
				} else if removed > 0 {
					log.Printf("cleaned up %d expired sessions", removed)
				}
				cancel()
			case <-backupTicker.C:
				ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
				if path, err := database.Backup(ctx, db, cfg.BackupDir); err != nil {
					log.Printf("sqlite backup error: %v", err)
				} else {
					log.Printf("sqlite backup created: %s", path)
				}
				cancel()
			}
		}
	}()

	go func() {
		log.Printf("Go auth backend listening on http://%s (env=%s)", cfg.Addr(), cfg.AppEnv)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}
	}()

	<-bgCtx.Done()
	log.Println("shutting down Go backend...")

	shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelShutdown()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Printf("graceful shutdown error: %v", err)
	}
}
