"""Os achados do teste do dono de 09/10/2026 — o que cada correção prende.

- o feriado/parada que entra **depois** do cálculo é apontado nas barras que o
  contavam como dia de obra (a versão congelada não recalcula sozinha);
- a versão nova do replanejamento **nasce calculada** (o Gantt não abre zerado);
- as **etapas da obra** seguem as raízes do plano em vigor: nascem, renomeiam,
  vão para a lixeira e voltam com elas;
- o julgamento da semana é pelo **% concluído**: vira apontamento de avanço e
  decide o "saiu" contra a meta;
- a **equipe** é uma composição (funcionários e fornecedores), e o cartão se
  liga a ela pelo nome.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from fornecedores.models import Fornecedor
from modulocalendar.models import Feriado
from nucleo.models import Tenant
from obras.models import EtapaObra, Obra

from modulopdca import etapas, services
from modulopdca.models import (
    ApontamentoAvanco, Atividade, CalendarioTrabalho, CausaNaoCumprimento,
    Cronograma, EquipeObra, ExcecaoCalendario, ItemProgramacao,
)
from modulopdca.serializers import EquipeObraSerializer, ItemProgramacaoSerializer


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-0910", nome="Construtora 0910")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra 0910", endereco="Rua do Teste",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )

    def setUp(self):
        Feriado.objects.all().delete()

    def _plano(self, **extra):
        return Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario, **extra,
        )

    def _atividade(self, cronograma, codigo, nome=None, duracao=5, pai=None):
        return Atividade.objects.create(
            tenant=self.tenant, cronograma=cronograma, pai=pai, codigo=codigo,
            nome=nome or f"Serviço {codigo}", duracao_dias=duracao,
            profundidade=1 if pai is None else pai.profundidade + 1,
        )


class ForaDoExpedienteTests(_Base):
    def test_a_parada_depois_do_calculo_aparece_na_barra(self):
        plano = self._plano()
        a = self._atividade(plano, "1", duracao=5)  # 01/06 (seg) a 05/06 (sex)
        services.calcular_cpm(plano)
        atividades = list(plano.atividades.all())
        self.assertEqual(services.datas_fora_do_expediente(plano, atividades)["total"], 0)

        ExcecaoCalendario.objects.create(
            tenant=self.tenant, calendario=self.calendario,
            data=date(2026, 6, 3), trabalha=False, motivo="Feriado municipal",
        )
        fora = services.datas_fora_do_expediente(plano, list(plano.atividades.all()))
        self.assertEqual(fora["total"], 1)
        linha = fora["atividades"][0]
        self.assertEqual(linha["atividade"], a.pk)
        self.assertEqual(linha["uteis_hoje"], 4)
        self.assertEqual(linha["dias"], [{"data": date(2026, 6, 3), "motivo": "exceção: parado"}])

    def test_recalcular_tira_o_aviso(self):
        plano = self._plano()
        self._atividade(plano, "1", duracao=5)
        services.calcular_cpm(plano)
        ExcecaoCalendario.objects.create(
            tenant=self.tenant, calendario=self.calendario,
            data=date(2026, 6, 3), trabalha=False,
        )
        services.calcular_cpm(plano)
        self.assertEqual(
            services.datas_fora_do_expediente(plano, list(plano.atividades.all()))["total"], 0,
        )

    def test_plano_nunca_calculado_nao_acusa_nada(self):
        plano = self._plano()
        self._atividade(plano, "1")
        self.assertEqual(services.datas_fora_do_expediente(plano, list(plano.atividades.all()))["total"], 0)


class ReplanejarNasceCalculadoTests(_Base):
    def test_a_versao_nova_ja_tem_datas(self):
        plano = self._plano()
        self._atividade(plano, "1", duracao=5)
        services.publicar(plano)
        nova = services.replanejar(plano, motivo="Chuva")
        nova.refresh_from_db()
        self.assertIsNotNone(nova.calculado_em)
        copia = nova.atividades.get(codigo="1")
        self.assertEqual(copia.inicio_cedo, date(2026, 6, 1))
        self.assertEqual(copia.termino_cedo, date(2026, 6, 5))


class EtapasDaObraSeguemOPlanoTests(_Base):
    def _vivas(self):
        return list(EtapaObra.objects.filter(obra=self.obra).order_by("ordem")
                    .values_list("nome_etapa", flat=True))

    def test_a_raiz_vira_etapa_da_obra_com_ordem_e_datas(self):
        plano = self._plano()
        r1 = self._atividade(plano, "1", "Fundação", duracao=5)
        self._atividade(plano, "2", "Estrutura", duracao=3)
        services.calcular_cpm(plano)
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        self.assertEqual(self._vivas(), ["Fundação", "Estrutura"])
        r1.refresh_from_db()
        etapa = EtapaObra.objects.get(pk=r1.etapa_id)
        self.assertEqual(etapa.data_inicio_prevista, date(2026, 6, 1))
        self.assertEqual(etapa.data_fim_prevista, date(2026, 6, 5))

    def test_a_etapa_cadastrada_a_mao_com_o_mesmo_nome_e_ligada(self):
        manual = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Fundação", ordem=9,
        )
        plano = self._plano()
        raiz = self._atividade(plano, "1", "Fundação")
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        raiz.refresh_from_db()
        self.assertEqual(raiz.etapa_id, manual.pk)
        self.assertEqual(EtapaObra.objects.filter(obra=self.obra).count(), 1)

    def test_excluir_a_raiz_manda_a_etapa_para_a_lixeira_e_ela_volta(self):
        plano = self._plano()
        raiz = self._atividade(plano, "1", "Fundação")
        self._atividade(plano, "2", "Estrutura")
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        etapa_id = Atividade.objects.get(pk=raiz.pk).etapa_id

        raiz.delete()
        # O sinal da exclusão é quem diz que a etapa era desta raiz.
        etapas.sincronizar(self.obra.pk, self.tenant.pk, soltas={etapa_id})
        self.assertEqual(self._vivas(), ["Estrutura"])
        self.assertIsNotNone(EtapaObra.todos.get(pk=etapa_id).excluido_em)

        # O Ctrl+Z recria a raiz com o mesmo nome: a etapa sai da lixeira.
        self._atividade(plano, "1", "Fundação")
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        self.assertIsNone(EtapaObra.todos.get(pk=etapa_id).excluido_em)
        self.assertEqual(sorted(self._vivas()), ["Estrutura", "Fundação"])

    def test_o_rascunho_do_replanejamento_nao_mexe_na_obra_ate_publicar(self):
        plano = self._plano()
        self._atividade(plano, "1", "Fundação")
        self._atividade(plano, "2", "Estrutura")
        services.publicar(plano)
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        nova = services.replanejar(plano, motivo="Escopo")
        nova.atividades.get(codigo="2").delete()
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        self.assertEqual(sorted(self._vivas()), ["Estrutura", "Fundação"])

        services.publicar(nova)
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        self.assertEqual(self._vivas(), ["Fundação"])

    def test_renomear_a_raiz_renomeia_a_etapa(self):
        plano = self._plano()
        raiz = self._atividade(plano, "1", "Fundação")
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        raiz.refresh_from_db()
        raiz.nome = "Fundações e contenções"
        raiz.save()
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        self.assertEqual(self._vivas(), ["Fundações e contenções"])

    def test_duas_raizes_com_o_mesmo_nome_nao_derrubam_a_sincronia(self):
        plano = self._plano()
        self._atividade(plano, "1", "Nova etapa")
        self._atividade(plano, "2", "Nova etapa")
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        self.assertEqual(self._vivas(), ["Nova etapa", "Nova etapa (2)"])

    def test_a_obra_recusa_excluir_a_etapa_que_o_plano_tem(self):
        plano = self._plano()
        raiz = self._atividade(plano, "1", "Fundação")
        etapas.sincronizar(self.obra.pk, self.tenant.pk)
        etapa = EtapaObra.objects.get(pk=Atividade.objects.get(pk=raiz.pk).etapa_id)
        self.assertIn("PDCA", etapas.motivo_para_nao_excluir(etapa))
        solta = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Paisagismo", ordem=5,
        )
        self.assertIsNone(etapas.motivo_para_nao_excluir(solta))

    def test_a_etapa_cadastrada_na_obra_entra_no_plano_em_montagem(self):
        plano = self._plano()
        self._atividade(plano, "1", "Fundação")
        nova = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Cobertura", ordem=2,
        )
        self.assertTrue(etapas.puxar_para_o_plano(nova))
        raiz = plano.atividades.get(etapa=nova)
        self.assertIsNone(raiz.pai_id)
        self.assertEqual(raiz.nome, "Cobertura")

    def test_o_gesto_agenda_a_sincronia_no_fim_da_transacao(self):
        with self.captureOnCommitCallbacks(execute=True):
            plano = self._plano()
            raiz = self._atividade(plano, "1", "Fundação")
            self._atividade(plano, "2", "Estrutura")
        self.assertEqual(self._vivas(), ["Fundação", "Estrutura"])

        # Excluir pela porta de verdade (o sinal), sem chamar a sincronia à mão.
        with self.captureOnCommitCallbacks(execute=True):
            Atividade.objects.get(pk=raiz.pk).delete()
        self.assertEqual(self._vivas(), ["Estrutura"])


class _BaseSemana(_Base):
    def setUp(self):
        super().setUp()
        self.plano = self._plano(status=Cronograma.Status.VIGENTE)
        self.a1 = self._atividade(self.plano, "1", "Alvenaria do 4º", duracao=5)
        self.prog = services.abrir_programacao(
            obra=self.obra, semana_inicio=date(2026, 6, 1), tenant_id=self.tenant.pk,
        )


class JulgarPeloConcluidoTests(_BaseSemana):
    def _cartao(self, previsto=None):
        item = ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=self.prog, atividade=self.a1,
            percentual_previsto=previsto,
        )
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.a1, data=date(2026, 6, 2),
            percentual=Decimal("5"),
        )
        services.comprometer(programacao=self.prog, por="Ana")
        return item

    def _total(self):
        return sum(ApontamentoAvanco.objects.filter(atividade=self.a1)
                   .values_list("percentual", flat=True), Decimal("0"))

    def test_bater_a_meta_e_saiu_e_o_avanco_anda(self):
        item = self._cartao(previsto=Decimal("20"))
        andamento = services.andamento_dos_itens(self.prog)[item.pk]
        self.assertEqual(andamento["inicio"], Decimal("0"))
        self.assertEqual(andamento["meta"], Decimal("20"))

        resultado = services.julgar_itens(programacao=self.prog, julgamentos=[
            {"item": item.pk, "percentual_concluido": Decimal("25")},
        ], por="Ana")
        item.refresh_from_db()
        self.assertTrue(item.cumprido)
        self.assertEqual(item.percentual_concluido, Decimal("25"))
        self.assertEqual(resultado["apontamentos"], 1)
        self.assertEqual(self._total(), Decimal("25"))

    def test_abaixo_da_meta_pede_causa(self):
        item = self._cartao(previsto=Decimal("20"))
        with self.assertRaises(ValidationError):
            services.julgar_itens(programacao=self.prog, julgamentos=[
                {"item": item.pk, "percentual_concluido": Decimal("10")},
            ])
        causa = CausaNaoCumprimento.objects.filter(tenant=self.tenant).first()
        services.julgar_itens(programacao=self.prog, julgamentos=[
            {"item": item.pk, "percentual_concluido": Decimal("10"), "causa": causa.pk},
        ])
        item.refresh_from_db()
        self.assertFalse(item.cumprido)
        self.assertEqual(self._total(), Decimal("10"))

    def test_sem_promessa_a_meta_e_concluir(self):
        item = self._cartao()
        self.assertEqual(services.andamento_dos_itens(self.prog)[item.pk]["meta"], Decimal("100"))
        services.julgar_itens(programacao=self.prog, julgamentos=[
            {"item": item.pk, "percentual_concluido": Decimal("100")},
        ])
        item.refresh_from_db()
        self.assertTrue(item.cumprido)

    def test_concluido_abaixo_do_apontado_e_recusado(self):
        item = self._cartao(previsto=Decimal("20"))
        with self.assertRaises(ValidationError) as ctx:
            services.julgar_itens(programacao=self.prog, julgamentos=[
                {"item": item.pk, "percentual_concluido": Decimal("3")},
            ])
        self.assertIn("estorne", " ".join(ctx.exception.messages))
        self.assertEqual(self._total(), Decimal("5"))

    def test_julgar_de_novo_nao_lanca_o_avanco_duas_vezes(self):
        item = self._cartao(previsto=Decimal("20"))
        for _ in range(2):
            services.julgar_itens(programacao=self.prog, julgamentos=[
                {"item": item.pk, "percentual_concluido": Decimal("25")},
            ])
        self.assertEqual(self._total(), Decimal("25"))

    def test_o_caminho_binario_continua(self):
        item = self._cartao()
        services.julgar_itens(programacao=self.prog, julgamentos=[
            {"item": item.pk, "cumprido": True},
        ])
        item.refresh_from_db()
        self.assertTrue(item.cumprido)
        self.assertIsNone(item.percentual_concluido)
        self.assertEqual(self._total(), Decimal("5"))


class EquipeComoComposicaoTests(_BaseSemana):
    def setUp(self):
        super().setUp()
        self.fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Construtora X", email="x@ex.com",
        )

    def test_sem_membro_nao_e_equipe(self):
        s = EquipeObraSerializer(data={"obra": self.obra.pk, "nome": "Turma"})
        self.assertFalse(s.is_valid())

    def test_o_nome_vazio_nasce_dos_membros(self):
        s = EquipeObraSerializer(data={"obra": self.obra.pk, "fornecedores": [self.fornecedor.pk]})
        self.assertTrue(s.is_valid(), s.errors)
        equipe = s.save(tenant=self.tenant)
        self.assertEqual(equipe.nome, "Construtora X")
        self.assertEqual(
            EquipeObraSerializer(equipe).data["membros"],
            [{"tipo": "fornecedor", "id": self.fornecedor.pk, "nome": "Construtora X"}],
        )

    def test_o_cartao_movido_para_a_coluna_se_liga_a_equipe(self):
        equipe = EquipeObra.objects.create(tenant=self.tenant, obra=self.obra, nome="Equipe do Zé")
        equipe.fornecedores.add(self.fornecedor)
        item = ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=self.prog, atividade=self.a1,
        )
        s = ItemProgramacaoSerializer(item, data={"responsavel": "equipe do zé"}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        item.refresh_from_db()
        self.assertEqual(item.equipe_id, equipe.pk)

        s = ItemProgramacaoSerializer(item, data={"equipe": equipe.pk}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        item.refresh_from_db()
        self.assertEqual(item.responsavel, "Equipe do Zé")


class AvancoFisicoFinanceiroTests(_Base):
    """O avanço físico-financeiro é do PDCA: previsto pelas datas × realizado
    pelos apontamentos, em % e em reais do orçado. O cronograma (o planejado
    por competência) continua no Orçamento — e este cálculo não escreve lá."""

    def setUp(self):
        super().setUp()
        from moduloorcamento.models import ItemOrcado, Orcamento

        self.orcamento = Orcamento.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Executivo",
        )
        item = ItemOrcado.objects.create(
            tenant=self.tenant, orcamento=self.orcamento, codigo_eap="1.1",
            descricao="Estacas", tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
            quantidade=Decimal("1"), custo_unitario=Decimal("1000"),
            total_custo_direto=Decimal("1000"), total_com_bdi=Decimal("1000"),
        )
        self.plano = self._plano(status=Cronograma.Status.VIGENTE)
        raiz = self._atividade(self.plano, "1", "Fundação", duracao=None)
        # 10 dias úteis: 01/06 (seg) a 12/06 (sex).
        self.folha = self._atividade(self.plano, "1.1", "Estacas", duracao=10, pai=raiz)
        self.folha.item_orcado = item
        self.folha.save()
        # Uma folha sem orçamento: pesa no físico, fica fora do dinheiro.
        sem = self._atividade(self.plano, "1.2", "Limpeza", duracao=10, pai=raiz)
        sem.peso_informado = Decimal("1000")
        sem.save()
        services.calcular_cpm(self.plano)

    def test_previsto_pelas_datas_e_realizado_pelo_apontamento(self):
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.folha, data=date(2026, 6, 3),
            percentual=Decimal("20"),
        )
        # 05/06: 5 dos 10 dias úteis passaram.
        dados = services.avanco_fisico_financeiro(self.plano, hoje=date(2026, 6, 5))
        etapa = dados["linhas"][0]
        self.assertEqual(etapa["nome"], "Fundação")
        self.assertEqual(etapa["previsto_pct"], 50.0)
        self.assertEqual(etapa["realizado_pct"], 10.0)   # 20% de metade do peso
        self.assertEqual(etapa["desvio_pct"], -40.0)
        self.assertEqual(etapa["valor_orcado"], "1000.00")
        self.assertEqual(etapa["valor_previsto"], "500.00")
        self.assertEqual(etapa["valor_realizado"], "200.00")
        self.assertEqual(etapa["valor_desvio"], "-300.00")
        self.assertEqual(dados["folhas_sem_orcamento"], 1)
        self.assertEqual(dados["obra"]["realizado_pct"], 10.0)

    def test_nao_escreve_no_cronograma_do_orcamento(self):
        from moduloorcamento.models import ParcelaEtapa

        services.avanco_fisico_financeiro(self.plano)
        self.assertFalse(ParcelaEtapa.objects.filter(orcamento=self.orcamento).exists())

    def test_compara_com_o_cronograma_planejado_do_orcamento(self):
        from moduloorcamento.models import ParcelaEtapa

        etapa = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Fundação", ordem=1,
        )
        Atividade.objects.filter(cronograma=self.plano, codigo="1").update(etapa=etapa)
        # A parcela é da etapa do orçamento (a linha de 1º nível); o vínculo dela
        # com a etapa da obra é o que o PDCA usa para comparar.
        grupo = self.folha.item_orcado
        grupo.etapa = etapa
        grupo.save(update_fields=["etapa"])
        for mes, valor in ((date(2026, 6, 1), "600"), (date(2026, 7, 1), "400")):
            ParcelaEtapa.objects.create(
                tenant=self.tenant, orcamento=self.orcamento, grupo=grupo,
                competencia=mes, percentual=Decimal("50"), valor_previsto=Decimal(valor),
            )
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.folha, data=date(2026, 6, 3),
            percentual=Decimal("20"),
        )
        # 15/06: metade de junho planejada (R$ 300), julho ainda não.
        dados = services.avanco_fisico_financeiro(self.plano, hoje=date(2026, 6, 15))
        linha = dados["linhas"][0]
        self.assertEqual(linha["valor_planejado"], "300.00")
        self.assertEqual(linha["valor_desvio_planejado"], "-100.00")
        self.assertEqual(dados["obra"]["valor_planejado"], "300.00")
        self.assertEqual(dados["planejado"]["total"], "1000.00")
        self.assertEqual([m["pct_acumulado"] for m in dados["planejado"]["mensal"]], [60.0, 100.0])

    def test_sem_cronograma_no_orcamento_o_planejado_e_nulo(self):
        dados = services.avanco_fisico_financeiro(self.plano, hoje=date(2026, 6, 15))
        self.assertIsNone(dados["planejado"])
        self.assertIsNone(dados["linhas"][0]["valor_planejado"])


class MaterialSemOrcamentoTests(_Base):
    """'Se eu não tiver orçamento, não posso pedir?' — pode: o material informado
    na atividade entra na necessidade de compra como o do orçamento."""

    def test_material_informado_entra_na_necessidade_e_vai_no_replanejamento(self):
        from modulopdca import suprimentos
        from modulopdca.models import MaterialDaAtividade

        plano = self._plano(status=Cronograma.Status.VIGENTE)
        a = self._atividade(plano, "1", "Alvenaria", duracao=5)
        services.calcular_cpm(plano)
        MaterialDaAtividade.objects.create(
            tenant=self.tenant, atividade=a, descricao="Bloco cerâmico 9x19x29",
            unidade="un", quantidade=Decimal("1000"),
        )
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=a, data=date(2026, 6, 2), percentual=Decimal("40"),
        )
        dados = suprimentos.necessidade_de_material(plano, hoje=date(2026, 5, 1))
        self.assertEqual(len(dados["linhas"]), 1)
        linha = dados["linhas"][0]
        self.assertEqual(linha["origem"], "informado")
        self.assertEqual(Decimal(linha["a_comprar"]), Decimal("600"))
        self.assertEqual(dados["cobertura"]["folhas_fora_da_conta"], 0)

        nova = services.replanejar(plano, motivo="Escopo")
        self.assertEqual(MaterialDaAtividade.objects.filter(atividade__cronograma=nova).count(), 1)


class ContratoQueAndaTests(TestCase):
    """10/10/2026 — "o contrato fica em rascunho eternamente", e a planilha que
    se monta do orçamento, do plano ou do Excel, tudo de uma vez."""

    @classmethod
    def setUpTestData(cls):
        from modulopdca.models import ContratoObra
        cls.tenant = Tenant.objects.create(slug="pdca-ctr-anda", nome="Construtora Anda")
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Obra Anda", endereco="Rua 1")
        cls.fornecedor = Fornecedor.objects.create(
            tenant=cls.tenant, razao_social="Empreiteira Beta", email="beta@example.com",
        )
        cls.ContratoObra = ContratoObra

    def _contrato(self):
        return self.ContratoObra.objects.create(
            tenant=self.tenant, obra=self.obra, fornecedor=self.fornecedor, numero="01",
            objeto="Manilhas", data_inicio=date(2026, 6, 1),
        )

    def test_tornar_vigente_pede_a_planilha_e_depois_vira(self):
        contrato = self._contrato()
        self.assertEqual(contrato.status, self.ContratoObra.Status.RASCUNHO)
        with self.assertRaises(ValidationError):
            services.ativar_contrato(contrato)
        services.incluir_na_planilha(contrato, [
            {"codigo": "01", "descricao": "Assentar manilhas", "unidade": "m",
             "quantidade_contratada": "75", "preco_unitario": "2500"},
        ])
        services.ativar_contrato(contrato)
        contrato.refresh_from_db()
        self.assertEqual(contrato.status, self.ContratoObra.Status.VIGENTE)

    def test_inclusao_em_lote_recusa_codigo_repetido_e_e_tudo_ou_nada(self):
        contrato = self._contrato()
        with self.assertRaises(ValidationError) as ctx:
            services.incluir_na_planilha(contrato, [
                {"codigo": "01", "descricao": "A", "quantidade_contratada": "1", "preco_unitario": "1"},
                {"codigo": "01", "descricao": "B", "quantidade_contratada": "1", "preco_unitario": "1"},
            ])
        self.assertIn("01", " ".join(ctx.exception.messages))
        self.assertFalse(contrato.itens.exists())

    def test_fontes_trazem_as_atividades_folha_do_plano(self):
        plano = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano", data_inicio=date(2026, 6, 1),
        )
        etapa = Atividade.objects.create(tenant=self.tenant, cronograma=plano, codigo="1", nome="Drenagem", profundidade=1)
        folha = Atividade.objects.create(
            tenant=self.tenant, cronograma=plano, pai=etapa, codigo="1.1", nome="Manilhas",
            duracao_dias=5, profundidade=2,
        )
        contrato = self._contrato()
        fontes = services.fontes_da_planilha(contrato)
        self.assertEqual([a["atividade"] for a in fontes["atividades"]], [folha.pk])
        services.incluir_na_planilha(contrato, [
            {"codigo": "1.1", "descricao": "Manilhas", "unidade": "m",
             "quantidade_contratada": "10", "preco_unitario": "100", "atividade": folha.pk},
        ])
        self.assertTrue(services.fontes_da_planilha(contrato)["atividades"][0]["ja_no_contrato"])