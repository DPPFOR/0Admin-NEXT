"""Health and readiness endpoints."""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter()


def get_version() -> str:
    """Get application version from pyproject.toml or commit hash."""
    try:
        import tomllib

        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
            return data.get("tool", {}).get("poetry", {}).get("version", "unknown")
    except Exception:
        # Fallback to pyproject.toml as TOML (older Python)
        try:
            import toml

            with open("pyproject.toml") as f:
                data = toml.load(f)
                return data.get("tool", {}).get("poetry", {}).get("version", "unknown")
        except Exception:
            return "dev"


async def check_database() -> str:
    """Check database connectivity with light query."""
    try:
        from backend.core.database import get_connection  # Assuming DB connection utility

        async with get_connection() as conn:
            # Use direct SQLAlchemy async connection
            result = await conn.execute(text("SELECT 1 as health_check"))
            row = result.first()
            return "OK" if row and row.health_check == 1 else "FAIL"
    except Exception:
        return "FAIL"


@router.get("/health/ready")
async def readiness_check() -> dict[str, Any]:
    """Readiness endpoint for load balancers."""
    db_status = await check_database()

    response = {
        "status": "OK" if db_status == "OK" else "DEGRADED",
        "version": get_version(),
        "db": db_status,
    }

    return response


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """Liveness endpoint - always OK if service is running."""
    return {"status": "OK"}
