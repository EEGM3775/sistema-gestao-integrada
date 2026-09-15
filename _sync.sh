#!/bin/bash
# Sincroniza no contêiner sgi-erp os arquivos que a PDCA.1 toca.
# A imagem tem o código embutido (o repo não é montado), então iterar exige
# copiar. É só para o ciclo de desenvolvimento — a verdade continua no repo.
set -e
cd /home/eegm/projetos/02sistema_gestao_integrada

docker cp payment/planos.py                sgi-erp:/app/payment/planos.py
docker cp backend/modulopdca/models.py     sgi-erp:/app/modulopdca/models.py
docker cp backend/modulopdca/services.py   sgi-erp:/app/modulopdca/services.py
docker cp backend/modulopdca/serializers.py sgi-erp:/app/modulopdca/serializers.py
docker cp backend/modulopdca/views.py      sgi-erp:/app/modulopdca/views.py
docker cp backend/modulopdca/urls.py       sgi-erp:/app/modulopdca/urls.py
docker cp backend/modulopdca/admin.py      sgi-erp:/app/modulopdca/admin.py
docker cp backend/modulopdca/tests.py      sgi-erp:/app/modulopdca/tests.py
docker cp backend/modulopdca/signals.py    sgi-erp:/app/modulopdca/signals.py
docker cp backend/modulopdca/apps.py       sgi-erp:/app/modulopdca/apps.py
docker cp backend/modulopdca/impexp.py     sgi-erp:/app/modulopdca/impexp.py
docker cp backend/config/urls.py           sgi-erp:/app/config/urls.py
docker cp backend/obras/serializers.py     sgi-erp:/app/obras/serializers.py
docker cp backend/nucleo/test_tetos_no_payment.py sgi-erp:/app/nucleo/test_tetos_no_payment.py

docker exec sgi-erp mkdir -p /app/modulopdca/management/commands
docker cp backend/modulopdca/management/. sgi-erp:/app/modulopdca/management/

if [ -d backend/modulopdca/migrations ]; then
  docker cp backend/modulopdca/migrations/. sgi-erp:/app/modulopdca/migrations/
fi
echo "sincronizado"
