# backend/modulopdca/migrations/0023_rls_pdca8.py
"""RLS fail-closed nas quatro tabelas da PDCA.8.

As da PDCA.7 protegiam o que a empresa sabe sobre os próprios **defeitos**.
Estas protegem o que ela sabe sobre as **pessoas dela que se machucaram**, e é
a primeira vez que este módulo guarda dado de saúde — o que muda a natureza do
vazamento: não é mais informação comercial, é o art. 11 da LGPD.

- `ocorrencia` é o pior dos quatro. Carrega nome de quem se acidentou, parte do
  corpo, natureza da lesão, CID-10 e dias de afastamento. Lida de fora, é
  prontuário; e como traz obra, data e hora, ela reidentifica o titular mesmo
  sem o nome — numa obra de vinte pessoas, "fratura em 12/03 às 14h" é uma
  pessoa só. Escrita de fora, planta um acidente numa obra alheia, e o registro
  nasce com aparência de CAT — com um protocolo que ninguém protocolou.
- `anexoocorrencia` é o atestado médico e a foto da cena. O atestado é o mesmo
  dado do `ASOFuncionario` do RH, que já viaja sob `rh.dado_medico`; a foto da
  cena é a peça que a outra parte leva à perícia. A tabela guarda só o caminho,
  mas é por ele que a porta única decide o que entrega — um SELECT cruzado aqui
  é o primeiro passo para baixar o arquivo do vizinho.
- `dialogoseguranca` parece o mais inofensivo dos quatro e é o que mais se
  falsifica. É ele que prova que a obra fazia diálogo de segurança **antes** do
  acidente, e essa prova vale dinheiro numa ação regressiva do INSS. Um INSERT
  cruzado fabrica um histórico de prevenção que nunca existiu; um UPDATE apaga
  o que existia.
- `participantedds` é nome de trabalhador em lista assinada. Vale a mesma
  leitura que o `itemprogramacao` e o `planoacao` receberam: um INSERT cruzado
  põe uma pessoa real assumindo presença numa roda em que ela não esteve — e é
  exatamente essa lista que a fiscalização confere contra o efetivo do dia.

Helper repetido em vez de importado porque nome de módulo de migration começa
com dígito e não é importável; é o padrão do repo.
"""
from django.db import migrations

_TABLES = (
    "modulopdca_dialogoseguranca",
    "modulopdca_participantedds",
    "modulopdca_ocorrencia",
    "modulopdca_anexoocorrencia",
)
POLICY = "tenant_isolation"
USING_CLOSED = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)


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


class Migration(migrations.Migration):

    dependencies = [
        ("modulopdca", "0022_pdca8_ssma"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
