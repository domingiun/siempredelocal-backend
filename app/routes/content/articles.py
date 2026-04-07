# backend/app/routes/content/articles.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db import get_db
from app.models.content.article import Article
from app.models.user.user import User
from app.schemas.content.article import ArticleResponse, ArticleListItem
from app.core.security import get_current_user
from app.core.dependencies import get_current_admin_user
from app.utils.file_upload import validate_image_mime, read_with_size_limit, generate_safe_filename, ALLOWED_EXTENSIONS
from app.utils.storage import upload_file, delete_file, extract_filename_from_url

router = APIRouter(prefix="/articles", tags=["articles"])

ARTICLE_FOLDER  = "article-images"
AUTHOR_FOLDER   = "author-photos"


def _parse_bool(value: Optional[str], default: bool = True) -> bool:
    """Convierte string form-data ('true'/'false') a bool de forma segura."""
    if value is None:
        return default
    return str(value).lower() in ("true", "1", "yes")


async def _upload_image(file: UploadFile, folder: str) -> str:
    import os
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Formato no permitido. Use: {', '.join(ALLOWED_EXTENSIONS)}")
    file_data = await read_with_size_limit(file)
    validate_image_mime(file_data[:16], file_ext)
    filename = generate_safe_filename(file_ext)
    # upload_file es síncrono (Supabase client) — corre en thread pool
    # para no bloquear el event loop de asyncio
    return await run_in_threadpool(
        upload_file,
        folder=folder,
        filename=filename,
        file_data=file_data,
        content_type=file.content_type or "image/jpeg",
    )


# ─── Público: listar artículos publicados ───────────────────────────────────
@router.get("/", response_model=List[ArticleListItem])
def list_articles(db: Session = Depends(get_db)):
    return (
        db.query(Article)
        .filter(Article.published == True)
        .order_by(Article.created_at.desc())
        .limit(20)
        .all()
    )


# ─── Admin: listar TODOS — DEBE ir antes de /{article_id} ───────────────────
@router.get("/admin/all", response_model=List[ArticleResponse])
def admin_list_articles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    return db.query(Article).order_by(Article.created_at.desc()).all()


# ─── Público: ver artículo completo ─────────────────────────────────────────
@router.get("/{article_id}", response_model=ArticleResponse)
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article or not article.published:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    return article


# ─── Admin: crear artículo ───────────────────────────────────────────────────
@router.post("/", response_model=ArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_article(
    title: str = Form(...),
    content: str = Form(...),
    published: str = Form("true"),          # str → _parse_bool para evitar error 422
    author_name: Optional[str] = Form(None),
    author_bio: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    author_photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    image_url        = None
    author_photo_url = None

    if image and image.filename:
        image_url = await _upload_image(image, ARTICLE_FOLDER)

    if author_photo and author_photo.filename:
        author_photo_url = await _upload_image(author_photo, AUTHOR_FOLDER)

    article = Article(
        title=title,
        content=content,
        published=_parse_bool(published),
        image_url=image_url,
        author_name=author_name or None,
        author_bio=author_bio or None,
        author_photo_url=author_photo_url,
        created_by=current_user.id,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


# ─── Admin: actualizar artículo ─────────────────────────────────────────────
@router.put("/{article_id}", response_model=ArticleResponse)
async def update_article(
    article_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    published: Optional[str] = Form(None),
    author_name: Optional[str] = Form(None),
    author_bio: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    author_photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    if title    is not None: article.title   = title
    if content  is not None: article.content = content
    if published is not None: article.published = _parse_bool(published)
    # author_name y author_bio: string vacío = limpiar campo
    if author_name is not None: article.author_name = author_name or None
    if author_bio  is not None: article.author_bio  = author_bio  or None

    if image and image.filename:
        if article.image_url:
            delete_file(ARTICLE_FOLDER, extract_filename_from_url(article.image_url))
        article.image_url = await _upload_image(image, ARTICLE_FOLDER)

    if author_photo and author_photo.filename:
        if article.author_photo_url:
            delete_file(AUTHOR_FOLDER, extract_filename_from_url(article.author_photo_url))
        article.author_photo_url = await _upload_image(author_photo, AUTHOR_FOLDER)

    db.commit()
    db.refresh(article)
    return article


# ─── Admin: eliminar artículo ────────────────────────────────────────────────
@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    if article.image_url:
        delete_file(ARTICLE_FOLDER, extract_filename_from_url(article.image_url))
    if article.author_photo_url:
        delete_file(AUTHOR_FOLDER, extract_filename_from_url(article.author_photo_url))

    db.delete(article)
    db.commit()
