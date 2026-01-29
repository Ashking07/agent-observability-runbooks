from __future__ import annotations

from uuid import UUID
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db import get_db  # adjust to your project
from ..models import Policy  # adjust path
from ..schemas import PolicyCreateIn, PolicyUpdateIn, PolicyOut  # adjust import

router = APIRouter(tags=["policies"])

def _get_policy_or_404(db: Session, policy_id: UUID) -> Policy:
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.post(
    "/v1/projects/{project_id}/policies",
    response_model=PolicyOut,
    status_code=status.HTTP_201_CREATED,
)
def create_policy(project_id: str, body: PolicyCreateIn, db: Session = Depends(get_db)):
    # Optional: enforce unique name within project at app-level
    existing = db.execute(
        select(Policy).where(Policy.project_id == project_id, Policy.name == body.name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Policy name already exists in this project")

    policy = Policy(
        project_id=project_id,
        name=body.name,
        description=body.description,
        runbook_yaml=body.runbook_yaml,
        is_active=True,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@router.get(
    "/v1/projects/{project_id}/policies",
    response_model=List[PolicyOut],
)
def list_policies(
    project_id: str,
    active: bool = Query(True, description="If true, only return active policies"),
    db: Session = Depends(get_db),
):
    q = select(Policy).where(Policy.project_id == project_id)
    if active:
        q = q.where(Policy.is_active.is_(True))
    q = q.order_by(Policy.updated_at.desc())
    rows = db.execute(q).scalars().all()
    return rows


@router.get(
    "/v1/policies/{policy_id}",
    response_model=PolicyOut,
)
def get_policy(policy_id: UUID, db: Session = Depends(get_db)):
    return _get_policy_or_404(db, policy_id)


@router.put(
    "/v1/policies/{policy_id}",
    response_model=PolicyOut,
)
def update_policy(policy_id: UUID, body: PolicyUpdateIn, db: Session = Depends(get_db)):
    policy = _get_policy_or_404(db, policy_id)

    # Apply partial updates
    if body.name is not None:
        policy.name = body.name
    if body.description is not None:
        policy.description = body.description
    if body.runbook_yaml is not None:
        policy.runbook_yaml = body.runbook_yaml
    if body.is_active is not None:
        policy.is_active = body.is_active

    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@router.delete(
    "/v1/policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_policy(policy_id: UUID, db: Session = Depends(get_db)):
    policy = _get_policy_or_404(db, policy_id)
    policy.is_active = False
    db.add(policy)
    db.commit()
    return None
