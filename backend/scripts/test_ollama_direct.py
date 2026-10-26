"""Direct Ollama connectivity test. Run from backend/ directory."""
import httpx
import time

payload = {
    "model": "qwen2.5:3b",
    "prompt": (
        '<|im_start|>system\nYou are a JSON generator. Output only valid JSON.<|im_end|>\n'
        '<|im_start|>user\nGenerate this exact JSON: {"name": "Test CRM", "industry": "saas"}<|im_end|>\n'
        '<|im_start|>assistant\n'
    ),
    "format": "json",
    "stream": False,
    "think": False,
    "options": {"temperature": 0.1, "top_p": 0.9},
}

print("Sending request to Ollama (think=false, timeout=120s)...")
t0 = time.perf_counter()
try:
    with httpx.Client(timeout=120.0) as client:
        resp = client.post("http://localhost:11434/api/generate", json=payload)
        elapsed = time.perf_counter() - t0
        print(f"Status:          {resp.status_code}")
        print(f"Time:            {elapsed:.1f}s")
        data = resp.json()
        print(f"Response:        {data.get('response', '')[:200]}")
        thinking = data.get("thinking", "")
        print(f"Thinking tokens: {len(thinking)} ({'DISABLED ✓' if not thinking else 'still active'})")
        print(f"Done:            {data.get('done')}")
except Exception as e:
    elapsed = time.perf_counter() - t0
    print(f"Error after {elapsed:.1f}s: {e}")
