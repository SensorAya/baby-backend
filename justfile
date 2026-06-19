uv := "uv"
fastapi := uv + " run fastapi"
ruff := uv + " run ruff"

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
