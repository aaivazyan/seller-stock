from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserRegister(BaseModel):
    email: str
    phone: Optional[str] = None
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    phone: Optional[str] = None
    is_special_offer: bool
    subscription_expires_at: Optional[datetime]
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class CompanyResponse(BaseModel):
    id: int
    name: str

class WarehouseCreate(BaseModel):
    name: str
    address: Optional[str] = None
    external_id: Optional[str] = None

class WarehouseResponse(BaseModel):
    id: int
    company_id: int
    company_name: Optional[str] = None
    name: str
    address: Optional[str] = None
    external_id: Optional[str] = None
    last_sync_at: Optional[datetime]
    created_at: datetime

class ProductCreate(BaseModel):
    sku: str
    name: str

class ProductResponse(BaseModel):
    id: int
    sku: str
    name: str
    created_at: datetime

class StockResponse(BaseModel):
    id: int
    warehouse_id: int
    warehouse_name: Optional[str] = None
    product_id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    physical_quantity: int
    available_quantity: int
    updated_at: datetime

class StockSummaryResponse(BaseModel):
    product_id: int
    product_sku: str
    product_name: str
    warehouses: dict  # {warehouse_name: {"physical": x, "available": y}}
    total_available: int

class CompanyApiKeyCreate(BaseModel):
    company_id: int
    api_key: str
    api_secret: Optional[str] = None

class CompanyApiKeyResponse(BaseModel):
    id: int
    company_id: int
    company_name: Optional[str] = None
    is_active: bool