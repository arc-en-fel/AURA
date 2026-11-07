"""Optional standalone smoke test script for live Ollama & Qwen 2.5 3B verification.

Usage:
    python backend/scripts/smoke_test_ollama.py
"""
import sys
import httpx

def main():
    base_url = "http://localhost:11434"
    print(f"[*] Checking local Ollama service at {base_url}...")

    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=3.0)
        if resp.status_code != 200:
            print(f"[!] Ollama returned status {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        models = [m.get("name") for m in data.get("models", [])]
        print(f"[+] Ollama service is ONLINE.")
        print(f"[+] Available models on disk: {models if models else 'None'}")

        target_model = "qwen2.5:3b"
        if not any(target_model in m for m in models):
            alt_models = [m for m in models if "qwen" in m or "gemma" in m]
            if alt_models:
                target_model = alt_models[0]
                print(f"[*] 'qwen2.5:3b' not found, testing with available model: '{target_model}'")
            else:
                print(f"[!] Neither 'qwen2.5:3b' nor alternative models found in Ollama.")
                print(f"[*] To pull Qwen: ollama pull qwen2.5:3b")
                return

        print(f"[*] Generating test CRM configuration using model: {target_model}...")
        prompt = "Create a B2B SaaS CRM to track enterprise leads, deals, and ARR value"
        
        # Test generation with OllamaAIProvider
        sys.path.insert(0, "backend")
        from app.services.ollama_provider import OllamaAIProvider
        from app.schemas.crm import CRMConfiguration

        provider = OllamaAIProvider(base_url=base_url, model=target_model, timeout=30.0)
        result = provider.generate_crm_config(prompt)
        config = CRMConfiguration(**result)
        
        print("\n[SUCCESS] Successfully generated and validated CRM configuration!")
        print(f"  Name: {config.name}")
        print(f"  Industry: {config.industry}")
        print(f"  Entities: {[e.name for e in config.entities]}")
        print(f"  Pipeline Stages: {config.pipeline_stages}")

    except httpx.ConnectError:
        print("[!] Connection Refused: Ollama service is not running.")
        print("[*] To start Ollama: run 'ollama serve' in a terminal.")
    except Exception as exc:
        print(f"[!] Live inference error: {exc}")

if __name__ == "__main__":
    main()
