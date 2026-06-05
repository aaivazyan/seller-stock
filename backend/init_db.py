from database import SessionLocal
from models import Company

db = SessionLocal()

companies = ["WB", "Ozon", "MyWarehouse"]
for name in companies:
    exists = db.query(Company).filter(Company.name == name).first()
    if not exists:
        db.add(Company(name=name))

db.commit()
db.close()
print("Companies initialized")