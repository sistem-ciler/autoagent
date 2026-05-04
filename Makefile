.PHONY: up up-infra up-apps up-obs down ps status logs logs-svc pull deploy backup clean shell

COMPOSE := docker compose
SVC     ?= autoagent

up:
	$(COMPOSE) up -d

up-infra:
	$(COMPOSE) up -d postgres redis minio

up-apps:
	$(COMPOSE) up -d autoagent cua trend-radar synapse

up-obs:
	$(COMPOSE) up -d caddy prometheus grafana loki promtail

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

status:
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

logs:
	$(COMPOSE) logs -f --tail=100

logs-svc:
	$(COMPOSE) logs -f --tail=200 $(SVC)

pull:
	$(COMPOSE) pull

deploy:
	./scripts/deploy.sh $(SVC)

backup:
	@echo "[backup] pg_dump all schemas → /tmp/"
	@docker exec $$($(COMPOSE) ps -q postgres) bash -c '\
		for db in autoagent cua trend_radar synapse; do \
			pg_dump -U $$POSTGRES_USER $$db | gzip > /tmp/$$db-$$(date +%Y%m%d-%H%M).sql.gz \
			&& echo "[backup] dumped $$db"; \
		done'

clean:
	docker container prune -f
	docker image prune -f

shell:
	$(COMPOSE) exec $(SVC) sh
