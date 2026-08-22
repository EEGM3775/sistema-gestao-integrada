# backend/moduloprancheta/entrega.py
"""Como o arquivo do acervo sai — o que é DESTE módulo depois da PRA.5.

Este arquivo já foi a porta de saída inteira. A PRA.2 o criou para tirar a
leitura do acervo de `/media/`, por dois motivos que continuam valendo e viraram
a docstring de [funcoesimpexp/entrega.py](../funcoesimpexp/entrega.py):

- **em produção `/media/` não existe**: [`config/urls.py`](../config/urls.py) só
  monta `MEDIA_URL` quando `DEBUG`; fora disso o gateway encaminha ao backend, que
  responde 404. O visualizador nasceria apontando para o vazio;
- **em desenvolvimento ela é aberta**: `django.views.static.serve` não passa por
  autenticação, entitlement nem RLS. É o **S10**, que o MAP.3 recusou repetir.

**O que mudou na PRA.5** (decisão do dono, 08/08/2026 — a porta única é de
entrada *e* de saída): o **mecanismo** subiu para o motor. `servir`,
`nome_para_download` e a política de cache eram quatro guarda-corpos
reimplementados aqui — `nosniff`, `attachment`, tipo decidido por nós, nome
saneado —, a mesma forma do [D75](../../docs/historico-correcoes.md) do lado da entrada.
Eles agora existem uma vez só, e todo módulo os herda.

**O que ficou, e é o que de fato é nosso:** qual MIME cada um dos nossos formatos
tem (o motor não conhece DWG nem glTF) e as URLs, que o serializer publica. As
URLs mudaram de *forma* — apontam para a rota do motor — e não de *contrato*: o
frontend consome `arquivo_url`, então nada nele precisou mudar.
"""
from __future__ import annotations

import hashlib
import os

from funcoesimpexp.entrega import TIPO_GENERICO, tipo_por_extensao, url_do_arquivo

from .formatos import FORMATO_POR_CODIGO

#: Os dois recursos deste módulo no registry do motor. São **dois** porque são
#: dois gates: o acervo é `prancheta.documento`, a marcação é
#: `prancheta.marcacao` — a segregação da PRA.3, que um recurso só apagaria.
#: Constantes e não texto solto: aparecem em quatro URLs, e um erro de digitação
#: num deles daria 404 só naquela.
RECURSO_ACERVO = "prancheta.acervo"
RECURSO_MARCACAO = "prancheta.marcacao"

# O mapa de extensão → MIME das nossas derivadas subiu para o motor no **D70**,
# quando os nove prefixos de `/media/` passaram a precisar do mesmo — dois mapas
# do mesmo assunto divergem, e é o que o D75 pegou acontecendo na entrada.
# `TIPO_GENERICO` continua exportado daqui porque os testes do módulo o leem.


def _url(recurso: str, especie: str, chave) -> str:
    """A URL da porta única. O mecanismo é do motor; o que é nosso é a espécie."""
    return url_do_arquivo(recurso, especie, chave)


def url_da_revisao(revisao_id: int) -> str:
    """O arquivo como o projetista o entregou."""
    return _url(RECURSO_ACERVO, "revisao", revisao_id)


def url_da_derivada(derivada_id: int, versao: str = "") -> str:
    """A conversão, com a versão do conteúdo na query.

    **A versão não é enfeite.** A derivada é única por `(revisão, tipo, motor)` e
    a mesma linha é reescrita a cada reconversão, então a URL sozinha não
    identifica o conteúdo — e a resposta é `immutable` por um ano. Sem `?v=`, uma
    prancha reconvertida continuava aparecendo como antes para quem já a tinha
    aberto, **sem nada na tela sugerindo que havia uma versão melhor**. O sintoma
    é cruel: o servidor conserta, o teste passa, e o cliente jura que nada mudou
    ([D51](../../docs/historico-correcoes.md)).

    Vazia quando quem chama não tem o objeto à mão — aí a URL volta a ser a de
    antes, e o comportamento também.
    """
    caminho = _url(RECURSO_ACERVO, "derivada", derivada_id)
    return f"{caminho}?v={versao}" if versao else caminho


def url_do_snap(derivada_id: int, versao: str = "") -> str:
    """O índice de snap da derivada — a geometria onde a mira gruda (PRA.10).

    Carrega o mesmo `?v=` da derivada, e pela mesma razão do D51: o sidecar é
    reescrito junto com o SVG a cada reconversão. Sem a versão, quem já tinha a
    prancha aberta continuaria medindo sobre a geometria antiga — e este é o pior
    lugar possível para um cache velho, porque a mira **parece** funcionar: ela
    gruda, com precisão, no traço que não existe mais.
    """
    caminho = _url(RECURSO_ACERVO, "snap", derivada_id)
    return f"{caminho}?v={versao}" if versao else caminho


def url_do_snapshot(ponto_de_vista_id: int) -> str:
    """A imagem do ponto de vista da marcação (PRA.3).

    Pela mesma porta e por **outro recurso**: o gate do snapshot é
    `prancheta.marcacao`, não `prancheta.documento`.
    """
    return _url(RECURSO_MARCACAO, "snapshot", ponto_de_vista_id)


def versao_da_derivada(derivada) -> str:
    """Identidade do **conteúdo** de uma derivada, curta o bastante para uma URL.

    Junta o que muda quando a conversão muda: o arquivo de origem
    (`hash_origem`), o motor que a produziu (`motor_versao` — é a chave de
    idempotência do pipeline) e o instante em que ela ficou pronta, que é o que
    separa duas conversões do *mesmo* arquivo pelo *mesmo* motor depois de um
    conserto como o do D46.
    """
    concluido = getattr(derivada, "concluido_em", None)
    origem = "|".join([
        str(getattr(derivada, "hash_origem", "") or ""),
        str(getattr(derivada, "motor_versao", "") or ""),
        concluido.isoformat() if concluido else "",
    ])
    return hashlib.sha256(origem.encode()).hexdigest()[:12]


def tipo_do_formato(codigo: str) -> str:
    """MIME do arquivo ORIGINAL, pelo código de formato que a entrada carimbou.

    Pelo **código**, e nunca pelo nome que o cliente mandou: deixar o `mimetypes`
    adivinhar por `nome_original` daria a quem enviou o poder de escolher como o
    browser interpreta o próprio upload.
    """
    formato = FORMATO_POR_CODIGO.get(codigo)
    return formato.mimes[0] if formato and formato.mimes else TIPO_GENERICO


def tipo_da_derivada(nome: str) -> str:
    """MIME da conversão que NÓS escrevemos — a extensão aqui é do adaptador."""
    return tipo_por_extensao(nome)


def nome_da_derivada(derivada) -> str:
    """Nome de download de uma conversão nossa.

    Sai do `tipo` e do id, e **não** do nome do arquivo guardado (que é um hash)
    nem do `nome_original` da revisão — este último custaria uma consulta a mais
    no caminho quente do visualizador para melhorar um nome que quase ninguém vê:
    a tela busca a derivada por `fetch`+blob, não pelo "salvar como" do navegador.
    """
    extensao = os.path.splitext(derivada.arquivo.name)[1] if derivada.arquivo else ""
    return f"{derivada.tipo}-{derivada.pk}{extensao}"
