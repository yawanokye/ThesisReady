from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from app.access_control import complimentary_status, public_access_status

router = APIRouter(tags=["ProjectReady access"])


@router.get("/api/access/status")
def access_status(product_area: str = Query(default="all", max_length=80)) -> dict:
    try:
        return public_access_status(product_area)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/access/complimentary/status")
def access_complimentary_status(
    product_area: str = Query(default="all", max_length=80),
    x_projectready_complimentary_token: str = Header(default=""),
    x_projectready_complimentary_email: str = Header(default=""),
) -> dict:
    if not str(x_projectready_complimentary_token or "").strip():
        raise HTTPException(status_code=404, detail="No complimentary access token is active on this device.")
    try:
        data = complimentary_status(
            x_projectready_complimentary_token,
            product_area=product_area,
            supplied_email=x_projectready_complimentary_email,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**data, "access_type": "complimentary_pages"}
