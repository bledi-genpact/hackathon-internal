@echo off
cd /d "%~dp0"
echo Starting all PipelineDoc services...

start "log-collector"    cmd /k "python -m uvicorn agents.log_collector.main:app --port 8001"
start "diagnosis"        cmd /k "python -m uvicorn agents.diagnosis.main:app --port 8002"
start "ownership-router" cmd /k "python -m uvicorn agents.ownership_router.main:app --port 8003"
start "notification"     cmd /k "python -m uvicorn agents.notification.main:app --port 8004"
start "orchestrator"     cmd /k "python -m uvicorn orchestrator.main:app --port 8000"
start "frontend"         cmd /k "python -m streamlit run frontend\app.py --server.port 8501"

echo.
echo All services started:
echo   Orchestrator   http://localhost:8000
echo   Log Collector  http://localhost:8001
echo   Diagnosis      http://localhost:8002
echo   Ownership      http://localhost:8003
echo   Notification   http://localhost:8004
echo   Frontend (UI)  http://localhost:8501
echo.
echo Open the UI: http://localhost:8501
echo Run CLI demo: python demo\simulate_failure.py dbt