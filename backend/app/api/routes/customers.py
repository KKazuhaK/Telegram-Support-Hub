from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.deps import CurrentUserDep, DbSession
from backend.app.models.account import Account, AccountGroupMember
from backend.app.models.customer import Customer, Friend
from backend.app.services.assignment import assign_customers
from backend.app.services.audit import write_audit
from backend.app.services.parsers import parse_customer_text
from backend.app.services.permissions import permission_denied_detail
from backend.app.services.serializers import list_dict, to_dict
from backend.app.services.tenant_scope import apply_merchant_scope, can_access_row

router = APIRouter()


class CustomerImport(BaseModel):
    text: str
    source: str | None = None
    assume_consent: bool = False
    # Optionally distribute the freshly created (consented) rows to accounts
    # in these groups in the same transaction. None / empty = skip assignment.
    account_group_ids: list[int] | None = None
    max_per_account: int | None = None


class CustomerAssign(BaseModel):
    customer_ids: list[int] | None = None
    account_group_ids: list[int] | None = None
    max_per_account: int | None = None
    only_unassigned: bool = True


class CustomerUpdate(BaseModel):
    """Editable fields. phone is deliberately not here — it's the dedup key
    and changing it would break audit trails and template-rendered messages
    that already captured the old phone in body_snapshot."""
    name: str | None = None
    tags: list[str] | None = None
    source: str | None = None
    consent: bool | None = None
    status: str | None = None
    assigned_account_id: int | None = None


def _scope_accounts_to_user(db, user, account_group_ids: list[int] | None) -> list[int] | None:
    if user.is_admin:
        return account_group_ids
    visible = set(user.visible_group_ids())
    if account_group_ids:
        return [g for g in account_group_ids if g in visible]
    return list(visible)


@router.get("")
def list_customers(
    db: DbSession, user: CurrentUserDep, status: str | None = None, limit: int = 100, offset: int = 0
) -> list[dict]:
    stmt = select(Customer).order_by(Customer.id.desc())
    stmt = apply_merchant_scope(stmt, user, db, Customer)
    if status:
        stmt = stmt.where(Customer.status == status)
    if user.actor_kind == "support_agent" and not user.is_admin:
        # Support agent (non-admin): also constrained by group permission.
        member_subq = select(AccountGroupMember.account_id).where(
            AccountGroupMember.group_id.in_(user.visible_group_ids() or [-1])
        )
        stmt = stmt.where(Customer.assigned_account_id.in_(member_subq))
    rows = list(db.scalars(stmt.offset(offset).limit(limit)))
    return list_dict(rows)


@router.post("/import")
def import_customers(payload: CustomerImport, db: DbSession, user: CurrentUserDep) -> dict:
    if not (user.is_admin or user.can("can_broadcast")):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_broadcast"))

    imported, rejected = parse_customer_text(payload.text, payload.source, payload.assume_consent)
    created: list[dict] = []
    created_ids: list[int] = []
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
        created_ids.append(customer.id)

    assignment = None
    if payload.account_group_ids and created_ids:
        scoped_groups = _scope_accounts_to_user(db, user, payload.account_group_ids)
        assignment = assign_customers(
            db,
            customer_ids=created_ids,
            account_group_ids=scoped_groups,
            max_per_account=payload.max_per_account,
            only_unassigned=True,
        )

    write_audit(
        db, actor=user, action="customer.import",
        detail={
            "created": len(created),
            "duplicated": len(duplicated),
            "rejected": len(rejected),
            "assignment": assignment,
        },
    )
    db.commit()
    return {
        "created": created,
        "duplicated": duplicated,
        "rejected": rejected,
        "assignment": assignment,
    }


@router.patch("/{customer_id}")
def update_customer(
    customer_id: int, payload: CustomerUpdate, db: DbSession, user: CurrentUserDep,
) -> dict:
    if not (user.is_admin or user.can("can_broadcast")
            or user.actor_kind in ("business_agent", "merchant")):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_broadcast"))
    row = db.get(Customer, customer_id)
    if not row or not can_access_row(user, db, row):
        # Return 404 (not 403) so the existence of the row is not leaked
        # to a tenant that shouldn't see it.
        raise HTTPException(status_code=404, detail="客户不存在")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(row, key, value)
    write_audit(db, actor=user, action="customer.update",
                target_type="customer", target_id=row.id, detail=values)
    db.commit()
    db.refresh(row)
    return to_dict(row)


@router.delete("/{customer_id}")
def delete_customer(customer_id: int, db: DbSession, user: CurrentUserDep) -> dict:
    if not (user.is_admin or user.can("can_broadcast")
            or user.actor_kind in ("business_agent", "merchant")):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_broadcast"))
    row = db.get(Customer, customer_id)
    if not row or not can_access_row(user, db, row):
        raise HTTPException(status_code=404, detail="客户不存在")
    db.delete(row)
    write_audit(db, actor=user, action="customer.delete",
                target_type="customer", target_id=customer_id,
                detail={"phone": row.phone})
    db.commit()
    return {"deleted": True}


@router.post("/assign")
def assign(payload: CustomerAssign, db: DbSession, user: CurrentUserDep) -> dict:
    if not (user.is_admin or user.can("can_broadcast")):
        raise HTTPException(status_code=403, detail=permission_denied_detail("can_broadcast"))

    scoped_groups = _scope_accounts_to_user(db, user, payload.account_group_ids)
    result = assign_customers(
        db,
        customer_ids=payload.customer_ids,
        account_group_ids=scoped_groups,
        max_per_account=payload.max_per_account,
        only_unassigned=payload.only_unassigned,
    )
    write_audit(db, actor=user, action="customer.assign", detail={"input": payload.model_dump(), "result": result})
    db.commit()
    return result


@router.get("/friends")
def list_friends(
    db: DbSession, user: CurrentUserDep, account_id: int | None = None,
    status: str | None = None, limit: int = 100, offset: int = 0,
) -> list[dict]:
    stmt = select(Friend).order_by(Friend.id.desc())
    if account_id:
        stmt = stmt.where(Friend.account_id == account_id)
    if status:
        stmt = stmt.where(Friend.status == status)
    if not user.is_admin:
        member_subq = select(AccountGroupMember.account_id).where(
            AccountGroupMember.group_id.in_(user.visible_group_ids() or [-1])
        )
        stmt = stmt.where(Friend.account_id.in_(member_subq))
    return list_dict(list(db.scalars(stmt.offset(offset).limit(limit))))


@router.post("/friends/sync")
def trigger_friend_sync(db: DbSession, user: CurrentUserDep, account_id: int) -> dict:
    """Queue a Celery task to sync friends from the given account's Telegram dialogs."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="该操作仅限管理员")
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="TG 账号不存在")

    from backend.app.workers.account_tasks import sync_account_friends
    task = sync_account_friends.delay(account_id)
    write_audit(db, actor=user, action="friend.sync.dispatch",
                target_type="account", target_id=account_id, detail={"task_id": task.id})
    db.commit()
    return {"task_id": task.id, "account_id": account_id}
