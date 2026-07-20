#!/bin/bash
# Cria os bancos e as roles de aplicação (menor privilégio) para backend e IAM.
# Executado uma única vez pelo container do Postgres na primeira subida.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
    -- Role + banco do backend
    CREATE ROLE ${backend_USER} WITH LOGIN PASSWORD '${backend_PASSWORD}';
    CREATE DATABASE ${backend_DB} OWNER ${backend_USER};

    -- Role + banco do IAM
    CREATE ROLE ${IAM_USER} WITH LOGIN PASSWORD '${IAM_PASSWORD}';
    CREATE DATABASE ${IAM_DB} OWNER ${IAM_USER};
SQL

# Revoga acesso público e garante privilégios só ao dono em cada banco.
for db_user in "${backend_DB}:${backend_USER}" "${IAM_DB}:${IAM_USER}"; do
    db="${db_user%%:*}"
    usr="${db_user##*:}"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-SQL
        REVOKE ALL ON SCHEMA public FROM PUBLIC;
        GRANT ALL ON SCHEMA public TO ${usr};
SQL
done

echo "Bancos ${backend_DB} e ${IAM_DB} criados com roles de aplicação."
