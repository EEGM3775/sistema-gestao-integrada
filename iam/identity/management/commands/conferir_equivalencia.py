"""Toda pessoa ativa, toda pergunta: o PDP responde o que as tabelas da IAM dizem?

    python manage.py conferir_equivalencia              # todas as empresas
    python manage.py conferir_equivalencia --tenant <id>
    python manage.py conferir_equivalencia --papeis-de-fabrica   # + empresa descartável

É a prova exaustiva da §10.12 — "zero divergência" medido pergunta por pergunta,
e não por amostragem do tráfego. A sombra do backend só confere as perguntas que
alguém fez; aqui entram todas (todo código do catálogo, todo módulo vendável,
admin e supervisor), para cada pessoa ativa, com consistência total. Foi com
ela que a fase 2 saiu no ambiente de desenvolvimento, onde não há duas semanas
de uso real para a sombra observar (decisão do dono, 25/09/2026).

Antes de conferir, reconcilia: o que se mede é a regra do schema, não o atraso
de uma escrita pendente. Sai com código 1 se houver qualquer divergência.

**`--papeis-de-fabrica`**: a base de desenvolvimento tem poucas pessoas, e elas
não portam todos os papéis. A opção cria uma empresa descartável que assina
metade dos módulos, com uma pessoa por papel de fábrica (`TEMPLATES_PAPEL`) —
liberada em todos os módulos e não liberada em nenhum — mais um admin, confere
todas e apaga a empresa ao fim (o sinal a tira do PDP), com ou sem falha.
"""
from __future__ import annotations

import json
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from identity import catalog, equivalencia, pdp
from identity.models import (
    AcessoUsuarioModulo,
    AssinaturaTenant,
    Modulo,
    Perfil,
    Permissao,
    Tenant,
    Usuario,
)


def criar_empresa_de_papeis() -> Tenant:
    """Uma pessoa por papel de fábrica, com e sem liberação de módulo."""
    sufixo = uuid.uuid4().hex[:8]
    with transaction.atomic():
        t = Tenant.objects.create(nome=f"Equivalência {sufixo}", slug=f"equivalencia-{sufixo}")
        modulos = list(Modulo.objects.order_by("codigo"))
        for m in modulos[::2]:  # metade assinada: o "usa" tem de negar a outra metade
            AssinaturaTenant.objects.create(tenant=t, modulo=m)
        Usuario.objects.create(username=f"eq-{sufixo}-admin", email=f"eq-{sufixo}-admin@x.invalid",
                               tenant=t, is_tenant_admin=True)
        for nome in catalog.TEMPLATES_PAPEL:
            papel = Perfil.objects.create(tenant=t, nome=nome)
            papel.permissoes.set([
                Permissao.objects.get_or_create(codename=c, defaults={"nome": c})[0]
                for c in catalog.codigos_do_template(nome)
            ])
            for liberado in (True, False):
                u = Usuario.objects.create(
                    username=f"eq-{sufixo}-{nome}-{'lib' if liberado else 'sem'}",
                    email=f"eq-{sufixo}-{nome}-{int(liberado)}@x.invalid", tenant=t,
                )
                u.perfis.set([papel])
                if liberado:
                    AcessoUsuarioModulo.objects.bulk_create(
                        [AcessoUsuarioModulo(usuario=u, modulo=m) for m in modulos]
                    )
    return t


class Command(BaseCommand):
    help = "Confere, para toda pessoa ativa, todas as perguntas de acesso: tabelas da IAM × PDP."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Só esta empresa (id).")
        parser.add_argument("--sem-reconciliar", action="store_true",
                            help="Mede o PDP como está, sem reconciliar antes.")
        parser.add_argument("--papeis-de-fabrica", action="store_true",
                            help="Inclui uma empresa descartável com uma pessoa por papel de fábrica.")

    def handle(self, *args, **opts):
        if not pdp.ativo():
            raise CommandError("SPICEDB_URL não configurada.")
        descartavel = criar_empresa_de_papeis() if opts["papeis_de_fabrica"] else None
        try:
            self._conferir(opts)
        finally:
            if descartavel is not None:
                with transaction.atomic():
                    Usuario.objects.filter(tenant=descartavel).delete()
                    descartavel.delete()

    def _conferir(self, opts):
        cli = pdp.cliente()
        if not opts["sem_reconciliar"]:
            pdp.garantir_esquema(cli)
            if opts["tenant"]:
                pdp.reconciliar_tenant(opts["tenant"], cli)
            else:
                pdp.reconciliar_tudo(cli)

        pessoas = Usuario.objects.filter(is_active=True, tenant__isnull=False).order_by("tenant_id", "username")
        if opts["tenant"]:
            pessoas = pessoas.filter(tenant_id=opts["tenant"])

        total_perguntas, divergentes = 0, {}
        empresas = set()
        for pessoa in pessoas:
            r = equivalencia.divergencias(cli, pessoa)
            total_perguntas += r.perguntas
            empresas.add(str(pessoa.tenant_id))
            if r.divergencias:
                divergentes[f"{pessoa.tenant_id}/{pessoa.username}"] = r.divergencias

        resumo = {
            "empresas": len(empresas),
            "pessoas": pessoas.count(),
            "perguntas": total_perguntas,
            "divergentes": divergentes,
        }
        self.stdout.write(json.dumps(resumo, ensure_ascii=False))
        if divergentes:
            raise CommandError(f"{len(divergentes)} pessoa(s) com divergência.")
        self.stdout.write(self.style.SUCCESS(
            f"Zero divergência: {resumo['pessoas']} pessoa(s) de {resumo['empresas']} empresa(s),"
            f" {total_perguntas} pergunta(s)."
        ))
