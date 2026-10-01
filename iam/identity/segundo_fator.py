"""Segundo fator — regras de domínio (remodelagem da segurança, fase 1).

Desenho em docs/acesso-e-permissoes.md §10.5. Separado das views pelo mesmo
motivo do `recuperacao.py`: o que sustenta a segurança (anti-reuso do código,
bloqueio por tentativa, código de recuperação de uso único, desafio que não se
reaproveita) não pode depender de cada endpoint lembrar de repetir.

**Quem é obrigado.** O admin do tenant e o supervisor da plataforma — as contas
que trocam papéis, alçadas e a escada de aprovação. Para os demais é opcional
*(decisão do dono, 24/09/2026)*, ligado na tela de perfil. O admin tem uma volta
atrás por empresa (`Tenant.segundo_fator_obrigatorio`); o supervisor não, porque
ele alcança o catálogo inteiro.

**O método.** TOTP (RFC 6238) — o código de 6 dígitos que qualquer app
autenticador gera. Implementado aqui, sem dependência: é um HMAC-SHA1 sobre o
número do passo de 30 s, e cabe em dez linhas. Passkey entra depois como outro
`SegundoFator.Metodo`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from payment.planos import (
    SEGUNDO_FATOR_BLOQUEIO_S,
    SEGUNDO_FATOR_CODIGOS_DE_RECUPERACAO,
    SEGUNDO_FATOR_DESAFIO_VALIDADE_S,
    SEGUNDO_FATOR_TENTATIVAS,
)

from . import recuperacao
from .models import CodigoRecuperacao, EventoSeguranca, SegundoFator

# RFC 6238 e o app do usuário — não são limites do produto (§5.6 do planos.py).
PASSO_S = 30
DIGITOS = 6
TOLERANCIA_PASSOS = 1  # um passo para cada lado: relógio do celular adiantado ou atrasado
EMISSOR = "SGI"

# As contas que mais interessam a um invasor — a tela de perfil insiste com quem
# tem uma destas (§10.5). Conjuntos explícitos, e não regra por sufixo: "aprovar"
# um orçamento e "baixar" um título pesam diferente, e a lista é revisada quando
# o catálogo ganha verbo de dinheiro. `test_segundo_fator` confere que cada código
# existe no catálogo.
ALCADA_FINANCEIRA = frozenset({
    "erp.conta_pagar.baixar",
    "erp.conta_receber.baixar",
    "erp.conta_pagar.estornar",
    "erp.conta_receber.estornar",
    "pdca.medicao.atestar",
    "pdca.aditivo.aprovar",
    "sil.requisicao.aprovar",
    "orcamento.orcamento.aprovar",
})
DADO_DE_SAUDE = frozenset({
    "rh.dado_medico.view",
    "pdca.ocorrencia.view",
})


class CodigoRecusado(Exception):
    """O código não abriu. `motivo` é `invalido` ou `bloqueado` — a view traduz."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


# --- quem --------------------------------------------------------------------
def obrigatorio(usuario) -> bool:
    if usuario.is_superuser:
        return True
    if usuario.is_tenant_admin:
        tenant = usuario.tenant
        return tenant is None or tenant.segundo_fator_obrigatorio
    return False


def ativo(usuario) -> SegundoFator | None:
    return SegundoFator.objects.filter(usuario=usuario, confirmado_em__isnull=False).first()


def motivos_para_ativar(usuario) -> list[str]:
    """Por que esta conta, em particular, deveria ter segundo fator."""
    permissoes = set(usuario.permissoes_efetivas())
    motivos = []
    if obrigatorio(usuario):
        motivos.append("administrador")
    if permissoes & ALCADA_FINANCEIRA:
        motivos.append("alcada_financeira")
    if permissoes & DADO_DE_SAUDE:
        motivos.append("dado_de_saude")
    return motivos


# --- cifra do segredo ----------------------------------------------------------
def _fernet() -> Fernet:
    """A chave vem de `SEGUNDO_FATOR_CHAVE` (Fernet, fora do banco). Sem ela, é
    derivada do `SECRET_KEY` por HKDF — serve ao dev, e em produção amarra o
    segundo fator à `SECRET_KEY`: trocá-la sem definir a chave própria obriga
    todo mundo a cadastrar de novo."""
    chave = getattr(settings, "SEGUNDO_FATOR_CHAVE", "") or ""
    if chave:
        return Fernet(chave.encode())
    derivada = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"sgi-iam-segundo-fator",
    ).derive(settings.SECRET_KEY.encode())
    return Fernet(base64.urlsafe_b64encode(derivada))


def cifrar(segredo: str) -> str:
    return _fernet().encrypt(segredo.encode()).decode()


def decifrar(texto: str) -> str | None:
    try:
        return _fernet().decrypt(texto.encode()).decode()
    except InvalidToken:
        return None


# --- TOTP ----------------------------------------------------------------------
def novo_segredo() -> str:
    """160 bits em base32, sem o `=` de preenchimento — o formato que todo app lê."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def passo_atual(agora: float | None = None) -> int:
    return int((time.time() if agora is None else agora) // PASSO_S)


def codigo_do_passo(segredo: str, passo: int) -> str:
    chave = base64.b32decode(segredo + "=" * (-len(segredo) % 8))
    mac = hmac.new(chave, struct.pack(">Q", passo), hashlib.sha1).digest()
    deslocamento = mac[-1] & 0x0F
    numero = struct.unpack(">I", mac[deslocamento:deslocamento + 4])[0] & 0x7FFFFFFF
    return f"{numero % 10 ** DIGITOS:0{DIGITOS}d}"


def _passo_que_casa(segredo: str, codigo: str, agora: float | None = None) -> int | None:
    atual = passo_atual(agora)
    casou = None
    # Compara com os três sem sair cedo: o tempo de resposta não diz qual passo era.
    for passo in range(atual - TOLERANCIA_PASSOS, atual + TOLERANCIA_PASSOS + 1):
        if hmac.compare_digest(codigo_do_passo(segredo, passo), codigo):
            casou = passo
    return casou


def uri_otpauth(usuario, segredo: str) -> str:
    rotulo = quote(f"{EMISSOR}:{usuario.username}")
    return (
        f"otpauth://totp/{rotulo}?secret={segredo}&issuer={quote(EMISSOR)}"
        f"&algorithm=SHA1&digits={DIGITOS}&period={PASSO_S}"
    )


def qr_svg(uri: str) -> str:
    """O QR do cadastro como `data:` URI de SVG — gerado aqui para o segredo não
    passar por nenhum serviço de terceiro que desenhe QR."""
    import segno

    return segno.make(uri, error="m").svg_data_uri(scale=5, border=2)


def _normalizar(codigo) -> str:
    return "".join(ch for ch in str(codigo or "") if ch.isalnum()).lower()


# --- bloqueio por tentativa ------------------------------------------------------
def _chave_falhas(usuario) -> str:
    return f"segundo_fator:falhas:{usuario.pk}"


def bloqueado(usuario) -> bool:
    return (cache.get(_chave_falhas(usuario)) or 0) >= SEGUNDO_FATOR_TENTATIVAS


def _registrar_falha(usuario, request=None) -> None:
    chave = _chave_falhas(usuario)
    cache.add(chave, 0, SEGUNDO_FATOR_BLOQUEIO_S)
    try:
        falhas = cache.incr(chave)
    except ValueError:  # expirou entre o add e o incr
        cache.set(chave, 1, SEGUNDO_FATOR_BLOQUEIO_S)
        falhas = 1
    if falhas == SEGUNDO_FATOR_TENTATIVAS:
        recuperacao.registrar_evento(
            EventoSeguranca.Tipo.SEGUNDO_FATOR_BLOQUEADO, alvo=usuario, request=request,
            minutos=SEGUNDO_FATOR_BLOQUEIO_S // 60,
        )


def _zerar_falhas(usuario) -> None:
    cache.delete(_chave_falhas(usuario))


def conferir_senha(usuario, senha, *, request=None) -> None:
    """A senha redigitada no ato grave de quem não tem segundo fator (step-up,
    fase 6 — §10.5, decisão 6 do dono). Conta no **mesmo** bloqueio do código:
    quem roubou a sessão não ganha, na confirmação, um adivinhador de senha sem
    freio. Levanta `CodigoRecusado`."""
    if bloqueado(usuario):
        raise CodigoRecusado("bloqueado")
    if not usuario.check_password(senha or ""):
        _registrar_falha(usuario, request)
        raise CodigoRecusado("invalido")
    _zerar_falhas(usuario)


# --- verificar -------------------------------------------------------------------
def verificar(usuario, codigo, *, request=None, aceita_recuperacao: bool = True) -> str:
    """Confere o código do app (ou um de recuperação). Devolve `totp` ou
    `recuperacao`; levanta `CodigoRecusado`. Toda recusa conta para o bloqueio."""
    if bloqueado(usuario):
        raise CodigoRecusado("bloqueado")
    fator = ativo(usuario)
    limpo = _normalizar(codigo)
    if fator is not None and limpo:
        if limpo.isdigit() and len(limpo) == DIGITOS:
            segredo = decifrar(fator.segredo_cifrado)
            passo = _passo_que_casa(segredo, limpo) if segredo else None
            # Anti-reuso: o update só pega se o passo é posterior ao último aceito,
            # e é atômico — dois logins com o mesmo código, ao mesmo tempo, não
            # passam os dois.
            if passo is not None and SegundoFator.objects.filter(
                pk=fator.pk, ultimo_passo__lt=passo,
            ).update(ultimo_passo=passo):
                _zerar_falhas(usuario)
                return "totp"
        elif aceita_recuperacao:
            hash_ = hashlib.sha256(limpo.encode()).hexdigest()
            usados = CodigoRecuperacao.objects.filter(
                usuario=usuario, codigo_hash=hash_, usado_em__isnull=True,
            ).update(usado_em=timezone.now())
            if usados:
                _zerar_falhas(usuario)
                restantes = codigos_restantes(usuario)
                recuperacao.registrar_evento(
                    EventoSeguranca.Tipo.SEGUNDO_FATOR_RECUPERACAO, alvo=usuario,
                    request=request, restantes=restantes,
                )
                from . import emails

                emails.enviar_aviso_segundo_fator(usuario, "recuperacao", restantes=restantes)
                return "recuperacao"
    _registrar_falha(usuario, request)
    raise CodigoRecusado("invalido")


# --- ciclo de vida ------------------------------------------------------------------
def iniciar_cadastro(usuario) -> tuple[str, str]:
    """Novo segredo, ainda não confirmado. Recomeçar o cadastro troca o segredo —
    o QR lido antes deixa de valer. Devolve `(segredo, uri)`."""
    if ativo(usuario) is not None:
        raise ValueError("O segundo fator já está ativo nesta conta.")
    segredo = novo_segredo()
    SegundoFator.objects.update_or_create(
        usuario=usuario,
        defaults={
            "segredo_cifrado": cifrar(segredo),
            "confirmado_em": None,
            "ultimo_passo": 0,
            "metodo": SegundoFator.Metodo.TOTP,
        },
    )
    return segredo, uri_otpauth(usuario, segredo)


@transaction.atomic
def confirmar_cadastro(usuario, codigo, *, request=None) -> list[str]:
    """O primeiro código certo liga o segundo fator e entrega os códigos de
    recuperação — a única vez em que eles aparecem em claro."""
    if bloqueado(usuario):
        raise CodigoRecusado("bloqueado")
    fator = SegundoFator.objects.select_for_update().filter(
        usuario=usuario, confirmado_em__isnull=True,
    ).first()
    limpo = _normalizar(codigo)
    segredo = decifrar(fator.segredo_cifrado) if fator else None
    passo = _passo_que_casa(segredo, limpo) if segredo and limpo.isdigit() else None
    if passo is None:
        _registrar_falha(usuario, request)
        raise CodigoRecusado("invalido")
    fator.confirmado_em = timezone.now()
    fator.ultimo_passo = passo
    fator.save(update_fields=["confirmado_em", "ultimo_passo"])
    _zerar_falhas(usuario)
    codigos = gerar_codigos(usuario)
    recuperacao.registrar_evento(
        EventoSeguranca.Tipo.SEGUNDO_FATOR_ATIVADO, alvo=usuario, autor=usuario,
        request=request, metodo=fator.metodo,
    )
    from . import emails

    emails.enviar_aviso_segundo_fator(usuario, "ativado")
    return codigos


def gerar_codigos(usuario) -> list[str]:
    """Troca todos os códigos de recuperação. Os antigos, usados ou não, somem."""
    CodigoRecuperacao.objects.filter(usuario=usuario).delete()
    claros = []
    for _ in range(SEGUNDO_FATOR_CODIGOS_DE_RECUPERACAO):
        bruto = base64.b32encode(secrets.token_bytes(10)).decode().lower()[:10]
        claros.append(f"{bruto[:5]}-{bruto[5:]}")
    CodigoRecuperacao.objects.bulk_create([
        CodigoRecuperacao(
            usuario=usuario,
            codigo_hash=hashlib.sha256(_normalizar(c).encode()).hexdigest(),
        )
        for c in claros
    ])
    return claros


def codigos_restantes(usuario) -> int:
    return CodigoRecuperacao.objects.filter(usuario=usuario, usado_em__isnull=True).count()


def remover(usuario) -> bool:
    """Apaga o segundo fator e os códigos. Devolve se havia um ativo."""
    havia = ativo(usuario) is not None
    SegundoFator.objects.filter(usuario=usuario).delete()
    CodigoRecuperacao.objects.filter(usuario=usuario).delete()
    _zerar_falhas(usuario)
    return havia


def estado(usuario) -> dict:
    fator = ativo(usuario)
    return {
        "ativo": fator is not None,
        "metodo": fator.metodo if fator else None,
        "desde": fator.confirmado_em.isoformat() if fator else None,
        "obrigatorio": obrigatorio(usuario),
        "codigos_restantes": codigos_restantes(usuario) if fator else 0,
        "motivos": motivos_para_ativar(usuario),
        "bloqueado": bloqueado(usuario),
    }


# --- o desafio do login ---------------------------------------------------------------
# A senha certa não dá sessão a quem tem (ou é obrigado a ter) segundo fator: dá
# este passe, assinado e de vida curta, para a segunda etapa. Ele diz quem é, se
# a sessão será "lembrada" e qual etapa falta — `codigo` (já tem o fator) ou
# `cadastro` (é obrigado e ainda não tem).
_SAL = "identity.segundo_fator.desafio"


def emitir_desafio(usuario, *, remember: bool, etapa: str) -> str:
    return signing.dumps(
        {"u": str(usuario.pk), "r": bool(remember), "e": etapa, "n": secrets.token_hex(8)},
        salt=_SAL,
    )


def abrir_desafio(texto: str, etapa: str):
    """`(usuario, remember, nonce)` ou `None` — vencido, adulterado, de outra
    etapa, já gasto ou de conta desativada, sem dizer qual."""
    from .models import Usuario

    try:
        carga = signing.loads(texto or "", salt=_SAL, max_age=SEGUNDO_FATOR_DESAFIO_VALIDADE_S)
    except signing.BadSignature:
        return None
    if carga.get("e") != etapa or cache.get(f"segundo_fator:desafio:{carga.get('n')}"):
        return None
    usuario = Usuario.objects.filter(pk=carga.get("u"), is_active=True).first()
    if usuario is None:
        return None
    return usuario, bool(carga.get("r")), carga.get("n")


def gastar_desafio(nonce: str) -> None:
    """Depois de abrir a sessão, o mesmo passe não abre outra."""
    cache.set(f"segundo_fator:desafio:{nonce}", 1, SEGUNDO_FATOR_DESAFIO_VALIDADE_S)
