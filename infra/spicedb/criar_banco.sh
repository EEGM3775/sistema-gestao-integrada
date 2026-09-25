#!/bin/sh
# Cria o banco e o role do SpiceDB (o PDP da remodelagem, fase 2) — idempotente.
#
# Não mora em infra/postgres/init/ de propósito: aquele script só roda na
# PRIMEIRA subida de um volume vazio, e todo ambiente que já existe (o dev, o
# staging) nunca veria o banco novo. Este roda a cada `up`, como serviço de uma
# volta só, e não faz nada quando o banco já está lá.
#
# Menor privilégio, pelo mesmo desenho dos outros dois bancos: o SpiceDB entra
# com um role comum, dono só do banco dele.
set -eu

export PGPASSWORD="$POSTGRES_SUPERUSER_PASSWORD"
PSQL="psql -v ON_ERROR_STOP=1 -h postgres -U $POSTGRES_SUPERUSER -d postgres -tA"

if [ -z "$($PSQL -c "SELECT 1 FROM pg_roles WHERE rolname = '$SPICEDB_DB_USER'")" ]; then
    $PSQL -c "CREATE ROLE $SPICEDB_DB_USER WITH LOGIN PASSWORD '$SPICEDB_DB_PASSWORD'"
fi
if [ -z "$($PSQL -c "SELECT 1 FROM pg_database WHERE datname = '$SPICEDB_DB'")" ]; then
    $PSQL -c "CREATE DATABASE $SPICEDB_DB OWNER $SPICEDB_DB_USER"
    psql -v ON_ERROR_STOP=1 -h postgres -U "$POSTGRES_SUPERUSER" -d "$SPICEDB_DB" \
        -c "REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT ALL ON SCHEMA public TO $SPICEDB_DB_USER;"
fi
echo "Banco $SPICEDB_DB pronto para o SpiceDB."
