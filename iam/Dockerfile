FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

# Aplica migrações e sobe o serviço. Em produção, rode `migrate` num passo
# separado (job) em vez de no entrypoint.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn iam_project.wsgi:application --bind 0.0.0.0:8001"]
