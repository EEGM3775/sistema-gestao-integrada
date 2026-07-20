# backend/modulodiario/services.py
"""
Serviço único de escrita do diário do dia (Fase C, §6).

Antes, a escrita vivia dentro de `DiarioObraViewSet.contribuir`, acoplada ao
`request.user`. Extraída aqui, a **web** e o **canal WhatsApp** chamam a mesma
função — um só lugar decide autoria, tenant, get-or-create do dia e disparo da
IA (mesmo movimento do `modulocrm/services.py` da Fase 11.2).

Deve ser chamada sob contexto de tenant (a view via `ATOMIC_REQUESTS`+RLS; a task
via `tenant_context`). O `tenant` das linhas criadas é herdado explicitamente da
obra/argumento (objeto criado fora de `perform_create` herda o tenant do pai).
"""
from django.utils import timezone

from .models import DiarioObra, EntradaDiario, DocumentoDiario


def registrar_contribuicao(
    *, obra, funcionario, texto=None, arquivo=None, descricao='',
    eh_ocorrencia=False, clima=None, origem='web', data=None,
    criado_por=None, tenant_id=None,
):
    """Anexa uma contribuição (texto e/ou documento) ao diário do dia da obra.

    Get-or-create do `DiarioObra` (obra, data); cria `EntradaDiario` (texto) e/ou
    `DocumentoDiario` (arquivo → dispara a análise de IA). Retorna o `DiarioObra`.
    """
    # `localdate()` (America/Sao_Paulo), NÃO `timezone.now().date()` (UTC). Com
    # UTC, toda contribuição feita entre 21h e meia-noite era arquivada no diário
    # do DIA SEGUINTE — justamente o horário em que a equipe de campo fecha o dia
    # pelo WhatsApp. Diário de obra é registro contratual: datar errado importa.
    data = data or timezone.localdate()
    if tenant_id is None:
        tenant_id = getattr(obra, 'tenant_id', None)

    diario, _created = DiarioObra.objects.get_or_create(
        obra=obra, data=data,
        defaults={'criado_por': criado_por, 'tenant_id': tenant_id},
    )

    # Clima é do dia inteiro: atualiza se enviado.
    if clima:
        diario.condicoes_climaticas = clima
        diario.save(update_fields=['condicoes_climaticas', 'data_atualizacao'])

    if texto:
        EntradaDiario.objects.create(
            diario_obra=diario, autor=funcionario, origem=origem,
            texto=texto, eh_ocorrencia=eh_ocorrencia, tenant_id=tenant_id,
        )

    if arquivo:
        documento = DocumentoDiario.objects.create(
            diario_obra=diario, autor=funcionario, origem=origem,
            arquivo=arquivo, descricao=descricao or '', tenant_id=tenant_id,
        )
        # Import tardio evita ciclo (tasks → funcoesia → modulodiario).
        from .tasks import disparar_analise_ia
        disparar_analise_ia.delay(
            documento_id=documento.documento_diario_id, tipo_analise='completa',
        )

    return diario
