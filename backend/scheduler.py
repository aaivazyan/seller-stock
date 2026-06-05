from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def sync_all_users():
    """Фоновая задача: синхронизация для всех активных пользователей"""
    logger.info(f"Starting scheduled sync at {datetime.now()}")
    
    try:
        from database import SessionLocal
        from models import User, CompanyApiKey
        from wb_sync import WBSync
        
        db = SessionLocal()
        
        users_with_keys = db.query(User.id).join(CompanyApiKey).filter(
            CompanyApiKey.company_id == 1,
            CompanyApiKey.is_active == True
        ).distinct().all()
        
        logger.info(f"Found {len(users_with_keys)} users with WB API key")
        
        for user in users_with_keys:
            try:
                syncer = WBSync(db, user.id)
                result = syncer.full_sync()
                logger.info(f"User {user.id}: sync completed")
            except Exception as e:
                logger.error(f"User {user.id}: sync failed - {str(e)[:100]}")
        
        db.close()
        
    except Exception as e:
        logger.error(f"Sync task failed: {e}")

def start_scheduler():
    """Запускает планировщик"""
    N = 15
    scheduler.add_job(
        func=sync_all_users,
        trigger=IntervalTrigger(minutes=N),
        id="wb_sync_job",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info(f"Scheduler started! Sync will run every {N} minutes.")

def stop_scheduler():
    """Останавливает планировщик"""
    scheduler.shutdown()
    logger.info("Scheduler stopped.")