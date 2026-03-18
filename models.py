from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base

class TrackedSet(Base):
    __tablename__ = "tracked_sets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    product_number = Column(String, unique=True, index=True)
    url = Column(String, unique=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship to price history
    prices = relationship("PriceHistory", back_populates="set", cascade="all, delete-orphan")

class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    set_id = Column(Integer, ForeignKey("tracked_sets.id"))
    price = Column(Float)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship back to the set
    set = relationship("TrackedSet", back_populates="prices")
