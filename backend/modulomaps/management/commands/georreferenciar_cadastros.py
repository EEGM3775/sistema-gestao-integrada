# backend/modulomaps/management/commands/georreferenciar_cadastros.py
"""MAP.0 — dá coordenada ao que já existe.

O sistema rodou até aqui com `endereco` em texto livre em obra, empreendimento e
almoxarifado. Ligar o Maps sem este passo entregaria um mapa vazio para toda
empresa que já usa a plataforma — e o mapa vazio seria interpretado como "o
módulo não funciona", não como "ninguém cadastrou coordenada ainda".

**Idempotente e conservador:** roda quantas vezes for preciso, nunca sobrescreve
ponto `exata` (o que alguém arrastou à mão vale mais que qualquer provedor) e
não apaga endereço nenhum. `--dry-run` diz o que faria sem gravar — é o modo de
conferir antes num tenant grande.

    python manage.py georreferenciar_cadastros --dry-run
    python manage.py georreferenciar_cadastros --tenant <uuid> --tipo obra
"""
from __future__ import annotations

from django.apps import apps
from django.core.management.base import BaseCommand

from modulomaps.models import Local, Precisao
from modulomaps.services import VINCULOS, completar_localidade, geocodificar_local, sincronizar_local
from nucleo.tenancy import tenant_context


class Command(BaseCommand):
    help = "Cria o Local (e geocodifica) de obras, empreendimentos, fornecedores e almoxarifados."

    def add_arguments(self, parser):
        # O id do tenant é UUID: `type=int` recusava qualquer empresa real.
        parser.add_argument("--tenant", help="Só este tenant, pelo id (default: todos).")
        parser.add_argument(
            "--tipo", choices=sorted(VINCULOS), help="Só este tipo de vínculo (default: todos)."
        )
        parser.add_argument("--limite", type=int, default=0, help="Máximo de registros por tipo.")
        parser.add_argument(
            "--sem-rede", action="store_true",
            help="Só cria os Locais, sem chamar provedor externo (útil para conferir o mapeamento).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Não grava nada.")

    def handle(self, *args, **opcoes):
        Tenant = apps.get_model("nucleo", "Tenant")
        tenants = Tenant.objects.all()
        if opcoes.get("tenant"):
            tenants = tenants.filter(pk=opcoes["tenant"])

        tipos = [opcoes["tipo"]] if opcoes.get("tipo") else list(VINCULOS)
        total = {"criados": 0, "geocodificados": 0, "sem_coordenada": 0}

        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nTenant {tenant.pk} — {tenant}"))
            # `tenant_context` arma a RLS: sem ele, o comando roda fora de request
            # e a política fail-closed devolve zero linhas — o comando "passaria"
            # sem fazer nada. É a lição registrada no D8.
            with tenant_context(tenant.pk):
                for tipo in tipos:
                    total_tipo = self._processar(tenant, tipo, opcoes)
                    for chave, valor in total_tipo.items():
                        total[chave] += valor

        self.stdout.write(self.style.SUCCESS(
            f"\n{total['criados']} locais criados · {total['geocodificados']} geocodificados · "
            f"{total['sem_coordenada']} sem coordenada (entram na fila de decisão do mapa)."
        ))
        if opcoes.get("dry_run"):
            self.stdout.write(self.style.WARNING("--dry-run: nada foi gravado."))

    def _processar(self, tenant, tipo, opcoes) -> dict:
        modelo = apps.get_model(VINCULOS[tipo]["modelo"])
        registros = modelo.objects.filter(tenant_id=tenant.pk)
        if opcoes.get("limite"):
            registros = registros[: opcoes["limite"]]

        contagem = {"criados": 0, "geocodificados": 0, "sem_coordenada": 0}
        for registro in registros:
            ja_existe = Local.objects.filter(tenant_id=tenant.pk, **{tipo: registro}).exists()
            if opcoes.get("dry_run"):
                if not ja_existe:
                    contagem["criados"] += 1
                    self.stdout.write(f"  + {tipo}: {registro}")
                continue

            local = sincronizar_local(registro, tipo, tenant_id=tenant.pk)
            if not ja_existe:
                contagem["criados"] += 1
            if opcoes.get("sem_rede"):
                continue

            completar_localidade(local)
            if geocodificar_local(local):
                contagem["geocodificados"] += 1
                self.stdout.write(
                    f"  ✓ {local.nome} → {local.get_precisao_display()} ({local.get_fonte_display()})"
                )
            local.refresh_from_db()
            if local.precisao == Precisao.DESCONHECIDA:
                contagem["sem_coordenada"] += 1

        self.stdout.write(
            f"  {tipo}: {contagem['criados']} novos, {contagem['geocodificados']} com coordenada"
        )
        return contagem
