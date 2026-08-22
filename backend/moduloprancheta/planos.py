# backend/moduloprancheta/planos.py
"""O que a Prancheta **vende** — e só isso. A porta é do `funcoesimpexp`.

Este arquivo é o que sobrou do `uploads.py` depois da PRA.5a, e o que saiu dele
diz mais do que o que ficou. Saíram: `validar_arquivo` (decidia o formato pelo
**nome** — o [D75](../../docs/historico-correcoes.md)), `teto_mb`, `calcular_hash` e a
recusa por tamanho. Nenhuma dessas coisas era "do módulo": eram a porta,
repartida. Seis módulos com a sua cópia são seis portas, ainda que todas chamem a
mesma função de detecção — e é isso que a régua da porta única (R17) desfaz.

Ficou o que é decisão de **produto**, e ela continua sendo do módulo dono:

- quais formatos o plano deste cliente abre (`formatos_do_plano`);
- qual tier de motor ele contratou (`tiers_do_plano`);
- o teto medido do motor livre e o aviso honesto do [D47](../../docs/historico-correcoes.md);
- o catálogo que a tela mostra, com o que está travado e por quê.

**Os números continuam em [payment/planos.py](../../payment/planos.py)**, onde o
dono os edita — aqui só se lê. É a regra do projeto: todo limite (tamanho,
formato, memória, tempo) é knob de plano, e knob de plano mora em `payment/`.

**A Prancheta não é um silo, é uma capacidade** (decisão do dono, 08/08/2026).
Quem a compra não está comprando "um módulo", e sim *poder ver os próprios
arquivos dentro do software* — então quando o Orçamento, o SIL ou o diário
precisarem mostrar um DWG, eles puxam esta visualização, e quem não a contratou vê
o aviso **na tela onde estava**, com cadeado, nunca um silo à parte. Por isso
`formatos_do_plano` é consultado pelo motor na porta única, e não por cada
módulo: o formato é vendido uma vez e honrado onde quer que a visualização seja
invocada.
"""
from __future__ import annotations

import logging

from rest_framework.exceptions import APIException

from payment.addons import ADDONS
from payment.planos import DWG_MB_MOTOR_LIVRE, PLANOS

from .formatos import (
    FORMATO_POR_CODIGO,
    FORMATOS,
    Formato,
    sem_assinatura,
    tiers_do_formato,
)

logger = logging.getLogger(__name__)


class FormatoNaoContratado(APIException):
    """402 — o formato existe, o plano não o inclui.

    Carrega `formato` e `formatos_aceitos` além do texto porque a tela precisa
    montar o CTA sozinha: dizer *qual* formato bateu e *quais* passam é o que
    transforma o erro em "seu plano abre PDF e DXF; RVT está no Empresarial",
    em vez de um 402 genérico que vira chamado de suporte.

    **Continua aqui, e não no motor, porque é a parede do BCF** (PRA.3): levar a
    marcação para o software do projetista é o que o plano vende. O upload de
    revisão já não passa por ela — quem levanta o 402 dele é o
    `funcoesimpexp.limites`, com um corpo equivalente, uma vez só para todos os
    módulos.
    """

    status_code = 402
    default_code = "formato_nao_contratado"

    def __init__(self, *, formato: Formato, aceitos: list[str], plano: str | None):
        super().__init__("formato não contratado")
        nomes = [FORMATO_POR_CODIGO[c].nome for c in aceitos if c in FORMATO_POR_CODIGO]
        self.detail = {
            "detail": (
                f"O plano contratado não inclui arquivos {formato.nome}. "
                f"Formatos disponíveis hoje: {', '.join(nomes) or 'nenhum'}. "
                "Faça upgrade do plano para abrir este formato."
            ),
            "code": self.default_code,
            "formato": formato.codigo,
            "formato_nome": formato.nome,
            "formatos_aceitos": aceitos,
            "plano": plano,
        }


class ArquivoAcimaDoTeto(APIException):
    """402 — o formato está contratado, o arquivo é que passou do teto do plano.

    Irmã da de cima e pela mesma razão: a porta única do `funcoesimpexp` levanta
    exceção **comum** (ela também roda no worker, onde `APIException` não quer
    dizer nada), e cabe a quem atende HTTP traduzir. Sem isto o teto de tamanho
    saía como 500.

    O corpo repete o que o `funcoesimpexp/views.py` já devolve — mesmo `code`,
    mesmos campos — para a tela tratar "passou do teto" de um jeito só, venha o
    arquivo da Prancheta ou de uma importação de planilha.
    """

    status_code = 402
    default_code = "arquivo_grande_demais"

    def __init__(self, *, mensagem: str, limite_mb: int, tamanho_mb: float):
        super().__init__(mensagem)
        self.detail = {
            "detail": mensagem,
            "code": self.default_code,
            "limite_mb": limite_mb,
            "tamanho_mb": round(tamanho_mb, 1),
        }


def _plano_do_usuario(user) -> dict | None:
    """Configuração do plano contratado, ou `None` quando não dá para saber.

    Fail-open sem a claim, pela mesma razão registrada em `nucleo/quotas.py`:
    token de serviço ou legado não deve virar indisponibilidade de escrita. É
    parede COMERCIAL — forjar um token exigiria a chave de assinatura da
    plataforma, e quem a tem não precisa burlar um gate de formato. Como lá, o
    caminho é **logado**: o D21 ensinou que protetor fail-open silencioso fica
    indistinguível de um protetor funcionando.
    """
    slug = getattr(user, "iam_plano", None)
    if not slug or slug not in PLANOS:
        logger.warning(
            "prancheta_formato_sem_plano",
            extra={"usuario": getattr(user, "username", None), "plano": slug},
        )
        return None
    return PLANOS[slug]


def formatos_do_plano(user) -> list[str]:
    """Códigos de formato que o plano deste usuário abre.

    `None` na configuração significa "tudo" (Sob Medida) — e ausência de plano
    conhecido cai no mesmo lugar, pelo fail-open acima.

    **Formato sem assinatura publicada nunca entra**, nem no "tudo": a plataforma
    não vende o que não sabe reconhecer pelos bytes. Hoje são o NWD e o SKP, e
    eles voltam na PRA.4 com a assinatura medida sobre arquivo real — ver
    `formatos.SEM_ASSINATURA_CONHECIDA`.
    """
    plano = _plano_do_usuario(user)
    declarados = None if plano is None else plano.get("formatos_prancheta")
    if declarados is None:
        declarados = [f.codigo for f in FORMATOS]
    return [c for c in declarados if not sem_assinatura(c)]


def tiers_do_plano(user) -> list[str]:
    """Tiers de motor que o plano habilita (`livre`/`premium`)."""
    plano = _plano_do_usuario(user)
    if plano is None:
        return ["livre", "premium"]
    declarados = plano.get("motores_prancheta")
    if declarados is None:
        return ["livre", "premium"]
    return list(declarados)


def teto_de_snap(user) -> int | None:
    """Quantos pontos de snap este plano indexa por folha.

    `0` = o plano não tem snap (o `free`); `None` = sem teto (Sob Medida). O
    valor sai de `payment/planos.py §5.7`, e a unidade é **ponto indexado** e não
    megabyte porque o custo não acompanha o tamanho do arquivo: no acervo medido,
    um DWG de 0,18 MB rende 464 mil pontos e um de 6,36 MB rende 466.

    **Os add-ons somam por cima**, e é a única quota da Prancheta que faz isso
    hoje: a distância até o teto varia demais entre plantas para caber num pacote
    só (`pacote_snap_200k`, `_500k`, `_1m`).

    O fail-open segue o dos vizinhos, mas com um limite: sem plano conhecido o
    usuário recebe o teto do **Profissional**, não "sem teto". Aqui fail-open
    ilimitado não seria generosidade e sim uma prancha de 40 MB de sidecar
    chegando ao celular de quem nem contratou o recurso.
    """
    plano = _plano_do_usuario(user)
    if plano is None:
        return PLANOS["profissional"]["snap_pontos"]
    teto = plano.get("snap_pontos", 0)
    if teto is None:
        return None
    return teto + _snap_dos_addons(user)


def _snap_dos_addons(user) -> int:
    """O que os pacotes contratados somam ao teto do plano.

    Lê a claim `iam_addons` — a mesma lista que o IAM já publica no token. Um
    add-on desconhecido é ignorado em silêncio de propósito: catálogo novo no IAM
    não pode derrubar conversão em backend que ainda não subiu.
    """
    contratados = getattr(user, "iam_addons", None) or []
    if isinstance(contratados, str):
        contratados = [contratados]
    soma = 0
    for codigo in contratados:
        incremento = ADDONS.get(codigo, {}).get("incrementa", {})
        soma += incremento.get("snap_pontos", 0)
    return soma


def teto_do_motor_livre(codigo_formato: str) -> int:
    """Peso acima do qual o motor livre não entrega nada, ou 0 se não há teto.

    Só o DWG tem um, e ele é medido (ver `DWG_MB_MOTOR_LIVRE` em
    `payment/planos.py`): acima de 40 MB o LibreDWG falha em **100%** do acervo
    varrido. Os outros formatos do caminho livre não têm degrau de peso conhecido
    — inventar um por simetria seria arbitrar limite sem medição, que é o oposto
    do que este módulo faz com número.
    """
    return DWG_MB_MOTOR_LIVRE if codigo_formato == "dwg" else 0


def aviso_do_upload(codigo_formato: str, tamanho_bytes: int, user) -> str | None:
    """O que dizer **na hora** sobre um arquivo que vai passar e não vai abrir.

    Nasceu do **D47**: o cliente sobe 138 MB, espera a fila e recebe
    `motor_insuficiente`. Com o teto medido a plataforma sabe disso **antes de
    converter**, pelo tamanho — e um diagnóstico tardio vira escolha informada.

    **Avisa e deixa passar**, deliberadamente. Recusar seria vender como fronteira
    de plano um motor premium que ainda não existe (PRA.4): o arquivo fica no
    acervo, é baixável na íntegra e reconverte sozinho quando o motor melhor
    chegar, porque a `DerivadaProjeto` é única por motor.

    Duas frases, porque são dois problemas diferentes: quem não contratou o motor
    premium tem o que comprar; quem contratou não tem, e merece a verdade — é a
    mesma distinção que `pipeline._traduzir` faz depois da falha.
    """
    teto = teto_do_motor_livre(codigo_formato)
    if not teto or not tamanho_bytes or tamanho_bytes <= teto * 1024 * 1024:
        return None

    mb = round(tamanho_bytes / (1024 * 1024))
    if "premium" in set(tiers_do_plano(user)):
        return (
            f"Este DWG tem {mb} MB. Acima de {teto} MB só o motor de alta fidelidade "
            "abre — ele está no seu plano, mas ainda não está ligado neste servidor. "
            "O arquivo fica no acervo e será convertido assim que ele entrar."
        )
    return (
        f"Este DWG tem {mb} MB. O motor incluído no seu plano não abre arquivos "
        f"acima de {teto} MB — normalmente é o projeto executivo completo, que o "
        "plano superior abre. O arquivo fica no acervo e continua baixável na "
        "íntegra; a prancha é que não será desenhada."
    )


def exigir_formato_contratado(codigo: str, user) -> Formato:
    """Parede comercial de um formato que NÃO entra por upload de revisão.

    Existe para o BCF (PRA.3): marcar dentro do sistema vem com o módulo, mas
    **levar a marcação para o software do projetista e trazê-la de volta** é o
    que o plano vende — é a linha `bcf` de `formatos_prancheta` em
    `payment/planos.py`.
    """
    formato = FORMATO_POR_CODIGO[codigo]
    aceitos = formatos_do_plano(user)
    if formato.codigo not in aceitos:
        raise FormatoNaoContratado(
            formato=formato, aceitos=aceitos, plano=getattr(user, "iam_plano", None),
        )
    return formato


def formatos_declarados(user) -> list[dict]:
    """O catálogo inteiro com o que este plano abre e o que não abre.

    Devolve **todos** os formatos, cada um com `contratado` e o tier de motor que
    o atenderia — a régua da planta §6 é explícita: formato não contratado
    aparece **travado com o motivo**, nunca escondido. Uma lista só do que passa
    deixaria o cliente sem saber que o produto abre RVT.

    A PRA.5a acrescentou um terceiro estado a essa mesma régua: `reconhecido`.
    NWD e SKP continuam **aparecendo** — a plataforma os abrirá — mas declaram
    que ainda não sabemos identificá-los pelos bytes, e por isso não são vendidos
    hoje. Escondê-los seria mentir por omissão; vendê-los seria mentir e cobrar.
    """
    aceitos = set(formatos_do_plano(user))
    tiers = set(tiers_do_plano(user))
    saida = []
    for formato in FORMATOS:
        tiers_possiveis = tiers_do_formato(formato.codigo)
        reconhecido = not sem_assinatura(formato.codigo)
        saida.append({
            "codigo": formato.codigo,
            "nome": formato.nome,
            "familia": formato.familia,
            "extensoes": list(formato.extensoes),
            "max_mb": formato.max_mb,
            # Acima disto o arquivo entra e a prancha não sai (D47). Zero = sem
            # teto conhecido. Vai junto do `max_mb` de propósito: são as duas
            # metades da mesma pergunta ("o que acontece se for grande?"), e
            # separá-las faria a tela avisar só depois do upload.
            "motor_livre_max_mb": teto_do_motor_livre(formato.codigo),
            "contratado": formato.codigo in aceitos,
            # PRA.5a — a plataforma sabe reconhecer este formato pelos bytes?
            # Falso hoje só para NWD e SKP, que por isso saíram da venda.
            "reconhecido": reconhecido,
            # Formato de interoperabilidade não tem motor porque não há o que
            # converter — e `tiers_do_formato` devolve vazio para ele. Sem este
            # ramo, o BCF apareceria como "exige motor de alta fidelidade" e
            # indisponível: um upsell inventado para quem já o contratou.
            "interop": formato.interop,
            "exige_motor_premium": (
                False if formato.interop else "livre" not in tiers_possiveis
            ),
            "motor_disponivel": (
                True if formato.interop else bool(tiers_possiveis & tiers)
            ),
        })
    return saida
