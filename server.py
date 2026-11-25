"""
server.py — Backward-compatibility wrapper for app.main:app.

The monolithic server.py has been refactored into:
- app/main.py (FastAPI app factory & middleware)
- app/config.py (Pathlib-based centralized config)
- app/api/problems.py (Problems endpoints)
- app/api/judge.py (C++ compiler & runner endpoints)
- app/api/ai.py (Ollama proxy & AI model endpoints)
- app/services/dataset_loader.py (Project_CodeNet reader)

This file is preserved so that existing tools/scripts (e.g., start_all.py)
calling `uvicorn server:app` continue to function seamlessly.
"""
from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT
    print(f"Starting refactored FastAPI backend on http://{HOST}:{PORT} ...")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
