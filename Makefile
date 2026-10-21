.PHONY: up down logs ps

up:
	@test -f .env || (echo "Create .env from .env.example and fill in the keys." && exit 1)
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f harness

ps:
	docker compose ps
