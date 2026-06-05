import requests
from sqlalchemy.orm import Session
from models import Product, ProductSize, Warehouse, Stock, CompanyApiKey
from typing import Dict, List, Set
from datetime import datetime

class WBSync:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.api_key = self._get_api_key()
        self.content_url = "https://content-api.wildberries.ru"
        self.marketplace_url = "https://marketplace-api.wildberries.ru"
        self.analytics_url = "https://seller-analytics-api.wildberries.ru"
    
    def _get_api_key(self) -> str:
        key_record = self.db.query(CompanyApiKey).filter(
            CompanyApiKey.user_id == self.user_id,
            CompanyApiKey.company_id == 1,
            CompanyApiKey.is_active == True
        ).first()
        
        if not key_record or not key_record.api_key:
            raise Exception("WB API key not found")
        
        return key_record.api_key
    
    def _get_headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    # ==================== ТОВАРЫ ====================
    
    def _fetch_cards_page(self, cursor: Dict = None) -> Dict:
        url = f"{self.content_url}/content/v2/get/cards/list"
        
        payload = {
            "settings": {
                "sort": {"ascending": True},
                "cursor": cursor if cursor else {"limit": 100},
                "filter": {"withPhoto": -1}
            }
        }
        
        response = requests.post(url, json=payload, headers=self._get_headers())
        # print(f"[WB API] POST /content/v2/get/cards/list -> Status: {response.status_code}")  # закомментировано
        
        if response.status_code != 200:
            print(f"[WB API] Error response: {response.text[:500]}")
            raise Exception(f"WB API error: {response.status_code} - {response.text}")
        
        return response.json()
    
    def sync_products(self) -> Dict:
        print(f"User {self.user_id}: syncing products...")
        
        all_skus: Set[str] = set()
        cursor = None
        page = 0
        limit = 100
        
        while True:
            page += 1
            # print(f"Fetching products page {page}...")  # закомментировано
            
            if cursor is None:
                request_cursor = {"limit": limit}
            else:
                request_cursor = {
                    "limit": limit,
                    "updatedAt": cursor.get("updatedAt"),
                    "nmID": cursor.get("nmID")
                }
            
            response = self._fetch_cards_page(request_cursor)
            cards = response.get("cards", [])
            
            if not cards:
                break
            
            for card in cards:
                nm_id = card.get("nmID")
                vendor_code = card.get("vendorCode")
                
                if not vendor_code or not nm_id:
                    continue
                
                all_skus.add(vendor_code)
                
                product = self.db.query(Product).filter(
                    Product.user_id == self.user_id,
                    Product.sku == vendor_code
                ).first()
                
                if product:
                    product.name = card.get("title", "Без названия")
                    product.wb_nm_id = nm_id
                    product.imt_id = card.get("imtID")
                    product.brand = card.get("brand")
                    product.subject_name = card.get("subjectName")
                    product.description = card.get("description")
                    product.created_at_wb = card.get("createdAt")
                    product.updated_at_wb = card.get("updatedAt")
                    product.need_kiz = card.get("needKiz", False)
                    product.kiz_marked = card.get("kizMarked", False)
                else:
                    product = Product(
                        user_id=self.user_id,
                        sku=vendor_code,
                        name=card.get("title", "Без названия"),
                        wb_nm_id=nm_id,
                        imt_id=card.get("imtID"),
                        brand=card.get("brand"),
                        subject_name=card.get("subjectName"),
                        description=card.get("description"),
                        created_at_wb=card.get("createdAt"),
                        updated_at_wb=card.get("updatedAt"),
                        need_kiz=card.get("needKiz", False),
                        kiz_marked=card.get("kizMarked", False),
                        is_hidden=False
                    )
                    self.db.add(product)
                    self.db.flush()
                
                sizes = card.get("sizes", [])
                for size in sizes:
                    chrt_id = size.get("chrtID") or size.get("chrtId")
                    if not chrt_id:
                        continue
                    
                    existing_size = self.db.query(ProductSize).filter(
                        ProductSize.chrt_id == chrt_id
                    ).first()
                    
                    if not existing_size:
                        product_size = ProductSize(
                            product_id=product.id,
                            chrt_id=chrt_id,
                            size_name=size.get("techSize", "")
                        )
                        self.db.add(product_size)
            
            cursor = response.get("cursor")
            if not cursor:
                break
            
            total = cursor.get("total", 0)
            if total < limit:
                break
        
        print(f"User {self.user_id}: products synced - {len(all_skus)}")
        
        all_products = self.db.query(Product).filter(
            Product.user_id == self.user_id
        ).all()
        
        hidden_count = 0
        for product in all_products:
            if product.sku not in all_skus and not product.is_hidden:
                product.is_hidden = True
                hidden_count += 1
        
        if hidden_count > 0:
            print(f"User {self.user_id}: hidden {hidden_count} products")
        
        self.db.commit()
        
        return {
            "products_total": len(all_skus),
            "products_hidden": hidden_count
        }
    
    # ==================== СКЛАДЫ FBS ====================
    
    def sync_fbs_warehouses(self) -> Dict:
        # print("Syncing FBS warehouses (seller's warehouses)...")  # закомментировано
        
        url = "https://marketplace-api.wildberries.ru/api/v3/warehouses"
        response = requests.get(url, headers=self._get_headers())
        # print(f"[WB API] GET /api/v3/warehouses -> Status: {response.status_code}")  # закомментировано
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch FBS warehouses: {response.status_code}")
        
        warehouses_data = response.json()
        new_count = 0
        
        for w in warehouses_data:
            external_id = str(w.get("id"))
            name = w.get("name", "Unknown")
            
            existing = self.db.query(Warehouse).filter(
                Warehouse.user_id == self.user_id,
                Warehouse.company_id == 1,
                Warehouse.external_id == external_id,
                Warehouse.type == "FBS"
            ).first()
            
            if not existing:
                warehouse = Warehouse(
                    company_id=1,
                    user_id=self.user_id,
                    external_id=external_id,
                    name=name,
                    type="FBS",
                    address=""
                )
                self.db.add(warehouse)
                new_count += 1
        
        self.db.commit()
        
        total = self.db.query(Warehouse).filter(
            Warehouse.user_id == self.user_id,
            Warehouse.company_id == 1,
            Warehouse.type == "FBS"
        ).count()
        
        print(f"User {self.user_id}: FBS warehouses - {total} total, {new_count} new")
        
        return {"type": "FBS", "total": total, "new": new_count}
    
    # ==================== СКЛАДЫ FBO ====================
    
    def sync_fbo_warehouses(self) -> Dict:
        # print("Syncing FBO warehouses (WB's warehouses)...")  # закомментировано
        
        url = "https://marketplace-api.wildberries.ru/api/v3/offices"
        response = requests.get(url, headers=self._get_headers())
        # print(f"[WB API] GET /api/v3/offices -> Status: {response.status_code}")  # закомментировано
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch FBO warehouses: {response.status_code}")
        
        warehouses_data = response.json()
        new_count = 0
        
        for w in warehouses_data:
            external_id = str(w.get("id"))
            name = w.get("name", "Unknown")
            address = w.get("address", "")
            
            existing = self.db.query(Warehouse).filter(
                Warehouse.user_id == self.user_id,
                Warehouse.company_id == 1,
                Warehouse.external_id == external_id,
                Warehouse.type == "FBO"
            ).first()
            
            if not existing:
                warehouse = Warehouse(
                    company_id=1,
                    user_id=self.user_id,
                    external_id=external_id,
                    name=name,
                    type="FBO",
                    address=address
                )
                self.db.add(warehouse)
                new_count += 1
        
        self.db.commit()
        
        total = self.db.query(Warehouse).filter(
            Warehouse.user_id == self.user_id,
            Warehouse.company_id == 1,
            Warehouse.type == "FBO"
        ).count()
        
        print(f"User {self.user_id}: FBO warehouses - {total} total, {new_count} new")
        
        return {"type": "FBO", "total": total, "new": new_count}
    
    # ==================== ОСТАТКИ ====================
    
    def _fetch_stocks_for_fbs_warehouse(self, warehouse_id: int, chrt_ids: List[int]) -> List[Dict]:
        url = f"{self.marketplace_url}/api/v3/stocks/{warehouse_id}"
        
        all_stocks = []
        for i in range(0, len(chrt_ids), 1000):
            chunk = chrt_ids[i:i+1000]
            payload = {"chrtIds": chunk}
            
            response = requests.post(url, json=payload, headers=self._get_headers())
            # print(f"[WB API] POST /api/v3/stocks/{warehouse_id} -> Status: {response.status_code}")  # закомментировано
            
            if response.status_code != 200:
                print(f"[WB API] Error response: {response.text[:500]}")
                continue
            
            data = response.json()
            all_stocks.extend(data.get("stocks", []))
        
        return all_stocks
    
    def _fetch_stocks_for_fbo_warehouse(self, nm_ids: List[int]) -> List[Dict]:
        url = f"{self.analytics_url}/api/analytics/v1/stocks-report/wb-warehouses"
        
        all_stocks = []
        limit = 1000
        offset = 0
        
        while True:
            payload = {
                "nmIds": nm_ids,
                "limit": limit,
                "offset": offset
            }
            
            response = requests.post(url, json=payload, headers=self._get_headers())
            # print(f"[WB API] POST /api/analytics/v1/stocks-report/wb-warehouses -> Status: {response.status_code}")  # закомментировано
            
            if response.status_code != 200:
                print(f"[WB API] Error response: {response.text[:500]}")
                break
            
            data = response.json()
            items = data.get("data", {}).get("items", [])
            
            if not items:
                break
            
            all_stocks.extend(items)
            
            if len(items) < limit:
                break
            
            offset += limit
        
        return all_stocks
    
    def sync_stocks(self) -> Dict:
        print(f"User {self.user_id}: processing stocks...")
        
        product_sizes = self.db.query(ProductSize).filter(
            ProductSize.chrt_id.isnot(None)
        ).all()
        
        if not product_sizes:
            print(f"User {self.user_id}: no product sizes found")
            return {"stocks_updated": 0, "fbs_warehouses_processed": 0, "fbo_warehouses_processed": 0}
        
        chrt_to_size = {ps.chrt_id: ps for ps in product_sizes}
        all_chrt_ids = list(chrt_to_size.keys())
        # print(f"Found {len(all_chrt_ids)} unique chrt_ids")  # закомментировано
        
        fbs_warehouses = self.db.query(Warehouse).filter(
            Warehouse.user_id == self.user_id,
            Warehouse.company_id == 1,
            Warehouse.type == "FBS"
        ).all()
        
        total_updated = 0
        
        # FBS склады
        for warehouse in fbs_warehouses:
            # print(f"Processing FBS warehouse {warehouse.external_id}...")  # закомментировано
            stocks = self._fetch_stocks_for_fbs_warehouse(warehouse.external_id, all_chrt_ids)
            
            for stock_item in stocks:
                chrt_id = stock_item.get("chrtId")
                quantity = stock_item.get("amount", 0)
                
                if not chrt_id or chrt_id not in chrt_to_size:
                    continue
                
                product_size = chrt_to_size[chrt_id]
                product = self.db.query(Product).filter(
                    Product.id == product_size.product_id,
                    Product.user_id == self.user_id
                ).first()
                
                if not product:
                    continue
                
                stock = self.db.query(Stock).filter(
                    Stock.user_id == self.user_id,
                    Stock.warehouse_id == warehouse.id,
                    Stock.product_id == product.id,
                    Stock.size_id == product_size.id
                ).first()
                
                if stock:
                    stock.available_quantity = quantity
                    stock.physical_quantity = quantity
                    stock.updated_at = datetime.now()
                else:
                    stock = Stock(
                        user_id=self.user_id,
                        warehouse_id=warehouse.id,
                        product_id=product.id,
                        size_id=product_size.id,
                        physical_quantity=quantity,
                        available_quantity=quantity
                    )
                    self.db.add(stock)
                
                total_updated += 1
            
            warehouse.last_sync_at = datetime.now()
        
        # FBO склады
        products = self.db.query(Product).filter(
            Product.user_id == self.user_id,
            Product.wb_nm_id.isnot(None),
            Product.is_hidden == False
        ).all()
        
        if products:
            nm_ids = list({p.wb_nm_id for p in products})
            # print(f"Found {len(nm_ids)} unique nm_ids for FBO")  # закомментировано
            
            fbo_stocks = self._fetch_stocks_for_fbo_warehouse(nm_ids)
            
            for stock_item in fbo_stocks:
                nm_id = stock_item.get("nmId")
                quantity = stock_item.get("quantity", 0)
                warehouse_id = str(stock_item.get("warehouseId"))
                
                if not nm_id:
                    continue
                
                product = self.db.query(Product).filter(
                    Product.user_id == self.user_id,
                    Product.wb_nm_id == nm_id
                ).first()
                
                if not product:
                    continue
                
                warehouse = self.db.query(Warehouse).filter(
                    Warehouse.user_id == self.user_id,
                    Warehouse.company_id == 1,
                    Warehouse.type == "FBO",
                    Warehouse.external_id == warehouse_id
                ).first()
                
                if not warehouse:
                    # print(f"Creating new FBO warehouse: {warehouse_id}")  # закомментировано
                    warehouse = Warehouse(
                        company_id=1,
                        user_id=self.user_id,
                        external_id=warehouse_id,
                        name=stock_item.get("warehouseName", f"WB Warehouse {warehouse_id}"),
                        type="FBO",
                        address=""
                    )
                    self.db.add(warehouse)
                    self.db.commit()
                    self.db.refresh(warehouse)
                
                chrt_id = stock_item.get("chrtId")
                size_id = None
                if chrt_id and chrt_id in chrt_to_size:
                    size_id = chrt_to_size[chrt_id].id
                
                stock = self.db.query(Stock).filter(
                    Stock.user_id == self.user_id,
                    Stock.warehouse_id == warehouse.id,
                    Stock.product_id == product.id,
                    Stock.size_id == size_id
                ).first()
                
                if stock:
                    stock.available_quantity = quantity
                    stock.physical_quantity = quantity
                    stock.updated_at = datetime.now()
                else:
                    stock = Stock(
                        user_id=self.user_id,
                        warehouse_id=warehouse.id,
                        product_id=product.id,
                        size_id=size_id,
                        physical_quantity=quantity,
                        available_quantity=quantity
                    )
                    self.db.add(stock)
                
                total_updated += 1
            
            fbo_warehouses = self.db.query(Warehouse).filter(
                Warehouse.user_id == self.user_id,
                Warehouse.company_id == 1,
                Warehouse.type == "FBO"
            ).all()
            
            for warehouse in fbo_warehouses:
                warehouse.last_sync_at = datetime.now()
        
        self.db.commit()
        print(f"User {self.user_id}: stocks updated - {total_updated}")
        
        return {
            "stocks_updated": total_updated,
            "fbs_warehouses_processed": len(fbs_warehouses),
            "fbo_warehouses_processed": len(products) if products else 0
        }
    
    # ==================== ПОЛНАЯ СИНХРОНИЗАЦИЯ ====================
    
    def full_sync(self) -> Dict:
        # print(f"Starting full sync for user {self.user_id}")  # закомментировано
        
        fbs_result = self.sync_fbs_warehouses()
        fbo_result = self.sync_fbo_warehouses()
        products_result = self.sync_products()
        stocks_result = self.sync_stocks()
        
        return {
            "warehouses": {
                "fbs": fbs_result,
                "fbo": fbo_result
            },
            "products": products_result,
            "stocks": stocks_result
        }