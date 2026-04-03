from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base

class TrackedSet(Base):
    __tablename__ = "tracked_sets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    product_number = Column(String, index=True)
    url = Column(String)
    retailer = Column(String, index=True, default="lego")
    user_id = Column(String, index=True, nullable=True)
    target_price = Column(Float, nullable=True)
    last_notified_price = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship to price history
    prices = relationship("PriceHistory", back_populates="set", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('user_id', 'product_number', 'retailer', name='uix_user_product_retailer'),
    )

class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    set_id = Column(Integer, ForeignKey("tracked_sets.id"))
    price = Column(Float)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship back to the set
    set = relationship("TrackedSet", back_populates="prices")
