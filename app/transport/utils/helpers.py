# app/transport/utils/helpers.py
"""
Transport module shared utilities.
Used across all api/ route files for consistent pagination and filtering.
"""
from flask import request
from sqlalchemy.orm import Query


# -------------------------------------------------------------------------
# Pagination
# -------------------------------------------------------------------------

def paginate(query: Query, page: int = None, per_page: int = None) -> dict:
    """
    Execute a paginated SQLAlchemy query and return a consistent dict.

    Usage in a Resource:
        result = paginate(DriverProfile.query.filter_by(is_deleted=False))

    Returns:
        {
            "items": [...],     # list of model instances
            "total": 120,       # total matching rows
            "page": 1,
            "per_page": 25,
            "pages": 5,
            "has_next": true,
            "has_prev": false
        }
    """
    page = page or max(request.args.get("page", 1, type=int), 1)
    per_page = per_page or min(request.args.get("per_page", 25, type=int), 100)

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        "items": paginated.items,
        "total": paginated.total,
        "page": paginated.page,
        "per_page": paginated.per_page,
        "pages": paginated.pages,
        "has_next": paginated.has_next,
        "has_prev": paginated.has_prev,
    }


# -------------------------------------------------------------------------
# Filtering
# -------------------------------------------------------------------------

def filter_query(query: Query, model, filters: dict) -> Query:
    """
    Apply a dict of field:value filters to a SQLAlchemy query.
    Skips None values so unset filters are ignored cleanly.

    Usage in a Resource:
        filters = {
            "verification_tier": request.args.get("verification_tier"),
            "compliance_status": request.args.get("compliance_status"),
            "is_online": request.args.get("is_online", type=bool),
        }
        query = filter_query(query, DriverProfile, filters)

    Supports:
        - Exact match:     {"field": "value"}
        - Min filter:      {"field__gte": value}
        - Max filter:      {"field__lte": value}
        - ILIKE search:    {"field__ilike": "search_term"}
    """
    for key, value in filters.items():
        if value is None:
            continue

        if "__gte" in key:
            field = key.replace("__gte", "")
            query = query.filter(getattr(model, field) >= value)

        elif "__lte" in key:
            field = key.replace("__lte", "")
            query = query.filter(getattr(model, field) <= value)

        elif "__ilike" in key:
            field = key.replace("__ilike", "")
            query = query.filter(getattr(model, field).ilike(f"%{value}%"))

        else:
            # Exact match
            if hasattr(model, key):
                query = query.filter(getattr(model, key) == value)

    return query


# -------------------------------------------------------------------------
# Sorting
# -------------------------------------------------------------------------

def sort_query(query: Query, model, allowed_fields: list) -> Query:
    """
    Apply sorting from query string params with a whitelist of allowed fields.
    Prevents arbitrary column injection.

    Usage:
        query = sort_query(query, DriverProfile, ["created_at", "average_rating"])

    Query params:
        ?sort_by=created_at&sort_order=desc
    """
    sort_by = request.args.get("sort_by", "created_at")
    sort_order = request.args.get("sort_order", "desc")

    # Only allow whitelisted fields
    if sort_by not in allowed_fields:
        sort_by = allowed_fields[0]

    column = getattr(model, sort_by, None)
    if column is None:
        return query

    return query.order_by(column.desc() if sort_order == "desc" else column.asc())
