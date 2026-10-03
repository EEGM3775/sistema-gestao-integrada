"""D24 — camada 3: cota comercial por plano (trava de OBJETO).

Desenho: docs/arquitetura/rate-limiting.md §4 · monetizacao.md §4 e §10 (item 2).

Diferente das camadas 1 e 2, esta **não é proteção técnica — é produto**. O teto
não existe para preservar capacidade; existe porque o cliente comprou um tamanho
de operação. Isso muda quatro coisas em relação ao throttle:

- **O status é 402, não 429.** Um 429 diz "tente de novo mais tarde", e o cliente
  espera; aqui esperar não resolve nada — a saída é comprar. O corpo carrega
  quota, limite e uso justamente para a tela conseguir dizer *qual* limite bateu
  e oferecer o upgrade, em vez de um erro genérico que vira chamado de suporte.
- **Só trava a família de VALOR** (monetizacao.md §4.1: empreendimentos, obras,
  clientes, fornecedores — barato de servir, serve para segmentar plano). A
  família de CUSTO (IA, NF, boleto, drone, armazenamento) **não entra aqui**: a
  regra de ouro do §4 manda medir e cobrar o excedente dela. Travar o cliente no
  meio de um fechamento fiscal para vender um pacote custa mais caro que o
  excedente que se evitaria.
- **Trava só a CRIAÇÃO.** Editar e excluir seguem livres mesmo acima da quota —
  senão um downgrade de plano (ou um "Sob Medida" renegociado para menos)
  deixaria o cliente sem conseguir nem corrigir nem apagar o que já existe, com
  os dados dele reféns. Quem está acima do teto pode arrumar a casa; só não
  cresce.
- **Fail-open sem a claim.** Token sem `quotas` (serviço, legado) não trava nada.
  Não é brecha de paywall: forjar um token exigiria a chave de assinatura da
  plataforma, e quem a tem não precisa burlar quota. O oposto — fail-closed —
  transformaria uma feature comercial em indisponibilidade de escrita. É o mesmo
  trade-off já registrado nas camadas 1 e 2, e pelo mesmo motivo o caminho é
  **logado**: o D21 ensinou que protetor fail-open silencioso fica
  indistinguível de um protetor funcionando.

**Corrida aceita, de propósito.** Duas criações simultâneas no mesmo tenant podem
passar as duas pela contagem e terminar em `limite + 1`. Serializar isso exigiria
travar a linha do tenant em toda criação de objeto — um gargalo por empresa no
caminho de escrita inteiro — para evitar um excesso de uma unidade num limite
COMERCIAL, que o próprio produto resolve no ciclo de faturamento seguinte. É a
diferença para o L5 (corrida na baixa), onde o que estava em jogo era o valor
pago de um título e o lock se pagava.
"""
from __future__ import annotations

import logging

from django.apps import apps
from rest_framework.exceptions import APIException

from payment.planos import QUOTAS_DE_OBJETO

logger = logging.getLogger(__name__)

# Nome da quota → modelo que a materializa. É o **registro único**: o mixin conta
# por aqui e o endpoint de plano itera por aqui, então não existe a possibilidade
# de a trava de um recurso e o medidor dele apontarem para tabelas diferentes.
#
# Este dicionário é ENGENHARIA (qual tabela contar); **quais** quotas travam é
# decisão comercial e mora em `payment/planos.py` §4, onde o dono do software a
# enxerga junto dos preços. Os dois lados precisam casar, e é isso que
# `test_quotas.py` verifica: quota declarada como aplicada sem contador aqui
# barraria o cliente por um limite que ninguém sabe medir; contador aqui sem a
# quota lá é código morto que dá falsa sensação de proteção.
#
# O modelo é referenciado por rótulo (`app.Modelo`), não importado: este módulo é
# carregado por `nucleo`, que é importado por todos os apps — importar os modelos
# deles de volta fecharia um ciclo no carregamento.
RECURSOS_CONTADOS: dict[str, str] = {
    "empreendimentos": "empreendimentos.Empreendimento",
    "obras": "obras.Obra",
    "clientes": "clientes.Cliente",
    "fornecedores": "fornecedores.Fornecedor",
    # ORC.5b — acervo de tabela de preço própria. A linha é a unidade certa (e
    # não o banco) porque é ela que ocupa espaço e é ela que a importação traz
    # aos milhares; limitar "bancos" deixaria um único banco com 200 mil linhas
    # passar batido.
    "banco_preco_linhas": "moduloorcamento.ItemBancoPreco",
    # PDCA.1b — o cronograma marcado como modelo. A tabela é a mesma dos planos
    # comuns, então esta quota é a primeira que conta um **recorte** dela: ver
    # `FILTRO_DO_RECURSO` logo abaixo.
    "planos_modelo": "modulopdca.Cronograma",
}

# Quando a quota não é "quantas linhas a tabela tem", e sim "quantas linhas de um
# certo tipo". Nasceu com `planos_modelo`, e nasceu como mapa em vez de código
# especial porque o caso não é excepcional: quota sobre estado de uma linha
# (modelo × comum, arquivado × ativo) tende a se repetir, e a alternativa — um
# `if recurso == "planos_modelo"` dentro do contador — é a que não escala.
FILTRO_DO_RECURSO: dict[str, dict] = {
    "planos_modelo": {"eh_modelo": True},
}

# Rótulo legível para a mensagem do 402 e para o medidor da UI.
ROTULOS: dict[str, str] = {
    "empreendimentos": "empreendimentos",
    "obras": "obras",
    "clientes": "clientes",
    "fornecedores": "fornecedores",
    "banco_preco_linhas": "linhas de banco de preço próprio",
    "planos_modelo": "planos modelo",
    # Janela, não contagem — o rótulo é lido numa frase ("15 dias para
    # desfazer"), nunca ao lado de uma barra de progresso. Ver `plano_views`.
    "lixo_retencao_dias": "dias de lixeira",
    # Teto de uma chamada (§5.5u): não tem uso a medir, só o limite.
    "boletos_por_lote": "boletos por lote",
    "notas_por_lote": "notas fiscais por lote",
}


class QuotaExcedida(APIException):
    """402 com o suficiente para a UI montar o CTA de upgrade sozinha.

    O corpo é estruturado (não só `detail`) porque a tela precisa saber *qual*
    limite bateu e quanto já se usou. Um 402 com texto solto obrigaria o frontend
    a interpretar string — que quebra na primeira vez que alguém reescrever a
    mensagem. Espelha a `QuotaExcedida` da IAM (`iam/identity/quotas.py`): os
    dois serviços travam quotas diferentes, mas o frontend trata **um** contrato.
    """

    status_code = 402
    default_code = "quota_excedida"

    def __init__(self, *, quota: str, limite: int, uso: int, plano: str | None):
        rotulo = ROTULOS.get(quota, quota)
        super().__init__("quota excedida")
        # A atribuição vem DEPOIS do `super().__init__` de propósito: o
        # `APIException` passa o que recebe por `_get_error_details`, que
        # converte recursivamente todo valor em `ErrorDetail` — uma subclasse de
        # `str`. Pelo construtor, `limite: 0` chegaria ao frontend como `"0"`, e
        # a barra de progresso teria de adivinhar quando converter. Números
        # precisam sair como números; o handler do DRF publica `exc.detail` tal
        # como está quando ele já é dict.
        self.detail = {
            "detail": (
                f"O plano contratado inclui {limite} {rotulo} e o limite já foi "
                "atingido. Exclua o que não usa mais ou faça upgrade do plano "
                "para continuar cadastrando."
            ),
            "code": self.default_code,
            "quota": quota,
            "limite": limite,
            "uso": uso,
            "plano": plano,
        }


def modelo_do_recurso(recurso: str):
    """Modelo Django que materializa a quota `recurso`."""
    return apps.get_model(RECURSOS_CONTADOS[recurso])


def uso_atual(recurso: str, tenant_id) -> int:
    """Quantos objetos deste recurso o tenant já tem.

    Filtra por `tenant_id` **explicitamente** em vez de confiar na RLS: para o
    dono da plataforma o contexto é o de bypass, e uma contagem apoiada só na RLS
    devolveria o total de TODAS as empresas. Mesmo motivo pelo qual
    `scope_queryset_by_tenant` existe ao lado da política do banco.
    """
    consulta = modelo_do_recurso(recurso).objects.filter(tenant_id=tenant_id)
    return consulta.filter(**FILTRO_DO_RECURSO.get(recurso, {})).count()


def limite_do_usuario(user, recurso: str):
    """Teto do recurso para o tenant deste usuário, lido da claim `quotas`.

    Devolve `None` quando não há teto a aplicar — tanto no caso "ilimitado por
    contrato" quanto no caso "token sem a claim". Os dois levam à mesma ação
    (não travar), e distingui-los aqui só faria o chamador repetir a decisão.
    """
    quotas = getattr(user, "iam_quotas", None)
    if not isinstance(quotas, dict):
        logger.warning(
            "quota_sem_claim",
            extra={"recurso": recurso, "usuario": getattr(user, "username", None)},
        )
        return None
    limite = quotas.get(recurso)
    return limite if isinstance(limite, int) and limite >= 0 else None


def checar_quota(user, recurso: str) -> None:
    """Levanta `QuotaExcedida` se o tenant já atingiu o teto do recurso.

    Chamada ANTES de gravar. Não se aplica ao dono da plataforma (não é cliente,
    não tem plano) nem a requisição sem tenant.
    """
    if user is None or getattr(user, "is_superuser", False):
        return

    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        return

    limite = limite_do_usuario(user, recurso)
    if limite is None:
        return

    uso = uso_atual(recurso, tenant_id)
    if uso < limite:
        return

    raise QuotaExcedida(
        quota=recurso,
        limite=limite,
        uso=uso,
        plano=getattr(user, "iam_plano", None),
    )


class QuotaEnforcedMixin:
    """Trava a criação quando o tenant atingiu a quota do plano.

    Uso: declare `quota_recurso = "obras"` no ViewSet. **Sem o atributo o mixin é
    inerte** — herdar por engano não cria trava fantasma, e um recurso novo só
    passa a travar quando alguém escreve o nome dele de propósito.

    Ordem na herança importa: venha **antes** do `TenantScopedViewSetMixin`, para
    que a quota seja checada antes de o tenant ser injetado e a linha gravada.

        class ObraViewSet(QuotaEnforcedMixin, TenantScopedViewSetMixin, ModelViewSet):
            quota_recurso = "obras"

    Só o caminho HTTP de criação passa por aqui, e isso é deliberado: lead que
    chega pelo webhook do WhatsApp, objeto criado por Celery task ou por
    migração **não** são barrados. Descartar em silêncio o dado que o cliente já
    mandou é pior que estourar a quota — o 402 só faz sentido quando existe
    alguém na frente da tela para reagir a ele.
    """

    quota_recurso: str | None = None

    def perform_create(self, serializer):
        if self.quota_recurso:
            checar_quota(getattr(self.request, "user", None), self.quota_recurso)
        super().perform_create(serializer)
