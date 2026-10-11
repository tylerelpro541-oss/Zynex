from flask import Flask, request, jsonify
from datetime import datetime, timezone
from threading import Lock

app = Flask(name)
reports = []
lock = Lock()
MAX_REPORTS = 500

@app.get("/")
def home():
return jsonify({
"service": "PET Finder",
"status": "online",
"reports": len(reports)
})

@app.get("/reports")
def get_reports():
rarity = request.args.get("rarity", "").upper()

with lock:
    data = list(reports)

if rarity and rarity != "ALL":
    data = [r for r in data if r["rarity"] == rarity]

return jsonify(data)

@app.post("/reports")
def add_report():
data = request.get_json(silent=True) or {}
name = str(data.get("name", "")).strip()[:100]
rarity = str(data.get("rarity", "UNKNOWN")).upper()[:30]

if not name:
    return jsonify({"error": "Missing egg name"}), 400

report = {
    "name": name,
    "rarity": rarity,
    "weight": data.get("weight"),
    "income": data.get("income"),
    "server_id": data.get("server_id"),
    "created_at": datetime.now(timezone.utc).isoformat()
}

with lock:
    reports.insert(0, report)
    del reports[MAX_REPORTS:]

return jsonify({"ok": True, "report": report}), 201

@app.get("/test-report")
def test_report():
report = {
"name": "Huevo de prueba",
"rarity": "SECRET",
"weight": 250,
"income": 1000,
"server_id": "TEST-123",
"created_at": datetime.now(timezone.utc).isoformat()
}

with lock:
    reports.insert(0, report)

return jsonify({"ok": True})

if name == "main":
app.run(host="0.0.0.0", port=10000)
