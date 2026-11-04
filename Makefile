.PHONY: up setup check down logs ps e2e

# build.sh creates .env, checks the keys, builds the image and (re)starts the container.
up setup:
	./build.sh

check:
	./build.sh --check

down:
	docker compose down

logs:
	docker compose logs -f harness

e2e:
	docker compose exec harness npm run e2e

ps:
	docker compose ps
