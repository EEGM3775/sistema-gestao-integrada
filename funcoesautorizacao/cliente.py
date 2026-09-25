"""Cliente do SpiceDB pela API HTTP — só biblioteca padrão.

**Por que HTTP e não o cliente gRPC oficial (`authzed`).** O pacote é
compartilhado pela IAM e pelo backend, e as duas imagens teriam de ganhar
`grpcio` (binário nativo, dezenas de MB) para dizer "pode?" e "grava esta
relação". A API HTTP do SpiceDB é a mesma API v1, servida pelo gateway dele, e
cobre tudo o que a remodelagem usa: escrita e leitura de relação, checagem
unitária e em lote, schema e o Watch (em fluxo, uma linha JSON por evento).

**O que este módulo não decide.** Ele não conhece tenant, cache nem classe de
ação: devolve o que o PDP respondeu, ou uma exceção que diz se a culpa foi do
PDP (`PdpIndisponivel`) ou da pergunta (`PerguntaInvalida`). Quem decide o que
fazer com cada caso é quem pergunta (`nucleo/autorizacao.py` no backend,
`identity/pdp.py` na IAM) — e a regra da casa é negar.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Iterator

# Máximo de atualizações numa escrita — é o padrão do SpiceDB
# (`--write-relationships-max-updates-per-call`), janela de protocolo de
# terceiro e não teto nosso (§5.6 do planos.py).
MAX_ATUALIZACOES_POR_ESCRITA = 1000


class ErroDoPdp(Exception):
    """Base: o PDP não deu uma resposta utilizável."""


class PdpIndisponivel(ErroDoPdp):
    """Rede, tempo esgotado ou erro do servidor. A pergunta pode estar certa."""


class PerguntaInvalida(ErroDoPdp):
    """O PDP entendeu e recusou: tipo, relação ou permissão fora do schema."""


@dataclass(frozen=True, order=True)
class Rel:
    """Uma relação: ``tipo:id#relacao@sujeito_tipo:sujeito_id[#sujeito_relacao]``."""

    tipo: str
    id: str
    relacao: str
    sujeito_tipo: str
    sujeito_id: str
    sujeito_relacao: str = ""

    def para_api(self) -> dict:
        sujeito = {"object": {"objectType": self.sujeito_tipo, "objectId": self.sujeito_id}}
        if self.sujeito_relacao:
            sujeito["optionalRelation"] = self.sujeito_relacao
        return {
            "resource": {"objectType": self.tipo, "objectId": self.id},
            "relation": self.relacao,
            "subject": sujeito,
        }

    @classmethod
    def da_api(cls, rel: dict) -> "Rel":
        sujeito = rel["subject"]
        return cls(
            tipo=rel["resource"]["objectType"],
            id=rel["resource"]["objectId"],
            relacao=rel["relation"],
            sujeito_tipo=sujeito["object"]["objectType"],
            sujeito_id=sujeito["object"]["objectId"],
            sujeito_relacao=sujeito.get("optionalRelation") or "",
        )

    def __str__(self) -> str:
        sufixo = f"#{self.sujeito_relacao}" if self.sujeito_relacao else ""
        return (
            f"{self.tipo}:{self.id}#{self.relacao}"
            f"@{self.sujeito_tipo}:{self.sujeito_id}{sufixo}"
        )


# --- Consistência (docs/acesso-e-permissoes.md §10.8) ------------------------


def consistencia_rapida() -> dict:
    """Classe A: a resposta que o PDP tiver mais à mão."""
    return {"minimizeLatency": True}


def consistencia_ao_menos(zedtoken: str | None) -> dict:
    """Classe B: pelo menos tão nova quanto a última mudança conhecida.

    Sem ZedToken conhecido, cai na rápida — é o caso de um tenant cuja relação
    nunca mudou depois que o processo subiu, e aí não há mudança a esperar.
    """
    if zedtoken:
        return {"atLeastAsFresh": {"token": zedtoken}}
    return consistencia_rapida()


def consistencia_total() -> dict:
    """Classe C: o estado mais recente, sem atalho."""
    return {"fullyConsistent": True}


class ClienteSpiceDB:
    """Um cliente por processo basta: não guarda conexão aberta entre chamadas."""

    def __init__(self, url: str, chave: str, *, timeout_s: float):
        if not url:
            raise ValueError("SpiceDB sem URL.")
        self.url = url.rstrip("/")
        self.chave = chave
        self.timeout_s = timeout_s

    # --- transporte ---------------------------------------------------------

    def _requisicao(self, caminho: str, corpo: dict) -> urllib.request.Request:
        return urllib.request.Request(
            self.url + caminho,
            data=json.dumps(corpo).encode(),
            headers={
                "Authorization": f"Bearer {self.chave}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    @staticmethod
    def _erro_http(exc: urllib.error.HTTPError) -> ErroDoPdp:
        try:
            detalhe = json.loads(exc.read().decode() or "{}")
        except (ValueError, OSError):
            detalhe = {}
        mensagem = detalhe.get("message") or (detalhe.get("error") or {}).get("message") or ""
        if 400 <= exc.code < 500 and exc.code not in (401, 403, 408, 429):
            return PerguntaInvalida(f"{exc.code}: {mensagem}")
        return PdpIndisponivel(f"{exc.code}: {mensagem}")

    def _post(self, caminho: str, corpo: dict, *, timeout_s: float | None = None) -> dict:
        try:
            with urllib.request.urlopen(
                self._requisicao(caminho, corpo), timeout=timeout_s or self.timeout_s
            ) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            raise self._erro_http(exc) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            raise PdpIndisponivel(str(exc)) from exc

    def _fluxo(self, caminho: str, corpo: dict, *, timeout_s: float | None,
               silencio_encerra: bool = False) -> Iterator[dict]:
        """Resposta em fluxo: uma linha JSON por item, ``{"result": …}`` ou ``{"error": …}``.

        `silencio_encerra`: um fluxo longo (o Watch) que passa `timeout_s` sem
        mandar nada termina **normalmente**, em vez de levantar — nada ter mudado
        não é erro, e quem ouve reabre a partir do último cursor.
        """
        try:
            resp = urllib.request.urlopen(self._requisicao(caminho, corpo), timeout=timeout_s)
        except urllib.error.HTTPError as exc:
            raise self._erro_http(exc) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            raise PdpIndisponivel(str(exc)) from exc
        with resp:
            try:
                for linha in resp:
                    linha = linha.strip()
                    if not linha:
                        continue
                    item = json.loads(linha)
                    if "error" in item:
                        erro = item["error"]
                        codigo = erro.get("code")
                        # gRPC 3/5/9 = argumento inválido / não encontrado / pré-condição.
                        if codigo in (3, 5, 9):
                            raise PerguntaInvalida(erro.get("message", ""))
                        raise PdpIndisponivel(erro.get("message", ""))
                    yield item.get("result", {})
            except (socket.timeout, TimeoutError) as exc:
                if silencio_encerra:
                    return
                raise PdpIndisponivel(str(exc)) from exc
            except (ConnectionError, OSError) as exc:
                raise PdpIndisponivel(str(exc)) from exc

    # --- schema -------------------------------------------------------------

    def ler_esquema(self) -> str | None:
        try:
            return self._post("/v1/schema/read", {}).get("schemaText")
        except PerguntaInvalida:
            return None  # 404: nenhum schema gravado ainda

    def revisao_atual(self) -> str:
        """Um ZedToken do agora — serve de cursor inicial do Watch, para quem
        começa a ouvir não perder o que muda entre uma conexão e a seguinte."""
        return (self._post("/v1/schema/read", {}).get("readAt") or {}).get("token", "")

    def escrever_esquema(self, texto: str) -> str:
        return self._post("/v1/schema/write", {"schema": texto}).get("writtenAt", {}).get("token", "")

    # --- decisão ------------------------------------------------------------

    def checar(self, tipo: str, id_: str, permissao: str, usuario_id: str,
               consistencia: dict) -> tuple[bool, str]:
        """``(permitido, zedtoken)``. Levanta `ErroDoPdp` sem resposta utilizável."""
        resp = self._post("/v1/permissions/check", {
            "consistency": consistencia,
            "resource": {"objectType": tipo, "objectId": id_},
            "permission": permissao,
            "subject": {"object": {"objectType": "usuario", "objectId": usuario_id}},
        })
        return (
            resp.get("permissionship") == "PERMISSIONSHIP_HAS_PERMISSION",
            (resp.get("checkedAt") or {}).get("token", ""),
        )

    def checar_em_lote(self, itens: list[tuple[str, str, str]], usuario_id: str,
                       consistencia: dict) -> list[bool | ErroDoPdp]:
        """Uma ida ao PDP para várias perguntas ``(tipo, id, permissao)``.

        Devolve, na mesma ordem, o booleano ou a exceção **daquele item** — uma
        permissão fora do schema não derruba as outras do lote.
        """
        if not itens:
            return []
        resp = self._post("/v1/permissions/checkbulk", {
            "consistency": consistencia,
            "items": [
                {
                    "resource": {"objectType": tipo, "objectId": id_},
                    "permission": permissao,
                    "subject": {"object": {"objectType": "usuario", "objectId": usuario_id}},
                }
                for tipo, id_, permissao in itens
            ],
        })
        saida: list[bool | ErroDoPdp] = []
        for par in resp.get("pairs", []):
            if "error" in par and par["error"]:
                saida.append(PerguntaInvalida(par["error"].get("message", "")))
            else:
                saida.append(
                    (par.get("item") or {}).get("permissionship") == "PERMISSIONSHIP_HAS_PERMISSION"
                )
        if len(saida) != len(itens):
            raise PdpIndisponivel("Lote respondido pela metade.")
        return saida

    # --- relações -----------------------------------------------------------

    def escrever(self, tocar: Iterable[Rel] = (), remover: Iterable[Rel] = ()) -> str:
        """Grava e remove relações. Devolve o ZedToken da última escrita ("" se nada).

        Acima de `MAX_ATUALIZACOES_POR_ESCRITA` a escrita é partida em várias, e
        deixa de ser atômica — quem chama é a reconciliação, que é idempotente e
        refaz o que faltar na volta seguinte.
        """
        atualizacoes = [
            {"operation": "OPERATION_DELETE", "relationship": r.para_api()} for r in remover
        ] + [
            {"operation": "OPERATION_TOUCH", "relationship": r.para_api()} for r in tocar
        ]
        token = ""
        for i in range(0, len(atualizacoes), MAX_ATUALIZACOES_POR_ESCRITA):
            resp = self._post("/v1/relationships/write", {
                "updates": atualizacoes[i:i + MAX_ATUALIZACOES_POR_ESCRITA],
            })
            token = (resp.get("writtenAt") or {}).get("token", token)
        return token

    def ler(self, tipo: str, prefixo_id: str = "") -> list[Rel]:
        """Todas as relações de um tipo, opcionalmente só dos ids com o prefixo."""
        filtro: dict = {"resourceType": tipo}
        if prefixo_id:
            filtro["optionalResourceIdPrefix"] = prefixo_id
        return [
            Rel.da_api(item["relationship"])
            for item in self._fluxo(
                "/v1/relationships/read",
                {"consistency": consistencia_total(), "relationshipFilter": filtro},
                timeout_s=max(self.timeout_s, 10.0),
            )
            if item.get("relationship")
        ]

    def vigiar(self, cursor: str | None, *, timeout_s: float | None = None
               ) -> Iterator[tuple[list[tuple[str, Rel]], str]]:
        """Fluxo de mudanças: ``([(operacao, rel), …], cursor_novo)`` por lote.

        `operacao` é ``"tocar"`` ou ``"remover"``. Lote sem mudança (batimento do
        servidor) chega com a lista vazia e o cursor adiante — é o que permite
        salvar o cursor mesmo num dia sem nenhuma troca de papel.
        """
        # O checkpoint é o batimento: sem ele, um fluxo sem mudança fica mudo e
        # quem ouve não distingue "nada mudou" de "a conexão morreu".
        corpo: dict = {"optionalUpdateKinds": [
            "WATCH_KIND_INCLUDE_RELATIONSHIP_UPDATES", "WATCH_KIND_INCLUDE_CHECKPOINTS",
        ]}
        if cursor:
            corpo["optionalStartCursor"] = {"token": cursor}
        for resultado in self._fluxo("/v1/watch", corpo, timeout_s=timeout_s, silencio_encerra=True):
            mudancas = []
            for upd in resultado.get("updates") or []:
                operacao = "remover" if upd.get("operation") == "OPERATION_DELETE" else "tocar"
                mudancas.append((operacao, Rel.da_api(upd["relationship"])))
            novo = (resultado.get("changesThrough") or {}).get("token") or cursor or ""
            yield mudancas, novo
