from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.template import MessageTemplate
from backend.app.services.audit import write_audit
from backend.app.services.permissions import permission_denied_detail
from backend.app.services.serializers import list_dict, to_dict

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    body: str


class TemplateUpdate(BaseModel):
    name: str | None = None
    body: str | None = None
    enabled: bool | None = None


@router.get("")
def list_templates(db: DbSession, _: CurrentUserDep) -> list[dict]:
    return list_dict(list(db.scalars(select(MessageTemplate).order_by(MessageTemplate.id.desc()))))


@router.post("")
def create_template(payload: TemplateCreate, db: DbSession, user: CurrentUserDep) -> dict:
    if not (user.is_admin or user.can("can_broadcast")):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_broadcast"))
    template = MessageTemplate(name=payload.name, body=payload.body, created_by=user.username)
    db.add(template)
    db.flush()
    write_audit(db, actor=user, action="template.create", target_type="message_template",
                target_id=template.id, detail={"name": template.name})
    db.commit()
    db.refresh(template)
    return to_dict(template)


@router.patch("/{template_id}")
def update_template(template_id: int, payload: TemplateUpdate, db: DbSession, user: CurrentUserDep) -> dict:
    if not (user.is_admin or user.can("can_broadcast")):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_broadcast"))
    template = db.get(MessageTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(template, key, value)
    write_audit(db, actor=user, action="template.update", target_type="message_template",
                target_id=template.id, detail=values)
    db.commit()
    db.refresh(template)
    return to_dict(template)
