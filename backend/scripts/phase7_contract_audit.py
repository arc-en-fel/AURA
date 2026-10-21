"""Phase 7 — API contract compliance audit script.

Run from backend/ directory:
    .venv/Scripts/python.exe scripts/phase7_contract_audit.py
"""
from __future__ import annotations

import uuid as uuidmod
from fastapi.testclient import TestClient
from jose import jwt
from app.main import create_app
from app.config import get_settings

settings = get_settings()
if not settings.supabase_jwt_secret:
    settings.supabase_jwt_secret = "test-jwt-secret-key-32-chars-minimum-length!"

app = create_app()
client = TestClient(app, raise_server_exceptions=False)

token = jwt.encode(
    {"sub": "00000000-0000-0000-0000-000000000099", "aud": "authenticated", "exp": 9999999999},
    settings.supabase_jwt_secret,
    algorithm="HS256",
)
auth = {"Authorization": f"Bearer {token}"}

passed = 0
failed = 0


def check(label: str, resp, expected_status: int, checks: dict):
    global passed, failed
    ok = resp.status_code == expected_status
    body = resp.json()
    details = []
    for key, expected in checks.items():
        parts = key.split(".")
        val = body
        for p in parts:
            val = val.get(p, "__MISSING__") if isinstance(val, dict) else "__MISSING__"
        match = val == expected
        if not match:
            details.append(f"    {key}: got={val!r} want={expected!r}")
        ok = ok and match
    if ok:
        passed += 1
        print(f"PASS [{resp.status_code}] {label}")
    else:
        failed += 1
        print(f"FAIL [{resp.status_code}] {label}")
        for d in details:
            print(d)


def check_bool(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS {label}")
    else:
        failed += 1
        print(f"FAIL {label}" + (f": {detail}" if detail else ""))


print("=" * 60)
print("Phase 7 — API Contract Compliance Audit")
print("=" * 60)

# ── 1. Health endpoint ──────────────────────────────────────────────
print("\n── Health ──")
r = client.get("/api/v1/health")
check("GET /api/v1/health returns 200", r, 200, {"data.status": "ok"})
b = r.json()
check_bool(
    "GET /api/v1/health has meta.request_id",
    bool(b.get("meta", {}).get("request_id", "")),
)

# ── 2. Auth enforcement ─────────────────────────────────────────────
print("\n── Auth enforcement (no token → 401) ──")
for method, url, body in [
    ("GET",  "/api/v1/crm", None),
    ("POST", "/api/v1/crm", {"configuration": {}}),
    ("POST", "/api/v1/crm/generate", {"prompt": "test prompt here"}),
    ("GET",  "/api/v1/crm/00000000-0000-0000-0000-000000000001", None),
]:
    fn = getattr(client, method.lower())
    r = fn(url, json=body) if body else fn(url)
    check(f"Auth required: {method} {url}", r, 401, {"error.code": "UNAUTHENTICATED"})

# ── 3. CRM generate — response shape and draft semantics ───────────
print("\n── POST /crm/generate ──")
r = client.post(
    "/api/v1/crm/generate",
    json={"prompt": "Build a SaaS CRM to track enterprise software leads and deals"},
    headers=auth,
)
check("POST /crm/generate → 200", r, 200, {})
b = r.json()
check_bool("POST /crm/generate has data.configuration", "configuration" in b.get("data", {}))
check_bool("POST /crm/generate has data.warnings list", isinstance(b.get("data", {}).get("warnings"), list))
check_bool("POST /crm/generate schema_version=1.0", b.get("data", {}).get("configuration", {}).get("schema_version") == "1.0")
check_bool("POST /crm/generate draft-only (no crm_id in data)", "crm_id" not in b.get("data", {}))
check_bool("POST /crm/generate has meta.request_id", bool(b.get("meta", {}).get("request_id")))

# prompt too short
r = client.post("/api/v1/crm/generate", json={"prompt": "short"}, headers=auth)
check("POST /crm/generate prompt too short → 422", r, 422, {"error.code": "VALIDATION_ERROR"})

# SQL injection blocked
r = client.post(
    "/api/v1/crm/generate",
    json={"prompt": "Create a CRM; UNION SELECT star FROM users-- inject"},
    headers=auth,
)
check_bool(
    "POST /crm/generate SQL injection → 502 AI_PROVIDER_ERROR",
    r.status_code == 502 and r.json().get("error", {}).get("code") == "AI_PROVIDER_ERROR",
    f"got {r.status_code} {r.json().get('error',{}).get('code')}",
)

# ── 4. Save CRM — validation ────────────────────────────────────────
print("\n── POST /crm (save) ──")
r = client.post("/api/v1/crm", json={}, headers=auth)
check("POST /crm missing body → 422", r, 422, {"error.code": "VALIDATION_ERROR"})

# ── 5. Error envelope shape ─────────────────────────────────────────
print("\n── Error envelope ──")
r = client.get("/api/v1/crm/not-a-valid-uuid", headers=auth)
b = r.json()
check_bool(
    "Error envelope has error.code + error.message + error.request_id",
    all(k in b.get("error", {}) for k in ("code", "message", "request_id")),
    str(b),
)
# Error envelope must NOT expose stack traces
body_str = str(b)
check_bool(
    "Error response does not contain 'Traceback' or raw exception",
    "Traceback" not in body_str and "Exception" not in body_str,
    body_str[:200],
)

# ── 6. Evolution objective — contract validation ────────────────────
print("\n── Evolution proposal ──")
fake_crm = str(uuidmod.uuid4())

r = client.post(
    f"/api/v1/crm/{fake_crm}/evolution/proposals",
    json={"objective": "hack_database"},
    headers=auth,
)
check("Evolution invalid objective → 422", r, 422, {"error.code": "VALIDATION_ERROR"})

r = client.post(
    f"/api/v1/crm/{fake_crm}/evolution/proposals",
    json={"objective": "improve_follow_up"},
)
check("Evolution unauthenticated → 401", r, 401, {"error.code": "UNAUTHENTICATED"})

# ── 7. PATCH /configuration always 403 ─────────────────────────────
print("\n── PATCH /crm/{id}/configuration ──")
r = client.patch(f"/api/v1/crm/{fake_crm}/configuration", json={}, headers=auth)
check("PATCH /configuration → 403 FORBIDDEN", r, 403, {"error.code": "FORBIDDEN"})

# ── 8. Records auth + entity validation ────────────────────────────
print("\n── Records ──")
r = client.post(
    f"/api/v1/crm/{fake_crm}/records/lead",
    json={"data": {"full_name": "Test"}},
)
check("POST /records unauthenticated → 401", r, 401, {"error.code": "UNAUTHENTICATED"})

# ── 9. Workflow creation — invalid trigger rejected ─────────────────
print("\n── Workflows ──")
r = client.post(
    f"/api/v1/crm/{fake_crm}/workflows",
    json={
        "name": "Test",
        "trigger": {"type": "record.deleted", "entity": "lead"},  # not in allowlist
        "actions": [{"type": "create_follow_up_task", "delay_hours": 4}],
    },
    headers=auth,
)
check_bool(
    "POST /workflows disallowed trigger type → 422",
    r.status_code == 422,
    f"got {r.status_code}",
)

# ── 10. Response never leaks secrets ───────────────────────────────
print("\n── Security: no secret leakage ──")
for label, resp in [
    ("health", client.get("/api/v1/health")),
    ("generate", client.post("/api/v1/crm/generate",
        json={"prompt": "Build a real estate CRM for property management"},
        headers=auth)),
]:
    body_str = str(resp.json())
    no_service_key = "service_role" not in body_str
    no_jwt_secret = "jwt_secret" not in body_str.lower()
    no_db_error = "psycopg" not in body_str and "sqlalchemy" not in body_str.lower()
    check_bool(
        f"No secrets/raw DB errors in {label} response",
        no_service_key and no_jwt_secret and no_db_error,
        body_str[:200],
    )

# ── Summary ────────────────────────────────────────────────────────
print()
print("=" * 60)
total = passed + failed
print(f"Result: {passed}/{total} checks passed, {failed} failed")
print("=" * 60)
