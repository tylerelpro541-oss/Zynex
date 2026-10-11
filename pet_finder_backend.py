
from flask import Flask, request, jsonify
from datetime import datetime, timezone
from threading import Lock

app = Flask(__name__)
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
