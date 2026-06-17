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

# All KV entries for Hotellerie & Gastronomie Austria
KV_LIST = [
    # Aktuell zusammengefasste KVs (ab 2024 ein gemeinsamer KV für Arbeiter+Angestellte)
    {"id": "hoga_2025", "label": "KV Hotellerie & Gastronomie – alle AN (2025)", "year": 2025, "group": "Aktuell"},
    {"id": "hoga_2024", "label": "KV Hotellerie & Gastronomie – alle AN (2024)", "year": 2024, "group": "Aktuell"},

    # Getrennte KVs (bis 2023)
    {"id": "hoga_ang_2023", "label": "KV Hotellerie & Gastronomie – Angestellte (2023)", "year": 2023, "group": "Angestellte (bis 2023)"},
    {"id": "hoga_ang_2022", "label": "KV Hotellerie & Gastronomie – Angestellte (2022)", "year": 2022, "group": "Angestellte (bis 2023)"},
    {"id": "hoga_ang_2021", "label": "KV Hotellerie & Gastronomie – Angestellte (2021)", "year": 2021, "group": "Angestellte (bis 2023)"},
    {"id": "hoga_arb_2023", "label": "KV Hotellerie & Gastronomie – Arbeiter (2023)", "year": 2023, "group": "Arbeiter (bis 2023)"},
    {"id": "hoga_arb_2022", "label": "KV Hotellerie & Gastronomie – Arbeiter (2022)", "year": 2022, "group": "Arbeiter (bis 2023)"},
    {"id": "hoga_arb_2021", "label": "KV Hotellerie & Gastronomie – Arbeiter (2021)", "year": 2021, "group": "Arbeiter (bis 2023)"},

    # Systemgastronomie
    {"id": "sysgast_2024", "label": "KV Systemgastronomie (2024)", "year": 2024, "group": "Systemgastronomie"},
    {"id": "sysgast_2023", "label": "KV Systemgastronomie (2023)", "year": 2023, "group": "Systemgastronomie"},
    {"id": "sysgast_2022", "label": "KV Systemgastronomie (2022)", "year": 2022, "group": "Systemgastronomie"},

    # Kaffeehäuser
    {"id": "kaffee_2024", "label": "KV Kaffeehäuser Österreich (2024)", "year": 2024, "group": "Kaffeehäuser"},
    {"id": "kaffee_2023", "label": "KV Kaffeehäuser Österreich (2023)", "year": 2023, "group": "Kaffeehäuser"},
]


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/kv_list")
def kv_list():
    return jsonify(KV_LIST)


@app.route("/api/kv_check_stream", methods=["POST"])
def kv_check_stream():
    data = request.json
    api_key = data.get("api_key", "").strip()
    if not api_key.startswith("sk-ant-"):
        return jsonify({"error": "Ungültiger API Key"}), 401

    kv_id    = data.get("kv_id", "")
    kv_label = data.get("kv_label", "")
    kv_year  = data.get("kv_year", "")

    prompt = f"""Du bist ein österreichischer Kollektivvertrags-Experte mit Fokus auf Hotellerie und Gastronomie.

Der Nutzer hat folgenden Kollektivvertrag als Basis ausgewählt:
**{kv_label}** (Jahr: {kv_year})

## Deine Aufgabe:

### SCHRITT 1: Prüfung ob neuerer KV vorliegt
Prüfe ob nach {kv_year} ein neuerer Kollektivvertrag für diese Berufsgruppe abgeschlossen wurde.
- Falls ja: Nenne den neuesten verfügbaren KV mit Datum des Abschlusses
- Falls nein: Erkläre warum (z.B. noch gültig, keine neueren Informationen vorhanden)

### SCHRITT 2: Gegenüberstellung der Änderungen
Wenn ein neuerer KV vorliegt, zeige ALLE Änderungen Paragraph für Paragraph:

Format für jede Änderung:
**§ [Nummer] – [Paragraphtitel]**
- ALT ({kv_year}): [alter Text/Regelung]
- NEU: [neuer Text/Regelung]  
- BEWERTUNG: [Wesentlich / Nicht wesentlich] – [kurze Begründung warum]

Prüfe insbesondere:
- Lohntabellen und Mindestlöhne (alle Beschäftigungsgruppen)
- Lehrlingsentschädigungen
- Zulagen und Zuschläge (Nacht, Sonn- und Feiertag, Überstunden)
- Arbeitszeit und Überstundenregelungen
- Urlaubsregelungen und Urlaubszuschuss
- Weihnachtsremuneration
- Aufsaugklausel (Anrechnung von Ist-Löhnen)
- Kündigungsfristen
- Senioritätsstufen / Vorrückungssystem
- Reisekosten und Diäten
- Sonstige Änderungen

### SCHRITT 3: Zusammenfassung
- Gesamtbewertung der Änderungen (KRITISCH / HOCH / MITTEL / INFO für Payroll-Software)
- Top 3 Handlungsempfehlungen für die Lohnverrechnung
- Umsetzungsdeadline

### SCHRITT 4: Quellen
Liste alle relevanten Quellen mit direkten URLs:
- WKO Kollektivvertragsdatenbank
- AK Österreich
- Relevante Dokumente

Antworte strukturiert mit Markdown-Formatierung (## für Hauptabschnitte, ### für Unterabschnitte, **fett** für wichtige Begriffe).
Sei präzise und praxisorientiert. Kein Marketingsprech."""

    def generate():
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={**HEADERS, "x-api-key": api_key},
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 8000,
                    "system": "Du bist Senior KV-Experte für österreichische Hotellerie und Gastronomie mit 20 Jahren Erfahrung in der Lohnverrechnung. Deine Analysen sind präzise, vollständig und praxisorientiert.",
                    "stream": True,
                    "messages": [{"role": "user", "content": prompt}]
                },
                stream=True,
                timeout=120
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

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
