from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from database import Base
import hashlib

# ==================== USERS ====================
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    telegram_chat_id = Column(String(100), nullable=True)
    max_user_id = Column(String(100), nullable=True)
    is_special_offer = Column(Boolean, default=False)
    subscription_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    def set_password(self, password: str):
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    def check_password(self, password: str) -> bool:
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()

# ==================== COMPANIES ====================
class Company(Base):
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)

# ==================== API KEYS ====================
class CompanyApiKey(Base):
    __tablename__ = "company_api_keys"
    __table_args__ = (UniqueConstraint('user_id', 'company_id'),)
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    api_key = Column(String(1000), nullable=True)
    api_secret = Column(String(1000), nullable=True)
    access_token = Column(String(1000), nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

# ==================== WAREHOUSES ====================
class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint('user_id', 'company_id', 'external_id', 'type'),)
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    external_id = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(10), nullable=False, default="FBS")  # 'FBO' или 'FBS'
    address = Column(String(255), nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

# ==================== PRODUCTS ====================
class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint('user_id', 'sku'),)
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Основные поля
    sku = Column(String(100), nullable=False)           # vendorCode (артикул продавца)
    name = Column(String(255), nullable=False)          # title (наименование)
    wb_nm_id = Column(Integer, nullable=True)          # nmID (артикул WB)
    
    # Дополнительные поля из карточки товара
    imt_id = Column(Integer, nullable=True)            # ID объединённой карточки
    brand = Column(String(255), nullable=True)         # бренд
    subject_name = Column(String(255), nullable=True)  # категория
    description = Column(Text, nullable=True)          # описание товара
    created_at_wb = Column(DateTime, nullable=True)    # дата создания в WB
    updated_at_wb = Column(DateTime, nullable=True)    # дата обновления в WB
    need_kiz = Column(Boolean, default=False)          # нужна ли маркировка
    kiz_marked = Column(Boolean, default=False)        # есть ли маркировка
    
    # Системные поля
    is_hidden = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# ==================== PRODUCT SIZES ====================
class ProductSize(Base):
    __tablename__ = "product_sizes"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    chrt_id = Column(Integer, unique=True, nullable=False)   # ID размера (для остатков)
    size_name = Column(String(100), nullable=True)            # S, M, L, 42, 44 и т.д.
    created_at = Column(DateTime, default=datetime.now)

# ==================== STOCKS ====================
class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (UniqueConstraint('user_id', 'warehouse_id', 'product_id', 'size_id'),)
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    size_id = Column(Integer, ForeignKey("product_sizes.id"), nullable=True)  # может быть NULL (если у товара нет размеров)
    physical_quantity = Column(Integer, default=0)
    available_quantity = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# ==================== MONITORING ====================
class MonitoringSettings(Base):
    __tablename__ = "monitoring_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    low_stock_threshold = Column(Integer, default=3)
    is_enabled = Column(Boolean, default=True)
    telegram_enabled = Column(Boolean, default=False)
    max_enabled = Column(Boolean, default=False)

class ProductMonitoring(Base):
    __tablename__ = "product_monitoring"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, unique=True)
    custom_threshold = Column(Integer, nullable=True)
    is_monitoring_disabled = Column(Boolean, default=False)

class NotificationLog(Base):
    __tablename__ = "notification_log"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    available_quantity = Column(Integer, nullable=False)
    threshold_used = Column(Integer, nullable=False)
    channel = Column(String(20), nullable=False)
    sent_at = Column(DateTime, default=datetime.now)