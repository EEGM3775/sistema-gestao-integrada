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
from fornecedores.models import Fornecedor
from catalogo.models import Item as ScmProduto
from moduloscm.models import (
    CentroCusto as ScmCentroCusto,
    OfertaFornecedor,
    Demanda,
    ItemDemanda,
    Cotacao,
    Proposta,
    ItemProposta,
    PedidoCompra,
    ItemPedido,
    Recebimento,
    AvaliacaoFornecedor,
)
from modulosil import services as sil_services
from modulosil.models import (
    LocalEstoque,
    SaldoEstoque,
    MovimentacaoEstoque,
    Requisicao,
    ItemRequisicao,
    Inventario,
    ItemInventario,
    EntregaEPI,
    Ferramenta,
    EmprestimoFerramenta,
)

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


def seed_scm(tenant, obras):
    """Suprimentos (SCM): fornecedores, catálogo, uma cotação aberta com 3
    propostas (o mapa comparativo), pedidos com recebimentos e avaliações."""
    D = Decimal

    # Fornecedores (a FK de ofertas/propostas/pedidos/avaliações).
    forn_defs = [
        ("Aço Forte Distribuidora", "10000000000101"),
        ("Casa do Construtor", "10000000000102"),
        ("Depósito União", "10000000000103"),
        ("Cimento Sul", "10000000000104"),
        ("Madeireira Central", "10000000000105"),
        ("Britagem Central", "10000000000106"),
    ]
    forn = {}
    for razao, cnpj in forn_defs:
        f, created = Fornecedor.objects.get_or_create(
            tenant=tenant, razao_social=razao,
            defaults={"cnpj": cnpj, "email": f"contato@{razao.split()[0].lower()}.com.br"},
        )
        forn[razao] = f
        if created:
            print(f"  Fornecedor: {razao}")

    # Centros de custo (vinculados a obras quando possível).
    cc_est, _ = ScmCentroCusto.objects.get_or_create(
        tenant=tenant, codigo="CC-AUR-EST",
        defaults={"nome": "Estrutura — Residencial Aurora", "tipo": "obra", "obra": obras[0] if obras else None},
    )
    cc_acab, _ = ScmCentroCusto.objects.get_or_create(
        tenant=tenant, codigo="CC-HRZ-ACAB",
        defaults={"nome": "Acabamento — Edifício Horizonte", "tipo": "obra", "obra": obras[1] if len(obras) > 1 else None},
    )

    # Produtos (catálogo mestre, supplier-agnostic).
    prod_defs = [
        ("AC-125", "Aço CA-50 12,5mm", "barra", "material", "Aços"),
        ("CM-32", "Cimento CP-II-E-32 50kg", "saco", "material", "Aglomerantes"),
        ("AR-18", "Arame recozido nº 18", "kg", "material", "Ferragens"),
        ("BR-01", "Brita nº 1", "m³", "material", "Agregados"),
        ("CU-25", "Concreto usinado FCK-25", "m³", "material", "Concreto"),
        ("SV-IMP", "Impermeabilização (serviço)", "m²", "servico", "Serviços"),
    ]
    prod = {}
    for cod, desc, un, tipo, cat in prod_defs:
        p, _ = ScmProduto.objects.get_or_create(
            tenant=tenant, codigo_interno=cod,
            defaults={
                "descricao": desc, "unidade": un, "tipo": tipo, "categoria": cat,
                "estocavel": tipo == "material", "consumivel": tipo == "material",
            },
        )
        prod[cod] = p

    # Ofertas (preço/estoque por fornecedor; algumas p/ compra direta e na rede).
    oferta_defs = [
        # produto, fornecedor, preco, estoque, compra_direta, visibilidade
        ("AC-125", "Depósito União", "52.40", "3200", True, "rede"),
        ("AC-125", "Aço Forte Distribuidora", "53.90", "5000", True, "rede"),
        ("AC-125", "Casa do Construtor", "55.20", "1800", False, "privada"),
        ("CM-32", "Cimento Sul", "34.50", "1240", True, "rede"),
        ("CM-32", "Casa do Construtor", "32.80", "600", True, "privada"),
        ("AR-18", "Depósito União", "13.20", "480", True, "privada"),
        ("BR-01", "Britagem Central", "118.00", "90", True, "privada"),
        ("CU-25", "Cimento Sul", "398.00", "0", False, "privada"),
        ("SV-IMP", "Casa do Construtor", "46.00", "0", False, "privada"),
    ]
    for cod, razao, preco, est, direta, vis in oferta_defs:
        OfertaFornecedor.objects.get_or_create(
            tenant=tenant, produto=prod[cod], fornecedor=forn[razao],
            defaults={
                "preco_direto": D(preco), "estoque_disponivel": D(est),
                "compra_direta": direta, "visibilidade": vis, "ativo": True,
            },
        )

    # Avaliações (reputação → estrelas do mapa + KPI). Uma vez só.
    aval_defs = [
        ("Aço Forte Distribuidora", 5, 5, 5, "Entrega pontual, produto conforme."),
        ("Casa do Construtor", 4, 5, 4, "Prazo excelente."),
        ("Depósito União", 4, 4, 3, "Preço bom, atendimento pode melhorar."),
        ("Cimento Sul", 5, 4, 5, "Fornecedor de confiança."),
    ]
    for razao, q, pt, at, com in aval_defs:
        AvaliacaoFornecedor.objects.get_or_create(
            tenant=tenant, fornecedor=forn[razao], comentario=com,
            defaults={"nota_qualidade": q, "nota_pontualidade": pt, "nota_atendimento": at},
        )

    # Fluxo transacional rico — idempotente pela demanda-marca (3º pavimento).
    if not Demanda.objects.filter(tenant=tenant, observacao__icontains="3º pavimento").exists():
        demanda = Demanda.objects.create(
            tenant=tenant, tipo="material", status="em_cotacao", origem="manual",
            centro_custo=cc_est, categoria="Estrutura", observacao="Estrutura do 3º pavimento — Residencial Aurora.",
        )
        it_aco = ItemDemanda.objects.create(tenant=tenant, demanda=demanda, produto=prod["AC-125"], quantidade=D("2400"), unidade="barra")
        it_cim = ItemDemanda.objects.create(tenant=tenant, demanda=demanda, produto=prod["CM-32"], quantidade=D("800"), unidade="saco")
        it_ara = ItemDemanda.objects.create(tenant=tenant, demanda=demanda, produto=prod["AR-18"], quantidade=D("120"), unidade="kg")

        cot = Cotacao.objects.create(
            tenant=tenant, demanda=demanda, status="aberta", data_limite=HOJE + datetime.timedelta(days=2),
        )
        # (fornecedor, [preço aço, preço cimento, preço arame], total, prazo)
        prop_defs = [
            ("Aço Forte Distribuidora", ["53.90", "34.50", "13.20"], "158544.00", 5),
            ("Casa do Construtor", ["55.20", "32.80", "12.90"], "160268.00", 3),
            ("Depósito União", ["52.40", "35.90", "13.50"], "156100.00", 8),
        ]
        for razao, (pa, pc, par), total, prazo in prop_defs:
            prop = Proposta.objects.create(
                tenant=tenant, cotacao=cot, fornecedor=forn[razao],
                valor_total=D(total), prazo_entrega_dias=prazo, status="recebida",
            )
            for item, preco in ((it_aco, pa), (it_cim, pc), (it_ara, par)):
                ItemProposta.objects.create(
                    tenant=tenant, proposta=prop, item_demanda=item,
                    preco_unitario=D(preco), quantidade=item.quantidade,
                )
        print(f"  Demanda #{demanda.demanda_id} + cotação #{cot.cotacao_id} (3 propostas)")

        # Pedidos com recebimentos (para as telas de Pedidos ficarem cheias).
        p1 = PedidoCompra.objects.create(
            tenant=tenant, origem="compra_direta", fornecedor=forn["Depósito União"], centro_custo=cc_est,
            status="recebido_parcial", valor_total=D("1584.00"), data_pedido=HOJE - datetime.timedelta(days=3),
        )
        ItemPedido.objects.create(tenant=tenant, pedido=p1, produto=prod["AR-18"], quantidade=D("120"), preco_unitario=D("13.20"))
        Recebimento.objects.create(tenant=tenant, pedido=p1, tipo="parcial", nota_fiscal_ref="000.114.208")

        p2 = PedidoCompra.objects.create(
            tenant=tenant, origem="cotacao", fornecedor=forn["Cimento Sul"], centro_custo=cc_est,
            status="recebido_total", valor_total=D("27600.00"), data_pedido=HOJE - datetime.timedelta(days=6),
        )
        ItemPedido.objects.create(tenant=tenant, pedido=p2, produto=prod["CM-32"], quantidade=D("800"), preco_unitario=D("34.50"))
        Recebimento.objects.create(tenant=tenant, pedido=p2, tipo="total", nota_fiscal_ref="000.118.771")
        AvaliacaoFornecedor.objects.get_or_create(
            tenant=tenant, fornecedor=forn["Cimento Sul"], pedido=p2,
            defaults={"nota_qualidade": 5, "nota_pontualidade": 5, "nota_atendimento": 4, "comentario": "Recebimento total no prazo."},
        )

        p3 = PedidoCompra.objects.create(
            tenant=tenant, origem="manual", fornecedor=forn["Britagem Central"], centro_custo=cc_est,
            status="aprovado", valor_total=D("14160.00"), data_pedido=HOJE - datetime.timedelta(days=1),
        )
        ItemPedido.objects.create(tenant=tenant, pedido=p3, produto=prod["BR-01"], quantidade=D("120"), preco_unitario=D("118.00"))
        print(f"  Pedidos: #{p1.pedido_id} (direta), #{p2.pedido_id} (cotação), #{p3.pedido_id} (manual)")


def seed_sil(tenant, obras, usuario):
    """Estoque & Logística (SIL): almoxarifado central + canteiro, saldos honestos
    construídos pelo **ledger** (via services → custo médio real), um item abaixo do
    mínimo (fila do cockpit), uma requisição pendente e um inventário aberto.

    Fecha o laço com o SCM na tela: o que entra por Recebimento vira ENTRADA aqui;
    o que cai abaixo do mínimo vira Demanda lá."""
    D = Decimal

    # Itens estocáveis do catálogo-mestre (promovidos do SCM). Re-consultados por
    # código p/ desacoplar do seed_scm (funciona mesmo rodando isolado depois dele).
    itens = {i.codigo_interno: i for i in ScmProduto.objects.filter(
        tenant=tenant, codigo_interno__in=["AC-125", "CM-32", "AR-18", "BR-01"]
    )}
    if not itens:
        print("  (SIL) sem itens estocáveis no catálogo — rode o seed do SCM antes.")
        return

    # Locais: almoxarifado central + canteiro vinculado à 1ª obra.
    central, _ = LocalEstoque.objects.get_or_create(
        tenant=tenant, nome="Almoxarifado Central",
        defaults={"tipo": LocalEstoque.Tipo.CENTRAL, "endereco": "Sede — Feira de Santana, BA"},
    )
    canteiro, _ = LocalEstoque.objects.get_or_create(
        tenant=tenant, nome="Canteiro — Torre A",
        defaults={"tipo": LocalEstoque.Tipo.CANTEIRO, "obra": obras[0] if obras else None},
    )

    # Ledger não é idempotente (toda entrada soma) — guarda o abastecimento inteiro.
    if not MovimentacaoEstoque.objects.filter(tenant=tenant).exists():
        # Entradas iniciais (custo médio nasce daqui). AR-18 entra abaixo do mínimo.
        estoque_inicial = [
            (central, "AC-125", "2400", "52.40"),
            (central, "CM-32", "800", "34.50"),
            (central, "AR-18", "40", "13.20"),
            (central, "BR-01", "90", "118.00"),
            (canteiro, "CM-32", "50", "34.50"),
        ]
        for local, cod, qtd, custo in estoque_inicial:
            item = itens.get(cod)
            if item is None:
                continue
            sil_services.aplicar_entrada(
                tenant.id, item.item_id, local.local_id, D(qtd), D(custo),
                usuario=usuario if getattr(usuario, "pk", None) else None,
                observacao="Estoque inicial (seed de demonstração).",
            )

        # Ponto de reposição: AR-18 fica abaixo do mínimo → entra na fila de decisão.
        SaldoEstoque.objects.filter(
            tenant=tenant, item=itens["AR-18"], local=central
        ).update(ponto_reposicao=D("120"))

        # Requisição pendente (fila "a aprovar"): a Torre A pede cimento do central.
        req = Requisicao.objects.create(
            tenant=tenant, local=central, obra=obras[0] if obras else None,
            solicitante=usuario if getattr(usuario, "pk", None) else None,
            status=Requisicao.Status.PENDENTE,
            observacao="Cimento para a laje do 3º pavimento — Torre A.",
        )
        ItemRequisicao.objects.create(tenant=tenant, requisicao=req, item=itens["CM-32"], quantidade=D("120"))

        # Inventário aberto (fila "inventários abertos"): contagem cíclica do arame.
        inv = Inventario.objects.create(
            tenant=tenant, local=central, tipo=Inventario.Tipo.CICLICA,
            status=Inventario.Status.ABERTO,
            usuario=usuario if getattr(usuario, "pk", None) else None,
        )
        saldo_ar = SaldoEstoque.objects.get(tenant=tenant, item=itens["AR-18"], local=central)
        ItemInventario.objects.create(
            tenant=tenant, inventario=inv, item=itens["AR-18"],
            quantidade_sistema=saldo_ar.quantidade, quantidade_contada=D("38"),
        )
        print(f"  Locais: {central.nome}, {canteiro.nome} · entradas: {len(estoque_inicial)} · 1 requisição, 1 inventário aberto")

    # Consumo aplicado à obra E etapa (físico-financeiro → aba Gestão). Guard próprio
    # (por movimento com etapa) p/ semear mesmo em banco já com ledger. Simula material
    # já aplicado na Torre A: aço nas Fundações, cimento na concretagem.
    if not MovimentacaoEstoque.objects.filter(tenant=tenant, etapa__isnull=False).exists():
        etapas = list(EtapaObra.objects.filter(obra=obras[0]).order_by("ordem")) if obras else []
        et_fund = etapas[1] if len(etapas) > 1 else (etapas[0] if etapas else None)
        for cod, quant, obs in (("AC-125", "600", "armadura das fundações"), ("CM-32", "200", "concretagem")):
            item = itens.get(cod)
            saldo = SaldoEstoque.objects.filter(tenant=tenant, item=item, local=central).first() if item else None
            if obras and et_fund and item and saldo and saldo.quantidade >= D(quant):
                sil_services.aplicar_saida(
                    tenant.id, item.item_id, central.local_id, D(quant),
                    usuario=usuario if getattr(usuario, "pk", None) else None,
                    obra_id=obras[0].obra_id, etapa_id=et_fund.etapa_id,
                    observacao=f"Aplicação na obra — {obs}.",
                )
        print(f"  Consumo apropriado à etapa '{et_fund.nome_etapa if et_fund else '—'}' (aplicado × orçado)")

    _seed_sil_epi_ferramentaria(tenant, central, obras, usuario)


def _seed_sil_epi_ferramentaria(tenant, central, obras, usuario):
    """EPI (NR-6) e ferramentaria (comodato) — construtora-native. Idempotente."""
    D = Decimal
    funcionarios = list(Funcionario.objects.filter(tenant=tenant).order_by("funcionario_id")[:3])
    fmt = lambda i: funcionarios[i] if i < len(funcionarios) else None

    # EPIs no catálogo-mestre (tipo=epi) + estoque + entregas (uma vencendo).
    epi_defs = [
        ("EPI-CAP", "Capacete de segurança branco", "un", "34521"),
        ("EPI-LUV", "Luva de vaqueta (par)", "par", "28190"),
        ("EPI-BOT", "Bota de segurança com biqueira", "par", "41007"),
    ]
    epi_itens = {}
    for cod, desc, un, _ca in epi_defs:
        it, _ = ScmProduto.objects.get_or_create(
            tenant=tenant, codigo_interno=cod,
            defaults={"descricao": desc, "unidade": un, "tipo": "epi", "categoria": "EPI", "estocavel": True, "consumivel": True},
        )
        epi_itens[cod] = it

    if not EntregaEPI.objects.filter(tenant=tenant).exists():
        for cod, _desc, _un, _ca in epi_defs:
            sil_services.aplicar_entrada(
                tenant.id, epi_itens[cod].item_id, central.local_id, D("40"), D("18.50"),
                usuario=usuario if getattr(usuario, "pk", None) else None, observacao="Estoque inicial de EPI.",
            )
        entregas = [
            ("EPI-CAP", 0, "34521", HOJE + datetime.timedelta(days=400), None),
            ("EPI-LUV", 1, "28190", HOJE + datetime.timedelta(days=300), HOJE + datetime.timedelta(days=15)),  # troca em 15d
            ("EPI-BOT", 2, "41007", HOJE - datetime.timedelta(days=5), None),  # CA vencido → fila
        ]
        for cod, fi, ca, ca_val, troca in entregas:
            func = fmt(fi)
            EntregaEPI.objects.create(
                tenant=tenant, item=epi_itens[cod], colaborador=func,
                colaborador_nome="" if func else "Colaborador terceirizado",
                local=central, obra=obras[0] if obras else None, quantidade=D("1"),
                ca_numero=ca, ca_validade=ca_val, data_prevista_troca=troca,
                status=EntregaEPI.Status.ENTREGUE, assinado=True, baixou_estoque=True,
            )
            sil_services.aplicar_saida(
                tenant.id, epi_itens[cod].item_id, central.local_id, D("1"),
                usuario=usuario if getattr(usuario, "pk", None) else None,
                obra_id=obras[0].obra_id if obras else None, observacao=f"Entrega de EPI ({cod}).",
            )

    # Ferramentaria: bens + um empréstimo em atraso, um item a calibrar.
    ferr_defs = [
        ("Furadeira de impacto Bosch", "FER-001", False, None, HOJE + datetime.timedelta(days=60)),
        ("Betoneira 400L", "FER-002", False, None, HOJE - datetime.timedelta(days=3)),  # manutenção vencida
        ("Nível a laser", "FER-003", True, HOJE + datetime.timedelta(days=20), None),   # calibração vencendo
    ]
    ferramentas = {}
    for nome, patr, calib, prox_cal, prox_man in ferr_defs:
        f, _ = Ferramenta.objects.get_or_create(
            tenant=tenant, patrimonio=patr,
            defaults={"nome": nome, "local": central, "calibravel": calib, "proxima_calibracao": prox_cal, "proxima_manutencao": prox_man, "valor": D("850.00")},
        )
        ferramentas[patr] = f

    if not EmprestimoFerramenta.objects.filter(tenant=tenant).exists():
        func = fmt(1)
        emp = EmprestimoFerramenta.objects.create(
            tenant=tenant, ferramenta=ferramentas["FER-001"], colaborador=func,
            colaborador_nome="" if func else "Pedreiro", obra=obras[0] if obras else None,
            data_emprestimo=HOJE - datetime.timedelta(days=10),
            data_prevista_devolucao=HOJE - datetime.timedelta(days=2),  # atrasada
            status=EmprestimoFerramenta.Status.EMPRESTADA,
        )
        Ferramenta.objects.filter(pk=emp.ferramenta_id).update(estado=Ferramenta.Estado.EMPRESTADA)
    print(f"  EPI: {EntregaEPI.objects.filter(tenant=tenant).count()} entregas · Ferramentas: {Ferramenta.objects.filter(tenant=tenant).count()} · Empréstimos: {EmprestimoFerramenta.objects.filter(tenant=tenant).count()}")


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

    print("\n→ Suprimentos (SCM):")
    seed_scm(tenant, obras)

    print("\n→ Estoque & Logística (SIL):")
    seed_sil(tenant, obras, usuario_demo)

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
    print(f"  SCM · Fornecedores: {Fornecedor.objects.count()} · Produtos: {ScmProduto.objects.count()} · Ofertas: {OfertaFornecedor.objects.count()}")
    print(f"  SCM · Cotações: {Cotacao.objects.count()} · Propostas: {Proposta.objects.count()} · Pedidos: {PedidoCompra.objects.count()} · Avaliações: {AvaliacaoFornecedor.objects.count()}")
    print(f"  SIL · Locais: {LocalEstoque.objects.count()} · Saldos: {SaldoEstoque.objects.count()} · Movimentações: {MovimentacaoEstoque.objects.count()} · Requisições: {Requisicao.objects.count()} · Inventários: {Inventario.objects.count()}")
    print(f"  SIL · EPI: {EntregaEPI.objects.count()} · Ferramentas: {Ferramenta.objects.count()} · Empréstimos: {EmprestimoFerramenta.objects.count()}")
    print("=" * 60)
