"""Create an administrator interactively; credentials never enter source control."""
import asyncio
import getpass
from uuid import uuid4

from sqlalchemy import text

from api.users import NewUser, hash_password
from config.settings import Settings
from market_data.db import create_engine


async def create():
    user = NewUser(email=input("Administrator email: "), password=getpass.getpass("Password: "), role="admin")
    engine = create_engine(Settings())
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""INSERT INTO app_users(id,email,password_hash,role)
                VALUES (:id,:email,:hash,'admin')"""),
                {"id": uuid4(), "email": user.email, "hash": hash_password(user.password)})
        print("Administrator created.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create())
