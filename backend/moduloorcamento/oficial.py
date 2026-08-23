# backend/moduloorcamento/oficial.py
"""ORC.8 — **de onde** a base oficial vem, e como chegar lá sem apanhar do WAF.

Este arquivo é a fronteira trocável da decisão de rumo do dono (§12.7): hoje o
caminho é *ZIP oficial + parser próprio*, porque não existe biblioteca madura
para SINAPI — o único ETL open source é alpha, de um autor, e GPLv3; as APIs
comerciais cobram e o plano gratuito não carrega base em massa. O artefato da
Caixa é autoritativo, gratuito e estável há anos. **A API comercial fica como
caminho futuro**, e é justamente por isso que a busca mora atrás de uma função
só: trocá-la não deve tocar em quem lê o arquivo nem em quem o grava.

Três coisas que este arquivo sabe e que ninguém deveria ter de reaprender:

1. **O WAF da Caixa (Azion) limita por taxa.** Rajada derruba tudo para `429`,
   inclusive a URL boa — então uma falha aqui não é sinal de URL errada, e
   tentar de novo mais rápido é a pior reação possível. Daí o backoff.
2. **Hit frio no arquivo é recusado.** Ele quer sessão aquecida: uma visita à
   página pública de downloads antes, e o `Referer` dela no pedido do arquivo.
3. **O teto de bytes é conferido durante o stream.** Conferir o
   `Content-Length` não basta (ele pode faltar, ou mentir), e conferir depois de
   gravar é conferir tarde: quem enche o disco do worker já encheu.

Os números — teto, tentativas, esperas, pausa entre arquivos — são do dono e
moram em `payment/planos.py` §5.5b. Aqui só há a mecânica.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date

import requests

from payment import planos

logger = logging.getLogger(__name__)

MB = 1024 * 1024

# Navegador comum. Não é disfarce: um `python-requests/2.x` é recusado por
# borda de CDN com regra de bot, e o pedido é legítimo — arquivo público,
# baixado uma vez por mês, com pausa. Declarar-se de um jeito que a borda
# reconheça é a diferença entre a carga funcionar e o dono achar que a URL
# quebrou.
AGENTE = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Códigos em que **vale a pena** tentar de novo. 404 não está aqui de propósito:
# no dia 5 do mês a publicação simplesmente ainda não saiu, e insistir quatro
# vezes com espera crescente não faz o mês adiantar — só segura a cadeira da
# frota e atrasa o relato honesto ("ainda não publicado") em quase dois minutos.
CODIGOS_QUE_MERECEM_ESPERA = frozenset({408, 425, 429, 500, 502, 503, 504})


class CargaIndisponivel(Exception):
    """A busca não trouxe o arquivo — e o motivo importa mais que a exceção.

    `motivo` é um código estável que a tela usa para decidir o que oferecer:
    `nao_publicado` propõe esperar, `bloqueado` propõe o upload (o plano B),
    `sem_template` manda para a caixa de texto da URL.
    """

    def __init__(self, mensagem: str, *, motivo: str = "falhou", url: str = ""):
        super().__init__(mensagem)
        self.motivo = motivo
        self.url = url


@dataclass
class Baixado:
    """O que a busca devolve: os bytes e a **procedência** deles."""

    conteudo: bytes
    url: str
    nome: str = ""
    tentativas: int = 1
    avisos: list[str] = field(default_factory=list)

    @property
    def mb(self) -> float:
        return len(self.conteudo) / MB


def sessao_aquecida(pagina_referencia: str = "") -> requests.Session:
    """Abre a sessão e, se houver página de referência, a visita primeiro.

    A visita pode falhar sem que isso condene o download — há mês em que a
    página de downloads está fora e o arquivo continua servido. Falhar aqui
    derrubaria a carga por causa do aquecimento, que é meio e não fim.
    """
    sessao = requests.Session()
    sessao.headers.update({
        "User-Agent": AGENTE,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    if pagina_referencia:
        try:
            sessao.get(pagina_referencia, timeout=30)
        except requests.RequestException as exc:  # pragma: no cover - rede
            logger.info("orcamento: aquecimento da sessão falhou (%s) — seguindo", exc)
        else:
            sessao.headers["Referer"] = pagina_referencia
    return sessao


def baixar(
    url: str,
    *,
    sessao: requests.Session | None = None,
    teto_mb: int | None = None,
    progresso=None,
) -> Baixado:
    """Traz o artefato, com backoff e teto de bytes conferido no stream.

    `progresso` é chamado com os MB já lidos — é o que faz a tela dizer
    "baixando (7,2 MB)" em vez de ficar parada por dois minutos.
    """
    if not url:
        raise CargaIndisponivel(
            "Sem URL: a fonte não tem template configurado, ou o template não "
            "resolveu para esta competência.",
            motivo="sem_template",
        )
    teto = (teto_mb or planos.ORCAMENTO_CARGA_TETO_MB) * MB
    minha_sessao = sessao is None
    sessao = sessao or sessao_aquecida()
    espera = planos.ORCAMENTO_CARGA_ESPERA_INICIAL_S
    ultimo_erro = ""

    try:
        for tentativa in range(1, planos.ORCAMENTO_CARGA_TENTATIVAS + 1):
            try:
                resposta = sessao.get(url, timeout=(30, 120), stream=True)
            except requests.RequestException as exc:
                ultimo_erro = f"{type(exc).__name__}: {exc}"
                resposta = None
            else:
                if resposta.status_code == 404:
                    resposta.close()
                    raise CargaIndisponivel(
                        "A fonte respondeu 404 — a publicação desta competência ainda "
                        "não foi divulgada, ou o endereço mudou. Confira o template "
                        "da URL antes de supor que o mês atrasou.",
                        motivo="nao_publicado", url=url,
                    )
                if resposta.status_code == 200:
                    conteudo = _ler_com_teto(resposta, teto, progresso)
                    return Baixado(
                        conteudo=conteudo, url=url,
                        nome=_nome_do_arquivo(resposta, url),
                        tentativas=tentativa,
                    )
                ultimo_erro = f"HTTP {resposta.status_code}"
                merece_espera = resposta.status_code in CODIGOS_QUE_MERECEM_ESPERA
                resposta.close()
                if not merece_espera:
                    raise CargaIndisponivel(
                        f"A fonte respondeu {ultimo_erro} e este código não melhora "
                        "com espera. Se persistir, use o envio manual do arquivo.",
                        motivo="bloqueado", url=url,
                    )

            if tentativa < planos.ORCAMENTO_CARGA_TENTATIVAS:
                logger.warning(
                    "orcamento: carga tentativa %d/%d falhou (%s) — esperando %.0fs",
                    tentativa, planos.ORCAMENTO_CARGA_TENTATIVAS, ultimo_erro, espera,
                )
                time.sleep(espera)
                espera = min(espera * 2, planos.ORCAMENTO_CARGA_ESPERA_MAXIMA_S)
    finally:
        if minha_sessao:
            sessao.close()

    raise CargaIndisponivel(
        f"A fonte não entregou o arquivo em {planos.ORCAMENTO_CARGA_TENTATIVAS} "
        f"tentativas (último: {ultimo_erro}). O limitador de taxa do site oficial "
        "derruba rajada — vale tentar mais tarde ou enviar o arquivo à mão.",
        motivo="bloqueado", url=url,
    )


def _ler_com_teto(resposta, teto: int, progresso=None) -> bytes:
    """Lê o corpo em pedaços, abortando **no** estouro e não depois dele."""
    declarado = resposta.headers.get("Content-Length")
    if declarado and declarado.isdigit() and int(declarado) > teto:
        resposta.close()
        raise CargaIndisponivel(
            f"O arquivo tem {int(declarado) / MB:.0f} MB e o teto da carga é "
            f"{teto / MB:.0f} MB. Ou a URL aponta para outra coisa, ou o teto "
            "precisa da decisão do dono (payment/planos.py §5.5b).",
            motivo="grande_demais",
        )
    pedacos: list[bytes] = []
    lidos = 0
    marco = 0
    try:
        for pedaco in resposta.iter_content(chunk_size=256 * 1024):
            if not pedaco:
                continue
            lidos += len(pedaco)
            if lidos > teto:
                raise CargaIndisponivel(
                    f"O download passou de {teto / MB:.0f} MB e foi interrompido. "
                    "O ZIP nacional da SINAPI tem cerca de 16 MB — um arquivo desta "
                    "ordem quase sempre significa endereço errado.",
                    motivo="grande_demais",
                )
            pedacos.append(pedaco)
            if progresso and lidos - marco >= MB:
                marco = lidos
                progresso(lidos / MB)
    finally:
        resposta.close()
    return b"".join(pedacos)


def _nome_do_arquivo(resposta, url: str) -> str:
    disposicao = resposta.headers.get("Content-Disposition", "")
    if "filename=" in disposicao:
        bruto = disposicao.split("filename=")[-1].strip().strip('";')
        if bruto:
            return bruto[:255]
    return url.rsplit("/", 1)[-1].split("?")[0][:255]


def competencia_alvo(defasagem_meses: int, hoje: date | None = None) -> date:
    """A competência que faz sentido pedir hoje.

    A SINAPI publica o mês M por volta do dia 10 de M+1, então pedir o mês
    corrente é pedir 404 com data marcada. A defasagem é da fonte e por isso é
    campo dela, não constante daqui.
    """
    hoje = hoje or date.today()
    ano, mes = hoje.year, hoje.month - int(defasagem_meses or 0)
    while mes <= 0:
        mes += 12
        ano -= 1
    return date(ano, mes, 1)


def pausar_entre_arquivos() -> None:
    """A pausa que separa dois downloads da mesma corrida (formato antigo)."""
    time.sleep(planos.ORCAMENTO_CARGA_PAUSA_ENTRE_ARQUIVOS_S)
