import json
import urllib.request

url = "http://localhost:11434/api/generate"
payload = {
    "model": "qwen3:4b",
    "prompt": "Write a Python hello-world program.",
    "stream": False
}

request = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

with urllib.request.urlopen(request, timeout=180) as response:
    result = json.loads(response.read().decode("utf-8"))

print("Model:", result.get("model"))
print("Response:")
print(result.get("response", "No response returned"))
