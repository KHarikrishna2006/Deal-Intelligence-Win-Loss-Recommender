from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=160)
    organization_name: str = Field(min_length=1, max_length=200)
    title: Optional[str] = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    title: Optional[str] = None
    organization_id: uuid.UUID
    is_active: bool
    created_at: datetime


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    industry: Optional[str] = None
    is_demo: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut
    organization: OrganizationOut


class SessionOut(TokenOut):
    permissions: list[str] = []
