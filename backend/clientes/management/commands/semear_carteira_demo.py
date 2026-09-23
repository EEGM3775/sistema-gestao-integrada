"""Semeia a carteira de demonstração: empreendimentos, unidades, vendas e carnês.

A tela de Clientes foi refeita para aguentar milhares de linhas (rolagem
infinita, virtualização, agrupamento no banco). Provar isso exige volume: com 20
cadastros qualquer implementação parece rápida.

O que muda em relação à versão anterior: a **unidade existe antes da venda** (é
cadastro do empreendimento, com preço de tabela e situação) e o carnê sai do
**mesmo motor de cálculo da tela** (`clientes.plano_pagamento`) — desconto,
entrada, Price/SAC, balões. Parcela semeada com número inventado deixaria a demo
mostrando uma matemática que o produto não faz.

Os CPF/CNPJ são **válidos** (dígito verificador correto): o Asaas, mesmo em
sandbox, recusa documento inválido ao criar o cliente da cobrança, e uma base
com documento aleatório não emite um boleto sequer.

    python manage.py semear_carteira_demo --tenant demo --clientes 2000
    python manage.py semear_carteira_demo --tenant demo --limpar

**Dev/staging apenas** — `--limpar` apaga carteira, unidades e títulos do tenant.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clientes import plano_pagamento
from clientes import vencimento as vencimento_svc
from clientes.models import Cliente, ClienteEmpreendimento, ContratoCliente
from empreendimentos.models import Empreendimento, Unidade
from moduloerp.models import ContaReceber, StatusConta
from nucleo.documentos import gerar_cnpj, gerar_cpf
from nucleo.models import Tenant
from nucleo.tenancy import rls_bypass

CIDADES = [
    ("Palhoça", "SC"), ("Biguaçu", "SC"), ("São José", "SC"),
    ("Tijucas", "SC"), ("Garopaba", "SC"),
]
NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Heitor",
         "Isabela", "João", "Karina", "Lucas", "Marina", "Nuno", "Olívia", "Paulo"]
SOBRENOMES = ["Souza", "Lima", "Costa", "Almeida", "Pereira", "Ribeiro", "Martins",
              "Carvalho", "Gomes", "Barbosa", "Rocha", "Dias"]

LOTES_POR_QUADRA = 20


class Command(BaseCommand):
    help = "Cria a carteira de demonstração: unidades à venda, vendas com plano e carnês."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="demo", help="Slug do tenant (padrão: demo)")
        parser.add_argument("--clientes", type=int, default=2000, help="Quantos clientes criar")
        parser.add_argument("--empreendimentos", type=int, default=4)
        parser.add_argument(
            "--vagas", type=float, default=1.35,
            help="Unidades cadastradas por cliente — o que passa de 1 fica à venda.",
        )
        parser.add_argument("--semente", type=int, default=42, help="Semente do random (reprodutível)")
        parser.add_argument(
            "--limpar", action="store_true",
            help="Apaga clientes, unidades, aquisições e títulos do tenant antes de semear.",
        )

    def handle(self, *args, **opcoes):
        try:
            tenant = Tenant.objects.get(slug=opcoes["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(f"Tenant '{opcoes['tenant']}' não existe. Rode o seed principal antes.")

        aleatorio = random.Random(opcoes["semente"])
        hoje = timezone.localdate()

        # Migrações e comandos cruzam tenants sob bypass explícito (RLS fail-closed).
        with rls_bypass():
            if opcoes["limpar"]:
                self._limpar(tenant)

            empreendimentos = self._empreendimentos(tenant, opcoes["empreendimentos"], aleatorio)
            self.stdout.write(f"Empreendimentos: {len(empreendimentos)}")

            unidades = self._unidades(
                tenant, empreendimentos, int(opcoes["clientes"] * opcoes["vagas"]), aleatorio,
            )
            self.stdout.write(self.style.SUCCESS(f"Unidades cadastradas: {len(unidades)}"))

            clientes = self._clientes(tenant, opcoes["clientes"], hoje, aleatorio)
            self.stdout.write(self.style.SUCCESS(f"Clientes criados: {len(clientes)}"))

            aquisicoes = self._vender(tenant, clientes, unidades, hoje, aleatorio)
            self.stdout.write(self.style.SUCCESS(f"Vendas registradas: {len(aquisicoes)}"))

            titulos = self._gerar_carnes(tenant, aquisicoes, hoje, aleatorio)
            self.stdout.write(self.style.SUCCESS(f"Parcelas geradas: {titulos}"))

            disponiveis = Unidade.objects.filter(tenant=tenant, situacao="disponivel").count()
            self.stdout.write(f"Unidades ainda à venda: {disponiveis}")

    # ─── Limpeza ──────────────────────────────────────────────────────────────

    def _limpar(self, tenant):
        """Na ordem das dependências: título → contrato → venda → unidade → pessoa.

        Só o que é da carteira. Obras, orçamento, SCM e SIL do tenant ficam de
        pé — apagar o que não se pediu é o tipo de ajuda que custa uma tarde.
        """
        with transaction.atomic():
            apagados = ContaReceber.objects.filter(tenant=tenant).delete()[0]
            apagados += ContratoCliente.objects.filter(tenant=tenant).delete()[0]
            apagados += ClienteEmpreendimento.objects.filter(tenant=tenant).delete()[0]
            apagados += Unidade.objects.filter(tenant=tenant).delete()[0]
            apagados += Cliente.objects.filter(tenant=tenant).delete()[0]
        self.stdout.write(self.style.WARNING(f"Limpeza: {apagados} registros apagados."))

    # ─── Cadastros ────────────────────────────────────────────────────────────

    def _empreendimentos(self, tenant, quantos, aleatorio):
        saida = []
        for i in range(quantos):
            cidade, uf = CIDADES[i % len(CIDADES)]
            emp, _ = Empreendimento.objects.get_or_create(
                tenant=tenant, empreendimento=f"Loteamento Demo {i + 1}",
                defaults={
                    "razao_social": f"Loteamento Demo {i + 1} SPE Ltda",
                    "cnpj": gerar_cnpj(7000 + i),
                    "telefone": "4833334444",
                    "endereco": f"Rodovia BR-101, km {aleatorio.randint(10, 300)}",
                    "cidade": cidade, "estado": uf,
                    "status_empreendimento": "em_execucao",
                },
            )
            if not emp.cidade:
                emp.cidade, emp.estado = cidade, uf
                emp.save(update_fields=["cidade", "estado"])
            saida.append(emp)
        return saida

    def _unidades(self, tenant, empreendimentos, quantas, aleatorio):
        """Lotes em quadras, com preço de tabela variando por quadra.

        Preço não é sorteado por lote: num loteamento real o valor sobe com a
        quadra (frente, esquina, área) e o vendedor reconhece o padrão. Ruído
        puro faria a tabela de preços parecer erro de cadastro.
        """
        existentes = {
            (u.empreendimento_id, u.quadra, u.lote): u
            for u in Unidade.objects.filter(tenant=tenant)
        }
        novas, por_emp = [], max(1, quantas // len(empreendimentos))
        for emp in empreendimentos:
            base = Decimal(aleatorio.randrange(95_000, 160_000))
            for ordem in range(por_emp):
                quadra = str(ordem // LOTES_POR_QUADRA + 1)
                lote = str(ordem % LOTES_POR_QUADRA + 1).zfill(2)
                if (emp.pk, quadra, lote) in existentes:
                    continue
                # Quadra mais alta = mais longe da entrada = mais barata.
                ajuste = Decimal(1) - Decimal(int(quadra) - 1) * Decimal("0.015")
                area = Decimal(aleatorio.choice([200, 250, 300, 360, 420]))
                novas.append(Unidade(
                    tenant=tenant, empreendimento=emp, quadra=quadra, lote=lote,
                    tipo="lote", situacao="disponivel",
                    valor_base=(base * ajuste * area / 300).quantize(Decimal("0.01")),
                    area_total=area, area_privativa=area,
                    endereco=f"Rua {quadra}, nº {lote} — {emp.cidade}/{emp.estado}",
                ))
        with transaction.atomic():
            Unidade.objects.bulk_create(novas, batch_size=1000)
        return list(Unidade.objects.filter(tenant=tenant).order_by("pk"))

    def _clientes(self, tenant, quantos, hoje, aleatorio):
        existentes = set(
            Cliente.objects.filter(tenant=tenant).values_list("cpf_cnpj", flat=True)
        )
        novos = []
        for i in range(quantos):
            documento = gerar_cpf(i)
            if documento in existentes:
                continue
            cidade, uf = aleatorio.choice(CIDADES)
            novos.append(Cliente(
                tenant=tenant,
                nome_completo=f"{aleatorio.choice(NOMES)} {aleatorio.choice(SOBRENOMES)}",
                cpf_cnpj=documento,
                email=f"carteira{i}@exemplo.dev", telefone=f"4899{i:07d}"[:20],
                cidade=cidade, estado=uf, bairro="Centro",
                data_nascimento=hoje - timedelta(days=aleatorio.randint(7000, 20000)),
            ))
        with transaction.atomic():
            Cliente.objects.bulk_create(novos, batch_size=500)
        return list(Cliente.objects.filter(tenant=tenant).order_by("pk"))

    # ─── Vendas ───────────────────────────────────────────────────────────────

    def _vender(self, tenant, clientes, unidades, hoje, aleatorio):
        """Cada venda ganha uma proposta plausível — e diferente da vizinha.

        O que varia é o que o vendedor negocia de verdade: desconto, tamanho da
        entrada, prazo, sistema e balão. É o que faz a grade de clientes ter
        alguma coisa para comparar.
        """
        livres = [u for u in unidades if u.situacao == "disponivel"]
        aleatorio.shuffle(livres)
        vendas, vendidas = [], []

        for i, cliente in enumerate(clientes):
            # Uma minoria compra dois lotes — o caso que a visão por unidade e o
            # vínculo parcela↔unidade existem para resolver.
            for _ in range(2 if i % 11 == 0 else 1):
                if not livres:
                    break
                unidade = livres.pop()
                tabela = unidade.valor_base
                desconto = Decimal(aleatorio.choice([0, 0, 0, 3, 5, 8]))
                negociado = (tabela * (1 - desconto / 100)).quantize(Decimal("0.01"))
                entrada = (negociado * Decimal(aleatorio.choice(["0.10", "0.15", "0.20"]))).quantize(Decimal("0.01"))
                tem_balao = aleatorio.random() < 0.25
                balao = (negociado * Decimal("0.05")).quantize(Decimal("0.01")) if tem_balao else Decimal("0")
                compra = hoje - timedelta(days=aleatorio.randint(60, 1000))

                vendas.append(ClienteEmpreendimento(
                    tenant=tenant, cliente=cliente, empreendimento=unidade.empreendimento,
                    unidade=unidade, data_compra=compra,
                    condicoes_pagamento="financiamento_direto",
                    valor_tabela=tabela, desconto_percentual=desconto,
                    valor_compra=negociado,
                    entrada_valor=entrada, entrada_parcelas=aleatorio.choice([1, 3, 6]),
                    entrada_primeiro_vencimento=compra,
                    sistema_amortizacao=aleatorio.choice(["price", "price", "sac"]),
                    juros_mensal=Decimal(aleatorio.choice(["0", "0.5", "0.79", "1.0"])),
                    num_parcelas=aleatorio.choice([24, 36, 48]),
                    primeiro_vencimento=plano_pagamento.somar_meses(compra, 1),
                    balao_valor=balao, balao_quantidade=2 if tem_balao else 0,
                    balao_periodicidade="anual",
                    balao_primeiro_vencimento=plano_pagamento.somar_meses(compra, 12) if tem_balao else None,
                ))
                unidade.situacao = "vendida"
                vendidas.append(unidade)

        with transaction.atomic():
            ClienteEmpreendimento.objects.bulk_create(vendas, batch_size=500)
            Unidade.objects.bulk_update(vendidas, ["situacao"], batch_size=1000)
        return list(
            ClienteEmpreendimento.objects.filter(tenant=tenant)
            .select_related("cliente", "empreendimento", "unidade")
        )

    def _gerar_carnes(self, tenant, aquisicoes, hoje, aleatorio):
        """O carnê de cada venda, pelo motor de cálculo do produto.

        Quem já tem título não é reprocessado (o comando é reexecutável). O que
        venceu antes de hoje é sorteado entre pago e em atraso — sem isso a
        carteira inteira nasceria inadimplente, já que toda compra é do passado.
        """
        pendentes = [a for a in aquisicoes if a.parcelas_geradas_em is None]
        if not pendentes:
            return 0

        # Um ajustador de vencimento por EMPREENDIMENTO, não por aquisição: o
        # calendário bancário depende da praça do imóvel, que é a mesma para
        # todos os lotes do loteamento. Sem este cache, semear 2000 vendas seria
        # 2000 consultas de `Local` e 2000 de feriados para sempre a mesma
        # resposta — e o comando existe justamente para provar volume.
        ajustes = {}
        for aquisicao in pendentes:
            if aquisicao.empreendimento_id not in ajustes:
                ajustes[aquisicao.empreendimento_id] = vencimento_svc.ajuste_do_empreendimento(
                    aquisicao.empreendimento
                )

        titulos, geradas = [], []
        for aquisicao in pendentes:
            try:
                plano = plano_pagamento.montar_da_aquisicao(
                    aquisicao, ajustar_vencimento=ajustes[aquisicao.empreendimento_id],
                )
            except ValueError:
                continue
            totais = {}
            for parcela in plano.parcelas:
                totais[parcela.tipo] = totais.get(parcela.tipo, 0) + 1
            # 3 em cada 4 compradores estão em dia: pagam tudo o que já venceu.
            pontual = aleatorio.random() < 0.75
            for parcela in plano.parcelas:
                vencida = parcela.vencimento < hoje
                quitada = vencida and pontual
                titulos.append(ContaReceber(
                    tenant=tenant, cliente=aquisicao.cliente,
                    empreendimento=aquisicao.empreendimento, cliente_empreendimento=aquisicao,
                    descricao=plano_pagamento.descricao_do_titulo(
                        parcela, totais[parcela.tipo], aquisicao,
                    ),
                    valor=parcela.valor,
                    valor_pago=parcela.valor if quitada else Decimal("0"),
                    data_emissao=aquisicao.data_compra,
                    data_vencimento=parcela.vencimento,
                    data_recebimento=parcela.vencimento if quitada else None,
                    status=StatusConta.QUITADO if quitada else StatusConta.ABERTO,
                ))
            # `bulk_create` não passa pelo serializer, que é quem normalmente
            # grava o total do plano — sem isto a ficha mostraria "R$ 0,00" de
            # desembolso para uma venda que tem carnê.
            aquisicao.valor_total_plano = plano.total
            aquisicao.parcelas_geradas_em = timezone.now()
            geradas.append(aquisicao)

        with transaction.atomic():
            ContaReceber.objects.bulk_create(titulos, batch_size=1000)
            ClienteEmpreendimento.objects.bulk_update(
                geradas, ["valor_total_plano", "parcelas_geradas_em"], batch_size=500,
            )
        return len(titulos)
