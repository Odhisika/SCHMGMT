#!/usr/bin/env bash

# Deploy the current branch, install changed dependencies, apply migrations,
# collect static files, and reload the app server.
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

LOG_FILE="deployment.log"
log_message() {
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2" >> "$LOG_FILE"
}

printf 'Starting deployment at %s\n' "$(date)"

# Do not hide local edits or create merge commits during an automated deploy.
if [[ ! -d .git ]]; then
    echo 'Error: this directory is not a Git repository.' >&2
    exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo 'Error: tracked local changes are present; commit or discard them before deploying.' >&2
    exit 1
fi
branch="$(git branch --show-current)"
if [[ -z "$branch" ]]; then
    echo 'Error: cannot deploy from a detached HEAD.' >&2
    exit 1
fi
git pull --ff-only --quiet origin "$branch"
log_message SUCCESS "Updated branch $branch"

VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"
if [[ -x "$VENV_DIR/bin/python" ]]; then
    PYTHON="$VENV_DIR/bin/python"
else
    echo "Error: virtual environment not found at $VENV_DIR" >&2
    exit 1
fi

REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-$PROJECT_DIR/requirements.txt}"
if [[ -f "$REQUIREMENTS_FILE" ]]; then
    requirements_hash="$(sha256sum "$REQUIREMENTS_FILE" | cut -d ' ' -f 1)"
    dependency_marker="$VENV_DIR/.deploy-requirements.sha256"
    if [[ ! -f "$dependency_marker" || "$(<"$dependency_marker")" != "$requirements_hash" ]]; then
        "$PYTHON" -m pip install -r "$REQUIREMENTS_FILE"
        printf '%s\n' "$requirements_hash" > "$dependency_marker"
        log_message SUCCESS 'Dependencies installed from requirements.txt'
    else
        echo 'Requirements unchanged; skipping dependency installation.'
    fi
else
    echo "Error: requirements file not found: $REQUIREMENTS_FILE" >&2
    exit 1
fi

# Migrations are generated during development and committed with code. A deploy
# only applies those committed migrations; makemigrations here can hide mistakes.
"$PYTHON" manage.py migrate --noinput
"$PYTHON" manage.py collectstatic --noinput
log_message SUCCESS 'Migrations applied and static files collected'

restarted=false
if [[ -d tmp ]]; then
    touch tmp/restart.txt
    echo 'Passenger reload requested.'
    restarted=true
fi

for service in gunicorn apache2; do
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$service" 2>/dev/null; then
        sudo systemctl restart "$service"
        echo "Restarted $service."
        restarted=true
    fi
done

if [[ "$restarted" == false ]]; then
    echo 'No Passenger or active gunicorn/apache2 service was detected; restart the app server manually.'
fi

log_message DEPLOY 'Deployment completed successfully'
printf 'Deployment completed at %s\n' "$(date)"
