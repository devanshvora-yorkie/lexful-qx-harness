.PHONY: up down logs ps e2e phase1

up:
	@test -f .env || (echo "Create .env from .env.example and fill in the keys." && exit 1)
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f harness

e2e phase1:
	docker compose exec harness npm run e2e

ps:
	docker compose ps
