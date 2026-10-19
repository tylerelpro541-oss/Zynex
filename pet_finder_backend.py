
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
        raise RuntimeError(
            "DATABASE_URL no está configurada en Render"
        )

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
                    created_at TIMESTAMPTZ
                        NOT NULL DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS
                egg_reports_created_at_idx
                ON egg_reports (created_at DESC)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS
                egg_reports_server_id_idx
                ON egg_reports (server_id)
            """)


def row_to_json(row):
    if not row:
        return None

    result = dict(row)

    if result.get("created_at"):
        result["created_at"] = (
            result["created_at"].isoformat()
        )

    result["weight_kg"] = result.get("weight")
    result["income_per_second"] = result.get("income")

    return result


@app.get("/")
def home():
    return jsonify({
        "ok": True,
        "service": "ZYNEX Pet Finder API",
        "storage": "postgresql",
        "features": [
            "reports",
            "servers",
            "health"
        ]
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

    except Exception:
        app.logger.exception("Health check failed")

        return jsonify({
            "ok": False,
            "database": "error"
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

        rarity = str(data.get("rarity") or "").strip().upper()

        weight = number_or_none(
            data.get("weight_kg", data.get("weight"))
        )

        income = number_or_none(
            data.get(
                "income_per_second",
                data.get("income")
            )
        )

        server_id = str(
            data.get("server_id") or ""
        ).strip()[:200]

        area = str(
            data.get("area") or ""
        ).strip()[:200]

        try:
            with get_conn() as conn:
                with conn.cursor(
                    cursor_factory=RealDictCursor
                ) as cur:
                    cur.execute("""
                        INSERT INTO egg_reports
                        (name, rarity, weight, income,
                         server_id, area)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, name, rarity, weight,
                                  income, server_id, area,
                                  created_at
                    """, (
                        name,
                        rarity or None,
                        weight,
                        income,
                        server_id or None,
                        area or None
                    ))

                    saved = row_to_json(cur.fetchone())

            return jsonify({
                "ok": True,
                "report": saved
            }), 201

        except Exception:
            app.logger.exception("Could not save report")

            return jsonify({
                "ok": False,
                "error": "No se pudo guardar el reporte"
            }), 503

    try:
        limit = request.args.get(
            "limit", default=100, type=int
        )
        limit = max(1, min(limit, 500))

        server_id = request.args.get(
            "server_id", default="", type=str
        ).strip()

        rarity = request.args.get(
            "rarity", default="", type=str
        ).strip().upper()

        conditions = []
        params = []

        if server_id:
            conditions.append("server_id = %s")
            params.append(server_id)

        if rarity and rarity != "ALL":
            conditions.append("UPPER(rarity) = %s")
            params.append(rarity)

        where_sql = (
            "WHERE " + " AND ".join(conditions)
            if conditions else ""
        )

        params.append(limit)

        with get_conn() as conn:
            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cur:
                cur.execute(f"""
                    SELECT id, name, rarity, weight,
                           income, server_id, area, created_at
                    FROM egg_reports
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s
                """, tuple(params))

                items = [
                    row_to_json(row)
                    for row in cur.fetchall()
                ]

        return jsonify(items)

    except Exception:
        app.logger.exception("Could not load reports")

        return jsonify({
            "ok": False,
            "error": "No se pudieron leer los reportes"
        }), 503


@app.get("/servers")
def servers():
    """Lista los servidores distintos presentes en los reportes."""

    try:
        limit = request.args.get(
            "limit", default=100, type=int
        )
        limit = max(1, min(limit, 500))

        with get_conn() as conn:
            with conn.cursor(
                cursor_factory=RealDictCursor
            ) as cur:
                cur.execute("""
                    SELECT
                        server_id,
                        COUNT(*) AS report_count,
                        MAX(created_at) AS last_seen,
                        COUNT(DISTINCT name) AS egg_types
                    FROM egg_reports
                    WHERE server_id IS NOT NULL
                      AND TRIM(server_id) <> ''
                    GROUP BY server_id
                    ORDER BY MAX(created_at) DESC
                    LIMIT %s
                """, (limit,))

                items = []

                for row in cur.fetchall():
                    item = dict(row)

                    if item.get("last_seen"):
                        item["last_seen"] = (
                            item["last_seen"].isoformat()
                        )

                    items.append(item)

        return jsonify({
            "ok": True,
            "servers_count": len(items),
            "servers": items
        })

    except Exception:
        app.logger.exception("Could not load servers")

        return jsonify({
            "ok": False,
            "error": "No se pudieron leer los servidores"
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
                    (name, rarity, weight, income,
                     server_id, area)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, name, rarity, weight,
                              income, server_id, area,
                              created_at
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

    except Exception:
        app.logger.exception("Test report failed")

        return jsonify({
            "ok": False,
            "error": "La prueba no pudo guardarse"
        }), 503


try:
    init_db()
except Exception:
    app.logger.exception(
        "Database initialization failed at startup"
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
    )
    
