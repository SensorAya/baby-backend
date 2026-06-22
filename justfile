set dotenv-load := true

uv := "uv"
fastapi := uv + " run fastapi"
ruff := uv + " run ruff"
dc := "docker compose"

# list available commands
default:
    @just --list

# install dependencies
install:
    {{uv}} sync

# run the dev server (with auto-reload)
dev:
    {{fastapi}} dev

# run the production server
run:
    {{fastapi}} run

# lint the codebase
lint:
    {{ruff}} check .

# format the codebase
format fmt:
    {{ruff}} format .

# auto-fix lint issues
fix:
    {{ruff}} check --fix .

# start postgresql in the background
db-up:
    {{dc}} up -d

# stop postgresql
db-down:
    {{dc}} down

# restart postgresql (destroy and recreate)
db-reset:
    {{dc}} down -v && {{dc}} up -d

# show postgresql logs
db-logs:
    {{dc}} logs -f

# open a psql shell to postgresql
db-shell:
    {{dc}} exec -e PGPASSWORD="$POSTGRES_PASSWORD" postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

_alembic := uv + " run alembic"

# create a new empty migration (write raw SQL in the generated file)
migrate-create name:
    {{_alembic}} revision -m "{{name}}"

# create a new migration with autogenerate (detects model changes)
migrate-autogen name:
    {{_alembic}} revision --autogenerate -m "{{name}}"

# apply all pending migrations
migrate:
    {{_alembic}} upgrade head

# rollback the last migration
rollback:
    {{_alembic}} downgrade -1

# show current migration revision
migrate-status:
    {{_alembic}} current

# show migration history
migrate-history:
    {{_alembic}} history
