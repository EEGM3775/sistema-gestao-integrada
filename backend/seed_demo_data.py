"""Seed de dados de demonstração para o backend (tenant 'demo').

Cria itens de teste para exercitar o frontend:
  - Empreendimentos (2)
  - Obras (3, com etapas)
  - Clientes (4, com aquisições e contratos)
  - Funcionários/RH (3, com cargos)
  - Eventos de calendário (5)
  - Notificações (4)

Rodar (no container erp):
  docker compose exec -T erp python manage.py shell < backend/seed_demo_data.py

Ou a partir da raiz do projeto (PowerShell):
  Get-Content backend/seed_demo_data.py | docker compose exec -T erp python manage.py shell
"""
import datetime
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from nucleo.models import Tenant, Usuario, Notificacao
from nucleo.tenancy import rls_bypass, tenant_context
from empreendimentos.models import Empreendimento
from obras.models import Obra, EtapaObra
from clientes.models import Cliente, ClienteEmpreendimento, ContratoCliente
from rh.models import Cargo, Funcionario
from modulocalendar.models import CalendarEvent
from funcoeswhatsapp.models import CanalWhatsApp

# Canal WhatsApp de demonstração (Fase 11.3 / Fase C). Estas credenciais de dev
# são também usadas pelo E2E infra/gateway/phaseC_whatsapp_test.py para assinar o
# webhook (HMAC) e verificar o handshake. `access_token=''` → o cliente de saída
# ignora o envio (sem HTTP à Meta), então o fluxo roda sem credencial real.
WA_PHONE_NUMBER_ID = "DEMO-WA-PNID"
WA_APP_SECRET = "demo-wa-app-secret"
WA_VERIFY_TOKEN = "demo-wa-verify-token"

# ID determinístico do tenant 'demo' — DEVE bater com o da IAM (iam/seed_demo.py),
# porque nucleo.authentication._sync_tenant espelha o tenant da IAM POR ID. Num
# ambiente greenfield (staging/prod), um id diferente aqui faz o 1º login colidir em
# slug e responder 500. Mesmo uuid5(nome) dos dois lados → mesmo valor, sem duplicar literal.
DEMO_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "sgi.tenant.demo")

HOJE = datetime.date.today()
AMANHA = HOJE + datetime.timedelta(days=1)
SEMANA = HOJE + datetime.timedelta(days=7)
MES = HOJE + datetime.timedelta(days=30)


def _get_or_create_tenant():
    """Garante que o tenant 'demo' existe no backend (espelho local da IAM)."""
    tenant, created = Tenant.objects.get_or_create(
        slug="demo", defaults={"id": DEMO_TENANT_ID, "nome": "Empresa Demo"}
    )
    if created:
        print(f"  Tenant 'demo' criado no backend (id={tenant.id}).")
    return tenant


def _get_or_create_usuario(tenant, username):
    """Garante que o usuário existe no backend (espelho JIT)."""
    u, created = Usuario.objects.get_or_create(
        username=username,
        defaults={"email": f"{username}@demo.com", "tenant": tenant},
    )
    if created:
        print(f"  Usuário '{username}' criado no backend.")
    return u


def seed_empreendimentos(tenant):
    """Cria 2 empreendimentos de teste."""
    items = [
        {
            "empreendimento": "Residencial Vista Verde",
            "razao_social": "Vista Verde Construtora Ltda",
            "cnpj": "12345678000195",
            "telefone": "(75) 3621-0000",
            "endereco": "Av. Principal, 100 — Centro, Feira de Santana, BA",
            "data_inicio_prevista": HOJE - datetime.timedelta(days=180),
            "data_fim_prevista": MES + datetime.timedelta(days=180),
            "orcamento_total": Decimal("5000000.00"),
            "status_empreendimento": "em_execucao",
            "descricao": "Condomínio residencial com 3 torres e 72 unidades.",
        },
        {
            "empreendimento": "Comercial Centro Norte",
            "razao_social": "Centro Norte Empreendimentos Ltda",
            "cnpj": "98765432000198",
            "telefone": "(75) 3621-1111",
            "endereco": "Rod. BR-116, Km 12 — Feira de Santana, BA",
            "data_inicio_prevista": HOJE - datetime.timedelta(days=30),
            "data_fim_prevista": MES + datetime.timedelta(days=365),
            "orcamento_total": Decimal("8500000.00"),
            "status_empreendimento": "planejamento",
            "descricao": "Galeria comercial com 40 lojas e 2 pavimentos.",
        },
    ]
    criados = []
    for d in items:
        emp, created = Empreendimento.objects.get_or_create(
            tenant=tenant,
            razao_social=d["razao_social"],
            defaults=d,
        )
        if created:
            print(f"  Empreendimento criado: {emp.empreendimento}")
        criados.append(emp)
    return criados


def seed_obras(tenant, empreendimentos):
    """Cria 3 obras com etapas."""
    items = [
        {
            "empreendimento": empreendimentos[0],
            "nome_obra": "Torre A — Fundações",
            "endereco": "Av. Principal, 100 — Centro",
            "status_obra": "em_execucao",
            "data_inicio_prevista": HOJE - datetime.timedelta(days=90),
            "data_fim_prevista": MES,
            "orcamento_previsto": Decimal("1200000.00"),
            "descricao": "Fundações e estrutura do Torre A.",
            "etapas": [
                ("Escavação", 1, "concluida", Decimal("100.00")),
                ("Fundações", 2, "em_execucao", Decimal("65.00")),
                ("Estrutura", 3, "planejamento", Decimal("0.00")),
            ],
        },
        {
            "empreendimento": empreendimentos[0],
            "nome_obra": "Torre B — Alvenaria",
            "endereco": "Av. Principal, 100 — Centro",
            "status_obra": "planejamento",
            "data_inicio_prevista": MES,
            "data_fim_prevista": MES + datetime.timedelta(days=120),
            "orcamento_previsto": Decimal("980000.00"),
            "descricao": "Alvenaria e acabamento do Torre B.",
            "etapas": [
                ("Alvenaria", 1, "planejamento", Decimal("0.00")),
                ("Revestimento", 2, "planejamento", Decimal("0.00")),
                ("Pintura", 3, "planejamento", Decimal("0.00")),
            ],
        },
        {
            "empreendimento": empreendimentos[1],
            "nome_obra": "Galeria — Pavimento Inferior",
            "endereco": "Rod. BR-116, Km 12",
            "status_obra": "planejamento",
            "data_inicio_prevista": MES + datetime.timedelta(days=30),
            "data_fim_prevista": MES + datetime.timedelta(days=300),
            "orcamento_previsto": Decimal("3500000.00"),
            "descricao": "Construção do pavimento inferior da galeria comercial.",
            "etapas": [
                ("Terraplanagem", 1, "planejamento", Decimal("0.00")),
                ("Estrutura", 2, "planejamento", Decimal("0.00")),
                ("Impermeabilização", 3, "planejamento", Decimal("0.00")),
            ],
        },
    ]
    criados = []
    for d in items:
        etapas_data = d.pop("etapas")
        obra, created = Obra.objects.get_or_create(
            tenant=tenant,
            empreendimento=d["empreendimento"],
            nome_obra=d["nome_obra"],
            defaults=d,
        )
        if created:
            print(f"  Obra criada: {obra.nome_obra}")
        for nome, ordem, status, pct in etapas_data:
            etapa, ec = EtapaObra.objects.get_or_create(
                tenant=tenant,
                obra=obra,
                nome_etapa=nome,
                defaults={
                    "ordem": ordem,
                    "status_etapa": status,
                    "percentual_conclusao": pct,
                },
            )
            if ec:
                print(f"    Etapa criada: {etapa.nome_etapa} ({pct}%)")
        criados.append(obra)
    return criados


def seed_clientes(tenant, empreendimentos):
    """Cria 4 clientes com aquisições e contratos."""
    items = [
        {
            "nome_completo": "João da Silva Santos",
            "cpf_cnpj": "12345678909",
            "email": "joao.silva@example.com",
            "telefone": "(75) 99999-0001",
            "endereco": "Rua das Flores, 25",
            "cidade": "Feira de Santana",
            "estado": "BA",
            "data_nascimento": datetime.date(1985, 3, 15),
            "estado_civil": "casado",
            "profissao": "Engenheiro Civil",
        },
        {
            "nome_completo": "Maria Oliveira Souza",
            "cpf_cnpj": "98765432100",
            "email": "maria.oliveira@example.com",
            "telefone": "(75) 99999-0002",
            "endereco": "Av. Brasil, 500",
            "cidade": "Salvador",
            "estado": "BA",
            "data_nascimento": datetime.date(1990, 7, 22),
            "estado_civil": "solteiro",
            "profissao": "Advogada",
        },
        {
            "nome_completo": "Carlos Eduardo Pereira",
            "cpf_cnpj": "45678912364",
            "email": "carlos.pereira@example.com",
            "telefone": "(75) 99999-0003",
            "endereco": "Rua dos Coqueiros, 78",
            "cidade": "Feira de Santana",
            "estado": "BA",
            "data_nascimento": datetime.date(1978, 11, 30),
            "estado_civil": "casado",
            "profissao": "Médico",
        },
        {
            "nome_completo": "Ana Paula Ferreira",
            "cpf_cnpj": "32165498791",
            "email": "ana.ferreira@example.com",
            "telefone": "(75) 99999-0004",
            "endereco": "Alameda São João, 12",
            "cidade": "Feira de Santana",
            "estado": "BA",
            "data_nascimento": datetime.date(1992, 5, 10),
            "estado_civil": "uniao_estavel",
            "profissao": "Arquiteta",
        },
    ]
    criados = []
    for d in items:
        cli, created = Cliente.objects.get_or_create(
            tenant=tenant,
            cpf_cnpj=d["cpf_cnpj"],
            defaults=d,
        )
        if created:
            print(f"  Cliente criado: {cli.nome_completo}")
        criados.append(cli)

    # Aquisições (vincula clientes a empreendimentos)
    aquisicoes = [
        (criados[0], empreendimentos[0], "A-101", Decimal("350000.00"), "financiamento_bancario"),
        (criados[1], empreendimentos[0], "A-102", Decimal("355000.00"), "a_vista"),
        (criados[2], empreendimentos[1], "Loja-01", Decimal("850000.00"), "financiamento_direto"),
        (criados[3], empreendimentos[0], "B-201", Decimal("380000.00"), "financiamento_bancario"),
    ]
    for cli, emp, unidade, valor, cond in aquisicoes:
        aq, created = ClienteEmpreendimento.objects.get_or_create(
            tenant=tenant,
            empreendimento=emp,
            unidade_comprada=unidade,
            defaults={
                "cliente": cli,
                "endereco_unidade": f"{emp.endereco} — {unidade}",
                "data_compra": HOJE - datetime.timedelta(days=60),
                "valor_compra": valor,
                "condicoes_pagamento": cond,
            },
        )
        if created:
            print(f"  Aquisição criada: {cli.nome_completo} → {emp.empreendimento} ({unidade})")

    # Contratos
    for i, cli in enumerate(criados):
        emp = empreendimentos[i % len(empreendimentos)]
        contrato, created = ContratoCliente.objects.get_or_create(
            tenant=tenant,
            numero_contrato=f"CT-2026-{i+1:03d}",
            defaults={
                "cliente": cli,
                "empreendimento": emp,
                "data_assinatura": HOJE - datetime.timedelta(days=55),
                "objeto_contrato": f"Contrato de aquisição da unidade no empreendimento {emp.empreendimento}.",
                "status_contrato": "ativo",
            },
        )
        if created:
            print(f"  Contrato criado: {contrato.numero_contrato} — {cli.nome_completo}")

    return criados


def seed_funcionarios(tenant, empreendimentos):
    """Cria 3 funcionários com cargos."""
    cargos = [
        ("Engenheiro Civil", "Engenharia"),
        ("Mestre de Obras", "Obras"),
        ("Administrador", "Administrativo"),
    ]
    cargo_objs = []
    for nome, depto in cargos:
        c, created = Cargo.objects.get_or_create(
            tenant=tenant, nome_cargo=nome,
            defaults={"departamento": depto},
        )
        if created:
            print(f"  Cargo criado: {c.nome_cargo}")
        cargo_objs.append(c)

    funcionarios = [
        {
            "nome_completo": "Pedro Almeida Costa",
            "cpf": "11122233396",
            "data_nascimento": datetime.date(1980, 1, 20),
            "genero": "masculino",
            "endereco_completo": "Rua Engenheiro, 50 — Feira de Santana, BA",
            "data_admissao": HOJE - datetime.timedelta(days=365),
            "salario_base": Decimal("8500.00"),
            "status_contrato": "ativo",
            "cargo": cargo_objs[0],
            "empreendimento_vinculado": empreendimentos[0],
        },
        {
            "nome_completo": "Raimundo Nonato Silva",
            "cpf": "55566677720",
            "data_nascimento": datetime.date(1975, 6, 12),
            "genero": "masculino",
            "endereco_completo": "Rua do Trabalho, 200 — Feira de Santana, BA",
            "data_admissao": HOJE - datetime.timedelta(days=200),
            "salario_base": Decimal("4500.00"),
            "status_contrato": "ativo",
            "cargo": cargo_objs[1],
            "empreendimento_vinculado": empreendimentos[0],
        },
        {
            "nome_completo": "Cláudia Regina Mendes",
            "cpf": "99988877714",
            "data_nascimento": datetime.date(1988, 9, 5),
            "genero": "feminino",
            "endereco_completo": "Av. Administrativa, 10 — Feira de Santana, BA",
            "data_admissao": HOJE - datetime.timedelta(days=500),
            "salario_base": Decimal("6500.00"),
            "status_contrato": "ativo",
            "cargo": cargo_objs[2],
            "empreendimento_vinculado": empreendimentos[1],
        },
    ]
    criados = []
    for d in funcionarios:
        f, created = Funcionario.objects.get_or_create(
            tenant=tenant, cpf=d["cpf"], defaults=d,
        )
        if created:
            print(f"  Funcionário criado: {f.nome_completo}")
        criados.append(f)
    return criados


def seed_canal_whatsapp(tenant):
    """Provisiona o canal WhatsApp do tenant demo (resolução por phone_number_id)."""
    canal, created = CanalWhatsApp.objects.get_or_create(
        phone_number_id=WA_PHONE_NUMBER_ID,
        defaults={
            "tenant": tenant,
            "nome_exibicao": "Demo WhatsApp",
            "app_secret": WA_APP_SECRET,
            "verify_token": WA_VERIFY_TOKEN,
            "access_token": "",  # sem token → cliente de saída não faz HTTP à Meta
            "ativo": True,
        },
    )
    if created:
        print(f"  Canal WhatsApp criado: {canal.phone_number_id} (tenant {tenant.id})")
    return canal


def seed_calendario(tenant, usuario):
    """Cria 5 eventos de calendário."""
    agora = timezone.now()
    eventos = [
        {
            "title": "Reunião de alinhamento — Torre A",
            "description": "Reunião com equipe de obras para revisar progresso das fundações.",
            "start_time": agora + datetime.timedelta(hours=2),
            "end_time": agora + datetime.timedelta(hours=3),
            "event_type": "reuniao",
        },
        {
            "title": "Inspeção de qualidade — Torre B",
            "description": "Verificação de alvenaria e revestimento.",
            "start_time": agora + datetime.timedelta(days=2),
            "end_time": agora + datetime.timedelta(days=2, hours=2),
            "event_type": "tarefa",
        },
        {
            "title": "Vencimento de contrato — Cliente João",
            "description": "Prazo final para assinatura do contrato CT-2026-001.",
            "start_time": agora + datetime.timedelta(days=3),
            "end_time": agora + datetime.timedelta(days=3, hours=1),
            "event_type": "lembrete",
        },
        {
            "title": "Visita técnica — Galeria Centro Norte",
            "description": "Visita ao terreno para avaliação de terraplanagem.",
            "start_time": agora + datetime.timedelta(days=5),
            "end_time": agora + datetime.timedelta(days=5, hours=4),
            "event_type": "tarefa",
        },
        {
            "title": "Reunião mensal de diretoria",
            "description": "Revisão de andamento de todos os empreendimentos.",
            "start_time": agora + datetime.timedelta(weeks=1),
            "end_time": agora + datetime.timedelta(weeks=1, hours=2),
            "event_type": "reuniao",
        },
    ]
    for d in eventos:
        ev, created = CalendarEvent.objects.get_or_create(
            tenant=tenant,
            user=usuario,
            title=d["title"],
            start_time=d["start_time"],
            defaults=d,
        )
        if created:
            print(f"  Evento criado: {ev.title}")


def seed_notificacoes(tenant, usuario):
    """Cria 4 notificações (2 não-lidas, 2 lidas)."""
    agora = timezone.now()
    notifs = [
        {
            "titulo": "Nova tarefa atribuída",
            "mensagem": "Você tem uma nova tarefa: 'Inspeção de qualidade — Torre B'.",
            "tipo": "sistema",
            "url": "/app/calendario",
            "lida_em": None,
        },
        {
            "titulo": "Lembrete: Vencimento de contrato",
            "mensagem": "O contrato CT-2026-001 vence em 3 dias.",
            "tipo": "lembrete",
            "url": "/app/calendario",
            "lida_em": None,
        },
        {
            "titulo": "Obra atualizada",
            "mensagem": "A obra 'Torre A — Fundações' teve seu status atualizado para 'Em Execução'.",
            "tipo": "sistema",
            "url": "/app/obras",
            "lida_em": agora - datetime.timedelta(hours=5),
        },
        {
            "titulo": "Novo cliente cadastrado",
            "mensagem": "O cliente 'Ana Paula Ferreira' foi cadastrado no sistema.",
            "tipo": "sistema",
            "url": "/app/clientes",
            "lida_em": agora - datetime.timedelta(days=1),
        },
    ]
    for d in notifs:
        n, created = Notificacao.objects.get_or_create(
            tenant=tenant,
            user=usuario,
            titulo=d["titulo"],
            defaults=d,
        )
        if created:
            print(f"  Notificação criada: {n.titulo}")


# ─── Execução ────────────────────────────────────────────────────────────────

print("=" * 60)
print("SEED DE DADOS DE DEMONSTRAÇÃO — backend (tenant 'demo')")
print("=" * 60)

with rls_bypass():
    tenant = _get_or_create_tenant()
    usuario_demo = _get_or_create_usuario(tenant, "demo")

    print("\n→ Empreendimentos:")
    empreendimentos = seed_empreendimentos(tenant)

    print("\n→ Obras:")
    obras = seed_obras(tenant, empreendimentos)

    print("\n→ Clientes:")
    clientes = seed_clientes(tenant, empreendimentos)

    print("\n→ Funcionários:")
    funcionarios = seed_funcionarios(tenant, empreendimentos)

    print("\n→ Calendário:")
    seed_calendario(tenant, usuario_demo)

    print("\n→ Notificações:")
    seed_notificacoes(tenant, usuario_demo)

    print("\n→ Canal WhatsApp:")
    seed_canal_whatsapp(tenant)

    print("\n" + "=" * 60)
    print("SEED OK")
    print(f"  Empreendimentos: {Empreendimento.objects.count()}")
    print(f"  Obras: {Obra.objects.count()}")
    print(f"  Etapas: {EtapaObra.objects.count()}")
    print(f"  Clientes: {Cliente.objects.count()}")
    print(f"  Aquisições: {ClienteEmpreendimento.objects.count()}")
    print(f"  Contratos: {ContratoCliente.objects.count()}")
    print(f"  Funcionários: {Funcionario.objects.count()}")
    print(f"  Eventos: {CalendarEvent.objects.count()}")
    print(f"  Notificações: {Notificacao.objects.count()}")
    print("=" * 60)
