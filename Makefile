.PHONY: up down logs ps phase1

up:
	@test -f .env || (echo "Create .env from .env.example and fill in the keys." && exit 1)
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f harness

phase1:
	docker compose exec harness npm run phase1

ps:
	docker compose ps
