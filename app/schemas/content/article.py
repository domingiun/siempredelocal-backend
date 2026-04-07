# backend/app/schemas/content/article.py
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class ArticleCreate(BaseModel):
    title: str
    content: str
    published: bool = True


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    published: Optional[bool] = None


class ArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    image_url: Optional[str] = None
    published: bool
    author_name: Optional[str] = None
    author_photo_url: Optional[str] = None
    author_bio: Optional[str] = None
    created_by: int
    created_at: datetime
    updated_at: datetime


class ArticleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: Optional[str] = None   # incluido para preview en homepage
    image_url: Optional[str] = None
    published: bool
    author_name: Optional[str] = None
    author_photo_url: Optional[str] = None
    author_bio: Optional[str] = None
    created_at: datetime
