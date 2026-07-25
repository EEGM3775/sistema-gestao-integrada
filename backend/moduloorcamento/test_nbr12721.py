# backend/moduloorcamento/test_nbr12721.py
"""Testes do ORC.4 — paramétrico (CUB) e os quadros da NBR 12721.

Aqui o critério de "certo" é mais duro que nos outros arquivos: os quadros
instruem **registro de incorporação em cartório**, e número que não fecha vira
exigência do registrador. Por isso os testes insistem nos fechamentos exatos —
soma dos coeficientes = 1,00000000 e soma do rateio = custo global, ao centavo,
mesmo com divisões que não são exatas.
"""
from datetime import date
from decimal import Decimal

from . import nbr12721, planilha
from .models import MemorialNBR, ParametroObra, PavimentoObra, UnidadeAutonoma
from .test_planilha import PlanilhaTestBase


class ParametricoTests(PlanilhaTestBase):
    def _parametro(self, **kwargs):
        dados = {
            "tenant": self.tenant, "obra": self.obra, "descricao": "Viabilidade",
            "projeto_padrao": "r8_n", "cub_m2": Decimal("2500.00"),
            "cub_uf": "SP", "cub_mes": date(2026, 7, 1),
            "area_real": Decimal("1000.00"), "area_equivalente": Decimal("800.00"),
        }
        dados.update(kwargs)
        return ParametroObra.objects.create(**dados)

    def test_custo_multiplica_a_area_equivalente_e_nao_a_real(self):
        """Garagem e área descoberta custam menos — é a equivalente que paga."""
        parametro = nbr12721.calcular_parametrico(self._parametro())
        self.assertEqual(parametro.custo_estimado, Decimal("2000000.00"))

    def test_adicionais_percentuais_incidem_so_sobre_o_custo_do_cub(self):
        """O percentual não pode incidir sobre os valores fechados, senão o
        terreno pagaria taxa de elevador."""
        parametro = nbr12721.calcular_parametrico(self._parametro(
            percentual_adicionais=Decimal("10.00"), valor_adicionais=Decimal("500000.00"),
        ))
        # 800 × 2500 = 2.000.000 · +10% = 200.000 · + 500.000 fechados
        self.assertEqual(parametro.custo_estimado, Decimal("2700000.00"))

    def test_sincronizar_area_puxa_dos_pavimentos(self):
        PavimentoObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Térreo", ordem=1,
            area_coberta_padrao=Decimal("300.00"), area_descoberta=Decimal("100.00"),
            coeficiente_descoberta=Decimal("0.3000"),
        )
        PavimentoObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Tipo", ordem=2,
            area_coberta_padrao=Decimal("500.00"),
        )
        parametro = nbr12721.calcular_parametrico(
            self._parametro(area_real=Decimal("0"), area_equivalente=Decimal("0")),
            sincronizar_area=True,
        )
        # real: 300+100+500 = 900 · equivalente: 300 + 100×0,3 + 500 = 830
        self.assertEqual(parametro.area_real, Decimal("900.00"))
        self.assertEqual(parametro.area_equivalente, Decimal("830.00"))
        self.assertEqual(parametro.custo_estimado, Decimal("2075000.00"))

    def test_comparacao_com_analitico_mede_o_desvio(self):
        parametro = nbr12721.calcular_parametrico(self._parametro())
        orc = self._orcamento()
        self._linha(orc, "Obra toda", quantidade="1", custo="2200000")
        planilha.aprovar_orcamento(orc)

        comparacao = nbr12721.comparar_parametrico_com_analitico(parametro)
        self.assertEqual(comparacao["parametrico"], "2000000.00")
        self.assertEqual(comparacao["analitico"], "2200000.00")
        self.assertEqual(comparacao["desvio"], "200000.00")
        self.assertEqual(comparacao["desvio_pct"], "10.00")

    def test_sem_analitico_a_comparacao_diz_isso(self):
        parametro = nbr12721.calcular_parametrico(self._parametro())
        comparacao = nbr12721.comparar_parametrico_com_analitico(parametro)

        self.assertIsNone(comparacao["analitico"])
        self.assertIn("não tem orçamento analítico", comparacao["detalhe"])


class QuadroITests(PlanilhaTestBase):
    def test_area_equivalente_aplica_coeficiente_por_natureza(self):
        PavimentoObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Garagem", ordem=1,
            area_coberta_padrao=Decimal("0"),
            area_coberta_diferente=Decimal("400.00"),
            coeficiente_coberta_diferente=Decimal("0.5000"),
            area_descoberta=Decimal("200.00"),
            coeficiente_descoberta=Decimal("0.3000"),
        )
        quadro = nbr12721.quadro_i(self.tenant.id, self.obra.pk)

        # real: 400 + 200 = 600 · equivalente: 400×0,5 + 200×0,3 = 260
        self.assertEqual(quadro["area_real_global"], "600.00")
        self.assertEqual(quadro["area_equivalente_global"], "260.00")

    def test_quadro_vazio_nao_quebra(self):
        quadro = nbr12721.quadro_i(self.tenant.id, self.obra.pk)
        self.assertEqual(quadro["pavimentos"], [])
        self.assertEqual(quadro["area_equivalente_global"], "0.00")


class CoeficientesTests(PlanilhaTestBase):
    def _unidade(self, designacao, area, **kwargs):
        return UnidadeAutonoma.objects.create(
            tenant=self.tenant, obra=self.obra, designacao=designacao,
            area_privativa_padrao=Decimal(area), **kwargs
        )

    def test_coeficientes_somam_exatamente_um(self):
        """Três unidades iguais: 1/3 cada, que não é exato em 8 casas. O resíduo
        vai na maior — soma 0,99999999 é exigência no cartório."""
        for i in range(3):
            self._unidade(f"Apto {i + 1}", "100.00")

        unidades = nbr12721.calcular_coeficientes(self.tenant.id, self.obra.pk)
        soma = sum(u.coeficiente_proporcionalidade for u in unidades)
        self.assertEqual(soma, Decimal("1.00000000"))

    def test_coeficiente_e_proporcional_a_area_equivalente(self):
        self._unidade("Apto 101", "100.00")
        self._unidade("Cobertura", "300.00")

        nbr12721.calcular_coeficientes(self.tenant.id, self.obra.pk)
        apto = UnidadeAutonoma.objects.get(designacao="Apto 101")
        cobertura = UnidadeAutonoma.objects.get(designacao="Cobertura")

        self.assertEqual(apto.coeficiente_proporcionalidade, Decimal("0.25000000"))
        self.assertEqual(cobertura.coeficiente_proporcionalidade, Decimal("0.75000000"))

    def test_area_de_padrao_diferente_pesa_menos_no_coeficiente(self):
        """Vaga/varanda entram pela equivalente, não pela real."""
        self._unidade("Apto 101", "100.00")
        self._unidade(
            "Apto 102", "100.00",
            area_privativa_diferente=Decimal("100.00"),
            coeficiente_privativa_diferente=Decimal("0.5000"),
        )
        nbr12721.calcular_coeficientes(self.tenant.id, self.obra.pk)
        um = UnidadeAutonoma.objects.get(designacao="Apto 101")
        dois = UnidadeAutonoma.objects.get(designacao="Apto 102")

        # equivalentes: 100 e 150 → 40% e 60%
        self.assertEqual(um.coeficiente_proporcionalidade, Decimal("0.40000000"))
        self.assertEqual(dois.coeficiente_proporcionalidade, Decimal("0.60000000"))

    def test_fracao_ideal_nao_e_escrita_sem_pedir(self):
        """Coeficiente é rateio de custo; fração ideal é quota do terreno, e
        decidi-la é do incorporador, não do sistema."""
        self._unidade("Apto 101", "100.00")
        nbr12721.calcular_coeficientes(self.tenant.id, self.obra.pk)

        unidade = UnidadeAutonoma.objects.get(designacao="Apto 101")
        self.assertEqual(unidade.coeficiente_proporcionalidade, Decimal("1.00000000"))
        self.assertEqual(unidade.fracao_ideal, Decimal("0"))

    def test_replicar_na_fracao_ideal_quando_pedido(self):
        self._unidade("Apto 101", "100.00")
        nbr12721.calcular_coeficientes(
            self.tenant.id, self.obra.pk, replicar_na_fracao_ideal=True
        )
        unidade = UnidadeAutonoma.objects.get(designacao="Apto 101")
        self.assertEqual(unidade.fracao_ideal, Decimal("1.00000000"))

    def test_sem_area_e_recusado_com_mensagem_util(self):
        self._unidade("Apto 101", "0")
        with self.assertRaises(nbr12721.DadosInsuficientes) as ctx:
            nbr12721.calcular_coeficientes(self.tenant.id, self.obra.pk)
        self.assertIn("área equivalente", str(ctx.exception))


class QuadroIIIeIVTests(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        PavimentoObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Tipo", ordem=1,
            area_coberta_padrao=Decimal("800.00"),
        )
        for i in range(3):
            UnidadeAutonoma.objects.create(
                tenant=self.tenant, obra=self.obra, designacao=f"Apto {i + 1}",
                area_privativa_padrao=Decimal("100.00"),
            )
        nbr12721.calcular_coeficientes(self.tenant.id, self.obra.pk)

    def _analitico(self, valor="1000000"):
        orc = self._orcamento()
        self._linha(orc, "Obra toda", quantidade="1", custo=valor)
        planilha.aprovar_orcamento(orc)
        return orc

    def _parametrico(self, valor_cub="1250.00"):
        return nbr12721.calcular_parametrico(ParametroObra.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Viabilidade",
            projeto_padrao="r8_n", cub_m2=Decimal(valor_cub),
            area_real=Decimal("800.00"), area_equivalente=Decimal("800.00"),
        ))

    def test_quadro_iii_prefere_o_analitico_e_declara_a_fonte(self):
        self._analitico("1000000")
        parametro = self._parametrico()

        quadro = nbr12721.quadro_iii(self.tenant.id, self.obra.pk, parametro=parametro)
        self.assertEqual(quadro["custo_global"], "1000000.00")
        self.assertEqual(quadro["fonte_do_custo"], "orcamento_analitico")
        self.assertEqual(quadro["custo_por_m2_equivalente"], "1250.00")

    def test_quadro_iii_cai_no_parametrico_declarando_isso(self):
        parametro = self._parametrico()
        quadro = nbr12721.quadro_iii(self.tenant.id, self.obra.pk, parametro=parametro)

        self.assertEqual(quadro["custo_global"], "1000000.00")
        self.assertEqual(quadro["fonte_do_custo"], "parametrico_cub")

    def test_sem_base_de_custo_o_quadro_iii_recusa(self):
        with self.assertRaises(nbr12721.DadosInsuficientes):
            nbr12721.quadro_iii(self.tenant.id, self.obra.pk)

    def test_rateio_do_quadro_iv_fecha_no_centavo(self):
        """1.000.000 entre 3 unidades iguais não divide exato — a soma das
        partes tem de dar o todo mesmo assim."""
        self._analitico("1000000")
        quadro = nbr12721.quadro_iv(self.tenant.id, self.obra.pk)

        self.assertEqual(quadro["total_rateado"], "1000000.00")
        custos = sorted(Decimal(u["custo_estimado"]) for u in quadro["unidades"])
        self.assertEqual(sum(custos), Decimal("1000000.00"))
        # Duas unidades a 333.333,33 e uma absorvendo o resíduo.
        self.assertEqual(custos[0], Decimal("333333.33"))
        self.assertEqual(custos[-1], Decimal("333333.34"))

    def test_rateio_grava_o_custo_na_unidade(self):
        self._analitico("900000")
        nbr12721.quadro_iv(self.tenant.id, self.obra.pk)

        unidade = UnidadeAutonoma.objects.get(designacao="Apto 1")
        self.assertEqual(unidade.custo_estimado, Decimal("300000.00"))

    def test_rateio_sem_gravar_nao_toca_no_banco(self):
        self._analitico("900000")
        nbr12721.quadro_iv(self.tenant.id, self.obra.pk, gravar=False)

        unidade = UnidadeAutonoma.objects.get(designacao="Apto 1")
        self.assertEqual(unidade.custo_estimado, Decimal("0.00"))

    def test_rateio_sem_coeficientes_e_recusado(self):
        self._analitico("900000")
        UnidadeAutonoma.objects.filter(obra=self.obra).update(
            coeficiente_proporcionalidade=Decimal("0")
        )
        with self.assertRaises(nbr12721.DadosInsuficientes) as ctx:
            nbr12721.quadro_iv(self.tenant.id, self.obra.pk)
        self.assertIn("coeficientes", str(ctx.exception).lower())


class QuadrosDescritivosTests(PlanilhaTestBase):
    def test_agrupa_por_quadro_e_aponta_o_que_falta(self):
        MemorialNBR.objects.create(
            tenant=self.tenant, obra=self.obra, quadro=MemorialNBR.Quadro.VII,
            dependencia="Sala", descricao="Piso porcelanato 60×60",
        )
        descritivos = nbr12721.quadros_descritivos(self.tenant.id, self.obra.pk)

        self.assertEqual(descritivos["preenchidos"], ["vii"])
        self.assertEqual(descritivos["faltando"], ["v", "vi", "viii"])
        self.assertEqual(descritivos["quadros"]["vii"]["linhas"][0]["dependencia"], "Sala")


class DossieTests(PlanilhaTestBase):
    def test_dossie_monta_o_que_da_e_explica_o_que_falta(self):
        """Incorporação é processo incremental — um quadro sem base não pode
        derrubar os outros sete."""
        PavimentoObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Tipo", ordem=1,
            area_coberta_padrao=Decimal("800.00"),
        )
        dossie = nbr12721.dossie(self.tenant.id, self.obra.pk)

        self.assertEqual(dossie["quadros"]["I"]["area_equivalente_global"], "800.00")
        self.assertIn("II", dossie["quadros"])
        # Sem custo e sem unidades, III e IV ficam indisponíveis com motivo.
        self.assertIn("III", dossie["indisponivel"])
        self.assertIn("IV", dossie["indisponivel"])
        self.assertEqual(dossie["descritivos_faltando"], ["v", "vi", "vii", "viii"])


class NBRAPITests(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        self.autenticar()

    def test_criar_parametrico_pela_api_calcula(self):
        resp = self.client.post("/api/orcamento/parametricos/", {
            "obra": self.obra.pk, "descricao": "Viabilidade", "projeto_padrao": "r8_n",
            "cub_m2": "2500.00", "area_real": "1000.00", "area_equivalente": "800.00",
        }, format="json")

        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Decimal(resp.data["custo_estimado"]), Decimal("2000000.00"))

    def test_dossie_pela_api(self):
        PavimentoObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Tipo", ordem=1,
            area_coberta_padrao=Decimal("800.00"),
        )
        resp = self.client.get(f"/api/orcamento/nbr12721/?obra={self.obra.pk}")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["quadros"]["I"]["area_equivalente_global"], "800.00")

    def test_quadro_isolado_pela_api(self):
        UnidadeAutonoma.objects.create(
            tenant=self.tenant, obra=self.obra, designacao="Apto 101",
            area_privativa_padrao=Decimal("100.00"),
        )
        resp = self.client.get(f"/api/orcamento/nbr12721/?obra={self.obra.pk}&quadro=II")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["quadro"], "II")
        self.assertEqual(len(resp.data["unidades"]), 1)

    def test_calcular_coeficientes_pela_api(self):
        for i in range(2):
            UnidadeAutonoma.objects.create(
                tenant=self.tenant, obra=self.obra, designacao=f"Apto {i + 1}",
                area_privativa_padrao=Decimal("100.00"),
            )
        resp = self.client.post("/api/orcamento/nbr12721/", {
            "obra": self.obra.pk, "acao": "coeficientes",
        }, format="json")

        self.assertEqual(resp.status_code, 200, resp.content)
        coeficientes = [u["coeficiente_proporcionalidade"] for u in resp.data["unidades"]]
        self.assertEqual(coeficientes, ["0.50000000", "0.50000000"])

    def test_quadro_sem_base_responde_409(self):
        resp = self.client.get(f"/api/orcamento/nbr12721/?obra={self.obra.pk}&quadro=III")
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_obra_ausente_e_400(self):
        resp = self.client.get("/api/orcamento/nbr12721/")
        self.assertEqual(resp.status_code, 400)

    def test_coeficiente_enviado_pelo_cliente_e_ignorado(self):
        """Rateio que não fecha com o custo global é exigência no cartório."""
        resp = self.client.post("/api/orcamento/unidades/", {
            "obra": self.obra.pk, "designacao": "Apto 101",
            "area_privativa_padrao": "100.00",
            "coeficiente_proporcionalidade": "0.99999999",
            "fracao_ideal": "0.12345678",
        }, format="json")

        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Decimal(resp.data["coeficiente_proporcionalidade"]), Decimal("0"))
        # A fração ideal É aceita: é decisão jurídica, não resultado de conta.
        self.assertEqual(Decimal(resp.data["fracao_ideal"]), Decimal("0.12345678"))

    def test_nbr_exige_permissao_de_relatorio(self):
        self.autenticar(perms=["orcamento.orcamento.view"])
        resp = self.client.get(f"/api/orcamento/nbr12721/?obra={self.obra.pk}")
        self.assertEqual(resp.status_code, 403)

    def test_pavimento_de_outra_obra_e_400(self):
        from obras.models import Obra

        outra = Obra.objects.create(tenant=self.tenant, nome_obra="Outra", endereco="Rua B")
        alheio = PavimentoObra.objects.create(
            tenant=self.tenant, obra=outra, nome="Tipo", ordem=1,
        )
        resp = self.client.post("/api/orcamento/unidades/", {
            "obra": self.obra.pk, "designacao": "Apto 101",
            "area_privativa_padrao": "100.00", "pavimento": alheio.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)
