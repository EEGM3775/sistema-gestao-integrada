# backend/modulodiario/tasks.py
"""
Disparo da análise de IA de um documento do diário.

Fase 11.3: o antigo `disparar_analise_ia` chamava o microsserviço Node
`funcoesia` por HTTP (com o `Token` legado → 401, achado D1). A lógica foi
absorvida por uma Celery task Python em `funcoesia.tasks.analisar_documento_ia`
(lê a imagem in-process e chama a LLM de visão local). Este alias mantém os
call sites existentes funcionando apontando para a nova task.
"""
from funcoesia.tasks import analisar_documento_ia

# Compat: nome histórico usado pelas views do diário.
disparar_analise_ia = analisar_documento_ia
