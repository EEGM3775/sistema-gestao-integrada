FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências de sistema: psycopg2/build + WeasyPrint (pango/cairo) para PDFs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 \
        libcairo2 libgdk-pixbuf-2.0-0 libffi8 shared-mime-info \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ATENÇÃO: o contexto de build é a RAIZ do repositório (ver deploy/compose/base.yml),
# não backend/. É o que permite copiar o pacote compartilhado `funcoesemail/`.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# Pacote compartilhado com a IAM: textos e transporte de e-mail (funcoesemail/README.md).
COPY funcoesemail/ ./funcoesemail/
# Idem: planos, quotas e preços (payment/README.md). O backend passou a precisar
# deles no D24, para servir o medidor de quota e a vitrine de upgrade a partir da
# MESMA tabela que a IAM usa para emitir os tetos.
COPY payment/ ./payment/

EXPOSE 8000

# Aplica migrações e sobe via gunicorn. Em produção, rode `migrate` num passo
# separado (job) em vez de no entrypoint.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000"]
