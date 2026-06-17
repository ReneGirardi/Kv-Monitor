import os
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

AREAS = [
    {
        "id": "kv",
        "icon": "🏨",
        "label": "KV Hotellerie & Gastronomie",
        "query": "Kollektivvertrag Hotellerie Gastronomie Österreich 2025 Lohnerhöhung Aufsaugklausel Stufensystem aktuell NEU"
    },
    {
        "id": "elda",
        "icon": "📡",
        "label": "ELDA / Transfer Webservice",
        "query": "ELDA Abschaltung 2027 Transfer Webservice V4 ÖGK Nachfolge Umstieg Österreich 2025 aktuell"
    },
    {
        "id": "bgbl",
        "icon": "⚖️",
        "label": "BGBl Arbeitsrecht",
        "query": "Bundesgesetzblatt Österreich Arbeitsrecht 2025 Änderungen Dienstvertrag Lohnrecht aktuell NEU"
    },
    {
        "id": "eu",
        "icon": "🇪🇺",
        "label": "EU – eIDAS & Pay Transparency",
        "query": "eIDAS 2 Pay Transparency Directive 2023/970 Umsetzung Österreich 2025 aktuell"
    }
]


def call_claude(user_msg, system_msg):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "interleaved-thinking-2025-05-14"
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 1000,
            "system": system_msg,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{"role": "user", "content": user_msg}]
        },
        timeout=60
    )
    response.raise_for_status()
    data = response.json()
    return " ".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")


def get_priority(text):
    if "KRITISCH" in text:
        return "KRITISCH"
    if "HOCH" in text:
        return "HOCH"
    if "INFO" in text and "HOCH" not in text and "KRITISCH" not in text:
        return "INFO"
    return "MITTEL"


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/research", methods=["POST"])
def research():
    data = request.json
    area_id = data.get("area_id")
    area = next((a for a in AREAS if a["id"] == area_id), None)
    if not area:
        return jsonify({"error": "Unknown area"}), 400

    try:
        text = call_claude(
            f'Recherchiere JETZT die aktuellsten Entwicklungen zu: "{area["query"]}"\n\n'
            f'Liefere:\n'
            f'1. Top 3 aktuelle Entwicklungen mit Datum\n'
            f'2. Konkrete Auswirkung auf Payroll-Software österreichische Hotellerie\n'
            f'3. Handlungsempfehlung + Deadline\n'
            f'4. Dringlichkeit: KRITISCH / HOCH / MITTEL / INFO',
            "Du bist Payroll-Compliance-Experte für österreichische Hotellerie und Gastronomie. "
            "Antworte NUR auf Deutsch. Konkret, keine Floskeln."
        )
        return jsonify({"text": text, "prio": get_priority(text)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/report", methods=["POST"])
def report():
    data = request.json
    results = data.get("results", {})

    combined = "\n\n".join(
        f'=== {a["label"]} ===\nPrio: {results.get(a["id"], {}).get("prio", "?")}\n{results.get(a["id"], {}).get("text", "")}'
        for a in AREAS
    )

    try:
        raw = call_claude(
            f'Erstelle Executive Report aus:\n\n{combined}\n\n'
            f'Antworte NUR als reines JSON ohne Backticks:\n'
            f'{{"zusammenfassung":"...","gesamtrisiko":"KRITISCH|HOCH|MITTEL|INFO",'
            f'"bereiche":[{{"id":"kv|elda|bgbl|eu","prio":"...","headline":"...",'
            f'"befund":"...","auswirkung":"...","aktion":"...","deadline":"..."}}],'
            f'"sofort":["...","...","..."],"naechste_pruefung":"..."}}',
            "Senior Payroll Compliance Officer Österreich. "
            "Antworte NUR als reines JSON, kein Text davor oder danach, keine Backticks."
        )
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        report_json = json.loads(cleaned)
        return jsonify(report_json)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/areas", methods=["GET"])
def areas():
    return jsonify(AREAS)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
