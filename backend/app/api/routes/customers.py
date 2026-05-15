from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import DbSession
from backend.app.models.customer import Customer, Friend
from backend.app.services.parsers import parse_customer_text
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class CustomerImport(BaseModel):
    text: str
    source: str | None = None
    assume_consent: bool = False


@router.get("")
def list_customers(db: DbSession, limit: int = 100, offset: int = 0) -> list[dict]:
    rows = list(db.scalars(select(Customer).order_by(Customer.id.desc()).offset(offset).limit(limit)))
    return list_dict(rows)


@router.post("/import")
def import_customers(payload: CustomerImport, db: DbSession) -> dict:
    imported, rejected = parse_customer_text(payload.text, payload.source, payload.assume_consent)
    created: list[dict] = []
    duplicated: list[str] = []

    for item in imported:
        existing = db.scalar(select(Customer).where(Customer.phone == item["phone"]))
        if existing:
            duplicated.append(item["phone"])
            continue
        customer = Customer(**item)
        db.add(customer)
        db.flush()
        created.append(to_dict(customer))

    db.commit()
    return {"created": created, "duplicated": duplicated, "rejected": rejected}


@router.get("/friends")
def list_friends(db: DbSession, limit: int = 100, offset: int = 0) -> list[dict]:
    rows = list(db.scalars(select(Friend).order_by(Friend.id.desc()).offset(offset).limit(limit)))
    return list_dict(rows)
