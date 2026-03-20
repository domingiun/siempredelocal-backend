# backend/app/utils/pagination.py
from typing import List, Tuple, Any
from sqlalchemy.orm import Query
from fastapi import Query as FastAPIQuery

class Paginator:
    @staticmethod
    def paginate_query(
        query: Query,
        page: int = 1,
        per_page: int = 10
    ) -> Tuple[List[Any], int, int, int]:
        """Pagina una consulta SQLAlchemy"""
        total = query.count()
        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()
        
        return items, total, page, per_page
    
    @staticmethod
    def create_pagination_dict(
        items: List,
        total: int,
        page: int,
        per_page: int
    ) -> dict:
        """Crea diccionario con metadatos de paginación"""
        total_pages = (total + per_page - 1) // per_page
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }