# AURA — Self-Evolving CRM

AI-powered, multi-tenant CRM platform built with FastAPI, React, Supabase PostgreSQL, and automated evolutionary schemas.

---

## Architecture Overview

- **Frontend:** React 18, Vite, TypeScript, Tailwind CSS
- **Backend:** Python 3.10+, FastAPI, Pydantic v2, Uvicorn
- **Database & Auth:** Supabase PostgreSQL with Row Level Security (RLS) & Supabase GoTrue Auth
- **AI Brain:** Local LLM / Ollama (`qwen3:4b`), Grok API, or deterministic Mock Provider
- **Port Mapping:**
  - Frontend: `http://localhost:5173`
  - Backend API: `http://localhost:8000/api/v1` (Proxied by Vite at `/api`)
  - Health Endpoint: `http://localhost:8000/api/v1/health` and `/health`
  - OpenAPI Docs: `http://localhost:8000/docs`

---

## Quick Start on Windows

### 1. Prerequisites
- Python 3.10+ (tested with Python 3.11)
- Node.js 18+ and npm
- A configured Supabase project

### 2. Environment Setup

#### Backend (`backend/.env`)
Copy the example template and supply your Supabase project credentials:
```powershell
copy backend\.env.example backend\.env
```
Key settings:
- `SUPABASE_URL`: Your Supabase project URL (e.g., `https://<ref>.supabase.co`)
- `SUPABASE_ANON_KEY`: Your Supabase publishable anon key
- `SUPABASE_JWT_SECRET`: (Optional) JWT secret for local HS256 verification (if omitted, tokens are verified via Supabase Auth GoTrue)
- `LLM_PROVIDER`: `mock`, `local` (Ollama), or `grok`

#### Frontend (`frontend/.env`)
Copy the example template:
```powershell
copy frontend\.env.example frontend\.env
```
Key settings:
- `VITE_API_BASE_URL`: `/api/v1` (proxied to port 8000 by Vite)
- `VITE_SUPABASE_URL`: Public Supabase project URL
- `VITE_SUPABASE_ANON_KEY`: Public publishable anon key (NEVER put service-role key in frontend!)
- `VITE_USE_MOCK`: `false` (enables live FastAPI integration; set to `true` only for standalone offline mock adapter)

### 3. Install Dependencies

#### Backend:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
cd ..
```

#### Frontend:
```powershell
cd frontend
npm install
cd ..
```

### 4. Running the Application Together

Double-click or run from PowerShell:
```powershell
.\start-dev.bat
```
`start-dev.bat` automatically verifies the virtual environment, checks dependencies, launches the FastAPI backend on port 8000, and starts the Vite frontend on port 5173 in separate terminals.

---

## Health Check & Verification Procedure

1. **Verify Backend Readiness:**
   ```powershell
   curl http://localhost:8000/api/v1/health
   ```
   Expected response:
   ```json
   {
     "data": {
       "status": "ok",
       "app_name": "Self-Evolving CRM",
       "version": "0.1.0",
       "environment": "development",
       "database": "configured",
       "auth": "configured"
     },
     "meta": {"request_id": "req_..."}
   }
   ```

2. **Verify Frontend Integration via UI:**
   Navigate to `http://localhost:5173/settings` (System Settings & Integration Status):
   - **FastAPI Backend:** Should display `Connected & Healthy` with active `/api/v1/health` status.
   - **Supabase Authentication:** Should display `Configured` with active session verification.
   - **Frontend Adapter Mode:** Should display `FastAPI Live`.

3. **Run Automated Test Suites:**
   - Backend tests (pytest):
     ```powershell
     cd backend
     .\.venv\Scripts\python.exe -m pytest
     ```
   - Frontend verification & audit suite:
     ```powershell
     cd frontend
     npm test
     ```
   - Frontend production build:
     ```powershell
     cd frontend
     npm run build
     ```

---

## Troubleshooting on Windows

- **Port 8000 occupied:**
  Check listening processes:
  ```powershell
  Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
  ```
- **Backend reports offline in Settings:**
  Ensure backend was started with `--port 8000` (matching `frontend/vite.config.ts`).
- **Silent Mock Fallback Guard:**
  When `FastAPI Live` is active, the frontend strictly raises and displays backend errors rather than silently substituting mock data. To use mock data for offline testing, explicitly switch to `Mock Adapter` in Settings.

