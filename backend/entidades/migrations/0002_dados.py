"""Os dados que já existem ganham dono — docs/modulos/entidades.md §7.

1. Cada tenant ganha a **matriz** (nome do tenant, sem documento: a tela pede).
2. Empreendimento com CNPJ que não é o da matriz vira **entidade externa** dona
   dele — o caso da empreitada, em que a construtora executa no empreendimento
   de outro. Quem for SPE se reclassifica na tela. Se houver um cliente com o
   mesmo documento, a entidade aponta para ele.
3. Obras, títulos, transações, centros de custo, notas, boletos, carteiras,
   lotes e a integração fiscal recebem a entidade pela regra do §2 — que hoje,
   com a matriz como única entidade do grupo, dá a matriz para tudo.
4. Quem já usa o sistema recebe acesso à matriz e a todos os empreendimentos:
   ninguém perde o que via.

As tabelas têm RLS fail-closed; a passada liga o bypass só na transação dela,
como as demais migrations de dados do repositório. Inclui o que está na lixeira:
o NOT NULL da 0025 do ERP vale para a linha excluída também.
"""
from django.db import migrations


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true)")


def _digitos(valor):
    return "".join(ch for ch in (valor or "") if ch.isdigit())


ERP_COM_ENTIDADE = (
    "ContaPagar", "ContaReceber", "Transacao", "CentroCusto", "Boleto", "NotaFiscal",
    "NotaFiscalServico", "NotaFiscalProduto", "ContaCobrancaBancaria", "IntegracaoFiscal", "LoteRemessa",
)


def preencher(apps, schema_editor):
    _bypass(schema_editor)
    Tenant = apps.get_model("nucleo", "Tenant")
    Usuario = apps.get_model("nucleo", "Usuario")
    Entidade = apps.get_model("entidades", "Entidade")
    ConcessaoEntidade = apps.get_model("entidades", "ConcessaoEntidade")
    ConcessaoEmpreendimento = apps.get_model("entidades", "ConcessaoEmpreendimento")
    Empreendimento = apps.get_model("empreendimentos", "Empreendimento")
    Obra = apps.get_model("obras", "Obra")
    Cliente = apps.get_model("clientes", "Cliente")

    for tenant in Tenant.objects.all():
        matriz = (
            Entidade.objects.filter(tenant=tenant, externa=False, papel="matriz").order_by("pk").first()
            or Entidade.objects.create(tenant=tenant, nome=tenant.nome, papel="matriz")
        )
        doc_matriz = _digitos(matriz.documento)

        # 2. O dono externo de cada empreendimento com CNPJ de outro.
        clientes_por_doc = {}
        for cliente_id, doc in Cliente._base_manager.filter(tenant=tenant).values_list("pk", "cpf_cnpj"):
            clientes_por_doc.setdefault(_digitos(doc), cliente_id)
        for emp in Empreendimento._base_manager.filter(tenant=tenant, entidade_propria__isnull=True):
            doc = _digitos(emp.cnpj)
            if len(doc) not in (11, 14) or doc == doc_matriz:
                continue
            dona = Entidade.objects.filter(tenant=tenant, documento=doc).first()
            if dona is None:
                dona = Entidade.objects.create(
                    tenant=tenant, nome=emp.razao_social or emp.empreendimento, documento=doc,
                    tipo_pessoa="PF" if len(doc) == 11 else "PJ", papel="outra", externa=True,
                    cliente_id=clientes_por_doc.get(doc), endereco=emp.endereco or "",
                    cidade=emp.cidade or "", estado=emp.estado or "",
                )
            emp.entidade_propria_id = dona.pk
            emp.save(update_fields=["entidade_propria"])

        # 3. Tudo do grupo é da matriz (é a única entidade do grupo hoje).
        Obra._base_manager.filter(tenant=tenant, entidade__isnull=True).update(entidade=matriz)
        for nome in ERP_COM_ENTIDADE:
            modelo = apps.get_model("moduloerp", nome)
            modelo._base_manager.filter(tenant=tenant, entidade__isnull=True).update(entidade=matriz)

        # 4. Ninguém perde o que via.
        empreendimentos = list(Empreendimento._base_manager.filter(tenant=tenant).values_list("pk", flat=True))
        for usuario_id in Usuario.objects.filter(tenant=tenant).values_list("pk", flat=True):
            ConcessaoEntidade.objects.get_or_create(tenant=tenant, usuario_id=usuario_id, entidade=matriz)
            for emp_id in empreendimentos:
                ConcessaoEmpreendimento.objects.get_or_create(
                    tenant=tenant, usuario_id=usuario_id, empreendimento_id=emp_id,
                )


class Migration(migrations.Migration):

    dependencies = [
        ("entidades", "0001_initial"),
        ("moduloerp", "0024_entidades"),
        ("obras", "0007_obra_entidade"),
        ("empreendimentos", "0010_empreendimento_entidade_propria"),
        ("clientes", "0016_encargos_por_atraso"),
        ("nucleo", "0031_notificacao_nivel"),
    ]

    operations = [
        migrations.RunPython(preencher, migrations.RunPython.noop),
    ]
