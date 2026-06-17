import os
import json
import re
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)


def call_claude(user_msg, sys_msg, api_key, max_tokens=1200):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "system": sys_msg,
            "messages": [{"role": "user", "content": user_msg}]
        },
        timeout=90
    )
    response.raise_for_status()
    data = response.json()
    return " ".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")


def extract_json(text):
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"Kein JSON gefunden: {text[:300]}")
    json_str = text[start:end+1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON Fehler: {e} | Text: {json_str[:300]}")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/research_direct", methods=["POST"])
def research_direct():
    data = request.json
    api_key = data.get("api_key", "").strip()
    if not api_key.startswith("sk-ant-"):
        return jsonify({"error": "Ungültiger API Key"}), 401
    mode = data.get("mode", "research")
    max_tokens = 2500 if mode == "report" else 1200
    try:
        text = call_claude(data["user_msg"], data["sys_msg"], api_key, max_tokens)
        if mode == "report":
            parsed = extract_json(text)
            return jsonify(parsed)
        else:
            return jsonify({"text": text})
    except requests.HTTPError as e:
        return jsonify({"error": f"API Fehler {e.response.status_code}: {e.response.text[:200]}"}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
