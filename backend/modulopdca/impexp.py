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

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError

from funcoesimpexp.cadastro import RecursoDeCadastro, RecursoDeLista
from funcoesimpexp.entrega import buscar_do_tenant, entregar_campo
from funcoesimpexp.registro import (
    NATUREZA_ARQUIVO,
    ArquivoEntregue,
    Coluna,
    ContextoInvalido,
    EntregaInvalida,
    Guardado,
    Recurso,
    registrar,
)
from funcoesimpexp.relatorio import RecursoDeRelatorio

from . import services
from .models import (
    AnexoOcorrencia, ApontamentoAvanco, Atividade, DialogoSeguranca, ItemVerificacao, LocalObra,
    Medicao, NaoConformidade, Ocorrencia, Restricao, Verificacao, VerificacaoEficacia,
)

RECURSO_LOCAIS = "pdca.local"
RECURSO_RESTRICOES = "pdca.restricao"
RECURSO_NCS = "pdca.nc"
RECURSO_OCORRENCIAS = "pdca.ocorrencia"
RECURSO_VERIFICACOES = "pdca.verificacao"
RECURSO_DDS = "pdca.dds"
RECURSO_MEDICOES = "pdca.medicao"
RECURSO_ATIVIDADES = "pdca.atividade"
RECURSO_CARTEIRA = "pdca.carteira"

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
    guardados = (Guardado(ESPECIE_FOTO, ApontamentoAvanco, "foto"),)

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
    guardados = (Guardado(ESPECIE_ITEM, ItemVerificacao, "foto"),)

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
    guardados = (Guardado(ESPECIE_NC, NaoConformidade, "foto"), Guardado(ESPECIE_EFICACIA, VerificacaoEficacia, "foto"))

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
    guardados = (Guardado(ESPECIE_ANEXO, AnexoOcorrencia, "arquivo",
                          filtro={"especie__in": [e for e in AnexoOcorrencia.Especie.values if e != AnexoOcorrencia.Especie.ATESTADO]}),)

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
    guardados = (Guardado(ESPECIE_ATESTADO, AnexoOcorrencia, "arquivo",
                          filtro={"especie": AnexoOcorrencia.Especie.ATESTADO}),)

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


# ---------------------------------------------------------------------------
# As listas da obra (15/10/2026)
# ---------------------------------------------------------------------------
#
# **Os locais importam; o resto só exporta** (decisão do dono, 15/10/2026). O
# local é cadastro — a árvore de torres, pavimentos e trechos que se monta de uma
# vez. Restrição e programação dependem de uma atividade do cronograma e têm
# fluxo próprio (remover/reabrir, compromisso e PPC); medição, verificação, NC,
# DDS e ocorrência são documentos com assinatura, encerramento e efeitos. Todos
# saem pelo ViewSet da tela (o recorte da obra e o que a pessoa enxerga).


def _num(valor):
    return Decimal(str(valor)) if valor not in (None, "") else None


def _caminho(local) -> str:
    """'T1/P02' — os códigos do topo até o local. É como a planilha diz quem é o
    pai: o código só é único entre irmãos."""
    partes = []
    while local is not None:
        partes.append(local.codigo)
        local = local.pai
    return "/".join(reversed(partes))


@registrar(RECURSO_LOCAIS)
class LocaisDaObra(RecursoDeCadastro):
    """A árvore de locais de uma obra (`contexto`: a obra da tela).

    O pai vem pelo **caminho de códigos** ("T1/P02"). Pai que ainda não existe
    trava a linha — a árvore entra nível a nível: um arquivo com as torres, depois
    o dos pavimentos. Num arquivo só, o pai e o filho novos não se enxergam,
    porque o lote é conferido inteiro contra o banco antes de gravar.
    """

    rotulo = "Locais da obra"
    modulo = "pdca"
    permissoes_exigidas = ("pdca.local.view", "pdca.local.edit")
    modelo = LocalObra
    chave = "codigo"
    contexto_requerido = ("obra",)
    ordem = ("profundidade", "ordem", "codigo")
    nao_validar = ("maps_local", "unidade")

    @property
    def viewset(self):
        from .views import LocalObraViewSet

        return LocalObraViewSet

    colunas = (
        Coluna("codigo", "Código", obrigatoria=True, exemplo="P02"),
        Coluna("nome", "Nome", obrigatoria=True, exemplo="2º pavimento"),
        Coluna("nivel", "Nível", obrigatoria=True, exemplo="Pavimento"),
        Coluna("pai", "Dentro de (caminho)", exemplo="T1", aliases=("pai", "local pai")),
        Coluna("ordem", "Ordem", tipo=int, exemplo="2"),
        Coluna("area_m2", "Área (m²)", tipo=Decimal, exemplo="480"),
        Coluna("observacao", "Observação"),
    )

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        from obras.models import Obra

        obra = Obra.objects.filter(pk=(contexto or {}).get("obra") or 0, tenant_id=tenant_id).first()
        if obra is None:
            raise ContextoInvalido("Escolha uma obra da sua empresa.")
        return {**dict(contexto or {}), "obra": obra.pk}

    def rotulo_do_contexto(self) -> str:
        from obras.models import Obra

        obra = Obra.objects.filter(pk=self.contexto.get("obra") or 0).first()
        return f"Obra: {obra.nome_obra}" if obra else ""

    def escopo(self, qs, request):
        obra = self.contexto.get("obra")
        return qs.filter(obra_id=obra) if obra else qs

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["pai"] = _caminho(obj.pai)
        return saida

    # --- entrada ----------------------------------------------------------------

    def _pai(self, caminho, tenant_id):
        pai = None
        for codigo in [c.strip() for c in str(caminho or "").split("/") if c.strip()]:
            pai = LocalObra.objects.filter(
                tenant_id=tenant_id, obra_id=self.contexto.get("obra"), pai=pai, codigo__iexact=codigo,
            ).first()
            if pai is None:
                return None
        return pai

    def chave_da_linha(self, dados: dict) -> str:
        pai = str(dados.get("pai") or "").strip().strip("/")
        codigo = self.normalizar_chave(dados.get("codigo"))
        return f"{pai}/{codigo}" if pai else codigo

    def localizar(self, dados: dict, tenant_id):
        codigo = self.normalizar_chave(dados.get("codigo"))
        caminho = str(dados.get("pai") or "").strip()
        pai = self._pai(caminho, tenant_id)
        if not codigo or (caminho and pai is None):
            return None
        return LocalObra.objects.filter(
            tenant_id=tenant_id, obra_id=self.contexto.get("obra"), pai=pai, codigo__iexact=codigo,
        ).first()

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        pai = self._pai(dados.get("pai"), tenant_id)
        saida["pai"] = pai
        saida["obra_id"] = self.contexto.get("obra")
        saida["profundidade"] = services.profundidade_de(pai)
        if saida.get("ordem") is None:
            saida["ordem"] = 0
        return saida

    def validar_no_destino(self, dados: dict, tenant_id) -> str:
        caminho = str(dados.get("pai") or "").strip()
        pai = self._pai(caminho, tenant_id)
        if caminho and pai is None:
            return (f"O local “{caminho}” ainda não existe nesta obra — importe primeiro o nível "
                    "de cima (um arquivo por nível).")
        try:
            services.validar_profundidade(pai)
        except DjangoValidationError as erro:
            return erro.messages[0]
        return super().validar_no_destino(dados, tenant_id)


class _ListaDaObra(RecursoDeLista):
    """Documento da obra: sai pelo ViewSet da tela, no recorte dela (`?obra=`)."""

    modulo = "pdca"
    #: Caminho da classe do ViewSet em `modulopdca.views`.
    nome_do_viewset: str = ""

    @property
    def viewset(self):
        from . import views

        return getattr(views, self.nome_do_viewset)

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        if "local" in saida:
            saida["local"] = _caminho(obj.local) if getattr(obj, "local_id", None) else ""
        return saida


@registrar(RECURSO_RESTRICOES)
class RestricoesDaObra(_ListaDaObra):
    rotulo = "Restrições"
    permissoes_exigidas = ("pdca.restricao.view",)
    modelo = Restricao
    nome_do_viewset = "RestricaoViewSet"
    ordem = ("prazo", "restricao_id")
    colunas = (
        Coluna("atividade__codigo", "Atividade (código)"),
        Coluna("atividade__nome", "Atividade"),
        Coluna("local", "Local"),
        Coluna("tipo", "Tipo"),
        Coluna("descricao", "Restrição"),
        Coluna("responsavel", "Responsável"),
        Coluna("prazo", "Prazo", tipo=date),
        Coluna("status", "Situação"),
        Coluna("criada_em", "Criada em", tipo=date),
        Coluna("removida_em", "Removida em", tipo=date),
    )


@registrar(RECURSO_NCS)
class NaoConformidadesDaObra(_ListaDaObra):
    rotulo = "Não conformidades"
    permissoes_exigidas = ("pdca.nc.view",)
    modelo = NaoConformidade
    nome_do_viewset = "NaoConformidadeViewSet"
    ordem = ("-aberta_em",)
    colunas = (
        Coluna("nc_id", "NC", tipo=int),
        Coluna("aberta_em", "Aberta em", tipo=date),
        Coluna("gravidade", "Gravidade"),
        Coluna("descricao", "Defeito"),
        Coluna("local", "Local"),
        Coluna("atividade__nome", "Serviço"),
        Coluna("status", "Situação"),
        Coluna("aberta_por", "Aberta por"),
        Coluna("encerrada_em", "Encerrada em", tipo=date),
    )


@registrar(RECURSO_OCORRENCIAS)
class OcorrenciasDaObra(_ListaDaObra):
    """Sem nenhum dado de saúde (parte do corpo, lesão, CID, atestado) nem o
    acidentado: são outro gate (`pdca.ocorrencia.dado_medico`), e o arquivo é
    para contar e acompanhar, não para o prontuário."""

    rotulo = "Ocorrências de segurança"
    permissoes_exigidas = ("pdca.ocorrencia.view",)
    modelo = Ocorrencia
    nome_do_viewset = "OcorrenciaViewSet"
    ordem = ("-ocorrido_em",)
    colunas = (
        Coluna("ocorrencia_id", "Ocorrência", tipo=int),
        Coluna("ocorrido_em", "Data", tipo=date),
        Coluna("tipo", "Tipo"),
        Coluna("classificacao", "Classificação"),
        Coluna("descricao", "O que aconteceu"),
        Coluna("local", "Local"),
        Coluna("dias_perdidos", "Dias perdidos", tipo=int),
        Coluna("status", "Situação"),
    )


@registrar(RECURSO_VERIFICACOES)
class VerificacoesDaObra(_ListaDaObra):
    rotulo = "Fichas de verificação"
    permissoes_exigidas = ("pdca.verificacao.view",)
    modelo = Verificacao
    nome_do_viewset = "VerificacaoViewSet"
    ordem = ("-data", "verificacao_id")
    colunas = (
        Coluna("verificacao_id", "Ficha", tipo=int),
        Coluna("data", "Data", tipo=date),
        Coluna("modelo__nome", "Modelo"),
        Coluna("local", "Local"),
        Coluna("atividade__nome", "Serviço"),
        Coluna("inspetor", "Inspetor"),
        Coluna("status", "Situação"),
    )


@registrar(RECURSO_DDS)
class DialogosDeSeguranca(_ListaDaObra):
    rotulo = "DDS"
    permissoes_exigidas = ("pdca.dds.view",)
    modelo = DialogoSeguranca
    nome_do_viewset = "DialogoSegurancaViewSet"
    ordem = ("-data", "dds_id")
    colunas = (
        Coluna("data", "Data", tipo=date),
        Coluna("tema", "Tema"),
        Coluna("responsavel_nome", "Responsável"),
        Coluna("duracao_min", "Duração (min)", tipo=int),
        Coluna("local", "Local"),
        Coluna("status", "Situação"),
    )


@registrar(RECURSO_MEDICOES)
class MedicoesDaObra(_ListaDaObra):
    rotulo = "Medições"
    permissoes_exigidas = ("pdca.medicao.view",)
    modelo = Medicao
    nome_do_viewset = "MedicaoViewSet"
    ordem = ("contrato__numero", "numero")
    colunas = (
        Coluna("contrato__numero", "Contrato"),
        Coluna("contrato__objeto", "Objeto"),
        Coluna("numero", "Medição", tipo=int),
        Coluna("periodo_inicio", "De", tipo=date),
        Coluna("periodo_fim", "Até", tipo=date),
        Coluna("status", "Situação"),
        Coluna("valor_reajuste", "Reajuste", tipo=Decimal),
        Coluna("apurada_em", "Apurada em", tipo=date),
    )


@registrar(RECURSO_ATIVIDADES)
class AtividadesDoPlano(_ListaDaObra):
    """A EAP do cronograma (`?cronograma=`), com as datas do caminho crítico."""

    rotulo = "Atividades do plano"
    permissoes_exigidas = ("pdca.cronograma.view",)
    modelo = Atividade
    nome_do_viewset = "AtividadeViewSet"
    ordem = ("ordem", "atividade_id")
    colunas = (
        Coluna("codigo", "Código"),
        Coluna("nome", "Atividade"),
        Coluna("duracao_dias", "Duração (dias)", tipo=int),
        Coluna("inicio_cedo", "Início", tipo=date),
        Coluna("termino_cedo", "Término", tipo=date),
        Coluna("folga_total", "Folga (dias)", tipo=int),
        Coluna("critica", "Crítica"),
        Coluna("local", "Local"),
        Coluna("etapa__nome_etapa", "Etapa"),
    )

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["critica"] = "Sim" if obj.critica else "Não"
        return saida


@registrar(RECURSO_CARTEIRA)
class CarteiraDeObras(RecursoDeRelatorio):
    """As obras lado a lado, como a carteira as mostra — uma linha por obra."""

    rotulo = "Carteira de obras"
    modulo = "pdca"
    permissoes_exigidas = ("pdca.cronograma.view",)

    @property
    def view(self):
        from .views import CarteiraView

        return CarteiraView

    colunas = (
        Coluna("nome", "Obra"),
        Coluna("status_rotulo", "Situação"),
        Coluna("data_fim_prevista", "Fim previsto", tipo=date),
        Coluna("termino", "Término pelo plano", tipo=date),
        Coluna("desvio_dias", "Desvio (dias)", tipo=int),
        Coluna("fisico", "Avanço físico (%)", tipo=Decimal),
        Coluna("ppc", "PPC da última semana (%)", tipo=Decimal),
        Coluna("conformidade", "Conformidade (%)", tipo=Decimal),
        Coluna("dias_sem_afastamento", "Dias sem afastamento", tipo=int),
        Coluna("pendencias", "Pendências"),
    )

    def linhas(self, dados) -> list[dict]:
        from datetime import date as _date

        def dia(texto):
            return _date.fromisoformat(texto[:10]) if texto else None

        saida = []
        for o in dados.get("obras", []):
            prazo, avanco = o.get("prazo") or {}, o.get("avanco") or {}
            saida.append({
                "nome": o.get("nome", ""), "status_rotulo": o.get("status_rotulo", ""),
                "data_fim_prevista": dia(o.get("data_fim_prevista")),
                "termino": dia(prazo.get("termino")), "desvio_dias": prazo.get("desvio_dias"),
                "fisico": _num(avanco.get("fisico")),
                "ppc": _num((o.get("ppc") or {}).get("ppc")),
                "conformidade": _num((o.get("conformidade") or {}).get("conformidade")),
                "dias_sem_afastamento": (o.get("seguranca") or {}).get("dias_sem_afastamento"),
                "pendencias": "; ".join(f"{p['rotulo']} ({p['quantas']})" for p in o.get("pendencias", [])),
            })
        return saida
