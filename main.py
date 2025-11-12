import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from database import db, create_document, get_documents
from schemas import Coupon, Redemption

app = FastAPI(title="Coupons API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Coupons Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response

# ---------------------- Coupon API ----------------------
class CreateCouponRequest(BaseModel):
    code: str = Field(..., description="Unique code")
    discount_type: str = Field(..., pattern="^(percent|fixed)$")
    value: float = Field(..., gt=0)
    max_uses: Optional[int] = Field(None, ge=1)
    expires_at: Optional[datetime] = None
    min_order_amount: Optional[float] = Field(0, ge=0)
    is_active: bool = True
    notes: Optional[str] = None

class CouponResponse(BaseModel):
    id: str
    code: str
    discount_type: str
    value: float
    max_uses: Optional[int]
    expires_at: Optional[datetime]
    min_order_amount: Optional[float]
    is_active: bool
    uses: int

@app.post("/api/coupons", response_model=CouponResponse)
def create_coupon(payload: CreateCouponRequest):
    # Normalize code
    code = payload.code.strip().upper()

    # Check for duplicates
    existing = db["coupon"].find_one({"code": code}) if db else None
    if existing:
        raise HTTPException(status_code=400, detail="Coupon code already exists")

    # Validate percent range
    if payload.discount_type == "percent" and not (0 < payload.value <= 100):
        raise HTTPException(status_code=400, detail="Percent discount must be between 0 and 100")

    doc = Coupon(
        code=code,
        discount_type=payload.discount_type, 
        value=payload.value,
        max_uses=payload.max_uses,
        expires_at=payload.expires_at,
        min_order_amount=payload.min_order_amount or 0,
        is_active=payload.is_active,
        notes=payload.notes,
    )

    coupon_id = create_document("coupon", doc)

    return CouponResponse(
        id=coupon_id,
        code=doc.code,
        discount_type=doc.discount_type,
        value=doc.value,
        max_uses=doc.max_uses,
        expires_at=doc.expires_at,
        min_order_amount=doc.min_order_amount,
        is_active=doc.is_active,
        uses=0,
    )

class ListCouponsResponse(BaseModel):
    id: str
    code: str
    status: str
    type: str
    value: float
    uses: int
    max_uses: Optional[int]
    expires_at: Optional[datetime]

@app.get("/api/coupons")
def list_coupons():
    items = []
    for c in get_documents("coupon"):
        uses = db["redemption"].count_documents({"coupon_code": c.get("code")}) if db else 0
        status = "active"
        if not c.get("is_active", True):
            status = "inactive"
        elif c.get("expires_at") and c["expires_at"] < datetime.now(timezone.utc):
            status = "expired"
        elif c.get("max_uses") and uses >= c["max_uses"]:
            status = "exhausted"
        items.append({
            "id": str(c.get("_id")),
            "code": c.get("code"),
            "status": status,
            "type": c.get("discount_type"),
            "value": float(c.get("value", 0)),
            "uses": int(uses),
            "max_uses": c.get("max_uses"),
            "expires_at": c.get("expires_at")
        })
    return items

class ApplyCouponRequest(BaseModel):
    code: str
    order_amount: float = Field(..., ge=0)
    user_id: Optional[str] = None

class ApplyCouponResponse(BaseModel):
    valid: bool
    reason: Optional[str] = None
    code: Optional[str] = None
    discount_amount: float = 0
    final_amount: float = 0

@app.post("/api/coupons/apply", response_model=ApplyCouponResponse)
def apply_coupon(payload: ApplyCouponRequest):
    code = payload.code.strip().upper()
    order_amount = payload.order_amount

    coupon = db["coupon"].find_one({"code": code}) if db else None
    if not coupon:
        return ApplyCouponResponse(valid=False, reason="Invalid code")

    # Status checks
    if not coupon.get("is_active", True):
        return ApplyCouponResponse(valid=False, reason="Coupon inactive")

    now = datetime.now(timezone.utc)
    exp = coupon.get("expires_at")
    if exp and exp < now:
        return ApplyCouponResponse(valid=False, reason="Coupon expired")

    uses = db["redemption"].count_documents({"coupon_code": code}) if db else 0
    if coupon.get("max_uses") and uses >= coupon["max_uses"]:
        return ApplyCouponResponse(valid=False, reason="Usage limit reached")

    if order_amount < float(coupon.get("min_order_amount", 0)):
        return ApplyCouponResponse(valid=False, reason="Order below minimum amount")

    # Compute discount
    if coupon["discount_type"] == "percent":
        discount = round(order_amount * (float(coupon["value"]) / 100.0), 2)
    else:
        discount = float(coupon["value"]) if order_amount >= float(coupon["value"]) else order_amount

    final_amount = round(order_amount - discount, 2)

    # Record redemption
    red_doc = Redemption(
        coupon_code=code,
        order_amount=order_amount,
        discount_amount=discount,
        final_amount=final_amount,
        user_id=payload.user_id,
        context={}
    )
    create_document("redemption", red_doc)

    return ApplyCouponResponse(valid=True, code=code, discount_amount=discount, final_amount=final_amount)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
