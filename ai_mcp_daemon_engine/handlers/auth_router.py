# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from .config import Config, LocalUser
from .jwt_local import create_local_jwt, get_or_create_admin_token

router = APIRouter(prefix="/auth", tags=["auth"])


def authenticate(username: str, password: str) -> LocalUser | None:
    user = Config._USERS.get(username)
    return user if user and user.verify(password) else None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    # static admin
    if (
        Config.admin_username
        and Config.admin_password
        and form.username == Config.admin_username
        and form.password == Config.admin_password
    ):
        return {"access_token": get_or_create_admin_token(), "token_type": "bearer"}

    # user file
    user = authenticate(form.username, form.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_local_jwt({"sub": user.username, "roles": user.roles})
    return {"access_token": token, "token_type": "bearer"}
