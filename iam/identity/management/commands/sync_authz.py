"""Sincroniza o catálogo de permissões (código) para o banco da IAM e, opcionalmente,
aplica os templates de papel de fábrica a um ou todos os tenants (Fase 9, fatia A).

  # só o catálogo global (idempotente):
  python manage.py sync_authz
  # catálogo + papéis de fábrica no tenant 'demo':
  python manage.py sync_authz --tenant demo
  # em todos os tenants:
  python manage.py sync_authz --all-tenants
  # realinhamento destrutivo (regrava os papéis de fábrica exatamente ao modelo):
  python manage.py sync_authz --all-tenants --reset
  # remove Permissao órfã (fora do catálogo) além de sincronizar:
  python manage.py sync_authz --prune

O catálogo é a fonte única (identity/catalog.py); este comando reflete-o na
tabela `Permissao` e compõe cada `Perfil`-template com suas permissões. Falha-alto
se algum template referenciar código fora do catálogo (guarda de conformidade).

**Aditivo por padrão (seguro para rodar no deploy):** ao sincronizar um papel de
fábrica que já existe, o comando **soma** as permissões do modelo — nunca remove o
que o admin do tenant ajustou à mão (`/app/admin/papeis`). É idempotente: rodar
N vezes converge o papel para "pelo menos o modelo". Use `--reset` só quando quiser
**realinhar** um papel de fábrica exatamente ao modelo (regrava, apagando ajustes).
Papéis criados/clonados pelo tenant nunca são tocados (só os nomes de fábrica).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from identity import catalog
from identity.models import Permissao, Perfil, Tenant


class Command(BaseCommand):
    help = "Sincroniza o catálogo de permissões e os templates de papel de fábrica."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Slug de um tenant p/ aplicar os templates de papel.")
        parser.add_argument("--all-tenants", action="store_true", help="Aplica os templates a todos os tenants.")
        parser.add_argument("--prune", action="store_true", help="Remove Permissao fora do catálogo.")
        parser.add_argument(
            "--reset", action="store_true",
            help="Realinhamento destrutivo: regrava os papéis de fábrica ao modelo "
                 "(apaga ajustes manuais). Sem o flag, a aplicação é ADITIVA.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        problemas = catalog.templates_invalidos()
        if problemas:
            raise CommandError(f"Templates com código fora do catálogo: {problemas}")

        criadas, atualizadas = self._sync_permissoes()
        self.stdout.write(f"Permissões: {criadas} criadas, {atualizadas} atualizadas ({len(catalog.CATALOGO)} no catálogo).")

        if opts["prune"]:
            orfas = Permissao.objects.exclude(codename__in=catalog.CODIGOS)
            n, _ = orfas.delete()
            self.stdout.write(f"Prune: {n} permissões órfãs removidas.")

        tenants = self._tenants_alvo(opts)
        modo = "reset (regrava)" if opts["reset"] else "aditivo (soma)"
        for t in tenants:
            n = self._aplicar_templates(t, reset=opts["reset"])
            self.stdout.write(f"Tenant '{t.slug}': {n} papéis de fábrica sincronizados [{modo}].")
        self.stdout.write(self.style.SUCCESS("sync_authz OK."))

    def _sync_permissoes(self) -> tuple[int, int]:
        criadas = atualizadas = 0
        for p in catalog.CATALOGO:
            obj, created = Permissao.objects.update_or_create(
                codename=p.code, defaults={"nome": p.nome}
            )
            criadas += int(created)
            atualizadas += int(not created)
        return criadas, atualizadas

    def _tenants_alvo(self, opts) -> list[Tenant]:
        if opts["all_tenants"]:
            return list(Tenant.objects.all())
        if opts["tenant"]:
            try:
                return [Tenant.objects.get(slug=opts["tenant"])]
            except Tenant.DoesNotExist:
                raise CommandError(f"Tenant '{opts['tenant']}' não existe.")
        return []

    def _aplicar_templates(self, tenant: Tenant, *, reset: bool = False) -> int:
        """Cria/atualiza um Perfil por template de fábrica, compondo suas permissões.
        Não sobrescreve papéis que o tenant tenha criado à mão (só os de fábrica).

        Papel **novo** → recebe exatamente o modelo. Papel de fábrica **já
        existente** → por padrão **soma** as permissões do modelo (aditivo, nunca
        remove ajuste manual do admin); com ``reset=True``, **regrava** ao modelo
        (destrutivo, para realinhar de propósito)."""
        por_codigo = {p.codename: p for p in Permissao.objects.filter(codename__in=catalog.CODIGOS)}
        n = 0
        for nome in catalog.TEMPLATES_PAPEL:
            descricao = catalog.DESCRICOES_TEMPLATE.get(nome, "")
            perfil, criado = Perfil.objects.get_or_create(
                tenant=tenant, nome=nome, defaults={"descricao": descricao}
            )
            # Mantém a descrição de fábrica em dia (mesmo em papel já existente),
            # sem sobrescrever se o admin tiver personalizado para algo não-vazio.
            if not criado and perfil.descricao in ("", "Papel de fábrica (Fase 9).", None):
                perfil.descricao = descricao
                perfil.save(update_fields=["descricao"])
            perms = [por_codigo[c] for c in catalog.codigos_do_template(nome)]
            if criado or reset:
                perfil.permissoes.set(perms)      # papel novo, ou realinhamento explícito
            else:
                perfil.permissoes.add(*perms)     # aditivo: preserva ajustes do admin
            n += 1
        return n
