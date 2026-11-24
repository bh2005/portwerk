"""Release-Hinweise (Änderungen je Version) für die Verwaltung."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import releases
from ..auth import Principal, current_principal

router = APIRouter(tags=["system"])


@router.get("/api/releases")
def get_releases(_: Principal = Depends(current_principal)):
    r = releases.load()
    return {"version": releases.current_version(), "releases": r}
