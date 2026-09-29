"""Password authentication and administrator-managed workspace accounts."""
import asyncio
import hashlib
import secrets
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"{salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    salt, expected = encoded.split("$")
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return secrets.compare_digest(actual, expected)


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if value.count("@") != 1 or any(c.isspace() for c in value):
            raise ValueError("Enter a valid email address")
        local, domain = value.split("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Enter a valid email address")
        return value


class NewUser(Login):
    role: Literal["admin", "user"] = "user"


async def session_user(app, token):
    if not token:
        raise HTTPException(401, "UNAUTHORIZED")
    async with app.state.engine.connect() as conn:
        row = (await conn.execute(text("""SELECT u.id, u.email, u.role FROM app_users u
            JOIN user_sessions s ON s.user_id=u.id
            WHERE s.token_hash=:token AND s.expires_at>now()"""),
            {"token": hashlib.sha256(token.encode()).hexdigest()})).mappings().first()
    if not row:
        raise HTTPException(401, "SESSION_EXPIRED_OR_INVALID")
    return dict(row)


def router(operator):
    routes = APIRouter(prefix="/api")
    dummy = hash_password(secrets.token_urlsafe(32))

    async def admin(request: Request, identity=Depends(operator)):
        if identity["role"] != "admin":
            raise HTTPException(403, "ADMIN_REQUIRED")
        return identity

    @routes.post("/auth/login")
    async def login(body: Login, request: Request):
        # Shared Redis limit applies across workers; do not trust forwarded client headers.
        bucket = hashlib.sha256(body.email.encode()).hexdigest()
        redis = request.app.state.redis
        attempts = await redis.eval("""local n=redis.call('INCR',KEYS[1]);
            if n==1 then redis.call('EXPIRE',KEYS[1],300) end; return n""", 1, f"login:{bucket}")
        if attempts > 10:
            raise HTTPException(429, "TOO_MANY_LOGIN_ATTEMPTS_TRY_IN_5_MINUTES")
        async with request.app.state.engine.begin() as conn:
            row = (await conn.execute(text("SELECT * FROM app_users WHERE email=:email"),
                                      {"email": body.email})).mappings().first()
            valid = await asyncio.to_thread(verify_password, body.password, row["password_hash"] if row else dummy)
            if not row or not valid:
                raise HTTPException(401, "INVALID_EMAIL_OR_PASSWORD")
            token = secrets.token_urlsafe(32)
            await conn.execute(text("DELETE FROM user_sessions WHERE expires_at<=now()"))
            await conn.execute(text("""INSERT INTO user_sessions VALUES
                (:token,:user,now()+interval '8 hours')"""),
                {"token": hashlib.sha256(token.encode()).hexdigest(), "user": row["id"]})
        return {"token": token, "email": row["email"], "role": row["role"]}

    @routes.post("/auth/logout", dependencies=[Depends(operator)])
    async def logout(request: Request):
        token = request.headers.get("X-API-Key", "")
        async with request.app.state.engine.begin() as conn:
            await conn.execute(text("DELETE FROM user_sessions WHERE token_hash=:token"),
                               {"token": hashlib.sha256(token.encode()).hexdigest()})
        return {"ok": True}

    @routes.get("/users", dependencies=[Depends(admin)])
    async def users(request: Request):
        async with request.app.state.engine.connect() as conn:
            return [dict(r) for r in (await conn.execute(text(
                "SELECT id,email,role,created_at FROM app_users ORDER BY created_at"))).mappings()]

    @routes.post("/users", status_code=201, dependencies=[Depends(admin)])
    async def create(body: NewUser, request: Request):
        encoded = await asyncio.to_thread(hash_password, body.password)
        try:
            async with request.app.state.engine.begin() as conn:
                row = (await conn.execute(text("""INSERT INTO app_users(id,email,password_hash,role)
                    VALUES (:id,:email,:password,:role) RETURNING id,email,role,created_at"""),
                    {"id": uuid4(), "email": body.email, "password": encoded, "role": body.role})).mappings().one()
                return dict(row)
        except IntegrityError:
            raise HTTPException(409, "EMAIL_ALREADY_EXISTS") from None

    @routes.delete("/users/{user_id}")
    async def delete(user_id: UUID, request: Request, identity=Depends(admin)):
        if identity.get("id") == user_id:
            raise HTTPException(409, "CANNOT_DELETE_YOUR_OWN_ACCOUNT")
        async with request.app.state.engine.begin() as conn:
            await conn.execute(text("LOCK TABLE app_users IN EXCLUSIVE MODE"))
            row = (await conn.execute(text("SELECT role FROM app_users WHERE id=:id"),
                                      {"id": user_id})).first()
            if not row:
                raise HTTPException(404, "USER_NOT_FOUND")
            count = (await conn.execute(text("SELECT count(*) FROM app_users WHERE role='admin'"))).scalar_one()
            if row.role == "admin" and count <= 1:
                raise HTTPException(409, "CANNOT_DELETE_LAST_ADMIN")
            await conn.execute(text("DELETE FROM app_users WHERE id=:id"), {"id": user_id})
        return {"ok": True}

    return routes
