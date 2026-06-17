import os
import json
import re
import requests
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

ANTHROPIC_HEADERS = {
    "Content-Type": "application/json",
    "anthropic-version": "2023-06-01",
}


def call_claude(user_msg, sys_msg, api_key, max_tokens=800):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={**ANTHROPIC_HEADERS, "x-api-key": api_key},
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
        raise ValueError(f"Kein JSON: {text[:200]}")
    try:
        return json.loads(text[start:end+1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON Fehler: {e} | {text[start:start+200]}")


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
    try:
        if mode == "report":
            text = call_claude(data["user_msg"], data["sys_msg"], api_key, max_tokens=2000)
            parsed = extract_json(text)
            return jsonify(parsed)
        else:
            text = call_claude(data["user_msg"], data["sys_msg"], api_key, max_tokens=800)
            return jsonify({"text": text})
    except requests.HTTPError as e:
        return jsonify({"error": f"API {e.response.status_code}: {e.response.text[:200]}"}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fullreport_stream", methods=["POST"])
def fullreport_stream():
    """Stream a detailed full report directly as text/HTML chunks."""
    data = request.json
    api_key = data.get("api_key", "").strip()
    if not api_key.startswith("sk-ant-"):
        return jsonify({"error": "Ungültiger API Key"}), 401

    area_text = data.get("area_text", "")
    area_label = data.get("area_label", "KV Hotellerie & Gastronomie")

    prompt = f"""Erstelle einen vollständigen, detaillierten Compliance-Bericht für österreichische Payroll-Software auf Basis dieser Recherche:

BEREICH: {area_label}

RECHERCHE-ERGEBNIS:
{area_text}

Strukturiere den Bericht mit folgenden Abschnitten:
1. ZUSAMMENFASSUNG (2-3 Sätze Executive Summary)
2. AKTUELLE RECHTSLAGE (detaillierte Darstellung der aktuellen Situation)
3. KONKRETE AUSWIRKUNGEN AUF PAYROLL-SOFTWARE (technische und rechtliche Implikationen)
4. HANDLUNGSEMPFEHLUNGEN (priorisierte Liste mit konkreten Schritten)
5. DEADLINES & FRISTEN (alle relevanten Termine)
6. RISIKOBEWERTUNG (was passiert bei Nicht-Umsetzung)

Sei präzise, konkret und praxisorientiert. Kein Marketingsprech."""

    def generate():
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={**ANTHROPIC_HEADERS, "x-api-key": api_key},
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 8000,
                    "system": "Du bist Senior Compliance Officer und Payroll-Experte für österreichische Hotellerie und Gastronomie. Schreibe präzise, strukturierte Berichte auf Deutsch.",
                    "stream": True,
                    "messages": [{"role": "user", "content": prompt}]
                },
                stream=True,
                timeout=120
            )
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        line = line[6:]
                        if line == '[DONE]':
                            break
                        try:
                            event = json.loads(line)
                            if event.get('type') == 'content_block_delta':
                                delta = event.get('delta', {})
                                if delta.get('type') == 'text_delta':
                                    text = delta.get('text', '')
                                    yield f"data: {json.dumps({'text': text})}\n\n"
                        except json.JSONDecodeError:
                            continue
            yield "data: {\"done\": true}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
