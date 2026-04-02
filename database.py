from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Database connection URL
# Default points to the Kubernetes service 'postgres'
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://scraper_user:scraper_pass@postgres:5432/scraper_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # test connections before use — auto-recovers after DB restarts
    pool_recycle=300,     # recycle connections every 5 min to prevent stale idle connections
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
