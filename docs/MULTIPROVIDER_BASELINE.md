# Multi-provider phase safety baseline

2026-09-25, before application changes:

- Existing directory was not a Git repository. Initialized a local repository;
  no remote was configured. Existing .gitignore excludes .env/.env.local,
  .local runtime state, logs, node_modules, dist and Python/build caches.
  Workspace Python/PostgreSQL/Redis binaries and databases are outside this repo.
- Backend: 72 passed, four database tests skipped without TEST_DATABASE_URL.
- Backend with a newly created disposable database: 76 passed, zero skipped.
  Only that disposable database was migrated and removed. The local application
  database and its instruments were not altered.
- Ruff: passed.
- Frontend: one test passed; production TypeScript/Vite build passed.
- Existing upstream Starlette TestClient deprecation warning remains.
- Application endpoints, local process topology and existing code were inspected.

The supplied next-phase request ends mid-sentence in section V. Work follows
the complete supplied requirements; no omitted requirements are inferred.

## Fresh baseline, 2026-09-27

This run received the complete phase request through section AU; the earlier truncated-request note
above describes the previous session only. Git already existed with baseline commit 3b8ed86. Existing
uncommitted .dockerignore and requirements.lock edits were preserved. No remote/push/new commit was made.

Before application changes: 72 backend tests passed, four integration tests skipped (no disposable DB URL),
Ruff passed, one frontend test passed and production build passed. Frontend esbuild initially failed
under sandbox ancestor-directory permissions; the same checks passed outside that sandbox.
The runtime NumPy pin was already present as numpy==2.5.3 and matches installed metadata. pip check passed.
No unrelated dependency upgrade was performed. Later all database tests ran against fresh disposable DBs.

Tracked file names and ignore rules were inspected. .env/.env.local, .local, tokens, credential directories,
logs, runtime data, caches and build outputs are excluded. No credentials were printed or committed.
