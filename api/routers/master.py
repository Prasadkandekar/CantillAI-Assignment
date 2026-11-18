"""Read-only master data."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from api.deps import get_db
from db import models as m
from services.engine_adapter import dec

router = APIRouter(prefix="/api", tags=["master"])


@router.get("/items")
def items(db=Depends(get_db)):
    return [{"item_code": i.item_code, "description": i.description, "uom": i.uom, "category": i.category,
             "item_type": i.item_type, "standard_price": str(dec(i.standard_price))}
            for i in db.scalars(select(m.Item).order_by(m.Item.item_code))]


@router.get("/suppliers")
def suppliers(db=Depends(get_db)):
    return [{"supplier_id": s.supplier_id, "name": s.name, "city": s.city, "categories": s.categories,
             "status": s.status, "on_time_pct": str(dec(s.on_time_pct)), "quality_rating": str(dec(s.quality_rating))}
            for s in db.scalars(select(m.Supplier).order_by(m.Supplier.supplier_id))]


@router.get("/plants")
def plants(db=Depends(get_db)):
    return [{"plant": p.plant, "name": p.name} for p in db.scalars(select(m.Plant).order_by(m.Plant.plant))]
