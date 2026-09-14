"""Semeia uma obra planejada **e em execução** para exercitar o PDCA na tela.

O que a PDCA.2 pôs no ar só se vê com o tempo passando: a curva realizada
precisa de apontamentos espalhados por semanas, o desvio precisa de um plano que
começou no passado, e a "integração visível" precisa de atividades amarradas a
etapas e a itens de orçamento **de verdade** — não a números inventados aqui.

Por isso este comando **não cria uma obra nova**: ele planeja uma obra que já
existe no seed (`--obra`), reaproveitando as etapas e o orçamento aprovado dela.
Semear um orçamento paralelo só para ter o que vincular produziria uma demo onde
a cobertura fecha em 100% — que é exatamente o número que a tela existe para
desconfiar.

    python manage.py semear_pdca_demo --tenant demo
    python manage.py semear_pdca_demo --tenant demo --obra 7 --aderencia 0.82
    python manage.py semear_pdca_demo --tenant demo --limpar

**Dev/staging apenas** — `--limpar` apaga o cronograma, os apontamentos e a
árvore de locais daquela obra.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from moduloorcamento.models import ItemOrcado, Orcamento
from nucleo.models import Tenant
from nucleo.tenancy import rls_bypass
from obras.models import EtapaObra, Obra

from modulopdca import services
from modulopdca.models import (
    ApontamentoAvanco, Atividade, CalendarioTrabalho, Cronograma, ExcecaoCalendario,
    LocalObra, NivelLocal, OrigemApontamento, Precedencia,
)

# A WBS da demo. Cada folha declara como quer ser ponderada, e as três formas
# estão representadas de propósito: pelo **item orçado** (o peso vem do
# Orçamento, em R$), pelo **peso informado** (o planejador digitou) e por
# **nenhuma** — a folha sem peso, que fica fora da média e aparece no
# denominador. Uma demo onde tudo tem peso esconde o número mais útil da tela.
#
# `orcado` é a posição do item analítico na lista do orçamento (0-based), e não
# um id: id de seed varia entre máquinas, e uma demo que quebra em ambiente novo
# não serve para demonstrar nada.
WBS = [
    ("1", "Serviços preliminares", None, None, None, 0),
    ("1.1", "Mobilização do canteiro", 5, None, Decimal("8000"), 0),
    ("1.2", "Locação da obra", 3, None, Decimal("4500"), 0),
    ("1.3", "Escavação e movimento de terra", 12, None, Decimal("45000"), 0),
    ("2", "Infraestrutura", None, None, None, 1),
    ("2.1", "Fabricação de formas da fundação", 10, 2, None, 1),
    ("2.2", "Armação da fundação", 12, 1, None, 1),
    ("2.3", "Concretagem da fundação", 6, 0, None, 1),
    ("2.4", "Fundação concluída", None, None, Decimal("1"), 1),  # marco
    ("3", "Superestrutura", None, None, None, 2),
    ("3.1", "Armação de pilares e vigas", 18, 4, None, 2),
    ("3.2", "Concretagem da estrutura", 15, 3, None, 2),
    ("4", "Vedações", None, None, None, 2),
    ("4.1", "Alvenaria de vedação", 20, 5, None, 2),
    ("4.2", "Chapisco", 10, 6, None, 2),
    ("4.3", "Limpeza final da frente", 5, None, None, 2),  # sem peso, de propósito
]

#: `(origem, destino, tipo, atraso)` — a rede. Os dois `SS` existem para o Gantt
#: da demo não ser uma escada de FS, que é como um cronograma de mentira parece.
REDE = [
    ("1.1", "1.2", "FS", 0),
    ("1.2", "1.3", "FS", 0),
    ("1.3", "2.1", "FS", 0),
    ("2.1", "2.2", "SS", 2),
    ("2.2", "2.3", "FS", 0),
    ("2.3", "2.4", "FS", 0),
    ("2.4", "3.1", "FS", 0),
    ("3.1", "3.2", "SS", 5),
    ("3.2", "4.1", "FS", 0),
    ("4.1", "4.2", "SS", 5),
    ("4.2", "4.3", "FS", 0),
]


class Command(BaseCommand):
    help = "Cria locais, calendário, cronograma vigente e o avanço apontado de uma obra."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="demo")
        parser.add_argument(
            "--obra", type=int, default=None,
            help="Id da obra. Sem isto, escolhe a primeira com etapas E orçamento aprovado.",
        )
        parser.add_argument(
            "--semanas", type=int, default=10,
            help="Há quantas semanas o plano começou (é o que dá passado à curva).",
        )
        parser.add_argument(
            "--aderencia", type=float, default=0.82,
            help="Quanto do previsto foi de fato apontado (0.82 = obra atrasada em ~18%%).",
        )
        parser.add_argument("--semente", type=int, default=7)
        parser.add_argument(
            "--limpar", action="store_true",
            help="Apaga cronograma, apontamentos e locais desta obra antes de semear.",
        )

    # ─── Entrada ──────────────────────────────────────────────────────────────

    def handle(self, *args, **opcoes):
        try:
            tenant = Tenant.objects.get(slug=opcoes["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(f"Tenant '{opcoes['tenant']}' não existe. Rode o seed principal antes.")

        aleatorio = random.Random(opcoes["semente"])
        hoje = timezone.localdate()

        # Comando cruza tenants sob bypass explícito — a RLS é fail-closed.
        with rls_bypass():
            obra = self._obra(tenant, opcoes["obra"])
            self.stdout.write(f"Obra: [{obra.pk}] {obra.nome_obra}")

            if opcoes["limpar"]:
                self._limpar(obra)

            if Cronograma.objects.filter(tenant=tenant, obra=obra).exists():
                raise CommandError(
                    f"A obra {obra.pk} já tem cronograma. Rode com --limpar para refazer, "
                    "ou escolha outra obra com --obra."
                )

            calendario = self._calendario(tenant, obra)
            locais = self._locais(tenant, obra)
            etapas = list(obra.etapas.order_by("ordem", "etapa_id"))
            itens = self._itens_orcados(obra)

            inicio = hoje - timedelta(weeks=opcoes["semanas"])
            inicio -= timedelta(days=inicio.weekday())  # ancora numa segunda-feira

            cronograma, atividades = self._cronograma(
                tenant, obra, calendario, inicio, etapas, itens, locais,
            )
            cpm = services.calcular_cpm(cronograma)
            self.stdout.write(
                f"CPM: {cpm['atividades']} atividades, {cpm['precedencias']} ligações, "
                f"{len(cpm['criticas'])} críticas, término {cpm['termino']}"
            )

            services.publicar(cronograma, por="Semeador da demo")
            self.stdout.write(self.style.SUCCESS(f"Cronograma v{cronograma.versao} publicado (vigente)."))

            quantos = self._apontar(
                cronograma, atividades, hoje, opcoes["aderencia"], aleatorio,
            )
            self.stdout.write(self.style.SUCCESS(f"Apontamentos: {quantos}"))

            self._resumo(cronograma, obra)

    # ─── Escolha da obra ──────────────────────────────────────────────────────

    def _obra(self, tenant, obra_id):
        if obra_id is not None:
            try:
                return Obra.objects.get(tenant=tenant, pk=obra_id)
            except Obra.DoesNotExist:
                raise CommandError(f"A obra {obra_id} não existe no tenant '{tenant.slug}'.")

        # Sem escolha explícita, a melhor obra é a que permite mostrar as DUAS
        # pontes do módulo ao mesmo tempo: etapa (cadastro de obra) e item
        # orçado (Orçamento). Uma obra sem as duas faria a demo abrir com dois
        # cadeados e nenhuma integração visível.
        for obra in Obra.objects.filter(tenant=tenant).order_by("pk"):
            if not obra.etapas.exists():
                continue
            if not Orcamento.objects.filter(obra=obra, status="aprovado").exists():
                continue
            if Cronograma.objects.filter(tenant=tenant, obra=obra).exists():
                continue
            return obra
        raise CommandError(
            "Nenhuma obra livre com etapas e orçamento aprovado. Passe --obra <id> "
            "(e --limpar, se ela já tiver plano)."
        )

    def _itens_orcados(self, obra) -> list[ItemOrcado]:
        """Os analíticos do orçamento **aprovado** — é deles que sai o peso em R$."""
        orcamento = (Orcamento.objects
                     .filter(obra=obra, status="aprovado")
                     .order_by("-versao").first())
        if orcamento is None:
            return []
        return list(ItemOrcado.objects
                    .filter(orcamento=orcamento)
                    .exclude(tipo_linha="sintetico")
                    .order_by("codigo_eap"))

    # ─── Limpeza ──────────────────────────────────────────────────────────────

    def _limpar(self, obra):
        """Na ordem das dependências: apontamento → precedência → atividade →
        cronograma → local. O apontamento é `PROTECT` na atividade de propósito
        (é histórico que vira medição), então ele **tem** de sair primeiro — e
        que este comando precise saber disso é a prova de que a trava funciona.
        """
        with transaction.atomic():
            # **Os estornos primeiro.** `estorna` é `PROTECT` no próprio
            # apontamento, e o coletor do Django **não isenta o que já está na
            # fila de exclusão** (a mesma lição do D116, do outro lado): apagar
            # tudo de uma vez levanta `ProtectedError` mesmo estando os dois no
            # mesmo `delete()`. Que um comando de bancada precise saber disso é a
            # prova de que a trava do livro-razão funciona.
            apagados = ApontamentoAvanco.objects.filter(
                atividade__cronograma__obra=obra, estorna__isnull=False).delete()[0]
            apagados += ApontamentoAvanco.objects.filter(
                atividade__cronograma__obra=obra).delete()[0]
            apagados += Precedencia.objects.filter(origem__cronograma__obra=obra).delete()[0]
            apagados += Atividade.objects.filter(cronograma__obra=obra).delete()[0]
            apagados += Cronograma.objects.filter(obra=obra).delete()[0]
            apagados += LocalObra.objects.filter(obra=obra).delete()[0]
            # O calendário é da empresa quando não tem obra; só o desta obra sai.
            apagados += ExcecaoCalendario.objects.filter(calendario__obra=obra).delete()[0]
            apagados += CalendarioTrabalho.objects.filter(obra=obra).delete()[0]
            EtapaObra.objects.filter(obra=obra).update(percentual_conclusao=Decimal("0"))
        self.stdout.write(self.style.WARNING(f"Limpeza: {apagados} registros apagados."))

    # ─── Fundação: quando se trabalha e onde ──────────────────────────────────

    def _calendario(self, tenant, obra):
        """Dois expedientes, porque a empresa real tem dois.

        O **padrão da empresa** (sem obra) é o que vale para todas e é o que o
        plano usa; o **da obra** existe ao lado para a frente que trabalha sábado.
        Semear só o da obra deixaria toda obra nova sem nada para escolher — foi
        exatamente o que aconteceu na primeira carga desta demo, e é a metade de
        cadastro do [D118](../../docs/historico-correcoes.md).
        """
        uf = (getattr(obra, "estado", "") or "SC")[:2]
        calendario, criado = CalendarioTrabalho.objects.get_or_create(
            tenant=tenant, nome="Expediente padrão da empresa", obra=None,
            defaults={
                "padrao": True,
                "horas_por_dia": Decimal("8.80"),
                "trabalha_sabado": False,
                "considera_feriados": True,
                "uf": uf,
            },
        )
        CalendarioTrabalho.objects.get_or_create(
            tenant=tenant, nome=f"Turno com sábado — {obra.nome_obra[:50]}", obra=obra,
            defaults={
                "horas_por_dia": Decimal("8.00"),
                "trabalha_sabado": True,
                "considera_feriados": True,
                "uf": uf,
            },
        )
        if criado:
            # Uma exceção real, porque expediente sem exceção não exercita nada:
            # a semana de recesso é o que faz a conta de dias úteis divergir da
            # contagem ingênua, e é justamente o erro que a tela de expediente
            # existe para pegar.
            inicio_recesso = timezone.localdate().replace(month=12, day=24)
            for n in range(8):
                ExcecaoCalendario.objects.get_or_create(
                    tenant=tenant, calendario=calendario,
                    data=inicio_recesso + timedelta(days=n),
                    defaults={"trabalha": False, "motivo": "Recesso de fim de ano"},
                )
        self.stdout.write(
            f"Calendários: '{calendario.nome}' ({'novo' if criado else 'reaproveitado'}) "
            f"+ o turno com sábado da obra"
        )
        return calendario

    def _locais(self, tenant, obra) -> list[LocalObra]:
        """A árvore construtiva pelo **gerador em lote** — o mesmo caminho que o
        usuário percorre na tela. Semear com `objects.create` em laço deixaria de
        exercitar a validação de profundidade e a idempotência dele."""
        resultado = services.gerar_em_lote(
            obra=obra, tenant_id=tenant.pk,
            receita=[
                {"nivel": NivelLocal.BLOCO, "itens": [{"codigo": "TA", "nome": "Torre A"}]},
                {"nivel": NivelLocal.PAVIMENTO, "de": 1, "ate": 6,
                 "formato_codigo": "P{n:02d}", "formato_nome": "{n}º pavimento"},
                {"nivel": NivelLocal.UNIDADE, "de": 1, "ate": 4,
                 "formato_codigo": "0{n}", "formato_nome": "Unidade 0{n}"},
            ],
        )
        self.stdout.write(
            f"Locais: {resultado['criados']} criados, {resultado['ja_existiam']} já existiam"
        )
        return list(LocalObra.objects.filter(obra=obra).order_by("profundidade", "ordem", "codigo"))

    # ─── O plano ──────────────────────────────────────────────────────────────

    def _cronograma(self, tenant, obra, calendario, inicio, etapas, itens, locais):
        cronograma = Cronograma.objects.create(
            tenant=tenant, obra=obra,
            descricao=f"Plano executivo — {obra.nome_obra[:100]}",
            data_inicio=inicio, calendario=calendario,
        )

        pavimentos = [l for l in locais if l.nivel == NivelLocal.PAVIMENTO]
        atividades: dict[str, Atividade] = {}
        for ordem, (codigo, nome, duracao, orcado, peso, etapa_idx) in enumerate(WBS):
            pai = atividades.get(codigo.rsplit(".", 1)[0]) if "." in codigo else None
            item = itens[orcado] if (orcado is not None and orcado < len(itens)) else None
            eh_marco = duracao is None and pai is not None
            atividades[codigo] = Atividade.objects.create(
                tenant=tenant, cronograma=cronograma, pai=pai,
                codigo=codigo, nome=nome, ordem=ordem,
                profundidade=1 if pai is None else pai.profundidade + 1,
                duracao_dias=duracao,
                eh_marco=eh_marco,
                # O vínculo com a etapa é o que faz o avanço apontado aqui subir
                # para o `percentual_conclusao` da obra (planta §11.2).
                etapa=etapas[etapa_idx] if etapa_idx < len(etapas) else None,
                item_orcado=item,
                peso_informado=peso if item is None else None,
                local=pavimentos[ordem % len(pavimentos)] if (pavimentos and pai is not None) else None,
            )

        for origem, destino, tipo, atraso in REDE:
            Precedencia.objects.create(
                tenant=tenant, origem=atividades[origem], destino=atividades[destino],
                tipo=tipo, atraso_dias=atraso,
            )

        self.stdout.write(
            f"WBS: {len(atividades)} atividades ({len(REDE)} ligações), "
            f"{sum(1 for a in atividades.values() if a.item_orcado_id)} vinculadas ao orçamento"
        )
        return cronograma, atividades

    # ─── A execução ───────────────────────────────────────────────────────────

    def _apontar(self, cronograma, atividades, hoje, aderencia, aleatorio) -> int:
        """Aponta o passado do plano — semana a semana, como a obra faria.

        A regra é simples e é o que dá verdade à curva: uma frente só recebe
        avanço **depois** de começar, o quanto ela avança na semana é a fatia
        prevista vezes a aderência (com ruído), e nada passa de 100%. Apontar
        tudo de uma vez na data de hoje encheria a tela de números e deixaria a
        curva realizada como um degrau — que é o oposto do que ela mostra.
        """
        criados = 0
        acumulado: dict[str, Decimal] = {}
        # Relê do banco: as instâncias em memória são de **antes** do CPM, e sem
        # datas não há como saber em que semana cada frente estava aberta. (Foi o
        # primeiro defeito deste comando: 0 apontamentos, silenciosamente.)
        frescas = list(Atividade.objects.filter(cronograma=cronograma)
                       .prefetch_related("filhos").order_by("ordem"))
        folhas = [
            a for a in frescas
            if a.duracao_dias and not a.filhos.exists() and a.inicio_cedo and a.termino_cedo
        ]
        marcos = [a for a in frescas if a.eh_marco]

        semana = cronograma.data_inicio
        while semana <= hoje:
            fim_semana = semana + timedelta(days=6)
            for a in folhas:
                if a.inicio_cedo > fim_semana or a.termino_cedo < semana:
                    continue
                dias_da_atividade = (a.termino_cedo - a.inicio_cedo).days + 1
                dias_na_semana = (min(a.termino_cedo, fim_semana) - max(a.inicio_cedo, semana)).days + 1
                previsto = Decimal(dias_na_semana) / Decimal(dias_da_atividade) * Decimal(100)
                fatia = previsto * Decimal(str(aderencia)) * Decimal(str(aleatorio.uniform(0.85, 1.1)))
                atual = acumulado.get(a.codigo, Decimal("0"))
                fatia = min(fatia, Decimal("100") - atual).quantize(Decimal("0.01"))
                if fatia <= 0:
                    continue
                dia = min(semana + timedelta(days=aleatorio.randint(1, 4)), hoje)
                services.registrar_apontamento(
                    atividade=a, percentual=fatia, data=dia,
                    local=a.local, por=aleatorio.choice(["Mestre Rui", "Eng. Marina", "Eng. Paulo"]),
                    origem=aleatorio.choice([
                        OrigemApontamento.WEB, OrigemApontamento.WEB, OrigemApontamento.WHATSAPP,
                    ]),
                    observacao=aleatorio.choice([
                        "", "", "Equipe reduzida na segunda", "Chuva na quarta",
                        "Frente liberada pelo topógrafo",
                    ]),
                    sincronizar=False,
                )
                acumulado[a.codigo] = atual + fatia
                criados += 1
            semana += timedelta(days=7)

        # O marco acontece quando a predecessora dele fecha — ou não acontece.
        for marco in marcos:
            anterior = Precedencia.objects.filter(destino=marco).first()
            if anterior and acumulado.get(anterior.origem.codigo, Decimal("0")) >= 100:
                services.registrar_apontamento(
                    atividade=marco, percentual=Decimal("100"),
                    data=min(marco.termino_cedo or hoje, hoje), por="Eng. Marina",
                    observacao="Concretagem liberada pela verificação", sincronizar=False,
                )
                criados += 1

        # **Um estorno**, porque a demo precisa mostrar o caminho do erro: é o
        # único jeito de corrigir o livro, e quem for testar tem de ver como a
        # linha riscada e a correção convivem.
        alvo = (ApontamentoAvanco.objects
                .filter(atividade__cronograma=cronograma, estorna__isnull=True)
                .order_by("-data").first())
        if alvo is not None:
            services.estornar(
                alvo, motivo="Avanço lançado na frente errada — corrigido no mesmo dia",
                por="Eng. Marina",
            )
            criados += 1

        # A sincronização das etapas roda **uma vez**, no fim: é escrita derivada
        # do gesto, e o gesto aqui é a carga inteira.
        etapas = services.sincronizar_percentual_das_etapas(cronograma)
        self.stdout.write(f"Etapas da obra sincronizadas: {etapas}")
        return criados

    # ─── Conferência ──────────────────────────────────────────────────────────

    def _resumo(self, cronograma, obra):
        avanco = services.avanco_do_cronograma(cronograma)
        curva = services.curva_s(cronograma)
        previsto_hoje = 0.0
        hoje = timezone.localdate().isoformat()
        for ponto in curva["pontos"]:
            if ponto["iso"] <= hoje:
                previsto_hoje = ponto["previsto"]

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("── O que a tela vai mostrar ──"))
        self.stdout.write(f"  Avanço físico:      {avanco['fisico']}%")
        self.stdout.write(f"  Previsto até hoje:  {previsto_hoje}%")
        if avanco["fisico"] is not None:
            self.stdout.write(
                f"  Desvio:             {avanco['fisico'] - previsto_hoje:+.1f} pontos percentuais"
            )
        if avanco["financeiro"]:
            self.stdout.write(
                f"  Realizado em R$:    {avanco['financeiro']['realizado']} "
                f"de {avanco['financeiro']['orcado']} orçados"
            )
        self.stdout.write(
            f"  Folhas:             {avanco['folhas']} "
            f"({avanco['folhas_sem_peso']} sem peso, fora da média — de propósito)"
        )
        self.stdout.write(f"  Curva S:            {len(curva['pontos'])} pontos por {curva['granularidade']}")
        for etapa in obra.etapas.order_by("ordem"):
            self.stdout.write(f"  Etapa '{etapa.nome_etapa}': {etapa.percentual_conclusao}% (apurado)")
        self.stdout.write("")
        self.stdout.write(
            f"  Abra: /app/pdca/obra/{obra.pk}/cronograma/{cronograma.pk} → lente **Avanço**"
        )
