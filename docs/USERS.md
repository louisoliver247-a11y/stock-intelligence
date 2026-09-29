# Workspace users

The site opens on a dedicated sign-in screen. Sign in with your email and
password to open the workspace. The sidebar and dashboard are hidden until
authentication succeeds. Signing out or an expired session returns to sign-in. Administrators can open **Users** to list,
create, and delete accounts. Regular users can read market data; administrators
can run market operations and manage accounts. The backend operator key remains an
administrator recovery method through the API. You cannot delete your own account or the last
administrator. Deleting an account revokes all its sessions immediately.

Deploy the backend and run `python -m alembic upgrade head` before signing in.
Create the first administrator with `python scripts/create_admin.py` using the
deployment's database environment. The script prompts for a password without
echoing it. Accounts live in PostgreSQL and are not uploaded with source code.

Passwords use individually salted scrypt hashes. Session tokens are random,
stored hashed on the server, and expire after eight hours. The browser keeps its
token only in memory; reload requires signing in again. Sign out revokes it.
Login is limited to ten attempts per email per five minutes using Redis.
Serve public deployments over HTTPS and retain database backups securely.

GitHub stores the source; GitHub Pages alone cannot run this Python/PostgreSQL/
Redis application. See DEPLOYMENT.md for the backend deployment requirements.
