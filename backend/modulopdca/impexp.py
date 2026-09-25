# backend/modulopdca/impexp.py
"""D120 — `pdca_apontamento/` sai pela porta única.

A foto que o encarregado tira ao apontar o avanço. Ela nasceu na PDCA.2 sem
porta, e o [teste do D70](../../testes/backend/funcoesimpexp/test_d70_portas_de_midia.py) —
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

from .models import (
    AnexoOcorrencia, ApontamentoAvanco, ItemVerificacao, NaoConformidade,
    VerificacaoEficacia,
)

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


# ---------------------------------------------------------------------------
# PDCA.7 — as três fotos da qualidade
# ---------------------------------------------------------------------------
# Nascem **com** porta, e não depois dela: o D120 custou ao módulo uma foto de
# obra gravada e inalcançável em produção (o gateway responde 404 em `/media/`)
# e, em dev, legível por qualquer um com a URL — fora de auth, de entitlement e
# de RLS. A lição foi que `upload_to` novo sem `Recurso` é um vazamento com data
# marcada, e o `test_d70_portas_de_midia` é quem cobra.
#
# **São dois recursos e não três**, porque o corte é por quem lê, não por
# tabela. A foto do item de verificação é parte da **ficha**, e quem a abre é
# quem lê a ficha (`pdca.verificacao.view`). A foto da NC e a foto da eficácia
# são as duas metades da mesma conversa — *o defeito* e *a prova de que ele foi
# consertado* —, e quem as abre é quem acompanha o tratamento (`pdca.nc.view`).
# Separar eficácia num terceiro recurso criaria uma permissão para metade de um
# par que sempre se olha junto.


RECURSO_VERIFICACAO = "pdca.verificacao_foto"
ESPECIE_ITEM = "item"

RECURSO_NC = "pdca.nc_foto"
ESPECIE_NC = "nc"
ESPECIE_EFICACIA = "eficacia"

RECURSO_SSMA = "pdca.ocorrencia_anexo"
ESPECIE_ANEXO = "anexo"
RECURSO_SSMA_CLINICO = "pdca.ocorrencia_atestado"
ESPECIE_ATESTADO = "atestado"


@registrar(RECURSO_VERIFICACAO)
class FotoDaVerificacao(Recurso):
    """A evidência de um item da ficha de verificação."""

    rotulo = "Foto do item de verificação"
    modulo = "pdca"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("pdca.verificacao.view", "pdca.verificacao.aplicar")
    #: **Só a leitura para entregar.** Responder a ficha e lê-la são pessoas
    #: diferentes por decisão da planta (§8): o `campo` e o `tecnico_qualidade`
    #: aplicam; `planejador`, `diretoria` e `fiscal_de_obra` leem. Exigir
    #: `aplicar` para abrir a foto tiraria do fiscal a evidência que ele está
    #: conferindo — fecharia com a régua da escrita um ato que é de leitura. É a
    #: mesma separação que a foto do apontamento precisou fazer.
    permissoes_entrega = ("pdca.verificacao.view",)

    colunas = (
        Coluna("verificacao", "Ficha"),
        Coluna("ordem", "Item"),
        Coluna("texto", "O que se verifica"),
        Coluna("resultado", "Resultado"),
        Coluna("respondido_por", "Respondido por"),
        Coluna("foto", "Foto"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_ITEM:
            raise EntregaInvalida(
                f"Espécie '{especie}' não existe na foto da verificação."
            )
        item = buscar_do_tenant(
            ItemVerificacao, chave, tenant_id, campo_pk="item_verificacao_id",
        )
        return entregar_campo(item, item.foto, alternativa="foto")


@registrar(RECURSO_NC)
class FotoDaNaoConformidade(Recurso):
    """A foto do defeito — e a da prova de que ele foi consertado."""

    rotulo = "Foto da não-conformidade"
    modulo = "pdca"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("pdca.nc.view", "pdca.nc.abrir")
    permissoes_entrega = ("pdca.nc.view",)

    colunas = (
        Coluna("nc", "Não-conformidade"),
        Coluna("gravidade", "Gravidade"),
        Coluna("descricao", "Descrição"),
        Coluna("status", "Situação"),
        Coluna("aberta_por", "Aberta por"),
        Coluna("foto", "Foto"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie == ESPECIE_NC:
            nc = buscar_do_tenant(
                NaoConformidade, chave, tenant_id, campo_pk="nc_id",
            )
            return entregar_campo(nc, nc.foto, alternativa="foto")
        if especie == ESPECIE_EFICACIA:
            registro = buscar_do_tenant(
                VerificacaoEficacia, chave, tenant_id, campo_pk="eficacia_id",
            )
            return entregar_campo(registro, registro.foto, alternativa="foto")
        raise EntregaInvalida(
            f"Espécie '{especie}' não existe na foto da não-conformidade."
        )


# **Dois recursos para uma tabela, e a razão é a permissão.**
#
# `AnexoOcorrencia` guarda a foto da cena e o atestado médico na mesma tabela, e
# as duas não podem sair pelo mesmo gate: a foto documenta o que aconteceu na
# obra, o atestado é dado de saúde do art. 11 da LGPD. Um recurso único daria a
# quem pode ver o acidente o direito de abrir o diagnóstico de quem se
# acidentou.
#
# O gate da saída é `permissoes_da_entrega`, que é **property sem argumento** —
# ele é do recurso, não da linha. Então a separação não cabe num recurso só, e a
# tentativa de fazê-la por dentro seria código que parece proteger e não
# protege. Dois recursos, cada um com o seu gate, e **cada um recusando a linha
# que não é dele**: pedir o atestado pela porta barata levanta `EntregaInvalida`
# antes de qualquer byte sair.


@registrar(RECURSO_SSMA)
class AnexoDaOcorrencia(Recurso):
    """A foto da cena, o boletim, a lista de presença — o que a obra viu."""

    rotulo = "Anexo da ocorrência de segurança"
    modulo = "pdca"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("pdca.ocorrencia.view", "pdca.ocorrencia.registrar")
    permissoes_entrega = ("pdca.ocorrencia.view",)

    colunas = (
        Coluna("ocorrencia", "Ocorrência"),
        Coluna("especie", "Espécie"),
        Coluna("descricao", "Descrição"),
        Coluna("enviado_por", "Enviado por"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_ANEXO:
            raise EntregaInvalida(
                f"Espécie '{especie}' não existe no anexo da ocorrência."
            )
        anexo = buscar_do_tenant(
            AnexoOcorrencia, chave, tenant_id, campo_pk="anexo_id",
        )
        #: **A trava que fecha o desvio.** Sem ela, bastaria pedir o atestado por
        #: esta porta para contornar o `dado_medico`.
        if anexo.especie == AnexoOcorrencia.Especie.ATESTADO:
            raise EntregaInvalida(
                "O atestado médico não sai por esta porta: ele é dado de saúde "
                "e tem gate próprio."
            )
        return entregar_campo(anexo, anexo.arquivo, alternativa="arquivo")


@registrar(RECURSO_SSMA_CLINICO)
class AtestadoDaOcorrencia(Recurso):
    """O atestado médico — **dado de saúde, e a primeira PII do `pdca`**."""

    rotulo = "Atestado médico da ocorrência"
    modulo = "pdca"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = (
        "pdca.ocorrencia.dado_medico", "pdca.ocorrencia.registrar",
    )
    permissoes_entrega = ("pdca.ocorrencia.dado_medico",)

    colunas = (
        Coluna("ocorrencia", "Ocorrência"),
        Coluna("descricao", "Descrição"),
        Coluna("enviado_por", "Enviado por"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_ATESTADO:
            raise EntregaInvalida(
                f"Espécie '{especie}' não existe no atestado da ocorrência."
            )
        anexo = buscar_do_tenant(
            AnexoOcorrencia, chave, tenant_id, campo_pk="anexo_id",
        )
        #: O espelho da trava acima: esta porta só entrega atestado. Pedir a foto
        #: da cena por aqui não vaza nada, mas confundiria a trilha de auditoria
        #: do `dado_medico` com acesso que não é clínico.
        if anexo.especie != AnexoOcorrencia.Especie.ATESTADO:
            raise EntregaInvalida(
                "Esta porta entrega apenas o atestado médico."
            )
        return entregar_campo(anexo, anexo.arquivo, alternativa="arquivo")
