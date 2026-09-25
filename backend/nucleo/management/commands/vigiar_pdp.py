"""O invalidador — lê o Watch do SpiceDB e aposenta a decisão cacheada (fase 3).

    python manage.py vigiar_pdp     # o processo `pdp-invalidador` do compose

docs/acesso-e-permissoes.md §10.8: "um processo consome o Watch do SpiceDB e, a
cada relação alterada, sobe a versão do usuário (ou do objeto) afetado". A
versão entra na chave do cache (`funcoesautorizacao/chaves.py`), então a
decisão antiga simplesmente deixa de ser lida.

**O que sobe, para cada relação que mudou:**

- sujeito é uma pessoa (`membro`, `administrador`, `portador`, `liberado`…) →
  a versão **daquela pessoa** naquela empresa;
- o resto (o papel passou a conceder outro código, a assinatura venceu) →
  a versão **da empresa** inteira;
- o supervisor da plataforma → a versão **global**.

A IAM já sobe a versão da empresa ao gravar; o Watch é a segunda garantia —
cobre escrita que não passou pela IAM e a anotação que falhou por Redis fora.

**O cursor é gravado no Redis a cada lote**, e a volta retoma de onde parou —
de uma queda de conexão, de um reinício do processo, do silêncio de um dia sem
troca de papel. Os eventos do intervalo são lidos na volta, então nada é
perdido. **Só quando o cursor se perde** (primeira subida, ou o SpiceDB o recusa
por velho) o vigia sobe a versão global: aí o intervalo não tem evento para ser
lido, e aposentar o cache inteiro é o único jeito de não servir o que foi
revogado nele.
"""
from __future__ import annotations

import signal
import time

from django.core.management.base import BaseCommand, CommandError

from funcoesautorizacao import chaves
from funcoesautorizacao.cliente import ErroDoPdp, PerguntaInvalida
from funcoesautorizacao.esquema import tenant_do_id
from nucleo import autorizacao_pdp

# O Watch fica aberto indefinidamente; o SpiceDB manda batimento a cada
# segundo. Sem nada em 60 s, a conexão está morta — reabre. Não é teto (§5.6).
_SILENCIO_MAXIMO_S = 60
_ESPERA_AO_RECONECTAR_S = 2


def versoes_a_subir(operacoes) -> set[str]:
    """As chaves de versão que um lote de mudanças aposenta."""
    alvo: set[str] = set()
    for _operacao, rel in operacoes:
        if rel.tipo == "plataforma":
            alvo.add(chaves.VERSAO_GLOBAL)
            continue
        tenant = tenant_do_id(rel.id)
        if rel.sujeito_tipo == "usuario":
            alvo.add(chaves.versao_do_usuario(tenant, rel.sujeito_id))
        else:
            alvo.add(chaves.versao_do_tenant(tenant))
    return alvo


class Command(BaseCommand):
    help = "Consome o Watch do SpiceDB e invalida o cache de decisão (remodelagem, fase 3)."

    def handle(self, *args, **opts):
        from django.conf import settings

        if not settings.SPICEDB_URL:
            raise CommandError("SPICEDB_URL não configurada.")
        parar = {"agora": False}
        signal.signal(signal.SIGTERM, lambda *_: parar.update(agora=True))

        while not parar["agora"]:
            r = autorizacao_pdp.redis()
            if r is None:
                time.sleep(_ESPERA_AO_RECONECTAR_S)
                continue
            try:
                cursor = r.get(chaves.CURSOR_DO_WATCH)
                if not cursor:
                    # Sem cursor não se sabe o que mudou antes: aposenta tudo e
                    # passa a ouvir do agora que o próprio PDP informa.
                    cursor = autorizacao_pdp.cliente().revisao_atual()
                    r.set(chaves.CURSOR_DO_WATCH, cursor)
                    r.incr(chaves.VERSAO_GLOBAL)
                    self.stdout.write("vigia: sem cursor — cache inteiro aposentado")
                self._ouvir(r, cursor, parar)
                # Voltou sem erro: foi só silêncio. Reabre do cursor salvo.
                continue
            except PerguntaInvalida as exc:
                # Cursor velho demais para o SpiceDB: recomeça do agora.
                self.stderr.write(f"vigia: cursor recusado ({exc}); recomeçando")
                r.delete(chaves.CURSOR_DO_WATCH)
            except ErroDoPdp as exc:
                self.stderr.write(f"vigia: PDP fora ({exc}); reconectando do cursor")
            except Exception as exc:  # noqa: BLE001 - o vigia não morre
                self.stderr.write(f"vigia: falhou ({exc}); reconectando")
                autorizacao_pdp.redis_caiu()
            time.sleep(_ESPERA_AO_RECONECTAR_S)

    def _ouvir(self, r, cursor, parar):
        r.set(chaves.WATCH_VIVO, int(time.time()))
        for operacoes, novo_cursor in autorizacao_pdp.cliente().vigiar(
            cursor, timeout_s=_SILENCIO_MAXIMO_S
        ):
            if operacoes:
                alvo = versoes_a_subir(operacoes)
                pipe = r.pipeline()
                for chave in alvo:
                    pipe.incr(chave)
                # A classe B passa a esperar pelo menos esta mudança.
                for tenant in {tenant_do_id(rel.id) for _, rel in operacoes if rel.tipo != "plataforma"}:
                    pipe.set(chaves.zedtoken_do_tenant(tenant), novo_cursor)
                pipe.execute()
            if novo_cursor:
                r.set(chaves.CURSOR_DO_WATCH, novo_cursor)
            r.set(chaves.WATCH_VIVO, int(time.time()))
            if parar["agora"]:
                return
