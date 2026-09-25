FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ATENÇÃO: o contexto de build é a RAIZ do repositório (ver deploy/compose/base.yml),
# não iam/. É o que permite copiar o pacote compartilhado `funcoesemail/`.
COPY iam/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY iam/ .
# Pacote compartilhado com o backend: textos e transporte de e-mail. A IAM entrega
# pelo SMTP dela — recuperação de senha não pode depender do backend estar no ar.
COPY funcoesemail/ ./funcoesemail/
# Valores comerciais (planos, quotas, tetos). A IAM os lê para compor o claim do
# teto de requisições (D23) — ver payment/README.md.
COPY payment/ ./payment/
# O cliente do PDP e o schema gerado do catálogo: a IAM é quem escreve as
# relações no SpiceDB (remodelagem, fase 2 — identity/pdp.py).
COPY funcoesautorizacao/ ./funcoesautorizacao/

EXPOSE 8001

# Aplica migrações, sincroniza o RBAC e sobe o serviço. Em produção, rode
# `migrate` + `sync_authz` num passo separado (job) em vez de no entrypoint.
# `sync_authz --all-tenants` é ADITIVO (Fase 9): reflete o catálogo e garante que
# os papéis de fábrica tenham as permissões do modelo, sem apagar ajustes manuais
# do admin — seguro/idempotente a cada boot.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py sync_authz --all-tenants && gunicorn iam_project.wsgi:application --bind 0.0.0.0:8001"]
