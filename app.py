import os
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)


def call_claude(user_msg, sys_msg, api_key):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 1000,
            "system": sys_msg,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{"role": "user", "content": user_msg}]
        },
        timeout=60
    )
    response.raise_for_status()
    data = response.json()
    return " ".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/research_direct", methods=["POST"])
def research_direct():
    data = request.json
    api_key = data.get("api_key", "").strip()
    if not api_key.startswith("sk-ant-"):
        return jsonify({"error": "Ungültiger API Key"}), 401
    try:
        text = call_claude(data["user_msg"], data["sys_msg"], api_key)
        return jsonify({"text": text})
    except requests.HTTPError as e:
        return jsonify({"error": f"Anthropic API Fehler: {e.response.status_code}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
