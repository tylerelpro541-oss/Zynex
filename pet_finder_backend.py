
import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")
PLACE_ID = "107778070777162"


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no configurada")
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public_servers (
                    place_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    playing INTEGER DEFAULT 0,
                    max_players INTEGER DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (place_id, server_id)
                )
            """)


def json_row(row):
    if not row:
        return None

    result = dict(row)

    for key in ("created_at", "updated_at", "last_seen"):
        if result.get(key):
            result[key] = result[key].isoformat()

    if "weight" in result:
        result["weight_kg"] = result.get("weight")

    if "income" in result:
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
            "health",
            "public_servers"
        ]
    })


@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")

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
                "error": "name obligatorio"
            }), 400

        def to_number(value):
            try:
                return float(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

        try:
            with get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        INSERT INTO egg_reports
                        (name, rarity, weight, income, server_id, area)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING *
                    """, (
                        name[:200],
                        str(data.get("rarity") or "")[:50],
                        to_number(data.get(
                            "weight_kg",
                            data.get("weight")
                        )),
                        to_number(data.get(
                            "income_per_second",
                            data.get("income")
                        )),
                        str(data.get("server_id") or "")[:200],
                        str(data.get("area") or "")[:200]
                    ))

                    saved = json_row(cur.fetchone())

            return jsonify({
                "ok": True,
                "report": saved
            }), 201

        except Exception:
            app.logger.exception("Saving report failed")
            return jsonify({
                "ok": False,
                "error": "No se pudo guardar"
            }), 503

    limit = max(
        1,
        min(request.args.get("limit", 100, type=int), 500)
    )

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM egg_reports
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))

                rows = [json_row(r) for r in cur.fetchall()]

        return jsonify(rows)

    except Exception:
        app.logger.exception("Loading reports failed")
        return jsonify({
            "ok": False,
            "error": "No se pudieron leer los reportes"
        }), 503


@app.get("/servers")
def servers():
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        server_id,
                        COUNT(DISTINCT name) AS egg_types,
                        COUNT(*) AS report_count,
                        MAX(created_at) AS last_seen
                    FROM egg_reports
                    WHERE server_id IS NOT NULL
                      AND server_id <> ''
                    GROUP BY server_id
                    ORDER BY MAX(created_at) DESC
                    LIMIT 200
                """)

                rows = [json_row(r) for r in cur.fetchall()]

        return jsonify({
            "ok": True,
            "servers": rows,
            "servers_count": len(rows)
        })

    except Exception:
        app.logger.exception("Loading servers failed")
        return jsonify({
            "ok": False,
            "error": "No se pudieron leer servidores"
        }), 503


@app.get("/sync-public-servers")
def sync_public_servers():
    url = (
        f"https://games.roblox.com/v1/games/"
        f"{PLACE_ID}/servers/Public"
    )

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                response = requests.get(
                    url,
                    params={
                        "sortOrder": "Asc",
                        "limit": 100
                    },
                    timeout=20,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json"
                    }
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")

                    app.logger.warning(
                        "Roblox rate limit 429; Retry-After=%s",
                        retry_after
                    )

                    return jsonify({
                        "ok": False,
                        "error": (
                            "Roblox está limitando las peticiones. "
                            "Espera antes de volver a intentar."
                        ),
                        "retry_after": retry_after
                    }), 429

                response.raise_for_status()
                payload = response.json()
                saved_count = 0

                for server in payload.get("data", []):
                    server_id = server.get("id")

                    if not server_id:
                        continue

                    cur.execute("""
                        INSERT INTO public_servers
                            (place_id, server_id, playing,
                             max_players, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (place_id, server_id)
                        DO UPDATE SET
                            playing = EXCLUDED.playing,
                            max_players = EXCLUDED.max_players,
                            updated_at = NOW()
                    """, (
                        PLACE_ID,
                        str(server_id),
                        int(server.get("playing") or 0),
                        int(server.get("maxPlayers") or 0)
                    ))

                    saved_count += 1

        return jsonify({
            "ok": True,
            "saved_or_updated": saved_count,
            "max_per_run": 100,
            "note": (
                "Se guardaron IDs públicos. "
                "Esto no detecta los huevos de esos servidores."
            )
        })

    except requests.exceptions.HTTPError:
        app.logger.exception("Roblox API HTTP error")
        return jsonify({
            "ok": False,
            "error": (
                "Roblox rechazó la petición. "
                "Si es 429, espera antes de reintentar."
            )
        }), 502

    except Exception:
        app.logger.exception("Public server sync failed")
        return jsonify({
            "ok": False,
            "error": "Falló la sincronización. Revisa los logs."
        }), 502


@app.get("/public-servers")
def public_servers():
    limit = max(
        1,
        min(request.args.get("limit", 100, type=int), 100)
    )

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT server_id, playing, max_players, updated_at
                    FROM public_servers
                    WHERE place_id = %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                """, (PLACE_ID, limit))

                rows = [json_row(r) for r in cur.fetchall()]

        return jsonify({
            "ok": True,
            "servers_count": len(rows),
            "servers": rows
        })

    except Exception:
        app.logger.exception("Loading public servers failed")
        return jsonify({
            "ok": False,
            "error": "No se pudieron leer los IDs"
        }), 503


try:
    init_db()
    app.logger.info("ZYNEX database initialized")
except Exception:
    app.logger.exception("Database initialization failed")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
        )
                
