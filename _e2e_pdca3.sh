#!/bin/bash
# Roda os quatro E2E da PDCA.3 em sequência e limpa o resíduo no fim.
# É só para o ciclo de desenvolvimento — a verdade continua em testes/e2e/.
cd /home/eegm/projetos/02sistema_gestao_integrada || exit 1
export LD_LIBRARY_PATH="$HOME/.local/chromium-libs"

# **A pausa entre testes não é cautela — é o `limit_req` do gateway.** A zona
# `login` é de 10 req/min por IP (infra/gateway/nginx.unified.conf), e cada teste
# faz de 1 a 5 logins. Rodados em sequência, o quarto leva 429 e falha por um
# motivo que nada tem a ver com o que ele prova.
for t in pdca3_medicao_test pdca3_grade_browser_test \
         pdca3_formulario_browser_test aprovacoes_admin_browser_test; do
  echo "=== $t ==="
  .venv/bin/python "testes/e2e/$t.py" 2>&1 | tail -4
  sleep 45
done

echo "=== faxina ==="
docker exec sgi-erp python manage.py limpar_residuo_e2e --confirmar 2>&1 \
  | grep -v 'INFO \|WARNING \|staticfiles' | tail -2
