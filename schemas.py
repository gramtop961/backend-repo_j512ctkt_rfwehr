"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

# Example schemas (keep for reference but not used directly in this app)
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Coupon system schemas used by the app
class Coupon(BaseModel):
    """
    Coupons collection schema
    Collection name: "coupon"
    """
    code: str = Field(..., description="Unique coupon code, case-insensitive")
    discount_type: Literal["percent", "fixed"] = Field(..., description="Type of discount")
    value: float = Field(..., gt=0, description="Discount value: percent (0-100) or fixed amount")
    max_uses: Optional[int] = Field(None, ge=1, description="Maximum total redemptions allowed")
    expires_at: Optional[datetime] = Field(None, description="UTC expiry datetime")
    min_order_amount: Optional[float] = Field(0, ge=0, description="Minimum order amount to be eligible")
    is_active: bool = Field(True, description="Whether this coupon is active")
    notes: Optional[str] = Field(None, description="Internal notes")

class Redemption(BaseModel):
    """
    Redemptions collection schema
    Collection name: "redemption"
    """
    coupon_code: str = Field(..., description="Coupon code used (uppercased)")
    order_amount: float = Field(..., ge=0, description="Original order amount before discount")
    discount_amount: float = Field(..., ge=0, description="Discount applied")
    final_amount: float = Field(..., ge=0, description="Amount after discount")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    context: Optional[dict] = Field(default_factory=dict, description="Arbitrary context metadata")
