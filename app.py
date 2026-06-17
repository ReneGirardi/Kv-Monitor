import os
import json
import re
import requests
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

HEADERS = {
    "Content-Type": "application/json",
    "anthropic-version": "2023-06-01",
}

AREAS = [
    {"id": "kv",   "icon": "🏨", "label": "KV Hotellerie & Gastronomie",   "query": "Kollektivvertrag Hotellerie Gastronomie Österreich 2025 Lohnerhöhung Aufsaugklausel Stufensystem aktuell"},
    {"id": "elda", "icon": "📡", "label": "ELDA / Transfer Webservice",    "query": "ELDA Abschaltung 2027 Transfer Webservice V4 ÖGK Nachfolge Umstieg Österreich 2025"},
    {"id": "bgbl", "icon": "⚖️", "label": "BGBl Arbeitsrecht",             "query": "Bundesgesetzblatt Österreich Arbeitsrecht 2025 Änderungen Dienstvertrag Lohnrecht aktuell"},
    {"id": "eu",   "icon": "🇪🇺", "label": "EU – eIDAS & Pay Transparency", "query": "eIDAS 2 Pay Transparency Directive 2023/970 Umsetzung Österreich 2025"},
]


def call_claude(user_msg, sys_msg, api_key, max_tokens=800):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={**HEADERS, "x-api-key": api_key},
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "system": sys_msg,
            "messages": [{"role": "user", "content": user_msg}]
        },
        timeout=90
    )
    r.raise_for_status()
    data = r.json()
    return " ".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/areas")
def get_areas():
    return jsonify(AREAS)


@app.route("/api/research", methods=["POST"])
def research():
    data = request.json
    api_key = data.get("api_key", "").strip()
    if not api_key.startswith("sk-ant-"):
        return jsonify({"error": "Ungültiger API Key"}), 401
    area = next((a for a in AREAS if a["id"] == data.get("area_id")), None)
    if not area:
        return jsonify({"error": "Unbekannter Bereich"}), 400
    try:
        text = call_claude(
            f'Recherchiere: "{area["query"]}"\n\nLiefere:\n1. Top 3 aktuelle Entwicklungen mit Datum\n2. Auswirkung auf Payroll-Software österreichische Hotellerie\n3. Handlungsempfehlung + Deadline\n4. Dringlichkeit: KRITISCH / HOCH / MITTEL / INFO',
            "Du bist Payroll-Compliance-Experte für österreichische Hotellerie. Deutsch, konkret, max 300 Wörter.",
            api_key, 600
        )
        prio = "KRITISCH" if "KRITISCH" in text else "HOCH" if "HOCH" in text else "INFO" if re.search(r'\bINFO\b', text) else "MITTEL"
        return jsonify({"text": text, "prio": prio})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fullreport_stream", methods=["POST"])
def fullreport_stream():
    data = request.json
    api_key = data.get("api_key", "").strip()
    if not api_key.startswith("sk-ant-"):
        return jsonify({"error": "Ungültiger API Key"}), 401

    area_id   = data.get("area_id")
    area_text = data.get("area_text", "")
    area      = next((a for a in AREAS if a["id"] == area_id), {"label": area_id})

    prompt = f"""Erstelle einen vollständigen Compliance-Bericht für österreichische Payroll-Software:

BEREICH: {area["label"]}
RECHERCHE:
{area_text}

Struktur:
## Zusammenfassung
## Aktuelle Rechtslage
## Auswirkungen auf Payroll-Software
## Handlungsempfehlungen
## Deadlines & Fristen
## Risikobewertung

Präzise, konkret, praxisorientiert. Kein Marketingsprech."""

    def generate():
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={**HEADERS, "x-api-key": api_key},
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 8000,
                    "system": "Senior Compliance Officer, Payroll-Experte österreichische Hotellerie. Schreibe strukturierte Berichte auf Deutsch.",
                    "stream": True,
                    "messages": [{"role": "user", "content": prompt}]
                },
                stream=True, timeout=120
            )
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        try:
                            evt = json.loads(chunk)
                            if evt.get("type") == "content_block_delta":
                                t = evt.get("delta", {}).get("text", "")
                                if t:
                                    yield f"data: {json.dumps({'text': t})}\n\n"
                        except Exception:
                            continue
            yield 'data: {"done":true}\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)})}\n\n'

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
