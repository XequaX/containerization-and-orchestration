#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$HOME/labs/lab1"
APP_DIR="$PROJECT_DIR/app"
PYTHON="$PROJECT_DIR/.venv/bin/python"
CGROUP="/sys/fs/cgroup/mydocker-test"

MEMORY_LIMIT=104857600
CPU_QUOTA="50000 100000"
PIDS_LIMIT=10

if [[ ! -x "$PYTHON" ]]; then
    echo "Ошибка: Python не найден: $PYTHON" >&2
    exit 1
fi

if [[ ! -f "$APP_DIR/main.py" ]]; then
    echo "Ошибка: не найден $APP_DIR/main.py" >&2
    exit 1
fi

if [[ $EUID -eq 0 ]]; then
    echo "Не запускай весь скрипт через sudo."
    echo "Он должен запускаться от обычного пользователя." >&2
    exit 1
fi

if [[ ! -d "$CGROUP" ]]; then
    echo "Создаю cgroup: $CGROUP"
    sudo mkdir "$CGROUP"
fi

echo "$MEMORY_LIMIT" | sudo tee "$CGROUP/memory.max" >/dev/null
echo 0 | sudo tee "$CGROUP/memory.swap.max" >/dev/null
echo "$CPU_QUOTA" | sudo tee "$CGROUP/cpu.max" >/dev/null
echo "$PIDS_LIMIT" | sudo tee "$CGROUP/pids.max" >/dev/null

echo "Лимиты cgroup настроены:"
echo "  memory.max = $(cat "$CGROUP/memory.max")"
echo "  cpu.max    = $(cat "$CGROUP/cpu.max")"
echo "  pids.max   = $(cat "$CGROUP/pids.max")"

echo
echo "Запускаю API в namespaces и cgroup..."
echo "Для остановки нажми Ctrl+C."

sudo bash -c '
    echo $$ > "$1/cgroup.procs"
    shift
    user="$1"
    shift
    exec runuser -u "$user" -- "$@"
' bash "$CGROUP" "$USER" \
    unshare \
    --user --map-root-user \
    --pid --mount --net --uts --ipc \
    --fork --mount-proc \
    "$PYTHON" -m uvicorn main:app \
    --app-dir "$APP_DIR" \
    --host 0.0.0.0 \
    --port 8000
