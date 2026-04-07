# backend/app/models/content/article.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db import Base


class Article(Base):
    __tablename__ = "articles"

    id              = Column(Integer, primary_key=True, index=True)
    title           = Column(String(255), nullable=False)
    content         = Column(Text, nullable=False)
    image_url       = Column(String(500), nullable=True)
    published       = Column(Boolean, default=True, nullable=False)
    # Autor
    author_name     = Column(String(150), nullable=True)
    author_photo_url= Column(String(500), nullable=True)
    author_bio      = Column(String(300), nullable=True)
    created_by      = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
