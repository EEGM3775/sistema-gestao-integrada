"""Semeia a **execução** do PDCA numa obra que já tem plano — o que vem depois
do cronograma: o contrato que paga, a semana que se compromete, a ficha que
reprova e o turno que começa com a roda de segurança.

O `semear_pdca_demo` entrega o planejamento (locais, expediente, WBS, avanço).
Este entrega o resto do ciclo, e existe por uma razão de tela: cinco dos seis
postos do frontend abrem numa **fila de decisão**, e fila vazia não se julga. O
que se semeia aqui é justamente o que espera alguém — a não-conformidade que
ninguém pegou, a ação vencida, o conserto que ninguém conferiu, a medição parada
no atesto e a ficha parada no meio.

Ele trabalha sobre as obras **que já existem** — as do seed, não obras novas: o
banco de desenvolvimento acumulou dezenas de obras de teste automatizado (`E2E
…`, `REPRO`, `PROBE`, `VIS`), e semear em cima delas encheria a carteira de lixo
com aparência de obra. O filtro está em `NOMES_DE_TESTE`.

    python manage.py semear_pdca_execucao --tenant demo          # todas as reais com plano
    python manage.py semear_pdca_execucao --tenant demo --obra 7 # só uma
    python manage.py semear_pdca_execucao --tenant demo --limpar

**Dev/staging apenas.** `--limpar` apaga contrato, medições, restrições,
programações, fichas, não-conformidades, DDS e ocorrências daquela obra.

Duas coisas que este comando **não** faz, e a ausência é deliberada:

- **não aprova medição.** Aprovar cria título no ERP, e uma medição carimbada
  como aprovada sem o título correspondente seria dinheiro que a demo mostra e o
  financeiro não tem. A medição fica **submetida**, que é o estado que a fila de
  atesto existe para mostrar;
- **não inventa homem-hora.** As taxas de frequência e de gravidade continuam
  vindo nulas, porque a apropriação ainda não existe — e zero numa tela de
  segurança é a mentira mais cara que um seed pode contar.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from fornecedores.models import Fornecedor
from nucleo.models import Tenant
from nucleo.tenancy import rls_bypass
from obras.models import Obra

from modulopdca import services
from modulopdca.models import (
    Atividade, CausaNaoCumprimento, ContratoObra, Cronograma, DialogoSeguranca, ItemContrato,
    ItemModeloVerificacao, ItemProgramacao, ItemVerificacao, Medicao,
    ModeloVerificacao, NaoConformidade, Ocorrencia, PlanoAcao,
    ProgramacaoSemanal, Restricao, Verificacao,
)

#: Obra de teste automatizado não é obra. O banco de desenvolvimento acumula
#: uma por execução de E2E, e a carteira da tela mostraria 90 delas ao lado das
#: cinco que a demo existe para contar.
NOMES_DE_TESTE = ("E2E ", "REPRO ", "PROBE ", "TEXTO ", "VIS ", "diag ", "Acervo ", "Corpus ")

#: Os itens do contrato, amarrados à WBS pelo **código da EAP** — id de seed
#: varia entre máquinas, e uma demo que quebra em ambiente novo não demonstra
#: nada. `(codigo_eap, unidade, quantidade, preco)`.
ITENS_DO_CONTRATO = [
    ("2.1", "m2", Decimal("420.00"), Decimal("86.40")),
    ("2.2", "kg", Decimal("8600.00"), Decimal("12.75")),
    ("2.3", "m3", Decimal("162.00"), Decimal("638.00")),
    ("3.1", "kg", Decimal("14200.00"), Decimal("13.10")),
    ("3.2", "m3", Decimal("245.00"), Decimal("652.00")),
    ("4.1", "m2", Decimal("1830.00"), Decimal("74.90")),
]

#: `(codigo_eap, tipo, descricao, dias_para_o_prazo, removida)`
RESTRICOES = [
    ("3.1", "material", "Aço CA-50 Ø10 e Ø12,5 — pedido colocado, entrega não confirmada pela usina.", -4, False),
    ("4.1", "projeto", "Detalhamento das vergas e contravergas do 3º pavimento não liberado.", 3, False),
    ("4.2", "mao_de_obra", "Equipe de chapisco não contratada — 4 serventes a definir.", 11, False),
    ("3.2", "area", "Frente do 2º pavimento ocupada pela montagem do elevador cremalheira.", -12, True),
    ("2.3", "equipamento", "Bomba lança sem disponibilidade na data da concretagem.", -20, True),
]

FVS_ALVENARIA = (
    "FVS-ALV", "Alvenaria de vedação", "qualidade",
    [
        ("Marcação da primeira fiada conferida contra o projeto", "Desvio máximo de 10 mm em relação ao eixo.", True),
        ("Prumo da parede", "Desvio máximo de 3 mm por metro, medido com régua de 2 m.", True),
        ("Espessura e preenchimento das juntas", "Junta de 10 mm ± 3 mm, totalmente preenchida.", True),
        ("Amarração com pilares (tela ou ferro-cabelo)", "A cada 2 fiadas, ancorada nos dois lados.", True),
        ("Encunhamento executado após 7 dias", "Sem frestas; argamassa expansiva ou tijolo inclinado.", False),
        ("Vãos de esquadria no gabarito", "Largura e altura dentro de ± 5 mm do projeto.", True),
    ],
)

INSPECAO_ALTURA = (
    "INSP-ALT", "Trabalho em altura — periférico", "seguranca",
    [
        ("Guarda-corpo com travessa superior, intermediária e rodapé", "Altura de 1,20 m; rodapé de 0,20 m.", True),
        ("Cinturão tipo paraquedista com talabarte duplo em uso", "Todos os trabalhadores na periferia.", True),
        ("Linha de vida instalada e inspecionada", "Com registro de inspeção do mês corrente.", True),
        ("Plataforma de proteção (bandeja) montada", "A cada 3 pavimentos, conforme NR-18.", False),
    ],
)


class Command(BaseCommand):
    help = "Semeia contrato, medição, semana, qualidade e segurança numa obra que já tem plano."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="demo")
        parser.add_argument(
            "--obra", type=int, default=None,
            help="Id de uma obra. Sem isto, semeia TODAS as obras reais com plano vigente.",
        )
        parser.add_argument("--semente", type=int, default=11)
        parser.add_argument(
            "--limpar", action="store_true",
            help="Apaga a execução já semeada nesta obra antes de recomeçar.",
        )

    def handle(self, *args, **opcoes):
        try:
            tenant = Tenant.objects.get(slug=opcoes["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(
                f"Tenant '{opcoes['tenant']}' não existe. Rode o seed principal antes."
            )

        hoje = timezone.localdate()

        with rls_bypass():
            services.semear_causas_de_fabrica(tenant.pk)
            alvos, sem_plano = self._obras_alvo(tenant, opcoes["obra"])

            if not alvos:
                raise CommandError(
                    "Nenhuma obra real com plano vigente neste tenant. "
                    "Rode `semear_pdca_demo --obra <id>` antes."
                )

            for obra, cronograma in alvos:
                self.stdout.write("")
                self.stdout.write(f"── [{obra.pk}] {obra.nome_obra} · plano v{cronograma.versao}")
                self._semear_obra(tenant, obra, cronograma, hoje, opcoes["limpar"])

            if sem_plano:
                self.stdout.write("")
                self.stdout.write(self.style.WARNING(
                    "Obras reais **sem plano**, que por isso ficaram de fora — o contrato, a "
                    "semana e a ficha se penduram nas atividades, e sem cronograma não há em quê:"
                ))
                for obra in sem_plano:
                    self.stdout.write(
                        f"    [{obra.pk}] {obra.nome_obra}"
                        f"  →  python manage.py semear_pdca_demo --obra {obra.pk}"
                    )

    def _semear_obra(self, tenant, obra, cronograma, hoje, limpar):
        if limpar:
            self._limpar(obra)

        if ContratoObra.objects.filter(tenant=tenant, obra=obra).exists():
            self.stdout.write(self.style.WARNING(
                "   já tem contrato — pulada. Rode com --limpar para refazer."
            ))
            return

        folhas = self._folhas(cronograma)
        if not folhas:
            self.stdout.write(self.style.WARNING(
                "   o plano não tem atividade-folha com data — calcule-o antes. Pulada."
            ))
            return

        contrato = self._contrato(tenant, obra, folhas, hoje)
        self._medicoes(tenant, contrato, hoje)
        self._restricoes(tenant, folhas, hoje)
        self._programacoes(tenant, obra, folhas, hoje)
        self._qualidade(tenant, obra, folhas, hoje)
        self._ssma(tenant, obra, folhas, hoje)
        self._resumo(obra)

    # ─── Pré-requisitos ───────────────────────────────────────────────────────

    def _obras_alvo(self, tenant, obra_id):
        """As obras **reais** do tenant, separadas entre as que têm plano e as que não.

        A separação é o dado útil: a segunda lista diz exatamente o comando que
        falta rodar, em vez de o seed falhar em silêncio numa obra vazia.
        """
        obras = Obra.objects.filter(tenant=tenant).order_by("pk")
        if obra_id:
            obras = obras.filter(pk=obra_id)
        else:
            obras = [
                o for o in obras
                if not any(o.nome_obra.startswith(p) for p in NOMES_DE_TESTE)
            ]

        planos = {
            c.obra_id: c
            for c in Cronograma.objects.filter(
                tenant=tenant, status=Cronograma.Status.VIGENTE,
            ).exclude(obra__isnull=True)
        }

        com, sem = [], []
        for obra in obras:
            cronograma = planos.get(obra.pk)
            if cronograma is not None and cronograma.atividades.exists():
                com.append((obra, cronograma))
            else:
                sem.append(obra)
        return com, sem

    def _folhas(self, cronograma) -> dict[str, Atividade]:
        """As atividades que se executam — as que têm filho são soma, não serviço."""
        todas = list(cronograma.atividades.all())
        com_filho = {a.pai_id for a in todas if a.pai_id}
        return {
            a.codigo: a for a in todas
            if a.atividade_id not in com_filho and a.inicio_cedo and not a.eh_marco
        }

    # ─── PDCA.3 — o contrato e o que ele paga ────────────────────────────────

    def _contrato(self, tenant, obra, folhas, hoje):
        fornecedor = Fornecedor.objects.filter(tenant=tenant).order_by("pk").first()
        if fornecedor is None:
            raise CommandError("O tenant não tem fornecedor. Rode o seed principal antes.")

        contrato = ContratoObra.objects.create(
            tenant=tenant, obra=obra, fornecedor=fornecedor,
            numero=f"CT-2026-{obra.pk:04d}",
            objeto="Execução de fundação, superestrutura e alvenaria de vedação da Torre A, "
                   "com fornecimento de mão de obra e equipamentos.",
            regime="unitario",
            data_inicio=hoje - timedelta(days=70),
            retencao_percentual=Decimal("5.00"),
            retencao_natureza="caucao",
            retencao_condicao_liberacao="Liberada no recebimento definitivo da etapa, "
                                        "mediante ausência de não-conformidade aberta.",
            prazo_pagamento_dias=30,
            status="vigente",
        )

        criados = 0
        for ordem, (codigo, unidade, quantidade, preco) in enumerate(ITENS_DO_CONTRATO):
            atividade = folhas.get(codigo)
            if atividade is None:
                continue
            ItemContrato.objects.create(
                tenant=tenant, contrato=contrato,
                codigo=codigo, descricao=atividade.nome,
                unidade=unidade, quantidade_contratada=quantidade,
                preco_unitario=preco, ordem=ordem,
                atividade=atividade, item_orcado_id=atividade.item_orcado_id,
            )
            criados += 1

        total = sum(q * p for _c, _u, q, p in ITENS_DO_CONTRATO)
        self.stdout.write(
            f"Contrato {contrato.numero}: {criados} itens, R$ {total:,.2f} contratados."
        )
        return contrato

    def _medicoes(self, tenant, contrato, hoje):
        """Uma submetida (é a fila de atesto) e uma em apuração.

        Nenhuma aprovada — ver a docstring do módulo: aprovar gera título no ERP.
        """
        primeiro_do_mes = hoje.replace(day=1)
        mes_passado_fim = primeiro_do_mes - timedelta(days=1)
        mes_passado_inicio = mes_passado_fim.replace(day=1)

        try:
            medicao1 = services.criar_medicao(
                contrato=contrato, inicio=mes_passado_inicio, fim=mes_passado_fim,
                por="Semeador da demo",
                observacao="Apurada a partir do avanço apontado no período.",
            )
        except Exception as erro:  # noqa: BLE001 — seed avisa e segue
            self.stdout.write(self.style.WARNING(f"Medição do mês anterior não abriu: {erro}"))
            return

        usuario = get_user_model().objects.filter(tenant=tenant).order_by("pk").first()
        if usuario is not None:
            try:
                services.submeter_medicao(
                    medicao=medicao1, solicitante=usuario,
                    observacao="Conferida com o boletim de campo do período.",
                )
                self.stdout.write(f"Medição {medicao1.numero}: submetida — espera atesto.")
            except Exception as erro:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"Medição não submeteu: {erro}"))
        else:
            self.stdout.write(self.style.WARNING(
                "Sem usuário no tenant — a medição ficou em rascunho."
            ))

        try:
            medicao2 = services.criar_medicao(
                contrato=contrato, inicio=primeiro_do_mes, fim=hoje,
                por="Semeador da demo",
            )
            self.stdout.write(f"Medição {medicao2.numero}: em apuração (período corrente).")
        except Exception as erro:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"Medição do mês corrente não abriu: {erro}"))

    # ─── PDCA.5 — o que trava e o que se assume ──────────────────────────────

    def _restricoes(self, tenant, folhas, hoje):
        criadas = 0
        for codigo, tipo, descricao, dias, removida in RESTRICOES:
            atividade = folhas.get(codigo)
            if atividade is None:
                continue
            restricao = Restricao.objects.create(
                tenant=tenant, atividade=atividade, tipo=tipo, descricao=descricao,
                local=atividade.local, prazo=hoje + timedelta(days=dias),
                criada_por="Semeador da demo",
            )
            if removida:
                restricao.status = "removida"
                restricao.removida_em = timezone.now() - timedelta(days=abs(dias) - 2)
                restricao.removida_por = "Semeador da demo"
                restricao.nota_remocao = "Trava resolvida em campo."
                restricao.save(update_fields=[
                    "status", "removida_em", "removida_por", "nota_remocao",
                ])
            criadas += 1
        abertas = sum(1 for *_x, removida in RESTRICOES if not removida)
        self.stdout.write(f"Restrições: {criadas} ({abertas} abertas, {criadas - abertas} removidas).")

    def _programacoes(self, tenant, obra, folhas, hoje):
        """Três semanas: duas encerradas (dão série ao PPC) e a corrente aberta."""
        segunda = hoje - timedelta(days=hoje.weekday())
        candidatas = [a for a in folhas.values()]
        if not candidatas:
            return

        causas = list(services.CAUSAS_DE_FABRICA)
        encerradas = 0

        for atras, cumpridos in ((2, 3), (1, 2)):
            inicio = segunda - timedelta(weeks=atras)
            try:
                prog = services.abrir_programacao(
                    obra=obra, semana_inicio=inicio, por="Semeador da demo",
                    tenant_id=tenant.pk,
                )
            except Exception as erro:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"Semana {inicio} não abriu: {erro}"))
                continue

            escolhidas = candidatas[:4]
            for ordem, atividade in enumerate(escolhidas):
                ItemProgramacao.objects.create(
                    tenant=tenant, programacao=prog, atividade=atividade,
                    local=atividade.local, ordem=ordem,
                    responsavel="Encarregado da frente",
                    percentual_previsto=Decimal("100.00"),
                )
            try:
                services.comprometer(programacao=prog, por="Semeador da demo")
            except Exception as erro:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"Semana {inicio} não comprometeu: {erro}"))
                continue

            for indice, item in enumerate(prog.itens.order_by("ordem")):
                item.cumprido = indice < cumpridos
                if not item.cumprido:
                    codigo = causas[(indice + atras) % len(causas)][0]
                    item.causa = CausaNaoCumprimento.objects.filter(
                        tenant=tenant, codigo=codigo,
                    ).first()
                    item.nota = "Registrado no encerramento da semana."
                item.save(update_fields=["cumprido", "causa", "nota"])

            try:
                services.encerrar(
                    programacao=prog, por="Semeador da demo", hoje=hoje, arrastar=False,
                )
                encerradas += 1
            except Exception as erro:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"Semana {inicio} não encerrou: {erro}"))

        try:
            corrente = services.abrir_programacao(
                obra=obra, semana_inicio=segunda, por="Semeador da demo", tenant_id=tenant.pk,
            )
            #: **A semana corrente tem dois donos, e é de propósito.** A tela do
            #: canteiro procura o que está no nome de quem abriu o celular, e o
            #: nome que ela usa é o do cadastro. Com o quadro inteiro em
            #: "Encarregado da frente", quem entra pela persona de campo abre a
            #: frente vazia — e frente vazia numa demo não demonstra o posto, e
            #: sim um defeito. Metade fica com o rótulo da obra (que é como o
            #: escritório escreve) e metade com quem consegue entrar.
            dono_de_campo = self._quem_aponta(tenant)
            for ordem, atividade in enumerate(candidatas[:5]):
                ItemProgramacao.objects.create(
                    tenant=tenant, programacao=corrente, atividade=atividade,
                    local=atividade.local, ordem=ordem,
                    responsavel=(
                        dono_de_campo if (dono_de_campo and ordem < 2)
                        else "Encarregado da frente"
                    ),
                    percentual_previsto=Decimal("100.00"),
                )
            services.comprometer(programacao=corrente, por="Semeador da demo")
        except Exception as erro:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"Semana corrente não abriu: {erro}"))

        self.stdout.write(f"Programação: {encerradas} semanas encerradas + a semana corrente.")

    @staticmethod
    def _quem_aponta(tenant) -> str:
        """O rótulo de quem aponta avanço no canteiro — o mesmo que o servidor
        procura na leitura da frente (`services.minhas_frentes`).

        É `get_full_name() or username`, e não uma escolha nova: a leitura casa
        por **nome**, porque `responsavel` é rótulo durável em todo o módulo.
        Uma segunda regra aqui faria o seed semear no nome que a tela não
        procura, e ninguém descobriria sem abrir o banco.
        """
        usuario = (
            get_user_model().objects
            .filter(tenant=tenant, username="campo").first()
        )
        if usuario is None:
            return ""
        return (usuario.get_full_name() or usuario.username or "").strip()

    # ─── PDCA.7 — a ficha, o defeito e o laço que o fecha ────────────────────

    def _qualidade(self, tenant, obra, folhas, hoje):
        modelos = {}
        for codigo, nome, dominio, itens in (FVS_ALVENARIA, INSPECAO_ALTURA):
            modelo = ModeloVerificacao.objects.create(
                tenant=tenant, codigo=codigo, nome=nome, dominio=dominio,
                descricao="Modelo de demonstração.", criado_por="Semeador da demo",
            )
            for ordem, (texto, criterio, obrigatorio) in enumerate(itens):
                ItemModeloVerificacao.objects.create(
                    tenant=tenant, modelo=modelo, texto=texto, criterio=criterio,
                    obrigatorio=obrigatorio, ordem=ordem,
                )
            modelos[codigo] = modelo

        alvenaria = folhas.get("4.1") or next(iter(folhas.values()))

        #: Ficha 1 — concluída com duas reprovas de gravidades diferentes. As NCs
        #: nascem do verbo do módulo, cada uma com o peso do seu item.
        ficha1 = self._aplicar(
            tenant, obra, modelos["FVS-ALV"], alvenaria, hoje - timedelta(days=12),
            "Ana Prado", {1: ("nao_conforme", "maior"), 5: ("nao_conforme", "menor")},
        )
        #: Ficha 2 — uma reprova crítica, que **para o serviço** (vira restrição).
        ficha2 = self._aplicar(
            tenant, obra, modelos["FVS-ALV"], alvenaria, hoje - timedelta(days=5),
            "Ana Prado", {3: ("nao_conforme", "critica")},
        )
        #: Ficha 3 — começou e ninguém terminou. É uma das quatro filas.
        self._aplicar(
            tenant, obra, modelos["INSP-ALT"], alvenaria, hoje - timedelta(days=2),
            "Carlos Beltrão", {0: ("conforme", None)}, concluir=False,
        )

        ncs = list(NaoConformidade.objects.filter(tenant=tenant, obra=obra).order_by("pk"))
        if len(ncs) >= 1:
            #: A primeira fica **sem plano** — ninguém pegou.
            pass
        if len(ncs) >= 2:
            #: A segunda ganha plano **vencido** — alguém pegou e não fez.
            PlanoAcao.objects.create(
                tenant=tenant, nao_conformidade=ncs[1], tipo="corretiva",
                o_que="Refazer o encunhamento do trecho reprovado.",
                por_que="Frestas comprometem o desempenho acústico e o travamento da parede.",
                onde="3º pavimento, fachada leste", quem="Equipe de alvenaria",
                quando=hoje - timedelta(days=3), como="Remoção e reexecução com argamassa expansiva.",
                quanto=Decimal("640.00"), status="em_execucao", criada_por="Semeador da demo",
            )
        if len(ncs) >= 3:
            #: A terceira: ação feita, **eficácia não verificada** — ninguém conferiu.
            plano = PlanoAcao.objects.create(
                tenant=tenant, nao_conformidade=ncs[2], tipo="corretiva",
                o_que="Corrigir o prumo do trecho e reapertar a amarração.",
                por_que="Desvio acima do critério da ficha.",
                onde="3º pavimento, fachada norte", quem="Equipe de alvenaria",
                quando=hoje - timedelta(days=6), como="Demolição parcial e reexecução.",
                quanto=Decimal("1280.00"), criada_por="Semeador da demo",
            )
            try:
                services.concluir_acao(plano=plano, por="Semeador da demo")
            except Exception as erro:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"Ação não concluiu: {erro}"))

        #: E uma história inteira, fechada como manda o laço: ação → eficácia → encerrada.
        fechada = NaoConformidade.objects.create(
            tenant=tenant, obra=obra, local=alvenaria.local, atividade=alvenaria,
            descricao="Junta de assentamento acima de 15 mm em três fiadas do 2º pavimento.",
            gravidade="menor", aberta_por="Ana Prado",
        )
        plano_ok = PlanoAcao.objects.create(
            tenant=tenant, nao_conformidade=fechada, tipo="corretiva",
            o_que="Reexecutar as três fiadas com gabarito de junta.",
            por_que="Junta fora do critério consome argamassa e reduz a resistência.",
            onde="2º pavimento", quem="Equipe de alvenaria",
            quando=hoje - timedelta(days=16), como="Gabarito de 10 mm em toda a fiada.",
            quanto=Decimal("960.00"), criada_por="Semeador da demo",
        )
        try:
            services.concluir_acao(plano=plano_ok, por="Semeador da demo")
            services.registrar_eficacia(
                nc=fechada, data=hoje - timedelta(days=9), eficaz=True,
                evidencia="Medidas 10 a 12 mm em 12 pontos conferidos com paquímetro.",
                por="Ana Prado",
            )
            services.encerrar_nc(
                nc=fechada, por="Ana Prado",
                nota="Conserto pegou; trecho liberado para chapisco.",
            )
        except Exception as erro:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"Laço da NC fechada não completou: {erro}"))

        total = NaoConformidade.objects.filter(tenant=tenant, obra=obra).count()
        self.stdout.write(
            f"   Qualidade: 2 modelos, 3 fichas (2 concluídas, 1 em andamento), "
            f"{total} não-conformidades."
        )

    def _aplicar(self, tenant, obra, modelo, atividade, data, inspetor, respostas, concluir=True):
        """Aplica a ficha copiando a pergunta **para dentro** da resposta — apertar
        o critério do modelo depois não reescreve inspeção passada."""
        verificacao = Verificacao.objects.create(
            tenant=tenant, modelo=modelo, obra=obra, data=data,
            local=atividade.local, atividade=atividade, inspetor=inspetor,
            criada_por="Semeador da demo",
        )
        for item_modelo in modelo.itens.order_by("ordem"):
            resultado, gravidade = respostas.get(item_modelo.ordem, ("conforme", None))
            ItemVerificacao.objects.create(
                tenant=tenant, verificacao=verificacao, item_modelo=item_modelo,
                texto=item_modelo.texto, criterio=item_modelo.criterio,
                obrigatorio=item_modelo.obrigatorio, ordem=item_modelo.ordem,
                resultado=resultado, gravidade=gravidade,
                observacao="Reprovado na inspeção de campo." if gravidade else "",
                respondido_em=timezone.now(), respondido_por=inspetor,
            )
        if not concluir:
            return verificacao
        try:
            services.concluir_verificacao(verificacao=verificacao, por=inspetor)
            services.abrir_ncs_dos_reprovados(verificacao=verificacao, por=inspetor)
        except Exception as erro:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"Ficha {modelo.codigo} não concluiu: {erro}"))
        return verificacao

    # ─── PDCA.8 — a roda antes do turno e o fato que ninguém queria ──────────

    def _ssma(self, tenant, obra, folhas, hoje):
        atividade = folhas.get("4.1") or next(iter(folhas.values()))
        equipe = [
            "José Nilton da Silva", "Marcos Aurélio Pinto", "Raimundo Sales",
            "Edivaldo Barros", "Cleber Antunes", "Wesley Moraes",
            "Antônio Carlos Lima", "Gilmar Teixeira",
        ]

        for atras, tema, presentes in (
            (1, "Trabalho em altura: ancoragem do talabarte", 8),
            (0, "Ordem e limpeza da frente de serviço", 7),
        ):
            try:
                dds = services.abrir_dds(
                    obra=obra, data=hoje - timedelta(days=atras), tema=tema,
                    tenant_id=tenant.pk, local=atividade.local, atividade=atividade,
                    assunto="Conversa de cinco minutos antes do início do turno.",
                    duracao_min=10, responsavel_nome="Carlos Beltrão (TST)",
                    por="Semeador da demo",
                )
                services.registrar_presenca(dds=dds, participantes=[
                    {"nome": nome, "presente": indice < presentes, "assinou": indice < presentes}
                    for indice, nome in enumerate(equipe)
                ])
                services.encerrar_dds(dds=dds, por="Carlos Beltrão", publicar_no_diario=True)
            except Exception as erro:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"DDS '{tema}' não fechou: {erro}"))

        agora = timezone.now()
        try:
            quase = services.registrar_ocorrencia(
                obra=obra, ocorrido_em=agora - timedelta(days=6), tipo="quase_acidente",
                descricao="Tábua de andaime escorregou durante o içamento e caiu na área isolada. "
                          "Ninguém estava no raio; isolamento havia sido montado na véspera.",
                tenant_id=tenant.pk, local=atividade.local, atividade=atividade,
                por="Carlos Beltrão",
                agente_causador="Material içado",
                situacao_geradora="Amarração insuficiente da carga",
            )
            self.stdout.write(f"Ocorrência {quase.pk}: quase-acidente registrado.")
        except Exception as erro:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"Quase-acidente não registrou: {erro}"))

        try:
            acidente = services.registrar_ocorrencia(
                obra=obra, ocorrido_em=agora - timedelta(days=2, hours=5),
                tipo="acidente_tipico",
                descricao="Servente sofreu corte superficial no antebraço esquerdo ao manusear "
                          "tela de amarração sem luva de proteção.",
                tenant_id=tenant.pk, local=atividade.local, atividade=atividade,
                por="Carlos Beltrão",
                acidentado_nome="Edivaldo Barros",
                agente_causador="Tela metálica",
                situacao_geradora="Manuseio sem EPI de mão",
                parte_do_corpo="Antebraço",
                lateralidade="esquerda",
                natureza_lesao="Corte superficial",
            )
            services.classificar_ocorrencia(
                ocorrencia=acidente, classificacao="sem_afastamento", por="Carlos Beltrão",
            )
            services.registrar_cat(
                ocorrencia=acidente, tipo="inicial", emitida_em=hoje - timedelta(days=1),
                protocolo="CAT-2026-0009182", por="Carlos Beltrão",
            )
            self.stdout.write(f"Ocorrência {acidente.pk}: acidente sem afastamento, CAT emitida.")
        except Exception as erro:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"Acidente não registrou: {erro}"))

    # ─── Limpeza e resumo ─────────────────────────────────────────────────────

    def _limpar(self, obra):
        with transaction.atomic():
            apagados = 0
            apagados += Ocorrencia.objects.filter(obra=obra).delete()[0]
            apagados += DialogoSeguranca.objects.filter(obra=obra).delete()[0]
            apagados += NaoConformidade.objects.filter(obra=obra).delete()[0]
            apagados += Verificacao.objects.filter(obra=obra).delete()[0]
            apagados += ModeloVerificacao.objects.filter(
                tenant=obra.tenant, codigo__in=["FVS-ALV", "INSP-ALT"],
            ).delete()[0]
            apagados += ProgramacaoSemanal.objects.filter(obra=obra).delete()[0]
            apagados += Restricao.objects.filter(atividade__cronograma__obra=obra).delete()[0]
            apagados += Medicao.objects.filter(contrato__obra=obra).delete()[0]
            apagados += ContratoObra.objects.filter(obra=obra).delete()[0]
        self.stdout.write(self.style.WARNING(f"Limpeza: {apagados} registros apagados."))

    def _resumo(self, obra):
        linhas = [
            ("contratos", ContratoObra.objects.filter(obra=obra).count()),
            ("medições", Medicao.objects.filter(contrato__obra=obra).count()),
            ("restrições", Restricao.objects.filter(atividade__cronograma__obra=obra).count()),
            ("programações", ProgramacaoSemanal.objects.filter(obra=obra).count()),
            ("fichas", Verificacao.objects.filter(obra=obra).count()),
            ("não-conformidades", NaoConformidade.objects.filter(obra=obra).count()),
            ("DDS", DialogoSeguranca.objects.filter(obra=obra).count()),
            ("ocorrências", Ocorrencia.objects.filter(obra=obra).count()),
        ]
        self.stdout.write("")
        for nome, quantos in linhas:
            self.stdout.write(f"  {nome:<20} {quantos}")
        self.stdout.write(self.style.SUCCESS("\nExecução semeada."))
