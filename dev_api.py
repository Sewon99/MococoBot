import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers.siblings import router as siblings_router
from routers.character import router as character_router
from database.connection import close_db_pool
from database.connection import get_db

from dev_server_router import router as dev_server_router
from dev_party_router import router as dev_party_router



def load_root_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_root_env()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Startup] dev_api started")
    yield
    await close_db_pool()
    print("[Shutdown] dev_api stopped")


app = FastAPI(
    title="NeundongBot Dev API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 봇이 실제 호출하는 경로와 맞춤
app.include_router(siblings_router, prefix="/siblings", tags=["siblings"])
app.include_router(character_router, prefix="/character", tags=["character"])
app.include_router(dev_party_router, prefix="/party", tags=["party"])
app.include_router(dev_server_router, prefix="/server", tags=["server"])

@app.get("/")
async def root():
    return {"ok": True, "message": "NeundongBot Dev API is running"}


@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/debug/db")
async def debug_db():
    try:
        async with get_db() as db:
            rows = await db.execute("SELECT 1 AS ok")
            return {
                "ok": True,
                "rows": rows,
            }
    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error": str(e),
            "db_env": {
                "DB_HOST_SET": bool(os.getenv("DB_HOST")),
                "DB_PORT_SET": bool(os.getenv("DB_PORT")),
                "DB_USER_SET": bool(os.getenv("DB_USER")),
                "DB_PASSWORD_SET": bool(os.getenv("DB_PASSWORD")),
                "DB_NAME_SET": bool(os.getenv("DB_NAME")),
            },
        }
    
@app.get("/debug/db-raw")
async def debug_db_raw():
    import aiomysql

    host = os.getenv("DB_HOST")
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    try:
        conn = await aiomysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            db=db_name,
            charset="utf8mb4",
        )

        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT 1 AS ok")
            row = await cur.fetchone()

        conn.close()

        return {
            "ok": True,
            "row": row,
            "debug": {
                "host_set": bool(host),
                "port": port,
                "user_set": bool(user),
                "password_set": bool(password),
                "db_name": db_name,
            },
        }

    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error": str(e),
            "debug": {
                "host_set": bool(host),
                "host_preview": host[:20] + "..." if host else None,
                "port": port,
                "user_set": bool(user),
                "password_set": bool(password),
                "db_name": db_name,
            },
        }

@app.get("/debug/env")
async def debug_env():
    return JSONResponse(
        content={
            "DB_HOST_SET": bool(os.getenv("DB_HOST")),
            "DB_PORT_SET": bool(os.getenv("DB_PORT")),
            "DB_USER_SET": bool(os.getenv("DB_USER")),
            "DB_PASSWORD_SET": bool(os.getenv("DB_PASSWORD")),
            "DB_NAME_SET": bool(os.getenv("DB_NAME")),
            "API_KEY_SET": bool(os.getenv("API_KEY")),
            "LOSTARK_API_KEY_SET": bool(os.getenv("LOSTARK_API_KEY")),
        }
    )

@app.get("/debug/raid-list")
async def debug_raid_list():
    async with get_db() as db:
        rows = await db.execute(
            """
            SELECT id, name, difficulty, min_lvl, dealer, supporter
            FROM raid
            ORDER BY id ASC
            """
        ) or []
        return {"data": rows}

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))

    uvicorn.run(
        "dev_api:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )