
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone
from threading import Lock

app = Flask(__name__)
CORS(app)

reports = []
lock = Lock()
MAX_REPORTS = 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "PET Finder Zynex",
        "status": "online",
        "reports": len(reports)
    })


@app.route("/reports", methods=["GET", "OPTIONS"])
def get_reports():
    rarity = request.args.get("rarity", "ALL").upper()

    with lock:
        data = list(reports)

    if rarity != "ALL":
        data = [
            report for report in data
            if report["rarity"] == rarity
        ]

    return jsonify({
        "ok": True,
        "count": len(data),
        "reports": data
    })


@app.route("/reports", methods=["POST", "OPTIONS"])
def add_report():
    if request.method == "OPTIONS":
        return "", 204

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

    return jsonify({
        "ok": True,
        "report": report
    }), 201


@app.route("/test-report", methods=["GET"])
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
        del reports[MAX_REPORTS:]

    return jsonify({
        "ok": True,
        "report": report
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
    
