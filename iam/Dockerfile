FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

# Aplica migrações, sincroniza o RBAC e sobe o serviço. Em produção, rode
# `migrate` + `sync_authz` num passo separado (job) em vez de no entrypoint.
# `sync_authz --all-tenants` é ADITIVO (Fase 9): reflete o catálogo e garante que
# os papéis de fábrica tenham as permissões do modelo, sem apagar ajustes manuais
# do admin — seguro/idempotente a cada boot.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py sync_authz --all-tenants && gunicorn iam_project.wsgi:application --bind 0.0.0.0:8001"]
