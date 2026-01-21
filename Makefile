.PHONY: up down logs config

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

config:
	docker compose config | sed -n '/^services:/,$$p' | sed -n '/^  api:/,/^  [a-z]/p'
