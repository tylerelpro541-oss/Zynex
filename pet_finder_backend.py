
import os
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada en Render")
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=8,
        sslmode="require"
    )


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS egg_reports (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    rarity TEXT,
                    weight DOUBLE PRECISION,
                    income DOUBLE PRECISION,
                    server_id TEXT,
                    area TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS egg_reports_created_at_idx
                ON egg_reports (created_at DESC)
            """)


def row_to_json(row):
    if not row:
        return None

    result = dict(row)

    if result.get("created_at"):
        result["created_at"] = result["created_at"].isoformat()

    result["weight_kg"] = result.get("weight")
    result["income_per_second"] = result.get("income")

    return result


@app.get("/")
def home():
    return jsonify({
        "ok": True,
        "service": "ZYNEX Pet Finder API",
        "storage": "postgresql"
    })


@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

        return jsonify({
            "ok": True,
            "database": "connected"
        })

    except Exception as exc:
        app.logger.exception("Health/database check failed")
        return jsonify({
            "ok": False,
            "database": "error",
            "error": str(exc)
        }), 503


@app.route("/reports", methods=["GET", "POST", "OPTIONS"])
def reports():
    if request.method == "OPTIONS":
        return "", 204

    if request.method == "POST":
        data = request.get_json(silent=True) or {}

        name = str(data.get("name") or "").strip()

        if not name:
            return jsonify({
                "ok": False,
                "error": "El campo 'name' es obligatorio"
            }), 400

        def number_or_none(value):
            if value is None or value == "":
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        rarity = data.get("rarity")
        weight = number_or_none(
            data.get("weight_kg", data.get("weight"))
        )
        income = number_or_none(
            data.get("income_per_second", data.get("income"))
        )
        server_id = str(data.get("server_id") or "")[:200]
        area = str(data.get("area") or "")[:200]

        try:
            with get_conn() as conn:
                with conn.cursor(
                    cursor_factory=RealDictCursor
                ) as cur:
                    cur.execute("""
                        INSERT INTO egg_reports
                        (name, rarity, weight, income, server_id, area)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, name, rarity, weight,
                        income, server_id, area, created_at
                    """, (
                        name, rarity, weight, income,
                        server_id, area
                    ))

                    saved = row_to_json(cur.fetchone())

            return jsonify({
                "ok": True,
                "report": saved
            }), 201

        except Exception as exc:
            app.logger.exception("Could not save report")
            return jsonify({
                "ok": False,
                "error": "No se pudo guardar el reporte",
                "detail": str(exc)
            }), 503

    try:
        limit = request.args.get("limit", default=100, type=int)
        limit = max(1, min(limit, 500))

        with get_conn() as conn:
            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cur:
                cur.execute("""
                    SELECT id, name, rarity, weight, income,
                    server_id, area, created_at
                    FROM egg_reports
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))

                items = [
                    row_to_json(row)
                    for row in cur.fetchall()
                ]

        return jsonify(items)

    except Exception as exc:
        app.logger.exception("Could not load reports")
        return jsonify({
            "ok": False,
            "error": "No se pudieron leer los reportes",
            "detail": str(exc)
        }), 503


@app.get("/test-report")
def test_report():
    try:
        with get_conn() as conn:
            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cur:
                cur.execute("""
                    INSERT INTO egg_reports
                    (name, rarity, weight, income, server_id, area)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, name, rarity, weight,
                    income, server_id, area, created_at
                """, (
                    "ZYNEX TEST REPORT",
                    "TEST",
                    1.0,
                    1.0,
                    "backend-test",
                    "test"
                ))

                saved = row_to_json(cur.fetchone())

        return jsonify({
            "ok": True,
            "message": "Prueba guardada en PostgreSQL",
            "report": saved
        }), 201

    except Exception as exc:
        app.logger.exception("Test report failed")
        return jsonify({
            "ok": False,
            "error": "La prueba no pudo guardarse",
            "detail": str(exc)
        }), 503


try:
    init_db()
except Exception:
    app.logger.exception("Database initialization failed at startup")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
    )
    
