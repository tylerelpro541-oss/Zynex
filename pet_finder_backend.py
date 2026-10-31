import os
import hashlib
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ["DATABASE_URL"]
READER_TOKEN = os.getenv("READER_TOKEN", "")


def db():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        cursor_factory=RealDictCursor
    )


def init_db():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS egg_reports (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    rarity TEXT DEFAULT 'Unknown',
                    weight DOUBLE PRECISION,
                    income DOUBLE PRECISION,
                    server_id TEXT DEFAULT 'unknown',
                    area TEXT DEFAULT 'unknown',
                    reader_id TEXT DEFAULT 'default',
                    report_key TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS egg_readers (
                    reader_id TEXT PRIMARY KEY,
                    server_id TEXT DEFAULT 'unknown',
                    place_id TEXT DEFAULT 'unknown',
                    last_seen TIMESTAMPTZ DEFAULT NOW(),
                    reports_sent BIGINT DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS egg_reports_created_idx
                ON egg_reports(created_at DESC)
            """)
        conn.commit()


def authorized():
    return (
        not READER_TOKEN
        or request.headers.get("X-Reader-Token") == READER_TOKEN
    )


def clean(value, default="unknown"):
    value = str(value or "").strip()
    return value[:180] if value else default


@app.get("/")
def home():
    return jsonify({
        "service": "PET Finder | ZYNEX",
        "status": "online"
    })


@app.get("/health")
def health():
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return jsonify({"ok": True, "database": "connected"})
    except Exception:
        return jsonify({"ok": False, "database": "disconnected"}), 503


@app.route("/reports", methods=["GET", "POST"])
def reports():

    if request.method == "POST":

        if not authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}

        name = clean(data.get("name"), "")
        if not name:
            return jsonify({"ok": False, "error": "name_required"}), 400

        rarity = clean(data.get("rarity"))
        server = clean(data.get("server_id"))
        area = clean(data.get("area"))
        reader = clean(data.get("reader_id"), "default")

        try:
            weight = data.get("weight", data.get("weight_kg"))
            income = data.get("income", data.get("income_per_second"))

            weight = float(weight) if weight not in (None, "") else None
            income = float(income) if income not in (None, "") else None

        except (ValueError, TypeError):
            return jsonify({"ok": False, "error": "invalid_numbers"}), 400

        raw = f"{name}|{rarity}|{server}|{area}|{weight}|{income}"
        report_key = hashlib.sha256(raw.encode()).hexdigest()

        try:
            with db() as conn:
                with conn.cursor() as cur:

                    cur.execute("""
                        SELECT id FROM egg_reports
                        WHERE report_key = %s
                        AND created_at > NOW() - INTERVAL '30 seconds'
                        LIMIT 1
                    """, (report_key,))

                    duplicate = cur.fetchone()

                    if duplicate:
                        return jsonify({
                            "ok": True,
                            "duplicate": True,
                            "id": duplicate["id"]
                        })

                    cur.execute("""
                        INSERT INTO egg_reports
                        (name, rarity, weight, income, server_id,
                         area, reader_id, report_key)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id
                    """, (
                        name, rarity, weight, income,
                        server, area, reader, report_key
                    ))

                    saved = cur.fetchone()

                    cur.execute("""
                        INSERT INTO egg_readers
                        (reader_id, server_id, last_seen, reports_sent)
                        VALUES (%s,%s,NOW(),1)
                        ON CONFLICT (reader_id)
                        DO UPDATE SET
                            server_id = EXCLUDED.server_id,
                            last_seen = NOW(),
                            reports_sent = egg_readers.reports_sent + 1
                    """, (reader, server))

                conn.commit()

            return jsonify({
                "ok": True,
                "id": saved["id"]
            }), 201

        except Exception:
            app.logger.exception("Report save failed")
            return jsonify({"ok": False, "error": "database_error"}), 500

    rarity = request.args.get("rarity", "ALL")

    try:
        with db() as conn:
            with conn.cursor() as cur:

                if rarity.upper() == "ALL":
                    cur.execute("""
                        SELECT id, name, rarity, weight,
                               weight AS weight_kg,
                               income, income AS income_per_second,
                               server_id, area, reader_id, created_at
                        FROM egg_reports
                        ORDER BY created_at DESC
                        LIMIT 1000
                    """)
                else:
                    cur.execute("""
                        SELECT id, name, rarity, weight,
                               weight AS weight_kg,
                               income, income AS income_per_second,
                               server_id, area, reader_id, created_at
                        FROM egg_reports
                        WHERE UPPER(rarity) = UPPER(%s)
                        ORDER BY created_at DESC
                        LIMIT 1000
                    """, (rarity,))

                rows = cur.fetchall()

        for row in rows:
            row["created_at"] = row["created_at"].isoformat()

        return jsonify(rows)

    except Exception:
        app.logger.exception("Report fetch failed")
        return jsonify({"ok": False, "error": "database_error"}), 500


@app.route("/readers", methods=["GET", "POST"])
def readers():

    if request.method == "POST":

        if not authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}

        reader = clean(data.get("reader_id"), "")
        if not reader:
            return jsonify({"ok": False, "error": "reader_id_required"}), 400

        server = clean(data.get("server_id"))
        place = clean(data.get("place_id"))

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO egg_readers
                    (reader_id, server_id, place_id, last_seen)
                    VALUES (%s,%s,%s,NOW())
                    ON CONFLICT (reader_id)
                    DO UPDATE SET
                        server_id = EXCLUDED.server_id,
                        place_id = EXCLUDED.place_id,
                        last_seen = NOW()
                """, (reader, server, place))
            conn.commit()

        return jsonify({"ok": True, "reader_id": reader})

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT reader_id, server_id, place_id,
                       last_seen, reports_sent
                FROM egg_readers
                ORDER BY last_seen DESC
            """)
            rows = cur.fetchall()

    now = datetime.now(timezone.utc)

    for row in rows:
        last = row["last_seen"]
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)

        row["status"] = (
            "online" if (now - last).total_seconds() < 90
            else "offline"
        )
        row["last_seen"] = last.isoformat()

    return jsonify({
        "ok": True,
        "readers": rows,
        "readers_count": len(rows)
    })


@app.get("/servers")
def servers():

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT server_id,
                       COUNT(*) AS report_count,
                       COUNT(DISTINCT name) AS egg_types,
                       MAX(created_at) AS last_seen
                FROM egg_reports
                GROUP BY server_id
                ORDER BY last_seen DESC
            """)
            rows = cur.fetchall()

    for row in rows:
        row["last_seen"] = row["last_seen"].isoformat()

    return jsonify({
        "ok": True,
        "servers": rows,
        "servers_count": len(rows)
    })


init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000"))
    )
