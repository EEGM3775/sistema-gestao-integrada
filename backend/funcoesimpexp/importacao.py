# backend/funcoesimpexp/importacao.py
"""IE.0 — o motor de importação: `preparar → conferir → aplicar`.

**R1, o ponto do módulo inteiro:** nada é gravado no destino antes de alguém
olhar. O arquivo é lido, cada linha recebe um veredito (nova · já existe ·
inválida) e a importação fica parada em `CONFERINDO`. Só então vem *confirmar
tudo*, *confirmar seleção* ou *negar tudo*.

Isso não é zelo excessivo — é o que separa este caminho de um `POST` que grava.
Planilha de origem externa sai do extrator com coluna trocada; base oficial muda
de layout entre publicações. Sem a parada, o erro só aparece semanas depois, como
dado estranho no meio de algo já aprovado, e aí ninguém sabe de onde veio.

Generalização do `moduloorcamento/importacao.py` (ORC.5b): a máquina de estados é
a mesma; o que era específico de preço virou `valores` governado pelas colunas do
recurso.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .formatos.leitura import LeituraInvalida, extrair, ler_bytes, mapear_colunas
from .models import Importacao, LinhaImportacao
from .registro import Recurso

logger = logging.getLogger(__name__)

# R10 — o corte entre síncrono e job, e ele é **do motor**, não de quem declara.
# Deixar cada módulo escolher produziria seis cortes diferentes e nenhum deles
# calibrado pelo que importa aqui, que é o timeout do gateway, não o domínio.
#
# 3.000 linhas é onde a classificação (ler, tipar, consultar o destino linha a
# linha) começa a passar de poucos segundos. Acima disso o request ficaria
# pendurado, o gateway cortaria em 60 s e o usuário reenviaria o mesmo arquivo —
# dobrando a carga, que é justamente a falha que a regra evita.
LIMITE_SINCRONO = 3_000

# Lote do progresso: gravar a cada linha faria um UPDATE por linha e o custo do
# progresso passaria o do trabalho.
PASSO_PROGRESSO = 250


class ImportacaoInvalida(Exception):
    """Importação pedida em estado ou destino que não permite."""


class ColunasNaoReconhecidas(Exception):
    """Cabeçalho não casou — quem chama mostra o que viu para o de-para manual (R4)."""

    def __init__(self, mensagem: str, *, cabecalhos_vistos: list, obrigatorias: list):
        super().__init__(mensagem)
        self.cabecalhos_vistos = cabecalhos_vistos
        self.obrigatorias = obrigatorias


class LimiteDoPlano(Exception):
    """Arquivo maior do que o plano contratado aceita."""

    def __init__(self, mensagem: str, *, limite: int, tentado: int, quota: str):
        super().__init__(mensagem)
        self.limite = limite
        self.tentado = tentado
        self.quota = quota


# ---------------------------------------------------------------------------
# 1. Ler e conferir
# ---------------------------------------------------------------------------


def vale_a_pena_job(conteudo: bytes) -> bool:
    """R10 — decide síncrono × job **antes** de ler o arquivo inteiro.

    Conta quebras de linha nos bytes crus: é uma estimativa grosseira (um XLSX é
    binário e não tem uma quebra por linha), e é de propósito. O que se decide
    aqui é só *por onde* o arquivo passa; a contagem exata sai da leitura, dos
    dois lados. Errar para o lado do job custa uma tela de progresso a mais;
    errar para o lado do request custa um timeout no gateway.
    """
    if len(conteudo) > 512 * 1024:
        return True
    return conteudo.count(b"\n") > LIMITE_SINCRONO


@transaction.atomic
def preparar(
    *,
    recurso: Recurso,
    conteudo: bytes,
    nome_arquivo: str,
    tenant_id,
    usuario_nome: str = "",
    limites: dict | None = None,
    de_para: dict | None = None,
    delimitador: str | None = None,
    lote: Importacao | None = None,
) -> Importacao:
    """Lê o arquivo, classifica linha a linha e para em `CONFERINDO`.

    `lote` é o caminho assíncrono: o registro já existe em `LENDO` (criado no
    request, para a tela ter o que mostrar) e aqui ele é preenchido. Sem `lote`,
    o registro nasce aqui — que é o caminho síncrono.
    """
    if not recurso.importa:
        raise ImportacaoInvalida(f"O recurso '{recurso.id}' não aceita importação.")

    try:
        brutas = ler_bytes(conteudo, nome_arquivo, delimitador=delimitador)
    except LeituraInvalida as exc:
        return _com_erro(
            recurso=recurso, tenant_id=tenant_id, nome_arquivo=nome_arquivo,
            mensagem=str(exc), usuario_nome=usuario_nome, lote=lote,
        )

    mapa, indice, vistos = mapear_colunas(brutas, recurso, manual=de_para)
    if mapa is None:
        if lote is not None:
            # No job não há para quem devolver 422 na hora — mas o de-para manual
            # da R4 **não pode** morrer aqui: arquivo grande é justamente o de
            # origem mais estranha (o PDF de 90 mil linhas da prefeitura), e é
            # nele que a R4 mais vale. Então o lote guarda o que o extrator viu e
            # **preserva o arquivo**; a tela oferece o mapeamento e chama
            # `remapear`, que relê o mesmo arquivo com o de-para na mão.
            lote.parametros = {
                "cabecalhos_vistos": vistos[:5],
                "obrigatorias": [c.rotulo for c in recurso.obrigatorias()],
                "colunas": [
                    {"campo": c.campo, "rotulo": c.rotulo, "obrigatoria": c.obrigatoria}
                    for c in recurso.colunas
                ],
                "aguarda_de_para": True,
            }
            lote.save(update_fields=["parametros"])
            return _com_erro(
                recurso=recurso, tenant_id=tenant_id, nome_arquivo=nome_arquivo,
                usuario_nome=usuario_nome, lote=lote, preservar_arquivo=True,
                mensagem=(
                    "Não reconheci as colunas obrigatórias no cabeçalho. "
                    "Escolha manualmente qual coluna é cada campo."
                ),
            )
        raise ColunasNaoReconhecidas(
            "Não reconheci as colunas obrigatórias no cabeçalho deste arquivo. "
            "Escolha manualmente qual coluna é cada campo.",
            cabecalhos_vistos=vistos,
            obrigatorias=[c.rotulo for c in recurso.obrigatorias()],
        )

    corpo = brutas[indice + 1:]
    # Tetos ANTES de materializar (R13): ler e classificar 90 mil linhas para
    # recusar no fim é pagar o custo inteiro por nada. Dois eixos — o de operação
    # é do motor e vale para todo recurso; o de acervo é do módulo, que conhece o
    # próprio (planta §9).
    _checar_teto_por_operacao(len(corpo), limites)
    recurso.checar_quota_objeto(len(corpo), limites, tenant_id)

    parametros = {
        "de_para": mapa, "delimitador": delimitador or "", "cabecalho_linha": indice,
    }
    if lote is None:
        importacao = Importacao.objects.create(
            tenant_id=tenant_id,
            recurso=recurso.id,
            arquivo_nome=nome_arquivo[:255],
            parametros=parametros,
            contexto=dict(recurso.contexto or {}),
            status=Importacao.Status.CONFERINDO,
            usuario_nome=usuario_nome[:150],
        )
    else:
        importacao = lote
        importacao.parametros = parametros
        importacao.status = Importacao.Status.CONFERINDO
        importacao.total_linhas = len(corpo)
        importacao.save(update_fields=["parametros", "status", "total_linhas"])

    existentes: set[str] = set()
    vistos_no_arquivo: set[str] = set()
    linhas: list[LinhaImportacao] = []

    for numero, bruta in enumerate(corpo, start=indice + 2):
        if not any(c not in (None, "") for c in bruta):
            continue
        dados = extrair(list(bruta), mapa, recurso)
        chave = str(dados.get(recurso.chave) or "").strip()
        situacao, motivo = _classificar(
            recurso, dados, chave, vistos_no_arquivo, existentes, tenant_id,
        )
        if chave and situacao != LinhaImportacao.Situacao.INVALIDA:
            vistos_no_arquivo.add(chave)
        linhas.append(LinhaImportacao(
            tenant_id=tenant_id,
            importacao=importacao,
            numero=numero,
            chave=chave[:200],
            valores=_jsonavel(dados),
            situacao=situacao,
            motivo=motivo[:255],
            # Linha inválida nasce desmarcada: o padrão nunca deve ser gravar o
            # que o próprio motor já sabe que está errado.
            aceita=situacao != LinhaImportacao.Situacao.INVALIDA,
            bruto=[None if c is None else str(c) for c in bruta],
        ))
        if lote is not None and len(linhas) % PASSO_PROGRESSO == 0:
            Importacao.objects.filter(pk=importacao.pk).update(processadas=len(linhas))

    LinhaImportacao.objects.bulk_create(linhas, batch_size=1000)
    importacao.total_linhas = len(linhas)
    importacao.processadas = len(linhas)
    importacao.save(update_fields=["total_linhas", "processadas"])
    return importacao


def _classificar(recurso, dados, chave, vistos, existentes, tenant_id):
    """Veredito da linha. Ordem importa: o defeito mais barato de explicar primeiro."""
    for coluna in recurso.obrigatorias():
        valor = dados.get(coluna.campo)
        if valor in (None, "") or (coluna.tipo is Decimal and valor == Decimal("0")
                                   and coluna.campo == recurso.chave):
            return LinhaImportacao.Situacao.INVALIDA, f"Sem {coluna.rotulo.lower()}."
    if not chave:
        return LinhaImportacao.Situacao.INVALIDA, f"Sem {(recurso.coluna_chave.rotulo).lower()}."
    if chave in vistos:
        return LinhaImportacao.Situacao.INVALIDA, "Chave repetida dentro do próprio arquivo."

    motivo = recurso.validar_linha(dados)
    if motivo:
        return LinhaImportacao.Situacao.INVALIDA, motivo

    if chave in existentes or recurso.localizar(dados, tenant_id) is not None:
        existentes.add(chave)
        return LinhaImportacao.Situacao.DUPLICADA, "Já existe no destino — aceitar atualiza."
    return LinhaImportacao.Situacao.NOVA, ""


def _jsonavel(dados: dict) -> dict:
    """Decimal não é serializável em JSON; vai como texto e volta com `para_decimal`."""
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in dados.items()}


def _com_erro(*, recurso, tenant_id, nome_arquivo, mensagem, usuario_nome, lote=None,
              preservar_arquivo: bool = False) -> Importacao:
    """Erro de leitura vira linha com status `ERRO`, não exceção solta.

    O usuário precisa ver *que* tentou importar e *por que* falhou; um 400 que
    não deixa rastro faz a mesma pessoa reenviar o mesmo arquivo três vezes.
    """
    if lote is not None:
        lote.status = Importacao.Status.ERRO
        lote.mensagem = mensagem[:500]
        # `decidida_em` fica vazio quando o lote ainda espera um de-para: ele não
        # foi decidido, foi interrompido — e é isso que o distingue de um erro
        # terminal na listagem.
        lote.decidida_em = None if preservar_arquivo else timezone.now()
        lote.save(update_fields=["status", "mensagem", "decidida_em"])
        return lote
    return Importacao.objects.create(
        tenant_id=tenant_id,
        recurso=recurso.id,
        arquivo_nome=nome_arquivo[:255],
        contexto=dict(recurso.contexto or {}),
        status=Importacao.Status.ERRO,
        mensagem=mensagem[:500],
        usuario_nome=usuario_nome[:150],
        decidida_em=timezone.now(),
    )


# ---------------------------------------------------------------------------
# 2. Teto do plano
# ---------------------------------------------------------------------------


def _teto(nome: str, limites: dict | None):
    """Teto lido da claim `quotas` do token — mesma fonte de `nucleo.quotas`.

    O backend não consulta a tabela de planos: quem resolve a precedência
    (contrato → plano → free) é a IAM, na emissão do token. Repetir a resolução
    aqui criaria dois lugares para o mesmo número divergir. Sem a claim, `None` =
    não travar — o mesmo fail-open logado das outras camadas.
    """
    if not isinstance(limites, dict):
        return None
    valor = limites.get(nome)
    return valor if isinstance(valor, int) and valor >= 0 else None


def _checar_teto_por_operacao(quantidade: int, limites: dict | None) -> None:
    limite = _teto("importacao_linhas", limites)
    if limite is None:
        logger.info("impexp: sem claim de quota no token — importação sem teto (fail-open).")
        return
    if quantidade <= limite:
        return
    raise LimiteDoPlano(
        f"O arquivo tem {quantidade} linhas e o plano contratado importa até {limite} "
        "por vez. Divida o arquivo ou faça upgrade do plano.",
        limite=limite, tentado=quantidade, quota="importacao_linhas",
    )


# ---------------------------------------------------------------------------
# 3. Decidir: confirmar tudo · confirmar seleção · negar tudo
# ---------------------------------------------------------------------------


@transaction.atomic
def marcar(importacao: Importacao, *, aceitar: bool, linhas: list[int] | None = None) -> int:
    """Marca/desmarca linhas antes de aplicar. `linhas=None` = todas."""
    if not importacao.pendente:
        raise ImportacaoInvalida("Esta importação já foi decidida.")
    consulta = importacao.linhas.all()
    if linhas is not None:
        consulta = consulta.filter(linha_id__in=linhas)
    return consulta.update(aceita=aceitar)


@transaction.atomic
def descartar(importacao: Importacao, *, usuario_nome: str = "") -> Importacao:
    """Negar tudo: nada foi gravado, e o registro fica como rastro do que se recusou."""
    if not importacao.pendente:
        raise ImportacaoInvalida("Esta importação já foi decidida.")
    importacao.status = Importacao.Status.DESCARTADA
    importacao.decidida_em = timezone.now()
    if usuario_nome:
        importacao.usuario_nome = usuario_nome[:150]
    importacao.save(update_fields=["status", "decidida_em", "usuario_nome"])
    return importacao


@transaction.atomic
def aplicar(
    importacao: Importacao,
    *,
    recurso: Recurso,
    usuario_nome: str = "",
    limites: dict | None = None,
) -> int:
    """Grava as linhas aceitas. Tudo ou nada — a transação é o lote.

    Linha inválida nunca entra, mesmo marcada à mão: aceitar uma linha que o
    motor classificou como inválida seria pedir para gravar o que ele já sabe
    estar errado.
    """
    if not importacao.pendente:
        raise ImportacaoInvalida("Esta importação já foi decidida.")

    aceitas = list(
        importacao.linhas.filter(aceita=True)
        .exclude(situacao=LinhaImportacao.Situacao.INVALIDA)
        .order_by("numero")
    )
    # Teto de acervo reconferido na aplicação, e não só na preparação: entre subir
    # o arquivo e confirmar cabe outra importação inteira, e a checagem de lá já
    # estaria velha. É o caso em que o usuário confere com calma — exatamente o
    # que a R1 pede — e por isso a janela é larga.
    recurso.checar_quota_objeto(len(aceitas), limites, importacao.tenant_id)

    aplicadas = 0
    for linha in aceitas:
        dados = _valores_tipados(linha.valores, recurso)
        existente = recurso.localizar(dados, importacao.tenant_id)
        estado = recurso.aplicar_linha(dados, existente, importacao.tenant_id)
        linha.aplicada = True
        linha.estado_anterior = estado
        aplicadas += 1
    if aceitas:
        LinhaImportacao.objects.bulk_update(
            aceitas, ["aplicada", "estado_anterior"], batch_size=500,
        )

    importacao.status = Importacao.Status.APLICADA
    importacao.total_aplicadas = aplicadas
    importacao.decidida_em = timezone.now()
    if usuario_nome:
        importacao.usuario_nome = usuario_nome[:150]
    importacao.save(
        update_fields=["status", "total_aplicadas", "decidida_em", "usuario_nome"],
    )
    return aplicadas


@transaction.atomic
def desfazer(importacao: Importacao, *, recurso: Recurso) -> int:
    """R6 — desfaz o lote inteiro, na ordem inversa da aplicação.

    Ordem inversa porque a criação pode ter dependências entre linhas do mesmo
    arquivo; desfazer na ordem direta apagaria um pai antes do filho.
    """
    if importacao.status != Importacao.Status.APLICADA:
        raise ImportacaoInvalida("Só uma importação aplicada pode ser desfeita.")
    if not recurso.desfazivel:
        raise ImportacaoInvalida(
            f"O recurso '{recurso.id}' não declara `desfazer_linha` — este lote não é reversível."
        )

    linhas = list(importacao.linhas.filter(aplicada=True).order_by("-numero"))
    for linha in linhas:
        if linha.estado_anterior:
            recurso.desfazer_linha(linha.estado_anterior, importacao.tenant_id)
        linha.aplicada = False
    if linhas:
        LinhaImportacao.objects.bulk_update(linhas, ["aplicada"], batch_size=500)

    importacao.status = Importacao.Status.DESFEITA
    importacao.save(update_fields=["status"])
    return len(linhas)


def _valores_tipados(valores: dict, recurso: Recurso) -> dict:
    """JSON → tipos declarados (o Decimal que virou texto na gravação volta a Decimal)."""
    from .formatos.leitura import para_decimal

    saida: dict = {}
    for coluna in recurso.colunas:
        cru = valores.get(coluna.campo)
        if coluna.tipo is Decimal:
            saida[coluna.campo] = para_decimal(cru)
        elif coluna.tipo is int:
            saida[coluna.campo] = int(para_decimal(cru))
        elif coluna.tipo is bool:
            saida[coluna.campo] = bool(cru)
        else:
            saida[coluna.campo] = "" if cru is None else str(cru)
    return saida


# ---------------------------------------------------------------------------
# 4. Leitura para a tela e a R5
# ---------------------------------------------------------------------------


def resumo(importacao: Importacao) -> dict:
    """Os números que a tela de conferência mostra antes da decisão."""
    contagem = {s: 0 for s, _ in LinhaImportacao.Situacao.choices}
    for situacao in importacao.linhas.values_list("situacao", flat=True):
        contagem[situacao] = contagem.get(situacao, 0) + 1
    return {
        "importacao_id": importacao.importacao_id,
        "recurso": importacao.recurso,
        "arquivo": importacao.arquivo_nome,
        "status": importacao.status,
        "status_nome": importacao.get_status_display(),
        "mensagem": importacao.mensagem,
        "contexto": importacao.contexto or {},
        "assincrona": importacao.assincrona,
        # R4 no caminho de job: quando o cabeçalho não casou, o lote carrega o
        # que o extrator viu para a tela oferecer o de-para em vez de um beco.
        "aguarda_de_para": bool((importacao.parametros or {}).get("aguarda_de_para")),
        "cabecalhos_vistos": (importacao.parametros or {}).get("cabecalhos_vistos", []),
        "obrigatorias": (importacao.parametros or {}).get("obrigatorias", []),
        "colunas_do_recurso": (importacao.parametros or {}).get("colunas", []),
        "processadas": importacao.processadas,
        "progresso": importacao.progresso_pct,
        "total": importacao.total_linhas,
        "aplicadas": importacao.total_aplicadas,
        "novas": contagem.get(LinhaImportacao.Situacao.NOVA, 0),
        "duplicadas": contagem.get(LinhaImportacao.Situacao.DUPLICADA, 0),
        "invalidas": contagem.get(LinhaImportacao.Situacao.INVALIDA, 0),
        "aceitas": importacao.linhas.filter(aceita=True).count(),
    }


def recusadas_xlsx(importacao: Importacao, recurso: Recurso) -> bytes:
    """R5 — as linhas recusadas de volta como planilha, com o motivo ao lado.

    Numa carga de 4.000 linhas, "37 falharam" sem dizer quais obriga a refazer
    tudo. Aqui a pessoa corrige o arquivo que recebeu e reenvia.
    """
    from .formatos.escrita import escrever
    from .registro import Coluna

    colunas = (*recurso.colunas, Coluna("_motivo", "Motivo da recusa"))
    linhas = [
        {**_valores_tipados(l.valores, recurso), "_motivo": l.motivo}
        for l in importacao.linhas.filter(situacao=LinhaImportacao.Situacao.INVALIDA)
        .order_by("numero")
    ]
    conteudo, _ = escrever("xlsx", colunas=colunas, linhas=linhas, procedencia={
        "recurso_rotulo": f"{recurso.rotulo} — linhas recusadas",
        "recorte": f"arquivo {importacao.arquivo_nome}",
        "usuario": importacao.usuario_nome or "—",
        "emitido_em": timezone.localtime(importacao.criada_em).strftime("%d/%m/%Y %H:%M"),
        "linhas": len(linhas),
    })
    return conteudo
