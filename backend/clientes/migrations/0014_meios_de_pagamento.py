"""A venda passa a ser uma lista livre de meios de pagamento.

Cria `MeioPagamento` (com RLS fail-closed, como toda tabela de negócio) e
converte cada aquisição gravada nos meios que o plano antigo descrevia — a
mesma conta que o motor fazia com os campos soltos:

- à vista → um meio "à vista" com o valor negociado;
- entrada → "entrada"; parcelas do saldo → "financiamento direto" com o saldo;
  balões → "anuais" com o total deles;
- no cartão, o valor que passou na maquininha era a "entrada" → "cartão";
- o que a condição quitava por fora (banco, permuta, "outro", o resto do
  cartão) → um meio com nome: "financiamento bancário", "permuta", "outro".
  Permuta e "outro" pedem descrição; a das observações da compra é aproveitada,
  e na falta dela o texto diz que o registro é anterior à lista de meios.

Os campos soltos só saem na migration seguinte: apagar coluna na mesma
transação em que se inseriu linha com FK para a tabela é o que o Postgres
recusa com "pending trigger events".
"""
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


_TABLES = ("clientes_meiopagamento",)
POLICY = "tenant_isolation"
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)
CENTAVO = Decimal("0.01")
SEM_DESCRICAO = "Não informado — registro anterior à lista de meios de pagamento."


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        for table in _TABLES:
            c.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            c.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
            c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            c.execute(
                f'CREATE POLICY {POLICY} ON "{table}" '
                f"USING ({USING_CLOSED}) WITH CHECK ({USING_CLOSED});"
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        for table in _TABLES:
            c.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            c.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
            c.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as c:
            c.execute("SELECT set_config('app.rls_bypass', 'on', true)")


def _meios_do_plano_antigo(a):
    """Os meios que os campos soltos descreviam, na ordem do carnê."""
    negociado = a.valor_compra or Decimal("0")
    if a.condicoes_pagamento == "a_vista":
        return [dict(
            tipo="a_vista", valor=negociado,
            primeiro_vencimento=a.entrada_primeiro_vencimento or a.data_compra,
        )]
    condicao = a.condicoes_pagamento
    meios = []
    entrada = a.entrada_valor or Decimal("0")
    baloes = ((a.balao_valor or Decimal("0")) * (a.balao_quantidade or 0)).quantize(CENTAVO)
    if condicao in ("permuta",):
        entrada = Decimal("0")
    if condicao in ("financiamento_bancario", "permuta", "cartao"):
        baloes = Decimal("0")
    if entrada > 0:
        meios.append(dict(
            tipo="cartao" if condicao == "cartao" else "entrada",
            valor=entrada, parcelas=1 if condicao == "cartao" else max(1, a.entrada_parcelas or 1),
            primeiro_vencimento=a.entrada_primeiro_vencimento,
        ))
    saldo = (negociado - entrada - baloes).quantize(CENTAVO)
    tem_parcelas = (a.num_parcelas or 0) > 0 and condicao in (
        "financiamento_direto", "outro", "",
    )
    if saldo > 0 and tem_parcelas:
        meios.append(dict(
            tipo="financiamento_direto", valor=saldo, parcelas=a.num_parcelas,
            juros_mensal=a.juros_mensal or Decimal("0"),
            sistema_amortizacao=a.sistema_amortizacao or "price",
            primeiro_vencimento=a.primeiro_vencimento,
        ))
        saldo = Decimal("0")
    if baloes > 0:
        meios.append(dict(
            tipo="anuais", valor=baloes, parcelas=a.balao_quantidade,
            periodicidade=a.balao_periodicidade or "anual",
            primeiro_vencimento=a.balao_primeiro_vencimento,
        ))
    if saldo > 0:
        # O que a condição quitava por fora — agora com nome.
        tipo = {"financiamento_bancario": "financiamento_bancario", "permuta": "permuta"}.get(
            condicao, "outro",
        )
        descricao = ""
        if tipo in ("permuta", "outro"):
            descricao = (a.observacoes_compra or "").strip() or SEM_DESCRICAO
        meios.append(dict(tipo=tipo, valor=saldo, descricao=descricao))
    return meios


#: Cópia congelada de `plano_pagamento.TIPOS_DE_MEIO[...].condicao` — migration
#: não importa código vivo, que pode mudar depois dela.
_CONDICAO_DO_TIPO = {
    "a_vista": "a_vista", "entrada": "financiamento_direto",
    "financiamento_direto": "financiamento_direto", "anuais": "financiamento_direto",
    "financiamento_bancario": "financiamento_bancario", "fgts": "financiamento_bancario",
    "permuta": "permuta", "cartao": "cartao", "outro": "outro",
}


def converter(apps, schema_editor):
    _bypass(schema_editor)
    Aquisicao = apps.get_model("clientes", "ClienteEmpreendimento")
    Meio = apps.get_model("clientes", "MeioPagamento")
    novos, recondicionadas = [], []
    for a in Aquisicao.objects.all().iterator():
        meios = _meios_do_plano_antigo(a)
        for ordem, dados in enumerate(meios, start=1):
            novos.append(Meio(tenant_id=a.tenant_id, aquisicao_id=a.pk, ordem=ordem, **dados))
        # A condição passa a ser derivada: a que responde pela maior parte do
        # valor (o empate fica com o primeiro meio). O cartão cujo resto era
        # "quitado fora" pode virar "outro" — que é o que o resto era.
        peso = {}
        for m in meios:
            condicao = _CONDICAO_DO_TIPO[m["tipo"]]
            peso[condicao] = peso.get(condicao, Decimal("0")) + m["valor"]
        principal = max(peso, key=lambda c: peso[c]) if peso else a.condicoes_pagamento
        if principal != a.condicoes_pagamento:
            a.condicoes_pagamento = principal
            recondicionadas.append(a)
    Meio.objects.bulk_create(novos, batch_size=1000)
    Aquisicao.objects.bulk_update(recondicionadas, ["condicoes_pagamento"], batch_size=1000)


def desconverter(apps, schema_editor):
    """Volta aos campos soltos o que eles comportam: a primeira entrada, o
    primeiro financiamento direto e as primeiras anuais. Meios que não cabem
    neles (banco, FGTS, permuta, outro) voltam a ser o resto "quitado fora"."""
    _bypass(schema_editor)
    Aquisicao = apps.get_model("clientes", "ClienteEmpreendimento")
    for a in Aquisicao.objects.all().iterator():
        meios = list(a.meios.order_by("ordem"))
        por_tipo = {}
        for m in meios:
            por_tipo.setdefault(m.tipo, m)
        if (e := por_tipo.get("entrada") or por_tipo.get("cartao") or por_tipo.get("a_vista")):
            a.entrada_valor, a.entrada_parcelas = e.valor, e.parcelas if e.tipo == "entrada" else 1
            a.entrada_primeiro_vencimento = e.primeiro_vencimento
        if (f := por_tipo.get("financiamento_direto")):
            a.num_parcelas, a.juros_mensal = f.parcelas, f.juros_mensal
            a.sistema_amortizacao, a.primeiro_vencimento = f.sistema_amortizacao, f.primeiro_vencimento
        if (b := por_tipo.get("anuais")) and b.parcelas:
            a.balao_quantidade, a.balao_periodicidade = b.parcelas, b.periodicidade
            a.balao_valor = (b.valor / b.parcelas).quantize(CENTAVO)
            a.balao_primeiro_vencimento = b.primeiro_vencimento
        a.save()


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0013_remove_cliente_cliente_cpf_cnpj_unico_por_tenant_and_more"),
        ("nucleo", "0027_autorizacao_pdp"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clienteempreendimento",
            name="valor_total_plano",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Soma dos títulos a receber da construtora. Maior que a parte dela quando há juros.",
                max_digits=15,
                verbose_name="Total do plano (desembolso)",
            ),
        ),
        migrations.CreateModel(
            name="MeioPagamento",
            fields=[
                (
                    "meio_pagamento_id",
                    models.AutoField(primary_key=True, serialize=False),
                ),
                (
                    "ordem",
                    models.PositiveSmallIntegerField(default=1, verbose_name="Ordem"),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("a_vista", "À vista"),
                            ("entrada", "Entrada / sinal (ATO)"),
                            (
                                "financiamento_direto",
                                "Financiamento direto (construtora)",
                            ),
                            ("anuais", "Parcelas anuais (intercaladas)"),
                            ("financiamento_bancario", "Financiamento bancário"),
                            ("fgts", "FGTS"),
                            ("permuta", "Permuta"),
                            ("cartao", "Cartão de crédito/débito"),
                            ("outro", "Outro"),
                        ],
                        max_length=30,
                        verbose_name="Forma de pagamento",
                    ),
                ),
                (
                    "valor",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="O principal que este meio quita, sem juros.",
                        max_digits=15,
                        verbose_name="Valor (R$)",
                    ),
                ),
                (
                    "descricao",
                    models.TextField(blank=True, default="", verbose_name="Descrição"),
                ),
                (
                    "parcelas",
                    models.PositiveSmallIntegerField(
                        default=1, verbose_name="Parcelas"
                    ),
                ),
                (
                    "primeiro_vencimento",
                    models.DateField(
                        blank=True, null=True, verbose_name="1º vencimento"
                    ),
                ),
                (
                    "juros_mensal",
                    models.DecimalField(
                        decimal_places=4,
                        default=Decimal("0"),
                        help_text="Financiamento direto, e a entrada parcelada quando o contrato cobra.",
                        max_digits=6,
                        verbose_name="Juros (% ao mês)",
                    ),
                ),
                (
                    "sistema_amortizacao",
                    models.CharField(
                        choices=[
                            ("price", "Price — parcela fixa"),
                            ("sac", "SAC — amortização constante, parcela decrescente"),
                        ],
                        default="price",
                        max_length=10,
                        verbose_name="Sistema de amortização",
                    ),
                ),
                (
                    "periodicidade",
                    models.CharField(
                        choices=[("anual", "Anual"), ("semestral", "Semestral")],
                        default="anual",
                        max_length=10,
                        verbose_name="Periodicidade (anuais)",
                    ),
                ),
                (
                    "aquisicao",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meios",
                        to="clientes.clienteempreendimento",
                        verbose_name="Aquisição",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="nucleo.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Meio de pagamento",
                "verbose_name_plural": "Meios de pagamento",
                "ordering": ["aquisicao_id", "ordem", "meio_pagamento_id"],
            },
        ),
        migrations.RunPython(enable_rls, disable_rls),
        migrations.RunPython(converter, desconverter),
    ]
