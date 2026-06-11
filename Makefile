.PHONY: up down restart build ps logs models list-audio test-aec backup reflection parakeet-on parakeet-off health

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart $(s)

build:
	docker compose build

ps:
	docker compose ps

# make logs s=orchestrator
logs:
	docker compose logs -f $(s)

models:
	bash scripts/download_models.sh

list-audio:
	docker compose run --rm orchestrator python bot.py --list-devices

# make test-aec d=plughw:1,0
test-aec:
	bash scripts/test_aec.sh $(d)

backup:
	bash scripts/backup.sh

reflection:
	docker compose run --rm -T reflection

# Fase 2-3: switch STT to parakeet (also set STT_BACKEND=openai in compose env)
parakeet-on:
	docker compose --profile stt-parakeet up -d

parakeet-off:
	docker compose --profile stt-parakeet stop stt-parakeet

health:
	bash scripts/healthcheck.sh
