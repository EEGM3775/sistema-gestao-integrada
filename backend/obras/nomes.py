# backend/obras/nomes.py
"""O nome da obra é único no empreendimento — e quem esbarra na regra recebe um
nome livre pronto, em vez de uma porta fechada.

> **Decisão do dono, 13/09/2026**, respondendo ao achado de que o seed criou duas
> "Torre A — Fundações" no mesmo empreendimento: *"quando a pessoa tenta criar
> uma obra nova e o nome já existe, avisa que o nome já existe e dá um aviso com
> a nova renomeação. Então a regra ainda continua existindo e a pessoa, quando
> for selecionar a obra em algum módulo, não tem que ficar adivinhando."*

**A regra não afrouxou.** Insistir no nome repetido continua sendo recusa. O que
mudou é que a recusa passou a carregar duas coisas que ela não tinha: **qual**
obra conflita (para a pessoa reconhecer se é a mesma que ela já tem) e **um nome
livre sugerido**, que ela aceita com um clique ou reescreve.

**Por que o sufixo é o mês de início, e não `(2)`.** O nome é como as pessoas
escolhem a obra — no seletor do PDCA, na medição, no diário. `Torre A (2)` não
diz nada: seis meses depois ninguém sabe qual é qual, e o seletor continua sendo
adivinhação, só que com um número no fim. `Torre A (05/2026)` diz o que de fato
separa duas obras homônimas: a segunda quase sempre é outra fase, um reinício ou
outro contrato. O número só entra se **duas começarem no mesmo mês**, que é o
caso em que a data deixou de distinguir.

**Por que isto vive aqui e não no serializer.** Importação de planilha, API e
qualquer módulo que crie obra esbarram na mesma regra; a sugestão tem de ser a
mesma nos três. O serializer é só o primeiro cliente.

**Sobre a lixeira (D116):** a busca usa `Obra.objects`, que já exclui o que está
sob lápide. Uma obra na lixeira **não** segura o nome — quem excluiu e recadastra
com o mesmo nome não recebe sugestão nenhuma, porque não há conflito.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from .models import Obra


class NomeDeObraEmUso(APIException):
    """400 com o payload **intacto** — e é por isso que não é `ValidationError`.

    O `ValidationError` do DRF passa tudo por `_get_error_details`, que converte
    cada folha em `ErrorDetail` (string) e embrulha escalar em lista. O aviso
    ficaria com `obra_id: "7"` em vez de `7` e `sugestao_nome: ["Torre A (05/2026)"]`
    em vez do nome — e a tela teria de desembrulhar cada campo adivinhando a
    forma. Aqui o `detail` é atribuído direto: o tratador do DRF usa `exc.detail`
    como veio quando ele é dict.

    Seguro porque o `ObraSerializer` tem **um** cliente, o `ObraViewSet`, que
    chama `is_valid(raise_exception=True)`. Se um dia alguém validar obra com
    `raise_exception=False`, esta exceção sobe em vez de virar `False` — e é isso
    que este parágrafo existe para avisar.
    """

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, payload: dict):
        self.detail = payload

#: Quantas variações o gerador tenta antes de desistir e devolver vazio (a tela
#: então só avisa, e a pessoa escreve o nome).
#:
#: **Não é teto de produto**, e por isso não mora no `payment/planos.py`: ele não
#: diz até onde o cliente vai — quem quiser a 61ª obra homônima digita o nome e
#: cria. É a mesma família do `JANELA` do extrator de CEP declarada na §5.6 de
#: lá: mexer nele muda o *acerto* da sugestão, não o quanto o cliente pode.
MAXIMO_DE_TENTATIVAS = 60

#: `Obra.nome_obra` é `max_length=255`. O sufixo tem de caber **dentro** disso, e
#: quem cede espaço é a base — um nome truncado com o sufixo intacto ainda
#: distingue as duas obras; o contrário devolveria um nome que o banco recusa.
LARGURA_DO_NOME = Obra._meta.get_field("nome_obra").max_length


def _escopo(tenant_id, empreendimento_id):
    """As obras que disputam o nome — o mesmo recorte das duas `UniqueConstraint`.

    Sem empreendimento a unicidade é por tenant; com ele, por empreendimento. São
    duas constraints no modelo justamente porque são dois recortes, e repetir a
    divisão aqui é o que mantém a sugestão honesta: sugerir um nome "livre" que o
    banco depois recusa seria pior que não sugerir.
    """
    qs = Obra.objects.filter(tenant_id=tenant_id)
    if empreendimento_id is None:
        return qs.filter(empreendimento__isnull=True)
    return qs.filter(empreendimento_id=empreendimento_id)


def obra_em_conflito(*, tenant_id, empreendimento_id, nome, excluir_pk=None):
    """A obra que já ocupa este nome, ou `None`.

    `excluir_pk` é o que faz o `PATCH` funcionar: uma obra não conflita consigo
    mesma ao ser editada sem trocar de nome.
    """
    if not nome:
        return None
    qs = _escopo(tenant_id, empreendimento_id).filter(nome_obra=nome)
    if excluir_pk is not None:
        qs = qs.exclude(pk=excluir_pk)
    return qs.first()


def _cabe(base: str, sufixo: str) -> str:
    """Encaixa `base + sufixo` em `LARGURA_DO_NOME` cortando a base, nunca o sufixo."""
    folga = LARGURA_DO_NOME - len(sufixo)
    if folga <= 0:
        return sufixo[:LARGURA_DO_NOME]
    return f"{base[:folga].rstrip()}{sufixo}"


def sugerir_nome_livre(
    *, tenant_id, empreendimento_id, nome, data_inicio=None, excluir_pk=None
) -> str:
    """Um nome que não colide, derivado do que a pessoa digitou. `""` se desistir.

    Primeiro tenta o mês de início; depois numera. Devolver vazio é resposta
    legítima e não erro: a tela cai no aviso sem sugestão, que ainda é melhor que
    oferecer um nome que o banco vai recusar.
    """
    if not nome:
        return ""

    # Sem data prevista, o mês corrente é a melhor aproximação disponível — é
    # quando a obra está sendo cadastrada, e cadastro costuma seguir o início.
    referencia = data_inicio or timezone.localdate()
    candidato = _cabe(nome, f" ({referencia:%m/%Y})")

    if not obra_em_conflito(
        tenant_id=tenant_id, empreendimento_id=empreendimento_id,
        nome=candidato, excluir_pk=excluir_pk,
    ):
        return candidato

    # Duas obras começando no mesmo mês: a data parou de distinguir, e aí o
    # número é o que sobra.
    for n in range(2, MAXIMO_DE_TENTATIVAS + 2):
        numerado = _cabe(candidato, f" {n}")
        if not obra_em_conflito(
            tenant_id=tenant_id, empreendimento_id=empreendimento_id,
            nome=numerado, excluir_pk=excluir_pk,
        ):
            return numerado
    return ""


def descrever_conflito(obra: Obra) -> dict:
    """O cartão da obra que conflita — o que a pessoa precisa para reconhecê-la.

    Traz **atividades** de propósito: é o número que separa "a obra de verdade,
    que já tem plano rodando" de "uma casca que alguém cadastrou e abandonou", e
    é essa distinção que decide se ela deve reusar a obra existente ou criar
    outra. Sem ele, duas linhas com o mesmo nome e a mesma data continuariam
    indistinguíveis — que é o problema que este arquivo existe para resolver.
    """
    return {
        "obra_id": obra.pk,
        "nome_obra": obra.nome_obra,
        "status_obra": obra.status_obra,
        "data_inicio_prevista": obra.data_inicio_prevista,
        "data_fim_prevista": obra.data_fim_prevista,
        "etapas": obra.etapas.count(),
        "atividades": sum(
            c.atividades.count() for c in obra.cronogramas.all()
        ),
    }
