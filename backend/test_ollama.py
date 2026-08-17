import requests

payload = {
    "model": "qwen2.5:7b",
    "prompt": 'Return ONLY {"name":"John"}',
    "stream": False,
}

response = requests.post(
    "http://localhost:11434/api/generate",
    json=payload,
    timeout=60,
)

print(response.status_code)
print(response.json())