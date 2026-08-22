# backend/moduloprancheta/taxonomia.py
"""PRA.5b — como a **pasta do projetista** vira metadado.

É o palpite da R18 ([funcoesimpexp §7.3](../../docs/modulos/funcoesimpexp.md)), e
mora aqui porque é a única parte do lote que exige conhecer o domínio: o motor
sabe que recebeu `TorreA/ARQ/PLANTA-BAIXA_R03.dwg` e que são 4,2 MB de DWG; que o
segundo nível é **disciplina** e que o `_R03` no fim do nome é **revisão** só o
dono do domínio sabe.

**O que se adivinha, e o que não.** Disciplina, código e revisão saem daqui;
**a obra não** — ela é o destino que a pessoa escolhe antes de o lote começar
([impexp.py](impexp.py), `validar_contexto`). A assimetria é deliberada e o
critério é o custo do erro:

- disciplina errada custa **um filtro**: a prancha aparece em "Outra" em vez de
  "Arquitetura", e o carimbo do desenho desmente a tela na hora;
- revisão errada custa **um rótulo**: as folhas continuam todas no acervo, na
  ordem em que chegaram, e nenhuma delas está vigente (publicar é outro verbo);
- **obra errada põe a planta de um prédio no canteiro de outro** — que é a mesma
  família de erro que fez o `importar-bcf` exigir a revisão de destino em vez de
  adivinhá-la, e em campo é pior do que não importar.

O que fecharia a assimetria é a conferência aceitar **correção linha a linha**, e
hoje ela aceita só aceitar/recusar (R1/R5). Quando aceitar, a obra pode passar a
ser palpite como as outras — o gatilho está registrado na planta §12.
"""
from __future__ import annotations

import re
import unicodedata

from .models import Disciplina, RevisaoDocumento

#: Como a pasta do escritório chama cada disciplina. As chaves são **tokens
#: normalizados** (sem acento, maiúsculas, só alfanumérico), e um segmento de
#: caminho casa quando *qualquer* um dos seus tokens está aqui — é o que faz
#: `PROJETO ARQ` e `ARQ` caírem no mesmo lugar sem uma entrada por combinação.
#:
#: A lista sai do vocabulário de canteiro, não de taxonomia acadêmica: é o que
#: está escrito na aba do AutoCAD e na pasta do Drive do escritório.
_TOKENS: dict[str, str] = {}


def _registrar(disciplina: str, *tokens: str) -> None:
    for token in tokens:
        _TOKENS[token] = disciplina


_registrar(Disciplina.ARQUITETURA, "ARQ", "ARQUITETURA", "ARQUITETONICO", "A")
_registrar(Disciplina.ESTRUTURAL, "EST", "ESTR", "ESTRUTURA", "ESTRUTURAL", "CALCULO", "E")
_registrar(Disciplina.FUNDACAO, "FUN", "FUND", "FUNDACAO", "FUNDACOES", "ESTACA", "ESTAQUEAMENTO")
_registrar(
    Disciplina.HIDROSSANITARIO,
    "HID", "HIDR", "HIDRAULICA", "HIDROSSANITARIO", "HIDROSANITARIO",
    "SAN", "SANITARIO", "ESGOTO", "AGUA", "PLUVIAL",
)
_registrar(Disciplina.ELETRICA, "ELE", "ELET", "ELETRICA", "ELETRICO", "SPDA", "TELECOM", "CFTV")
_registrar(Disciplina.INCENDIO, "INC", "INCENDIO", "PPCI", "PCI", "COMBATE", "SPK", "SPRINKLER")
_registrar(
    Disciplina.CLIMATIZACAO,
    "CLI", "CLIM", "CLIMATIZACAO", "AVAC", "HVAC", "ARCONDICIONADO", "EXAUSTAO",
)
_registrar(Disciplina.TERRAPLANAGEM, "TER", "TERRAPLANAGEM", "TERRAPLENAGEM", "MOVIMENTACAO")
_registrar(Disciplina.PAVIMENTACAO, "PAV", "PAVIMENTACAO", "ASFALTO", "DRENAGEM")
_registrar(Disciplina.TOPOGRAFIA, "TOP", "TOPO", "TOPOGRAFIA", "LEVANTAMENTO", "PLANIALTIMETRICO")
_registrar(Disciplina.IMPLANTACAO, "IMP", "IMPLANTACAO", "URB", "URBANISMO", "PAISAGISMO")
_registrar(Disciplina.LEGAL, "LEG", "LEGAL", "APROVACAO", "PREFEITURA", "BOMBEIROS", "HABITESE")

#: `PLANTA-BAIXA_R03` → código `PLANTA-BAIXA`, revisão `R03`.
#:
#: O separador antes do `R` é **obrigatório** de propósito: sem ele, `PILAR03`
#: viraria o documento `PILA` na revisão 3. É o mesmo cuidado da extensão
#: composta do [D75.1](../../docs/historico-correcoes.md) — regra que parece
#: excesso de zelo até o dia em que renomeia o acervo inteiro errado.
_MARCA_DE_REVISAO = re.compile(r"[-_ ]+R(?:EV)?[-_ .]?(\d{1,3})\s*$", re.IGNORECASE)

#: Rótulo de revisão quando o nome do arquivo não traz nenhum. É o mesmo padrão
#: do upload avulso, e a numeração continua a partir dele.
REVISAO_INICIAL = "R00"


def _normalizar(texto: str) -> str:
    """Sem acento, maiúsculas, só alfanumérico. `Elétrica-2` → `ELETRICA2`."""
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return "".join(c for c in sem_acento.upper() if c.isalnum())


def disciplina_do_caminho(caminho: str) -> str:
    """A disciplina que a pasta declara, ou `OUTRA` quando ela não declara nada.

    **Procura da pasta mais funda para a mais rasa**, porque é onde o escritório
    põe a disciplina: em `TorreA/PROJETOS/ARQ/plantas/x.dwg` o `ARQ` está no meio,
    e varrer de fora para dentro acharia primeiro qualquer pasta genérica que por
    acaso casasse. O nome do **arquivo** fica de fora da varredura — `ARQ-001.dwg`
    dentro de `EST/` é o código do documento, não um voto sobre a disciplina.

    `OUTRA` não é fracasso: é o default do modelo, aparece na conferência como
    qualquer outro palpite e o operador recusa a linha se não servir.
    """
    pastas = [p for p in (caminho or "").split("/")[:-1] if p]
    for pasta in reversed(pastas):
        for token in re.split(r"[^0-9A-Za-zÀ-ÿ]+", pasta):
            achado = _TOKENS.get(_normalizar(token))
            if achado:
                return achado
    return Disciplina.OUTRA


def disciplinas_do_nome(nome: str) -> list[str]:
    """O que o **nome do arquivo** declara — `ARQ-ELE-PLB-001.dwg` → as duas.

    Irmã da `disciplina_do_caminho`, e nasceu na PRA.9c por um motivo de produto,
    não de completude: o palpite é o que faz a pessoa **confirmar** em vez de
    preencher. Um seletor vazio na frente de trinta arquivos é o que desmotiva a
    classificar — e classificar mal é o que já vinha acontecendo, com tudo em
    *Outra*.

    Varre os segmentos do código (o que sobra depois de tirar extensão e marca de
    revisão) contra o **mesmo** `_TOKENS` da pasta: um vocabulário só, então
    ensinar "SPDA" à plataforma vale para os dois caminhos. Devolve na ordem em
    que aparecem — a primeira vira a principal —, e lista vazia quando o nome não
    declara nada, que é resposta legítima e diferente de "Outra".

    Só o **código** entra, e não o nome inteiro: `PLANTA-DE-ELETRICA-R02` é uma
    coisa, mas o `_R02` já saiu e a extensão também, então o que resta é o que o
    escritório escreveu para identificar a prancha.
    """
    codigo, _ = codigo_e_revisao(nome)
    achados: list[str] = []
    for token in re.split(r"[^0-9A-Za-zÀ-ÿ]+", codigo):
        achado = _TOKENS.get(_normalizar(token))
        if achado and achado not in achados:
            achados.append(achado)
    return achados


def codigo_e_revisao(nome: str) -> tuple[str, str]:
    """`PLANTA-BAIXA_R03.dwg` → `("PLANTA-BAIXA", "R03")`.

    **Separar os dois é o que faz um acervo histórico virar acervo**, e não uma
    pilha: as quatro entregas da mesma prancha colapsam num documento com quatro
    revisões, que é a pergunta que o canteiro faz ("esta é a última?"). Sem isto,
    `R00` a `R03` seriam quatro documentos diferentes, cada um com uma revisão só
    e nenhuma superando ninguém.

    Sem marca de revisão no nome, o código é o nome inteiro e a revisão é
    `R00` — quem numera a partir daí é o `impexp`, contra o que já existe no
    documento.
    """
    # Corta no PRIMEIRO ponto, e não no último: a extensão composta
    # (`nuvem.copc.laz`) tem de sumir inteira, senão o código do documento nasce
    # `nuvem.copc`. Nome que começa com ponto vira código vazio, e aí a linha é
    # recusada na conferência dizendo isso — que é a resposta certa para um
    # arquivo chamado `.dwg`.
    caule = (nome or "").rsplit("/", 1)[-1].split(".", 1)[0]

    achado = _MARCA_DE_REVISAO.search(caule)
    if achado is None:
        return caule.strip()[:60], REVISAO_INICIAL
    codigo = caule[: achado.start()].strip(" -_")
    return codigo[:60], f"R{int(achado.group(1)):02d}"


def revisao_declarada(nome: str) -> str:
    """O rótulo que o **nome traz**, ou `""` quando ele não traz nenhum.

    Existe porque `codigo_e_revisao` devolve `R00` em dois casos que não são o
    mesmo: o arquivo que **diz** `_R00` e o que **não diz nada**. Para o lote a
    fusão é inofensiva — a revisão é palpite de qualquer jeito, e o rótulo livre
    resolve. Para o `atualizar/` ela inverte a entrega: um documento que começa em
    `R02` recebe `qualquer.pdf`, o `R00` está livre, e a entrega **de hoje** entra
    atrás da que está em campo. Foi o que o E2E pegou e o teste unitário não —
    ali o documento começava em `R00`, e a colisão escondia o defeito.
    """
    caule = (nome or "").rsplit("/", 1)[-1].split(".", 1)[0]
    achado = _MARCA_DE_REVISAO.search(caule)
    return f"R{int(achado.group(1)):02d}" if achado else ""


def proximo_rotulo(documento, preferido: str = "") -> str:
    """O rótulo que esta revisão pode ocupar sem colidir com as que já existem.

    **Duas regras, e a ordem entre elas é o produto.** Se o nome do arquivo trouxe
    um rótulo (`PLANTA_R03.dwg`) e ele está livre, é ele que vale: quem numera o
    acervo é o escritório, não nós. Se não trouxe — ou se já está ocupado — vem o
    **seguinte ao maior**, que é o que uma pessoa faria ao ver `R00, R01, R02` na
    tela e ter de dizer qual é a próxima.

    Continuar do maior, e não do primeiro buraco, é o que separa este helper do
    palpite de lote: no lote a colisão é entre `PLANTA.dwg` e `PLANTA (cópia).dwg`
    do mesmo acervo histórico, e tapar buraco é o certo. Aqui alguém está
    entregando a versão nova de uma prancha viva, e devolver `R01` porque a `R01`
    foi apagada um dia poria a entrega de hoje **atrás** da que está em campo.
    """
    ocupados = set(
        RevisaoDocumento.objects.filter(
            documento=documento, tenant_id=documento.tenant_id,
        ).values_list("revisao", flat=True)
    )
    if preferido and preferido not in ocupados:
        return preferido
    if not ocupados:
        return REVISAO_INICIAL

    # Só os `Rnn` entram na conta do "maior": um acervo pode ter rótulo escrito à
    # mão ("R02-A", "PRELIMINAR"), e tentar ordená-lo junto daria um número
    # arbitrário. Sem nenhum `Rnn` reconhecível, a numeração recomeça do inicial e
    # o laço abaixo acha o primeiro livre.
    numeros = [
        int(r[1:]) for r in ocupados
        if len(r) >= 2 and r[0].upper() == "R" and r[1:].isdigit()
    ]
    proximo = max(numeros) + 1 if numeros else 0
    for numero in range(proximo, proximo + len(ocupados) + 2):
        candidato = f"R{numero:02d}"
        if candidato not in ocupados:
            return candidato
    return preferido or REVISAO_INICIAL  # inalcançável: o intervalo cobre o conjunto
