from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from models import User, Company, Warehouse, Product, Stock, CompanyApiKey
from schemas import (
    UserRegister, UserResponse, UserLogin, TokenResponse,
    CompanyResponse, 
    WarehouseCreate, WarehouseResponse,
    ProductCreate, ProductResponse,
    StockResponse, StockSummaryResponse,
    CompanyApiKeyCreate, CompanyApiKeyResponse
)
from auth import create_access_token, decode_access_token
import asyncio
from wb_sync import WBSync
from models import Stock, CompanyApiKey
from contextlib import asynccontextmanager


# Создаём таблицы
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запуск при старте
    from scheduler import start_scheduler
    start_scheduler()
    yield
    # Остановка при завершении
    from scheduler import stop_scheduler
    stop_scheduler()

app = FastAPI(
    title="Seller Stock API",
    lifespan=lifespan
)

security = HTTPBearer()

@app.get("/")
def root():
    return {"message": "Seller Stock API работает!"}

@app.post("/auth/register", response_model=UserResponse)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    if user_data.phone:
        existing_phone = db.query(User).filter(User.phone == user_data.phone).first()
        if existing_phone:
            raise HTTPException(status_code=400, detail="Phone already registered")
    
    new_user = User(
        email=user_data.email,
        phone=user_data.phone
    )
    new_user.set_password(user_data.password)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

@app.post("/auth/login", response_model=TokenResponse)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not user.check_password(user_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": token}

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user

@app.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.get("/companies", response_model=list[CompanyResponse])
def get_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()

@app.get("/warehouses", response_model=list[WarehouseResponse])
def get_warehouses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    warehouses = db.query(Warehouse).filter(Warehouse.user_id == current_user.id).all()
    
    result = []
    for w in warehouses:
        company = db.query(Company).filter(Company.id == w.company_id).first()
        result.append({
            "id": w.id,
            "company_id": w.company_id,
            "company_name": company.name if company else None,
            "name": w.name,
            "address": w.address,
            "external_id": w.external_id,
            "last_sync_at": w.last_sync_at,
            "created_at": w.created_at
        })
    return result

@app.post("/warehouses", response_model=WarehouseResponse)
def create_warehouse(
    warehouse_data: WarehouseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Пока company_id = 1 (WB) для простоты, потом добавим выбор
    new_warehouse = Warehouse(
        company_id=1,
        user_id=current_user.id,
        name=warehouse_data.name,
        address=warehouse_data.address,
        external_id=warehouse_data.external_id
    )
    db.add(new_warehouse)
    db.commit()
    db.refresh(new_warehouse)
    
    company = db.query(Company).filter(Company.id == new_warehouse.company_id).first()
    
    return {
        "id": new_warehouse.id,
        "company_id": new_warehouse.company_id,
        "company_name": company.name if company else None,
        "name": new_warehouse.name,
        "address": new_warehouse.address,
        "external_id": new_warehouse.external_id,
        "last_sync_at": new_warehouse.last_sync_at,
        "created_at": new_warehouse.created_at
    }

@app.get("/products", response_model=list[ProductResponse])
def get_products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    search: Optional[str] = None
):
    query = db.query(Product).filter(Product.user_id == current_user.id)
    
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    
    return query.all()

@app.post("/products", response_model=ProductResponse)
def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Проверяем, не существует ли уже товар с таким sku
    existing = db.query(Product).filter(
        Product.user_id == current_user.id,
        Product.sku == product_data.sku
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Product with this SKU already exists")
    
    new_product = Product(
        user_id=current_user.id,
        sku=product_data.sku,
        name=product_data.name
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    
    return new_product

@app.get("/stocks/summary", response_model=list[StockSummaryResponse])
def get_stocks_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Получаем все товары пользователя
    products = db.query(Product).filter(Product.user_id == current_user.id).all()
    
    # Получаем все склады пользователя
    warehouses = db.query(Warehouse).filter(Warehouse.user_id == current_user.id).all()
    warehouse_dict = {w.id: w for w in warehouses}
    
    # Получаем все остатки
    stocks = db.query(Stock).filter(
        Stock.warehouse_id.in_([w.id for w in warehouses])
    ).all()
    
    # Группируем остатки по товарам
    result = []
    for product in products:
        product_stocks = {}
        total_available = 0
        
        for stock in stocks:
            if stock.product_id == product.id:
                warehouse = warehouse_dict.get(stock.warehouse_id)
                if warehouse:
                    product_stocks[warehouse.name] = {
                        "physical": stock.physical_quantity,
                        "available": stock.available_quantity
                    }
                    total_available += stock.available_quantity
        
        result.append({
            "product_id": product.id,
            "product_sku": product.sku,
            "product_name": product.name,
            "warehouses": product_stocks,
            "total_available": total_available
        })
    
    return result

@app.post("/stocks/sync/wb")
def sync_wb_stocks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Получаем API-ключ пользователя для WB
    api_key = db.query(CompanyApiKey).filter(
        CompanyApiKey.user_id == current_user.id,
        CompanyApiKey.company_id == 1,  # WB
        CompanyApiKey.is_active == True
    ).first()
    
    if not api_key:
        raise HTTPException(status_code=400, detail="WB API key not configured")
    
    # TODO: реальный запрос к WB API
    # Пока возвращаем заглушку
    
    return {"message": "Sync started (mock)", "warehouses_updated": 0}

@app.post("/api-keys", response_model=CompanyApiKeyResponse)
def create_api_key(
    key_data: CompanyApiKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Проверяем, существует ли компания
    company = db.query(Company).filter(Company.id == key_data.company_id).first()
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")
    
    # Проверяем, нет ли уже ключа
    existing = db.query(CompanyApiKey).filter(
        CompanyApiKey.user_id == current_user.id,
        CompanyApiKey.company_id == key_data.company_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="API key already exists for this company")
    
    new_key = CompanyApiKey(
        user_id=current_user.id,
        company_id=key_data.company_id,
        api_key=key_data.api_key,
        api_secret=key_data.api_secret
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    
    return {
        "id": new_key.id,
        "company_id": new_key.company_id,
        "company_name": company.name,
        "is_active": new_key.is_active
    }

@app.get("/api-keys", response_model=list[CompanyApiKeyResponse])
def get_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    keys = db.query(CompanyApiKey).filter(
        CompanyApiKey.user_id == current_user.id
    ).all()
    
    result = []
    for key in keys:
        company = db.query(Company).filter(Company.id == key.company_id).first()
        result.append({
            "id": key.id,
            "company_id": key.company_id,
            "company_name": company.name if company else None,
            "is_active": key.is_active
        })
    
    return result

@app.post("/sync/wb/products")
def sync_wb_products(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    syncer = WBSync(db, current_user.id)
    return syncer.sync_products()

@app.post("/sync/wb/warehouses")
def sync_wb_warehouses(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    syncer = WBSync(db, current_user.id)
    return syncer.sync_warehouses()

@app.post("/sync/wb/stocks")
def sync_wb_stocks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    syncer = WBSync(db, current_user.id)
    return syncer.sync_stocks()

@app.post("/sync/wb/full")
def sync_wb_full(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    syncer = WBSync(db, current_user.id)
    return syncer.full_sync()