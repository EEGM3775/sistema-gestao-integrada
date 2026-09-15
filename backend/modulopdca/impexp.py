# backend/modulopdca/impexp.py
"""D120 — `pdca_apontamento/` sai pela porta única.

A foto que o encarregado tira ao apontar o avanço. Ela nasceu na PDCA.2 sem
porta, e o [teste do D70](../funcoesimpexp/test_d70_portas_de_midia.py) —
escrito exatamente para que a lista não voltasse a crescer sozinha — apontou o
campo pelo nome.

**O que faltava, e eram duas coisas de gravidade diferente:**

- **em produção o arquivo não abria.** Sem porta ele sairia por `/media/`, que o
  gateway responde **404**. A foto era gravada e ficava inalcançável — o pior
  desfecho possível para uma evidência, porque o sistema aceita o envio e só
  falha na hora de mostrar;
- **em dev com `DEBUG=True` era o oposto, e pior.** O Django serve o binário
  direto, **fora de auth, fora de entitlement e fora da RLS**: a foto de obra de
  um tenant ficava legível por quem tivesse a URL.

**Por que `permissoes_entrega` é só a leitura.** Apontar e ver são pessoas
diferentes por decisão da planta (§8): `campo` aponta, `planejador` e
`diretoria` só leem. Exigir `pdca.avanco.apontar` para abrir a foto tiraria do
planejador a evidência do avanço que ele está conferindo — fecharia com a régua
da escrita um ato que é de leitura. É a mesma separação que a Prancheta precisou
fazer para o `campo` não perder o desenho no canteiro.

**O rastro fica `RASTRO_AUDITADO`, que é o padrão do `entregar_campo`.** A foto é
dado do cliente saindo do perímetro (R12) e, diferente da miniatura do diário,
ela é **prova de medição**: a PDCA.3 faz dinheiro sair a partir do avanço que
esta foto documenta, e quem abriu a evidência é pergunta de auditoria de obra.
O risco de afogar a trilha ([D67](../../docs/historico-correcoes.md)) não se
aplica na mesma medida — o diário mostra dezenas de miniaturas por página, aqui
é no máximo uma foto por lançamento, e a maioria dos lançamentos não tem
nenhuma.
"""
from __future__ import annotations

from funcoesimpexp.entrega import buscar_do_tenant, entregar_campo
from funcoesimpexp.registro import (
    NATUREZA_ARQUIVO,
    ArquivoEntregue,
    Coluna,
    EntregaInvalida,
    Recurso,
    registrar,
)

from .models import ApontamentoAvanco

RECURSO_FOTO = "pdca.avanco_foto"
ESPECIE_FOTO = "foto"


@registrar(RECURSO_FOTO)
class FotoDoApontamento(Recurso):
    """A foto de campo de um apontamento de avanço."""

    rotulo = "Foto do apontamento de avanço"
    modulo = "pdca"
    # `entitlement` fica no padrão (o próprio `modulo`): o PDCA é vendido do
    # `empresarial` para cima (decisão do dono, 22/08), e não é fundação como o
    # diário de obra — que por isso declara `None`.
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("pdca.avanco.view", "pdca.avanco.apontar")
    permissoes_entrega = ("pdca.avanco.view",)

    colunas = (
        Coluna("atividade", "Atividade"),
        Coluna("local", "Local da obra"),
        Coluna("data", "Data do avanço"),
        Coluna("percentual", "Avanço (%)"),
        Coluna("apontado_por", "Apontado por"),
        Coluna("foto", "Foto"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_FOTO:
            raise EntregaInvalida(f"Espécie '{especie}' não existe na foto do apontamento.")
        apontamento = buscar_do_tenant(
            ApontamentoAvanco, chave, tenant_id, campo_pk="apontamento_id",
        )
        return entregar_campo(apontamento, apontamento.foto, alternativa="foto")
