#!/bin/bash
# Запускает ig_local_agent.py и держит Mac в рабочем состоянии (caffeinate -i).
# caffeinate завершается вместе с python3 — Mac снова засыпает когда сервис остановлен.

cd /Users/egorzukov/juma-agent

# Подгружаем секреты из .env если есть
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

exec caffeinate -i python3 ig_local_agent.py
