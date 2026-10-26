"""Authenticated Copilot smoke harness using normal Supabase user sign-in.

Required environment variables: SUPABASE_URL, SUPABASE_ANON_KEY,
AURA_TEST_EMAIL, and AURA_TEST_PASSWORD. Never use a service-role key here.
Set AURA_API_BASE_URL to target a non-default backend.
Pass --offline-test to pause for stopping and restarting Ollama around the offline case.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings


SCENARIOS = {
    "active_crm_typo": "set export bussinesss crm as the active crm",
    "create_rahul": (
        "Add a new lead named Rahul Sharma, email rahul@abctech.com, phone "
        "9876543210, company ABC Technologies, lead source Website, status New."
    ),
    "offline_check": "What leads are in my CRM?",
    "active_crm_variant_1": "Make Export Business CRM my active CRM.",
    "active_crm_variant_2": "Switch my active CRM to Export Business.",
    "active_crm_variant_3": "Activate the Export Business CRM for me.",
}


def require_env() -> tuple[str, str, str, str]:
    # Ignore a host-level DEBUG value that may be a non-boolean release label.
    settings = Settings(debug=False)
    test_env = dotenv_values(Path(__file__).resolve().parents[1] / ".env.test")
    email = os.getenv("AURA_TEST_EMAIL") or test_env.get("AURA_TEST_EMAIL")
    password = os.getenv("AURA_TEST_PASSWORD") or test_env.get("AURA_TEST_PASSWORD")
    missing = [
        name for name, value in (("AURA_TEST_EMAIL", email), ("AURA_TEST_PASSWORD", password))
        if not value
    ]
    if not settings.supabase_url or "<your-project-id>" in settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_anon_key or settings.supabase_anon_key == "mock-anon-key" or settings.supabase_anon_key.startswith("<"):
        missing.append("SUPABASE_ANON_KEY")
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    return settings.supabase_url, settings.supabase_anon_key, str(email), str(password)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-test", action="store_true", help="Pause after normal cases so you can stop Ollama for the offline case, then restart it.")
    args = parser.parse_args()
    try:
        supabase_url, anon_key, email, password = require_env()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    api_base = os.getenv("AURA_API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
    with httpx.Client(timeout=90.0) as client:
        auth = client.post(
            f"{supabase_url.rstrip('/')}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": anon_key},
            json={"email": email, "password": password},
        )
        if auth.status_code != 200:
            print(f"Supabase user sign-in failed: HTTP {auth.status_code}", file=sys.stderr)
            return 3
        access_token = auth.json().get("access_token")
        if not access_token:
            print("Supabase user sign-in response did not include an access token.", file=sys.stderr)
            return 3

        headers = {"Authorization": f"Bearer {access_token}"}
        crms = client.get(f"{api_base}/crm", headers=headers)
        if crms.status_code != 200:
            print(f"Could not list caller-owned CRMs: HTTP {crms.status_code}", file=sys.stderr)
            return 4
        items = crms.json().get("data", {}).get("items", [])
        active = next((crm for crm in items if crm.get("status") == "active"), None)
        if not active:
            print("No active CRM is available for this test user.", file=sys.stderr)
            return 5

        crm_id = active.get("crm_id") or active.get("id")
        before: dict[str, Any] | None = None
        records_url = f"{api_base}/crm/{crm_id}/records/lead"
        before_response = client.get(records_url, headers=headers)
        if before_response.status_code == 200:
            before = before_response.json().get("data", {})

        def run_case(name: str) -> None:
            response = client.post(
                f"{api_base}/copilot/chat",
                headers=headers,
                json={"messages": [{"role": "user", "content": SCENARIOS[name]}], "crm_id": crm_id},
            )
            try:
                body = response.json()
            except ValueError:
                body = {}
            data = body.get("data", {})
            error = body.get("error", {})
            print({
                "scenario": name,
                "http_status": response.status_code,
                "response_source": data.get("response_source") or error.get("response_source"),
                "reply": data.get("reply") or error.get("message"),
                "action": data.get("action"),
            })

        run_case("active_crm_typo")
        run_case("create_rahul")
        if args.offline_test:
            input("Stop Ollama now, then press Enter to run the offline case: ")
            run_case("offline_check")
            input("Restart Ollama now, then press Enter to run the phrasing variants: ")
        for name in ["active_crm_variant_1", "active_crm_variant_2", "active_crm_variant_3"]:
            run_case(name)

        after_response = client.get(records_url, headers=headers)
        if before is not None and after_response.status_code == 200:
            after = after_response.json().get("data", {})
            print({
                "scenario": "rahul_record_count_check",
                "before_total": before.get("total"),
                "after_total": after.get("total"),
                "changed": before.get("total") != after.get("total"),
            })
        else:
            print({"scenario": "rahul_record_count_check", "result": "UNKNOWN: records endpoint did not return 200"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
