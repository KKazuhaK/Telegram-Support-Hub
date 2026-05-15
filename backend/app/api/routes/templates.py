from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import DbSession
from backend.app.models.template import MessageTemplate
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    body: str
    created_by: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    body: str | None = None
    enabled: bool | None = None


@router.get("")
def list_templates(db: DbSession) -> list[dict]:
    return list_dict(list(db.scalars(select(MessageTemplate).order_by(MessageTemplate.id.desc()))))


@router.post("")
def create_template(payload: TemplateCreate, db: DbSession) -> dict:
    template = MessageTemplate(name=payload.name, body=payload.body, created_by=payload.created_by)
    db.add(template)
    db.commit()
    db.refresh(template)
    return to_dict(template)


@router.patch("/{template_id}")
def update_template(template_id: int, payload: TemplateUpdate, db: DbSession) -> dict:
    template = db.get(MessageTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="template not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    db.commit()
    db.refresh(template)
    return to_dict(template)
