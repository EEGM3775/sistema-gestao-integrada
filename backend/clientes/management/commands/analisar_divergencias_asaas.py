"""
Auditoria de identidade banco × Asaas: aponta os clientes cujo cadastro
impediria ou desviaria uma cobrança (sem CPF/CNPJ válido, mesmo documento com
nome diferente no gateway, ou vínculo `id_cliente_gateway` apontando para outro
cadastro). Só leitura — não corrige nada.

Uso:
    manage.py analisar_divergencias_asaas                 # todos os tenants
    manage.py analisar_divergencias_asaas --tenant emp-a  # só um tenant
"""
from django.core.management.base import BaseCommand

from nucleo.tenancy import rls_bypass

from clientes.models import Cliente
from funcoescobrancas.client import AsaasAPIError
from funcoescobrancas.services import (
    analisar_divergencias_asaas,
    DIVERGENCIA_SEM_DOCUMENTO,
    DIVERGENCIA_NOME,
    DIVERGENCIA_VINCULO,
)

_ROTULO = {
    DIVERGENCIA_SEM_DOCUMENTO: 'SEM CPF/CNPJ VÁLIDO',
    DIVERGENCIA_NOME: 'NOME DIVERGENTE NO ASAAS',
    DIVERGENCIA_VINCULO: 'VÍNCULO APONTA P/ OUTRO CADASTRO',
}


class Command(BaseCommand):
    help = 'Analisa divergências de identidade entre os Clientes e os customers do Asaas (só leitura).'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', help='Slug do tenant a analisar (padrão: todos).')

    def handle(self, *args, **options):
        # Auditoria cross-tenant fora de request: sob a RLS fail-closed (S2) a
        # sessão nasce sem contexto e não enxergaria linha alguma. Este comando
        # de plataforma (só leitura) roda sob bypass explícito.
        with rls_bypass():
            qs = Cliente.objects.all().order_by('nome_completo')
            if options.get('tenant'):
                qs = qs.filter(tenant__slug=options['tenant'])

            try:
                relatorio = analisar_divergencias_asaas(qs)
            except AsaasAPIError as exc:
                self.stderr.write(self.style.ERROR(f'Falha ao consultar o Asaas: {exc}'))
                return

        total = relatorio['total_clientes']
        divergencias = relatorio['divergencias']
        self.stdout.write(f'Clientes analisados: {total}')

        if not divergencias:
            self.stdout.write(self.style.SUCCESS('Nenhuma divergência encontrada — banco e Asaas estão alinhados.'))
            return

        self.stdout.write(self.style.WARNING(f'{len(divergencias)} divergência(s) encontrada(s):\n'))
        for d in divergencias:
            rotulo = _ROTULO.get(d['tipo'], d['tipo'])
            self.stdout.write(self.style.WARNING(
                f"  • #{d['cliente_id']} {d['nome']} (doc {d['documento'] or '—'}) — {rotulo}"
            ))
            if d.get('nome_gateway'):
                self.stdout.write(f"      Asaas: \"{d['nome_gateway']}\" (customer {d.get('customer_id')})")
            self.stdout.write(f"      {d['detalhe']}")
