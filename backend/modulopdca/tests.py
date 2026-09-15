"""PDCA.0 e PDCA.1 — o esqueleto da obra, o calendário e o plano de tempo.

O que estes testes protegem, em uma frase cada:

- a **árvore** não vira recursão sem fundo nem cresce sem teto (o D57 ensinou que
  todo caminho proporcional a uma entrada do cliente precisa de limite superior);
- o **gerador em lote** conta antes de escrever, e rodar duas vezes não duplica;
- o **calendário** conta dias úteis com a precedência certa entre exceção,
  feriado e regra da semana — porque é dele que sai a data que vira prazo;
- as **duas camadas de acesso** (entitlement e permissão) fecham a porta, e o
  tenant vizinho não enxerga nada.

E, da PDCA.1:

- o **CPM** converte duração em data pelo calendário certo, acha o caminho
  crítico e devolve folga que fecha a conta — inclusive com feriado, exceção,
  calendário por atividade e os quatro tipos de precedência;
- o **ciclo** é recusado com os nomes das atividades, e não com "erro ao calcular";
- o **versionamento** publica, replaneja e preserva a versão anterior legível
  inteira — que é o que faz dela uma linha de base;
- o **peso** diz de onde veio, e diz "sem apuração" em vez de zero.

E, da PDCA.2:

- o livro do avanço **não se reescreve** — nem pelo model, nem pela API;
- o avanço **sobe a árvore ponderado**, e folha sem peso fica fora da média com o
  denominador declarado;
- as recusas acontecem **antes** da escrita: sintética, marco, plano não vigente
  e acumulado fora de 0–100;
- o avanço **atravessa o replanejamento** pelo código da EAP;
- a curva S realizada **para** onde a obra parou de apontar, e a granularidade
  engrossa **declarando** qual valeu;
- o percentual da etapa vira **apurado**, e a caneta passa a ter dono.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from modulocalendar.models import Feriado
from nucleo.models import Tenant, Usuario
from obras.models import EtapaObra, Obra
from payment.planos import (
    PDCA_PROFUNDIDADE_MAXIMA_LOCAL, PDCA_TETO_APONTAMENTOS_POR_LOTE,
    PDCA_TETO_LOCAIS_POR_GERACAO, PDCA_TETO_PONTOS_CURVA_S,
)

from . import services
from .models import (
    ApontamentoAvanco, Atividade, CalendarioTrabalho, ContratoObra, Cronograma,
    ExcecaoCalendario, ItemContrato, ItemMedicao, LiberacaoRetencao, LocalObra,
    Medicao, NaturezaRetencao, NivelLocal, OrigemCusto, Precedencia,
    RegimeContrato,
)


class ArvoreDeLocaisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-arv", nome="Construtora Árvore")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Aurora", endereco="Rua 1",
        )

    def _local(self, codigo, pai=None, nivel=NivelLocal.BLOCO):
        return LocalObra.objects.create(
            tenant=self.tenant, obra=self.obra, pai=pai, nivel=nivel,
            codigo=codigo, nome=codigo,
            profundidade=services.profundidade_de(pai),
        )

    def test_a_profundidade_acompanha_o_pai(self):
        torre = self._local("T1")
        pav = self._local("P01", pai=torre, nivel=NivelLocal.PAVIMENTO)
        apto = self._local("101", pai=pav, nivel=NivelLocal.UNIDADE)
        self.assertEqual((torre.profundidade, pav.profundidade, apto.profundidade), (1, 2, 3))

    def test_o_teto_de_profundidade_vem_do_payment(self):
        pai = None
        for n in range(PDCA_PROFUNDIDADE_MAXIMA_LOCAL):
            pai = self._local(f"N{n}", pai=pai, nivel=NivelLocal.AREA)
        with self.assertRaises(ValidationError):
            services.validar_profundidade(pai)

    def test_codigo_repetido_entre_irmaos_e_barrado(self):
        torre = self._local("T1")
        self._local("P01", pai=torre, nivel=NivelLocal.PAVIMENTO)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._local("P01", pai=torre, nivel=NivelLocal.PAVIMENTO)

    def test_codigo_repetido_na_raiz_tambem_e_barrado(self):
        """No Postgres dois NULL são distintos: sem a constraint parcial própria
        da raiz, duas torres 'T1' passariam — o caso exato do gerador chamado
        duas vezes."""
        self._local("T1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._local("T1")

    def test_o_mesmo_codigo_em_pais_diferentes_convive(self):
        """O apartamento 101 existe na torre 1 e na torre 2, e são dois lugares
        diferentes. Unicidade global de código quebraria toda obra com mais de
        uma torre."""
        t1, t2 = self._local("T1"), self._local("T2")
        self._local("101", pai=t1, nivel=NivelLocal.UNIDADE)
        self._local("101", pai=t2, nivel=NivelLocal.UNIDADE)
        self.assertEqual(LocalObra.objects.filter(codigo="101").count(), 2)


class GeradorEmLoteTests(TestCase):
    """"Torre A, pavimentos 1 a 20, quatro unidades por andar" — a frase curta
    que produz 1.600 linhas, e o motivo de o teto existir."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-ger", nome="Construtora Gerador")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Torre Única", endereco="Rua 2",
        )

    def _receita(self, pavimentos=4, unidades=2):
        return [
            {"nivel": "bloco", "itens": [{"codigo": "T1", "nome": "Torre 1"}]},
            {"nivel": "pavimento", "de": 1, "ate": pavimentos,
             "formato_codigo": "P{n:02d}", "formato_nome": "{n}º pavimento"},
            {"nivel": "unidade", "itens": [str(100 + i) for i in range(1, unidades + 1)]},
        ]

    def _gerar(self, **kwargs):
        return services.gerar_em_lote(
            obra=self.obra, tenant_id=self.tenant.id, receita=self._receita(**kwargs),
        )

    def test_a_arvore_sai_com_a_forma_pedida(self):
        relatorio = self._gerar(pavimentos=4, unidades=2)
        # 1 torre + 4 pavimentos + 8 unidades
        self.assertEqual(relatorio["total_previsto"], 13)
        self.assertEqual(relatorio["criados"], 13)
        self.assertEqual(LocalObra.objects.filter(nivel="unidade").count(), 8)
        self.assertEqual(
            LocalObra.objects.filter(nivel="pavimento").first().profundidade, 2,
        )

    def test_o_formato_numera_com_zero_a_esquerda(self):
        """'P10' antes de 'P9' é o defeito clássico de ordenar por texto — o
        formato existe para o cliente não ter de saber disso."""
        self._gerar(pavimentos=12, unidades=1)
        codigos = list(
            LocalObra.objects.filter(nivel="pavimento").order_by("codigo")
            .values_list("codigo", flat=True)
        )
        self.assertEqual(codigos[:3], ["P01", "P02", "P03"])

    def test_simular_conta_sem_escrever(self):
        """A tela pergunta antes de fazer. Sem isto o cliente descobre que pediu
        16.000 locais depois de tê-los criado."""
        relatorio = services.gerar_em_lote(
            obra=self.obra, tenant_id=self.tenant.id, receita=self._receita(),
            simular=True,
        )
        self.assertTrue(relatorio["simulado"])
        self.assertEqual(relatorio["criados"], 0)
        self.assertGreater(relatorio["total_previsto"], 0)
        self.assertEqual(LocalObra.objects.count(), 0)

    def test_rodar_duas_vezes_nao_duplica(self):
        """Clique dobrado e retry do navegador são o caso comum, não o exótico."""
        self._gerar()
        segundo = self._gerar()
        self.assertEqual(segundo["criados"], 0)
        self.assertEqual(segundo["ja_existiam"], 13)
        self.assertEqual(LocalObra.objects.count(), 13)

    def test_o_teto_por_geracao_conta_o_PRODUTO_e_nao_as_linhas_da_receita(self):
        """Três linhas de formulário produzem milhares de locais — é o produto
        cartesiano que o teto precisa ver."""
        with self.assertRaises(ValidationError) as erro:
            services.gerar_em_lote(
                obra=self.obra, tenant_id=self.tenant.id,
                receita=self._receita(pavimentos=60, unidades=40), simular=True,
            )
        self.assertIn(
            f"{PDCA_TETO_LOCAIS_POR_GERACAO:,}".replace(",", "."),
            str(erro.exception),
            "a recusa tem de dizer QUAL é o limite, e em português",
        )

    def test_receita_vazia_ou_sem_forma_e_recusada(self):
        for receita in ([], [{"nivel": "bloco"}], [{"nivel": "inexistente", "itens": ["X"]}]):
            with self.assertRaises(ValidationError):
                services.gerar_em_lote(
                    obra=self.obra, tenant_id=self.tenant.id, receita=receita,
                )

    def test_a_profundidade_da_receita_respeita_o_teto(self):
        receita = [
            {"nivel": "area", "itens": [f"A{n}"]}
            for n in range(PDCA_PROFUNDIDADE_MAXIMA_LOCAL + 1)
        ]
        with self.assertRaises(ValidationError):
            services.gerar_em_lote(
                obra=self.obra, tenant_id=self.tenant.id, receita=receita, simular=True,
            )


class CalendarioDeTrabalhoTests(TestCase):
    """De duração para datas — o cálculo que a PDCA.1 vai usar dentro do CPM."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-cal", nome="Construtora Calendário")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra do Calendário", endereco="Rua 3",
        )
        # 07/09/2026 é uma segunda-feira (Independência) — feriado nacional que
        # cai em dia útil, que é o único caso em que o feriado muda a conta.
        Feriado.objects.create(
            data=date(2026, 9, 7), nome="Independência", escopo="nacional",
        )
        Feriado.objects.create(
            data=date(2026, 9, 8), nome="Padroeira local", escopo="municipal",
            uf="BA", ibge="2927408", cidade="Salvador",
        )

    def setUp(self):
        self.cal = CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Padrão 5×2", obra=self.obra,
        )

    def test_semana_util_ignora_sabado_e_domingo(self):
        # 14/09/2026 (segunda) a 20/09/2026 (domingo) = 5 dias úteis.
        self.assertEqual(
            services.dias_uteis(self.cal, date(2026, 9, 14), date(2026, 9, 20)), 5,
        )

    def test_feriado_nacional_sai_da_conta(self):
        # 07/09 (segunda, feriado) a 11/09 (sexta) = 4, não 5.
        self.assertEqual(
            services.dias_uteis(self.cal, date(2026, 9, 7), date(2026, 9, 11)), 4,
        )

    def test_feriado_municipal_so_vale_para_quem_declarou_o_municipio(self):
        """Afirmar feriado municipal sem saber o município seria inventar dia
        parado — e o cronograma inteiro sairia deslocado."""
        sem_localidade = services.dias_uteis(self.cal, date(2026, 9, 8), date(2026, 9, 8))
        self.cal.uf, self.cal.ibge = "BA", "2927408"
        self.cal.save(update_fields=["uf", "ibge"])
        com_localidade = services.dias_uteis(self.cal, date(2026, 9, 8), date(2026, 9, 8))
        self.assertEqual((sem_localidade, com_localidade), (1, 0))

    def test_desligar_feriados_e_opcao_de_obra_de_turno_continuo(self):
        self.cal.considera_feriados = False
        self.cal.save(update_fields=["considera_feriados"])
        self.assertEqual(
            services.dias_uteis(self.cal, date(2026, 9, 7), date(2026, 9, 11)), 5,
        )

    def test_a_excecao_vence_o_feriado_e_a_regra_da_semana(self):
        """O mutirão de sábado e o recesso são o registro mais específico sobre
        aquele dia — precedência: exceção > feriado > semana."""
        ExcecaoCalendario.objects.create(
            tenant=self.tenant, calendario=self.cal, data=date(2026, 9, 7),
            trabalha=True, motivo="mutirão de concretagem",
        )
        self.assertTrue(services.eh_dia_util(self.cal, date(2026, 9, 7)))
        ExcecaoCalendario.objects.create(
            tenant=self.tenant, calendario=self.cal, data=date(2026, 9, 9),
            trabalha=False, motivo="chuva",
        )
        self.assertFalse(services.eh_dia_util(self.cal, date(2026, 9, 9)))

    def test_o_dia_de_inicio_conta_como_o_primeiro(self):
        """Convenção do MS Project e do P6, e a que o planejador espera:
        duração 1 termina no mesmo dia."""
        self.assertEqual(
            services.somar_dias_uteis(self.cal, date(2026, 9, 14), 1), date(2026, 9, 14),
        )
        # Segunda + 5 dias úteis = sexta da mesma semana.
        self.assertEqual(
            services.somar_dias_uteis(self.cal, date(2026, 9, 14), 5), date(2026, 9, 18),
        )
        # Atravessando o fim de semana: 5 + 1 cai na segunda seguinte.
        self.assertEqual(
            services.somar_dias_uteis(self.cal, date(2026, 9, 14), 6), date(2026, 9, 21),
        )

    def test_comecar_em_dia_nao_util_empurra_para_o_proximo(self):
        # 19/09/2026 é sábado.
        self.assertEqual(
            services.somar_dias_uteis(self.cal, date(2026, 9, 19), 1), date(2026, 9, 21),
        )

    def test_calendario_sem_dia_util_falha_como_erro_e_nao_como_laco_infinito(self):
        for campo in ("trabalha_segunda", "trabalha_terca", "trabalha_quarta",
                      "trabalha_quinta", "trabalha_sexta"):
            setattr(self.cal, campo, False)
        self.cal.save()
        with self.assertRaises(ValidationError):
            services.somar_dias_uteis(self.cal, date(2026, 9, 14), 3)

    def test_a_obra_herda_o_calendario_da_empresa_quando_nao_tem_o_seu(self):
        outra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra sem calendário", endereco="Rua 4",
        )
        self.assertIsNone(services.calendario_da_obra(outra, tenant_id=self.tenant.id))
        padrao = CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Padrão da empresa", padrao=True,
        )
        self.assertEqual(
            services.calendario_da_obra(outra, tenant_id=self.tenant.id).pk, padrao.pk,
        )
        self.assertEqual(
            services.calendario_da_obra(self.obra, tenant_id=self.tenant.id).pk,
            self.cal.pk,
            "a obra com calendário próprio não pode cair no padrão da empresa",
        )

    def test_um_so_calendario_padrao_por_empresa(self):
        CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Padrão", padrao=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CalendarioTrabalho.objects.create(
                    tenant=self.tenant, nome="Outro padrão", padrao=True,
                )


class AcessoAoModuloTests(APITestCase):
    """As duas camadas da docs/acesso-e-permissoes.md, nesta ordem: o tenant
    assina o módulo? esta pessoa pode isto?"""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-api", nome="Construtora API")
        cls.vizinha = Tenant.objects.create(slug="pdca-viz", nome="Construtora Vizinha")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra da API", endereco="Rua 5",
        )
        cls.obra_vizinha = Obra.objects.create(
            tenant=cls.vizinha, nome_obra="Obra vizinha", endereco="Rua 6",
        )
        cls.local = LocalObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, nivel=NivelLocal.BLOCO,
            codigo="T1", nome="Torre 1",
        )
        LocalObra.objects.create(
            tenant=cls.vizinha, obra=cls.obra_vizinha, nivel=NivelLocal.BLOCO,
            codigo="T1", nome="Torre da vizinha",
        )
        cls.usuario = Usuario.objects.create(username="planejador", tenant=cls.tenant)

    def _autenticar(self, modules=("pdca",), permissions=("pdca.local.view",)):
        self.usuario.iam_modules = list(modules)
        self.usuario.iam_permissions = list(permissions)
        self.client.force_authenticate(user=self.usuario)

    def test_sem_o_modulo_no_token_a_camada_1_barra(self):
        self._autenticar(modules=())
        self.assertEqual(self.client.get("/api/pdca/locais/").status_code, 403)

    def test_com_o_modulo_e_sem_a_permissao_a_camada_2_barra(self):
        self._autenticar(permissions=())
        self.assertEqual(self.client.get("/api/pdca/locais/").status_code, 403)

    def test_ler_exige_view_e_escrever_exige_edit(self):
        self._autenticar(permissions=("pdca.local.view",))
        self.assertEqual(self.client.get("/api/pdca/locais/").status_code, 200)
        resposta = self.client.post("/api/pdca/locais/", {
            "obra": self.obra.pk, "nivel": "bloco", "codigo": "T2", "nome": "Torre 2",
        })
        self.assertEqual(resposta.status_code, 403)

    def test_a_listagem_nao_atravessa_a_empresa(self):
        self._autenticar()
        dados = self.client.get("/api/pdca/locais/").json()
        nomes = [linha["nome"] for linha in dados["results"]]
        self.assertEqual(nomes, ["Torre 1"])

    def test_gerar_em_lote_pela_api_devolve_o_relatorio(self):
        self._autenticar(permissions=("pdca.local.view", "pdca.local.edit"))
        resposta = self.client.post("/api/pdca/locais/gerar-em-lote/", {
            "obra": self.obra.pk,
            "simular": True,
            "receita": [
                {"nivel": "pavimento", "de": 1, "ate": 3, "formato_codigo": "P{n:02d}"},
            ],
        }, format="json")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["total_previsto"], 3)
        self.assertEqual(resposta.json()["criados"], 0)

    def test_gerar_em_lote_em_obra_de_outra_empresa_e_recusado(self):
        """A checagem é pelo queryset escopado, não pelo id que chegou — um id
        de outra empresa não pode virar árvore lá dentro."""
        self._autenticar(permissions=("pdca.local.view", "pdca.local.edit"))
        resposta = self.client.post("/api/pdca/locais/gerar-em-lote/", {
            "obra": self.obra_vizinha.pk,
            "receita": [{"nivel": "bloco", "itens": ["T9"]}],
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(
            LocalObra.objects.filter(tenant=self.vizinha).count(), 1,
        )

    def test_pai_de_outra_obra_e_recusado_no_cadastro(self):
        self._autenticar(permissions=("pdca.local.view", "pdca.local.edit"))
        outra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Segunda obra", endereco="Rua 7",
        )
        resposta = self.client.post("/api/pdca/locais/", {
            "obra": outra.pk, "pai": self.local.pk, "nivel": "pavimento",
            "codigo": "P01", "nome": "1º pavimento",
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("pai", resposta.json())

    def test_o_status_do_modulo_declara_o_que_existe(self):
        """Dado honesto vale para a própria capacidade: a tela não pode oferecer
        cronograma porque o módulo respondeu 'ativo'."""
        self._autenticar()
        dados = self.client.get("/api/pdca/status/").json()
        self.assertEqual(dados["fatia"], "PDCA.4")
        self.assertTrue(dados["recursos"]["locais"])
        self.assertTrue(dados["recursos"]["cronograma"])
        self.assertTrue(dados["recursos"]["modelo"])
        self.assertTrue(dados["recursos"]["avanco"])
        self.assertTrue(dados["recursos"]["contrato"])
        self.assertTrue(dados["recursos"]["medicao"])
        self.assertTrue(dados["recursos"]["retencao"])
        # PDCA.4: o aditivo passou a existir, e com ele a trava do acumulado
        # deixou de ser contra o contratado do dia da assinatura.
        self.assertTrue(dados["recursos"]["aditivo"])
        self.assertTrue(dados["recursos"]["deducoes"])
        self.assertTrue(dados["recursos"]["material_estocado"])
        # O que ainda NÃO existe continua dizendo que não existe: é a mesma
        # honestidade, agora sobre o que a PDCA.4 deixou de fora. A planilha do
        # empreiteiro entra colando coluna, não por wizard de xlsx; e o anexo
        # por linha é texto, porque a foto mora no apontamento de avanço.
        self.assertFalse(dados["recursos"]["importar_planilha_do_empreiteiro"])
        self.assertFalse(dados["recursos"]["anexo_por_linha"])

    def test_o_status_entrega_os_tetos_que_a_tela_precisa_respeitar(self):
        """A tela fatia o que cola em blocos, e o tamanho do bloco é do dono. Se
        ela carregasse uma cópia do número, mudá-lo no `planos.py` exigiria um
        deploy de frontend para valer."""
        from payment.planos import PDCA_TETO_LINHAS_POR_LOTE

        self._autenticar()
        tetos = self.client.get("/api/pdca/status/").json()["tetos"]
        self.assertEqual(tetos["linhas_por_lote"], PDCA_TETO_LINHAS_POR_LOTE)

    def test_criar_calendario_sem_citar_os_dias_usa_o_padrao(self):
        """Achado no teste de fumaça pelo gateway: o payload normal não cita os
        dias da semana (segunda a sexta **é** o padrão do modelo), e a validação
        lia campo ausente como `False` — recusando o calendário com a mensagem de
        um erro que o cliente não cometeu."""
        self._autenticar(permissions=("pdca.calendario.view", "pdca.calendario.edit"))
        resposta = self.client.post("/api/pdca/calendarios/", {
            "nome": "Padrão da obra", "obra": self.obra.pk,
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertTrue(resposta.json()["trabalha_segunda"])
        self.assertFalse(resposta.json()["trabalha_domingo"])

    def test_calendario_com_todos_os_dias_desligados_continua_recusado(self):
        self._autenticar(permissions=("pdca.calendario.view", "pdca.calendario.edit"))
        resposta = self.client.post("/api/pdca/calendarios/", {
            "nome": "Obra parada", "obra": self.obra.pk,
            "trabalha_segunda": False, "trabalha_terca": False, "trabalha_quarta": False,
            "trabalha_quinta": False, "trabalha_sexta": False,
            "trabalha_sabado": False, "trabalha_domingo": False,
        }, format="json")
        self.assertEqual(resposta.status_code, 400)

    def test_dias_uteis_declara_se_a_base_de_feriados_esta_vazia(self):
        """A tabela de feriados é global e nasce vazia. Um calendário que promete
        considerá-los e responde sem eles precisa dizer isso na cara — foi
        exatamente o que o teste de fumaça pegou."""
        self._autenticar(permissions=("pdca.calendario.view", "pdca.calendario.edit"))
        cal = CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Com feriados", obra=self.obra,
        )
        Feriado.objects.all().delete()
        resposta = self.client.get(
            f"/api/pdca/calendarios/{cal.calendario_id}/dias-uteis/"
            "?inicio=2026-09-07&fim=2026-09-11"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.json()["feriados_sincronizados"])

        Feriado.objects.create(
            data=date(2026, 9, 7), nome="Independência", escopo="nacional",
        )
        resposta = self.client.get(
            f"/api/pdca/calendarios/{cal.calendario_id}/dias-uteis/"
            "?inicio=2026-09-07&fim=2026-09-11"
        )
        self.assertTrue(resposta.json()["feriados_sincronizados"])
        self.assertEqual(resposta.json()["dias_uteis"], 4)


# ===========================================================================
# PDCA.1 — o plano de tempo
# ===========================================================================
#
# A âncora de todos os testes de data é **1º/06/2026, uma segunda-feira**. Um
# cronograma que começa no meio da semana esconde erro de contagem: o primeiro
# fim de semana atravessado já corrige a conta errada por acaso.


class BaseCronograma(TestCase):
    """Cenário comum: obra, calendário de segunda a sexta e um cronograma vazio."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-cpm", nome="Construtora CPM")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra do CPM", endereco="Rua do Prazo",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )

    def setUp(self):
        Feriado.objects.all().delete()
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano inicial",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
        )

    def atividade(self, codigo, duracao=1, pai=None, **extra):
        return Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, pai=pai,
            codigo=codigo, nome=f"Serviço {codigo}",
            duracao_dias=duracao,
            profundidade=1 if pai is None else pai.profundidade + 1,
            **extra,
        )

    def ligar(self, origem, destino, tipo=Precedencia.Tipo.FS, atraso=0):
        return Precedencia.objects.create(
            tenant=self.tenant, origem=origem, destino=destino,
            tipo=tipo, atraso_dias=atraso,
        )


class CpmTests(BaseCronograma):
    def test_uma_atividade_sozinha_comeca_na_ancora_do_plano(self):
        a = self.atividade("1", duracao=5)
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db()
        # Segunda a sexta: cinco dias úteis contando o próprio início.
        self.assertEqual(a.inicio_cedo, date(2026, 6, 1))
        self.assertEqual(a.termino_cedo, date(2026, 6, 5))

    def test_a_duracao_de_um_dia_termina_no_mesmo_dia(self):
        """A convenção do MS Project e do P6 — e a que o planejador espera.
        Terminar no dia seguinte faria toda obra durar o dobro das atividades."""
        a = self.atividade("1", duracao=1)
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db()
        self.assertEqual(a.inicio_cedo, a.termino_cedo)

    def test_fs_poe_a_sucessora_no_proximo_dia_util(self):
        a = self.atividade("1", duracao=5)   # 01→05/06 (seg→sex)
        b = self.atividade("2", duracao=3)
        self.ligar(a, b)
        services.calcular_cpm(self.cronograma)
        b.refresh_from_db()
        # Pula o fim de semana: começa na segunda seguinte.
        self.assertEqual(b.inicio_cedo, date(2026, 6, 8))
        self.assertEqual(b.termino_cedo, date(2026, 6, 10))

    def test_o_termino_do_projeto_e_o_maior_termino(self):
        a = self.atividade("1", duracao=5)
        b = self.atividade("2", duracao=3)
        self.ligar(a, b)
        resultado = services.calcular_cpm(self.cronograma)
        self.assertEqual(resultado["termino"], date(2026, 6, 10))
        self.cronograma.refresh_from_db()
        self.assertEqual(self.cronograma.termino_calculado, date(2026, 6, 10))
        self.assertIsNotNone(self.cronograma.calculado_em)

    def test_a_corrente_mais_longa_e_a_critica_e_a_curta_tem_folga(self):
        """O que o CPM existe para responder: onde atrasar custa prazo e onde
        não custa."""
        a = self.atividade("1", duracao=5)
        b = self.atividade("2", duracao=3)
        self.ligar(a, b)
        curta = self.atividade("3", duracao=2)   # solta, 01→02/06
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db(); b.refresh_from_db(); curta.refresh_from_db()

        self.assertTrue(a.critica)
        self.assertTrue(b.critica)
        self.assertEqual(a.folga_total, 0)
        self.assertFalse(curta.critica)
        # Termina 02/06 e podia terminar 10/06: seis dias úteis de folga.
        self.assertEqual(curta.folga_total, 6)

    def test_a_folga_livre_nao_passa_da_total(self):
        a = self.atividade("1", duracao=2)
        b = self.atividade("2", duracao=2)
        c = self.atividade("3", duracao=10)
        self.ligar(a, c)
        self.ligar(b, c)
        services.calcular_cpm(self.cronograma)
        for atividade in (a, b, c):
            atividade.refresh_from_db()
            self.assertLessEqual(atividade.folga_livre, atividade.folga_total)
            self.assertGreaterEqual(atividade.folga_livre, 0)

    def test_o_marco_e_um_instante_e_nao_um_intervalo(self):
        """O `Marco` da v01 é atividade de duração zero — no Gantt, o losango."""
        a = self.atividade("1", duracao=5)
        marco = self.atividade("2", duracao=None, eh_marco=True)
        self.ligar(a, marco)
        services.calcular_cpm(self.cronograma)
        marco.refresh_from_db()
        self.assertEqual(marco.inicio_cedo, marco.termino_cedo)
        self.assertEqual(marco.inicio_cedo, date(2026, 6, 8))

    def test_o_atraso_positivo_empurra_e_o_negativo_antecipa(self):
        a = self.atividade("1", duracao=5)      # 01→05/06
        depois = self.atividade("2", duracao=1)
        antes = self.atividade("3", duracao=1)
        self.ligar(a, depois, atraso=2)         # 08/06 + 2 = 10/06
        self.ligar(a, antes, atraso=-1)         # 08/06 - 1 = 05/06 (sobreposição)
        services.calcular_cpm(self.cronograma)
        depois.refresh_from_db(); antes.refresh_from_db()
        self.assertEqual(depois.inicio_cedo, date(2026, 6, 10))
        self.assertEqual(antes.inicio_cedo, date(2026, 6, 5))

    def test_ss_faz_as_duas_andarem_juntas(self):
        a = self.atividade("1", duracao=10)
        b = self.atividade("2", duracao=3)
        self.ligar(a, b, tipo=Precedencia.Tipo.SS, atraso=2)
        services.calcular_cpm(self.cronograma)
        b.refresh_from_db()
        # Começa dois dias úteis depois de a predecessora começar.
        self.assertEqual(b.inicio_cedo, date(2026, 6, 3))

    def test_ff_faz_as_duas_terminarem_juntas(self):
        a = self.atividade("1", duracao=5)      # termina 05/06
        b = self.atividade("2", duracao=3)
        self.ligar(a, b, tipo=Precedencia.Tipo.FF)
        services.calcular_cpm(self.cronograma)
        b.refresh_from_db()
        self.assertEqual(b.termino_cedo, date(2026, 6, 5))
        self.assertEqual(b.inicio_cedo, date(2026, 6, 3))

    def test_a_restricao_de_data_ancora_a_atividade(self):
        """"Não começar antes de" — a atividade que depende do mundo (o
        equipamento importado, a licença com data marcada), não de uma
        predecessora."""
        a = self.atividade("1", duracao=2, nao_comecar_antes_de=date(2026, 6, 10))
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db()
        self.assertEqual(a.inicio_cedo, date(2026, 6, 10))

    def test_o_ciclo_e_recusado_com_o_nome_das_atividades(self):
        """Ligar a barra errada no Gantt é caso comum, não exceção rara. A
        mensagem tem de dizer QUAIS atividades, senão o conserto vira caça."""
        a = self.atividade("1", duracao=2)
        b = self.atividade("2", duracao=2)
        self.ligar(a, b)
        Precedencia.objects.create(
            tenant=self.tenant, origem=b, destino=a, tipo=Precedencia.Tipo.FS,
        )
        with self.assertRaises(ValidationError) as capturado:
            services.calcular_cpm(self.cronograma)
        mensagem = " ".join(capturado.exception.messages)
        self.assertIn("ciclo", mensagem)
        self.assertIn("Serviço 1", mensagem)

    def test_cronograma_vazio_nao_calcula(self):
        with self.assertRaises(ValidationError):
            services.calcular_cpm(self.cronograma)

    def test_sem_calendario_nenhum_o_cpm_recusa_em_vez_de_inventar(self):
        """Assumir segunda a sexta seria inventar quando a empresa trabalha — e
        a data errada sairia com cara de calculada."""
        self.cronograma.calendario = None
        self.cronograma.save(update_fields=["calendario"])
        self.atividade("1", duracao=3)
        with self.assertRaises(ValidationError):
            services.calcular_cpm(self.cronograma)


class CpmComCalendarioTests(BaseCronograma):
    def test_o_feriado_empurra_o_termino(self):
        Feriado.objects.create(
            data=date(2026, 6, 3), nome="Feriado de teste", escopo="nacional",
        )
        a = self.atividade("1", duracao=5)
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db()
        # 01, 02, (03 feriado), 04, 05, 08 → termina na segunda seguinte.
        self.assertEqual(a.termino_cedo, date(2026, 6, 8))

    def test_o_mutirao_de_sabado_vence_a_regra_da_semana(self):
        """Exceção > feriado > regra: o registro mais específico sobre o dia."""
        ExcecaoCalendario.objects.create(
            tenant=self.tenant, calendario=self.calendario,
            data=date(2026, 6, 6), trabalha=True, motivo="Mutirão",
        )
        a = self.atividade("1", duracao=6)
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db()
        self.assertEqual(a.termino_cedo, date(2026, 6, 6))

    def test_a_parada_de_chuva_atrasa(self):
        ExcecaoCalendario.objects.create(
            tenant=self.tenant, calendario=self.calendario,
            data=date(2026, 6, 3), trabalha=False, motivo="Chuva",
        )
        a = self.atividade("1", duracao=5)
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db()
        self.assertEqual(a.termino_cedo, date(2026, 6, 8))

    def test_a_atividade_com_calendario_proprio_usa_o_dela(self):
        """A frente de turno contínuo não pode obrigar a obra inteira ao mesmo
        expediente — e é por isso que o calendário desce até a atividade."""
        sete_dias = CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Turno contínuo", obra=self.obra,
            trabalha_sabado=True, trabalha_domingo=True,
        )
        comum = self.atividade("1", duracao=7)
        continua = self.atividade("2", duracao=7, calendario=sete_dias)
        services.calcular_cpm(self.cronograma)
        comum.refresh_from_db(); continua.refresh_from_db()
        self.assertEqual(continua.termino_cedo, date(2026, 6, 7))
        self.assertEqual(comum.termino_cedo, date(2026, 6, 9))

    def test_o_resultado_declara_se_a_base_de_feriados_esta_vazia(self):
        """Mesma régua da PDCA.0: um cronograma calculado sem a base de feriados
        devolve datas que a ignoram — e precisa dizer isso."""
        self.atividade("1", duracao=2)
        resultado = services.calcular_cpm(self.cronograma)
        self.assertFalse(resultado["feriados_sincronizados"])


class ArvoreDaWbsTests(BaseCronograma):
    def test_a_sintetica_e_o_intervalo_dos_filhos(self):
        pai = self.atividade("1", duracao=None)
        filho_a = self.atividade("1.1", duracao=5, pai=pai)
        filho_b = self.atividade("1.2", duracao=2, pai=pai)
        self.ligar(filho_a, filho_b)
        services.calcular_cpm(self.cronograma)
        pai.refresh_from_db(); filho_b.refresh_from_db()
        self.assertEqual(pai.inicio_cedo, date(2026, 6, 1))
        self.assertEqual(pai.termino_cedo, filho_b.termino_cedo)

    def test_a_sintetica_nao_entra_no_grafo(self):
        """Só a folha tem duração e precedência; a sintética é derivada. O
        resultado declara quantas folhas entraram, e é por aí que se confere."""
        pai = self.atividade("1", duracao=None)
        self.atividade("1.1", duracao=3, pai=pai)
        resultado = services.calcular_cpm(self.cronograma)
        self.assertEqual(resultado["atividades"], 2)
        self.assertEqual(resultado["folhas"], 1)

    def test_o_teto_de_profundidade_da_wbs_vem_do_payment(self):
        from payment.planos import PDCA_PROFUNDIDADE_MAXIMA_WBS

        pai = None
        for n in range(PDCA_PROFUNDIDADE_MAXIMA_WBS):
            pai = self.atividade(f"N{n}", duracao=1, pai=pai)
        with self.assertRaises(ValidationError):
            services.validar_profundidade_wbs(pai)

    def test_codigo_repetido_no_mesmo_cronograma_e_barrado(self):
        """O código da EAP é o que sobrevive ao replanejamento e reencontra a
        atividade na linha de base — repetido, o pareamento passaria a mentir."""
        self.atividade("1.1", duracao=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.atividade("1.1", duracao=1)


class VersionamentoTests(BaseCronograma):
    def test_publicar_roda_o_cpm_e_vira_a_chave(self):
        self.atividade("1", duracao=5)
        services.publicar(self.cronograma, por="Ana Planejadora")
        self.cronograma.refresh_from_db()
        self.assertEqual(self.cronograma.status, Cronograma.Status.VIGENTE)
        self.assertIsNotNone(self.cronograma.calculado_em)
        self.assertEqual(self.cronograma.publicado_por, "Ana Planejadora")

    def test_so_rascunho_publica(self):
        self.atividade("1", duracao=2)
        services.publicar(self.cronograma)
        with self.assertRaises(ValidationError):
            services.publicar(self.cronograma)

    def test_replanejar_exige_motivo(self):
        self.atividade("1", duracao=2)
        services.publicar(self.cronograma)
        with self.assertRaises(ValidationError):
            services.replanejar(self.cronograma, motivo="   ")

    def test_replanejar_copia_a_arvore_e_as_setas(self):
        a = self.atividade("1", duracao=5)
        b = self.atividade("2", duracao=3)
        self.ligar(a, b)
        services.publicar(self.cronograma)

        nova = services.replanejar(self.cronograma, motivo="Chuva em maio")
        self.assertEqual(nova.versao, 2)
        self.assertEqual(nova.status, Cronograma.Status.RASCUNHO)
        self.assertEqual(nova.origem_id, self.cronograma.pk)
        self.assertEqual(nova.atividades.count(), 2)
        self.assertEqual(
            Precedencia.objects.filter(origem__cronograma=nova).count(), 1,
        )
        # A cópia é nova: ids diferentes, códigos iguais. É o código que atravessa
        # a versão, e é por ele que a linha de base pareia.
        copiadas = set(nova.atividades.values_list("codigo", flat=True))
        self.assertEqual(copiadas, {"1", "2"})
        self.assertFalse(
            set(nova.atividades.values_list("atividade_id", flat=True))
            & {a.pk, b.pk}
        )

    def test_replanejar_preserva_a_hierarquia_na_copia(self):
        pai = self.atividade("1", duracao=None)
        self.atividade("1.1", duracao=2, pai=pai)
        services.publicar(self.cronograma)
        nova = services.replanejar(self.cronograma, motivo="Revisão de escopo")
        copia_filho = nova.atividades.get(codigo="1.1")
        copia_pai = nova.atividades.get(codigo="1")
        self.assertEqual(copia_filho.pai_id, copia_pai.pk)

    def test_publicar_a_nova_versao_rebaixa_a_anterior(self):
        self.atividade("1", duracao=2)
        services.publicar(self.cronograma)
        nova = services.replanejar(self.cronograma, motivo="Aditivo de prazo")
        services.publicar(nova)

        self.cronograma.refresh_from_db()
        nova.refresh_from_db()
        self.assertEqual(self.cronograma.status, Cronograma.Status.SUBSTITUIDO)
        self.assertEqual(nova.status, Cronograma.Status.VIGENTE)
        # A constraint parcial garante o resto: um vigente por obra.
        self.assertEqual(
            Cronograma.objects.filter(
                obra=self.obra, status=Cronograma.Status.VIGENTE
            ).count(),
            1,
        )

    def test_dois_vigentes_na_mesma_obra_sao_barrados_pelo_banco(self):
        self.atividade("1", duracao=2)
        services.publicar(self.cronograma)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cronograma.objects.create(
                    tenant=self.tenant, obra=self.obra, descricao="Paralelo",
                    versao=99, status=Cronograma.Status.VIGENTE,
                    data_inicio=date(2026, 6, 1), calendario=self.calendario,
                )

    def test_o_teto_de_versoes_vem_do_payment(self):
        from payment.planos import PDCA_TETO_VERSOES_POR_CRONOGRAMA

        self.atividade("1", duracao=1)
        services.publicar(self.cronograma)
        Cronograma.objects.filter(pk=self.cronograma.pk).update(
            versao=PDCA_TETO_VERSOES_POR_CRONOGRAMA,
        )
        self.cronograma.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.replanejar(self.cronograma, motivo="Mais uma")

    def test_o_rascunho_e_editavel_e_o_vigente_nao(self):
        self.assertTrue(self.cronograma.editavel)
        self.atividade("1", duracao=1)
        services.publicar(self.cronograma)
        self.cronograma.refresh_from_db()
        self.assertFalse(self.cronograma.editavel)


class LinhaDeBaseTests(BaseCronograma):
    def test_sem_origem_nao_ha_base_e_a_resposta_diz_isso(self):
        self.atividade("1", duracao=2)
        services.calcular_cpm(self.cronograma)
        comparacao = services.comparar_com_base(self.cronograma)
        self.assertFalse(comparacao["tem_base"])
        self.assertEqual(comparacao["linhas"], [])

    def test_a_base_mostra_o_desvio_de_cada_atividade(self):
        """A leitura que o Gantt desenha como fantasma atrás da barra: *atrasou
        quanto desde que a gente combinou?*"""
        a = self.atividade("1", duracao=5)
        self.atividade("2", duracao=2)
        services.publicar(self.cronograma)
        termino_original = Atividade.objects.get(pk=a.pk).termino_cedo

        nova = services.replanejar(self.cronograma, motivo="Estouro de prazo")
        copia = nova.atividades.get(codigo="1")
        copia.duracao_dias = 8
        copia.save(update_fields=["duracao_dias"])
        services.calcular_cpm(nova)

        comparacao = services.comparar_com_base(nova)
        self.assertTrue(comparacao["tem_base"])
        linha = next(l for l in comparacao["linhas"] if l["codigo"] == "1")
        self.assertEqual(linha["base_termino"], termino_original)
        self.assertEqual(linha["situacao"], "atrasada")
        self.assertGreater(linha["desvio_dias"], 0)

    def test_a_atividade_nova_e_a_removida_aparecem_nomeadas(self):
        self.atividade("1", duracao=2)
        self.atividade("2", duracao=2)
        services.publicar(self.cronograma)

        nova = services.replanejar(self.cronograma, motivo="Escopo mudou")
        nova.atividades.get(codigo="2").delete()
        Atividade.objects.create(
            tenant=self.tenant, cronograma=nova, codigo="3", nome="Serviço novo",
            duracao_dias=1, profundidade=1,
        )
        services.calcular_cpm(nova)

        situacoes = {l["codigo"]: l["situacao"] for l in services.comparar_com_base(nova)["linhas"]}
        self.assertEqual(situacoes["3"], "nova")
        self.assertEqual(situacoes["2"], "removida")


class PesoTests(BaseCronograma):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from moduloorcamento.models import ItemOrcado, Orcamento

        cls.orcamento = Orcamento.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Orçamento base",
        )
        cls.item = ItemOrcado.objects.create(
            tenant=cls.tenant, orcamento=cls.orcamento, codigo_eap="1.1",
            descricao="Alvenaria", tipo_linha=ItemOrcado.TipoLinha.ANALITICO,
            quantidade=Decimal("100"), custo_unitario=Decimal("50"),
            total_custo_direto=Decimal("5000"), total_com_bdi=Decimal("6000"),
        )

    def test_com_vinculo_o_peso_e_o_valor_orcado(self):
        a = self.atividade("1", duracao=2, item_orcado=self.item, peso_informado=Decimal("9"))
        peso, origem = services.peso_de(a)
        self.assertEqual(peso, Decimal("6000"))
        # O vínculo vence o informado: régua de custo real ganha de digitação.
        self.assertEqual(origem, "orcado")

    def test_sem_vinculo_vale_o_peso_informado(self):
        a = self.atividade("1", duracao=2, peso_informado=Decimal("7.5"))
        peso, origem = services.peso_de(a)
        self.assertEqual(peso, Decimal("7.5"))
        self.assertEqual(origem, "informado")

    def test_sem_nenhum_dos_dois_o_peso_e_nulo_e_nao_zero(self):
        """Zero faria o avanço do pai parecer calculado quando não é. `None` diz
        'sem apuração', que é a verdade."""
        a = self.atividade("1", duracao=2)
        peso, origem = services.peso_de(a)
        self.assertIsNone(peso)
        self.assertEqual(origem, "")

    def test_a_cobertura_traz_o_denominador(self):
        """No molde do `realizado_cobertura` do Orçamento: vínculo que não existe
        não é inventado, e o número vem com quantas linhas ficaram de fora."""
        self.atividade("1", duracao=2, item_orcado=self.item)
        self.atividade("2", duracao=2, peso_informado=Decimal("3"))
        self.atividade("3", duracao=2)
        cobertura = services.cobertura_do_orcamento(self.cronograma)
        self.assertEqual(cobertura["folhas"], 3)
        self.assertEqual(cobertura["com_item_orcado"], 1)
        self.assertEqual(cobertura["com_peso_informado"], 1)
        self.assertEqual(cobertura["sem_peso"], 1)
        self.assertEqual(cobertura["valor_orcado_vinculado"], Decimal("6000"))


class ApiDoCronogramaTests(APITestCase):
    """Os verbos do plano pela API — e a segregação entre montar e assumir."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-crono-api", nome="Construtora Plano")
        cls.vizinha = Tenant.objects.create(slug="pdca-crono-viz", nome="Vizinha")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra do plano", endereco="Rua 9",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )
        cls.usuario = Usuario.objects.create(username="planeja", tenant=cls.tenant)

    def setUp(self):
        Feriado.objects.all().delete()
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
        )
        self.a = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Fundação", duracao_dias=5, profundidade=1,
        )

    def _autenticar(self, permissions=("pdca.cronograma.view",)):
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = list(permissions)
        self.client.force_authenticate(user=self.usuario)

    def test_sem_o_modulo_a_camada_1_barra(self):
        self.usuario.iam_modules = []
        self.usuario.iam_permissions = ["pdca.cronograma.view"]
        self.client.force_authenticate(user=self.usuario)
        self.assertEqual(self.client.get("/api/pdca/cronogramas/").status_code, 403)

    def test_publicar_exige_a_permissao_de_publicar(self):
        """Montar o plano e assumi-lo perante a obra são atos diferentes — a
        mesma segregação que o ORC.6 provou necessária, agora sobre o prazo."""
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        url = f"/api/pdca/cronogramas/{self.cronograma.pk}/publicar/"
        self.assertEqual(self.client.post(url).status_code, 403)

        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.publicar"))
        resposta = self.client.post(url)
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["cronograma"]["status"], "vigente")

    def test_replanejar_exige_a_propria_permissao(self):
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.publicar"))
        self.client.post(f"/api/pdca/cronogramas/{self.cronograma.pk}/publicar/")

        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        url = f"/api/pdca/cronogramas/{self.cronograma.pk}/replanejar/"
        self.assertEqual(
            self.client.post(url, {"motivo": "x"}, format="json").status_code, 403,
        )

        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.replanejar"))
        resposta = self.client.post(url, {"motivo": "Chuva"}, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(resposta.json()["versao"], 2)

    def test_replanejar_sem_motivo_e_recusado_pela_api(self):
        self._autenticar(permissions=(
            "pdca.cronograma.view", "pdca.cronograma.publicar", "pdca.cronograma.replanejar",
        ))
        self.client.post(f"/api/pdca/cronogramas/{self.cronograma.pk}/publicar/")
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.cronograma.pk}/replanejar/",
            {"motivo": ""}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_a_segunda_obra_nao_ganha_um_segundo_cronograma_do_zero(self):
        """Um plano por obra, que ganha versões. Dois planos sem parentesco
        tirariam da linha de base justamente o parentesco que ela é."""
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        resposta = self.client.post("/api/pdca/cronogramas/", {
            "obra": self.obra.pk, "descricao": "Outro plano",
            "data_inicio": "2026-06-01", "calendario": self.calendario.pk,
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("obra", resposta.json())

    def test_editar_atividade_de_plano_vigente_e_recusado(self):
        self._autenticar(permissions=(
            "pdca.cronograma.view", "pdca.cronograma.edit", "pdca.cronograma.publicar",
        ))
        self.client.post(f"/api/pdca/cronogramas/{self.cronograma.pk}/publicar/")
        resposta = self.client.patch(
            f"/api/pdca/atividades/{self.a.pk}/", {"duracao_dias": 9}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_o_gantt_devolve_tudo_numa_chamada(self):
        """Montar o Gantt em três requisições paginadas faria a tela desenhar a
        WBS antes de saber as datas — e pular quando as setas chegassem."""
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        b = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="2",
            nome="Estrutura", duracao_dias=3, profundidade=1,
        )
        Precedencia.objects.create(
            tenant=self.tenant, origem=self.a, destino=b, tipo=Precedencia.Tipo.FS,
        )
        resposta = self.client.get(f"/api/pdca/cronogramas/{self.cronograma.pk}/gantt/")
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(len(dados["atividades"]), 2)
        self.assertEqual(len(dados["precedencias"]), 1)
        self.assertIn("base", dados)
        self.assertIn("cobertura_orcamento", dados)

    def test_reprogramar_e_o_gesto_de_arrastar_a_barra(self):
        """Arrastar não move a barra: fixa uma restrição e manda o CPM decidir.
        É a diferença entre uma tela de desenho e um cronograma."""
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        resposta = self.client.post(
            f"/api/pdca/atividades/{self.a.pk}/reprogramar/",
            {"nao_comecar_antes_de": "2026-06-10"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["atividade"]["inicio_cedo"], "2026-06-10")
        self.assertIn("cpm", resposta.json())

    def test_a_seta_entre_cronogramas_diferentes_e_recusada(self):
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        outra_obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Outra", endereco="Rua 10",
        )
        outro = Cronograma.objects.create(
            tenant=self.tenant, obra=outra_obra, descricao="Outro plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
        )
        forasteira = Atividade.objects.create(
            tenant=self.tenant, cronograma=outro, codigo="9", nome="De fora",
            duracao_dias=1, profundidade=1,
        )
        resposta = self.client.post("/api/pdca/precedencias/", {
            "origem": self.a.pk, "destino": forasteira.pk, "tipo": "FS",
        }, format="json")
        self.assertEqual(resposta.status_code, 400)

    def test_a_seta_que_fecharia_ciclo_e_recusada_na_escrita(self):
        """Erro barrado na entrada tem endereço; erro barrado no cálculo vira
        'o cronograma não calcula' numa tela com centenas de setas."""
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        b = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="2",
            nome="Estrutura", duracao_dias=3, profundidade=1,
        )
        self.client.post("/api/pdca/precedencias/", {
            "origem": self.a.pk, "destino": b.pk, "tipo": "FS",
        }, format="json")
        resposta = self.client.post("/api/pdca/precedencias/", {
            "origem": b.pk, "destino": self.a.pk, "tipo": "FS",
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("ciclo", str(resposta.json()))

    def test_a_seta_para_uma_sintetica_e_recusada(self):
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        filho = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, pai=self.a,
            codigo="1.1", nome="Sapata", duracao_dias=2, profundidade=2,
        )
        outra = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="2",
            nome="Estrutura", duracao_dias=3, profundidade=1,
        )
        self.assertTrue(filho.pk)
        resposta = self.client.post("/api/pdca/precedencias/", {
            "origem": self.a.pk, "destino": outra.pk, "tipo": "FS",
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("sintética", str(resposta.json()))

    def test_a_listagem_de_cronogramas_nao_atravessa_a_empresa(self):
        obra_vizinha = Obra.objects.create(
            tenant=self.vizinha, nome_obra="Obra vizinha", endereco="Rua 11",
        )
        Cronograma.objects.create(
            tenant=self.vizinha, obra=obra_vizinha, descricao="Plano da vizinha",
            data_inicio=date(2026, 6, 1),
        )
        self._autenticar()
        dados = self.client.get("/api/pdca/cronogramas/").json()
        descricoes = [linha["descricao"] for linha in dados["results"]]
        self.assertEqual(descricoes, ["Plano"])

    def test_a_atividade_analitica_sem_duracao_e_recusada(self):
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        resposta = self.client.post("/api/pdca/atividades/", {
            "cronograma": self.cronograma.pk, "codigo": "5", "nome": "Sem duração",
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("duracao_dias", resposta.json())

    def test_o_marco_nao_aceita_duracao(self):
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        resposta = self.client.post("/api/pdca/atividades/", {
            "cronograma": self.cronograma.pk, "codigo": "6", "nome": "Alvará",
            "eh_marco": True, "duracao_dias": 3,
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("duracao_dias", resposta.json())

    def test_o_peso_viaja_com_a_origem_na_api(self):
        self._autenticar()
        dados = self.client.get(f"/api/pdca/atividades/{self.a.pk}/").json()
        self.assertIn("peso", dados)
        self.assertIn("peso_origem", dados)
        self.assertIsNone(dados["peso"])
        self.assertEqual(dados["peso_origem"], "")


class IntegridadeReferencialTests(APITestCase):
    """O `PROTECT` chega como recusa com motivo, e não como 500.

    Achado escrevendo o E2E da PDCA.1: apagar o calendário que um cronograma usa
    levantava `ProtectedError`, que não é `APIException` — o DRF deixava subir e
    o cliente recebia 500. Pior: a página de erro do Django quebrava por cima,
    ao imprimir os objetos protegidos, e o log guardava o rastro da renderização
    em vez do da causa.

    O teste mora aqui porque foi o PDCA que expôs o buraco, mas o tratador é da
    plataforma ([nucleo/excecoes.py](../nucleo/excecoes.py)) e vale para toda
    `PROTECT` do sistema.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-protect", nome="Construtora Protegida")
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Obra", endereco="Rua 1")
        cls.usuario = Usuario.objects.create(username="protege", tenant=cls.tenant)

    def setUp(self):
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Comercial", obra=self.obra,
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
        )
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = ["pdca.calendario.view", "pdca.calendario.edit",
                                        "pdca.calendario.delete"]
        self.client.force_authenticate(user=self.usuario)

    def test_apagar_calendario_em_uso_devolve_409_e_nao_500(self):
        resposta = self.client.delete(f"/api/pdca/calendarios/{self.calendario.pk}/")
        self.assertEqual(resposta.status_code, 409, resposta.content)

    def test_a_recusa_diz_quem_depende(self):
        """Sem isto, "não é possível excluir" manda o usuário caçar o motivo na
        mão — e o motivo é justamente o que ele precisa para decidir."""
        corpo = self.client.delete(f"/api/pdca/calendarios/{self.calendario.pk}/").json()
        self.assertEqual(corpo["total_dependentes"], 1)
        self.assertIn(str(self.cronograma.pk), corpo["dependentes"][0])
        self.assertIn("depende", corpo["detail"].lower())

    def test_o_calendario_sem_plano_algum_sai(self):
        """A trava é sobre dependência real, não sobre a tabela."""
        livre = CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Sem uso", obra=self.obra,
        )
        self.assertEqual(
            self.client.delete(f"/api/pdca/calendarios/{livre.pk}/").status_code, 204,
        )

    def test_a_mensagem_nao_imprime_o_objeto_protegido(self):
        """O texto sai de `verbose_name` + pk, e nunca de `str(obj)`: o objeto
        protegido pode vir com campos diferidos, e imprimi-lo dispara uma ida ao
        banco por uma linha que talvez já não exista — que foi exatamente o que
        derrubou a página de erro quando o defeito apareceu."""
        corpo = self.client.delete(f"/api/pdca/calendarios/{self.calendario.pk}/").json()
        self.assertNotIn(self.cronograma.descricao, corpo["detail"])
        self.assertIn("cronograma", corpo["dependentes"][0].lower())


class PlanoModeloTests(APITestCase):
    """A biblioteca de padrões da construtora (PDCA.1b).

    *Decisão do dono, 23/08/2026:* **"deixa o plano para poder ser usado como
    modelo em outra obra... para não ter que criar 300 planos em um
    empreendimento grande"**. O caso é o mais comum de todos — um empreendimento
    de 300 unidades repete a mesma sequência construtiva 300 vezes.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-modelo", nome="Construtora Padrão")
        cls.obra_a = Obra.objects.create(tenant=cls.tenant, nome_obra="Torre A", endereco="Rua 1")
        cls.obra_b = Obra.objects.create(tenant=cls.tenant, nome_obra="Torre B", endereco="Rua 2")
        cls.usuario = Usuario.objects.create(username="padroniza", tenant=cls.tenant)

    def setUp(self):
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, nome="Comercial", obra=self.obra_a,
        )
        self.plano = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra_a, descricao="Plano da Torre A",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
        )
        self.pai = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, codigo="1", nome="Estrutura",
            ordem=1, profundidade=1,
        )
        self.filha1 = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, pai=self.pai, codigo="1.1",
            nome="Fôrma", duracao_dias=4, ordem=1, profundidade=2,
        )
        self.filha2 = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, pai=self.pai, codigo="1.2",
            nome="Concretagem", duracao_dias=2, ordem=2, profundidade=2,
        )
        Precedencia.objects.create(
            tenant=self.tenant, origem=self.filha1, destino=self.filha2, tipo="FS",
        )
        self._autenticar()

    def _autenticar(self, permissions=("pdca.cronograma.view", "pdca.cronograma.edit"),
                    quotas=None):
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = list(permissions)
        self.usuario.iam_quotas = quotas if quotas is not None else {"planos_modelo": 5}
        self.client.force_authenticate(user=self.usuario)

    def test_marcar_como_modelo_exige_nome(self):
        url = f"/api/pdca/cronogramas/{self.plano.pk}/marcar-modelo/"
        self.assertEqual(self.client.post(url, {"nome": ""}, format="json").status_code, 400)

    def test_o_modelo_entra_na_biblioteca_com_o_nome_dado(self):
        url = f"/api/pdca/cronogramas/{self.plano.pk}/marcar-modelo/"
        resposta = self.client.post(url, {"nome": "Torre residencial 20 pav."}, format="json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertTrue(resposta.json()["eh_modelo"])

        lista = self.client.get("/api/pdca/cronogramas/modelos/").json()
        nomes = [c["nome_modelo"] for c in lista.get("results", lista)]
        self.assertEqual(nomes, ["Torre residencial 20 pav."])

    def test_dois_modelos_com_o_mesmo_nome_sao_recusados(self):
        """Decisão do dono: um nome por modelo. Dois iguais é a forma mais rápida
        de alguém aplicar o padrão errado numa obra inteira."""
        services.marcar_como_modelo(self.plano, nome="Torre padrão")
        outro = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra_b, descricao="Outro",
            data_inicio=date(2026, 6, 1),
        )
        Atividade.objects.create(
            tenant=self.tenant, cronograma=outro, codigo="1", nome="x",
            duracao_dias=1, profundidade=1,
        )
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{outro.pk}/marcar-modelo/",
            {"nome": "torre padrão"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400, resposta.content)

    def test_cronograma_vazio_nao_vira_modelo(self):
        vazio = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra_b, descricao="Vazio",
            data_inicio=date(2026, 6, 1),
        )
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{vazio.pk}/marcar-modelo/",
            {"nome": "Nada"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_a_quota_do_plano_trava_o_proximo_modelo(self):
        """402 e não 403: não falta permissão, falta plano — e a tela precisa
        oferecer upgrade em vez de mandar falar com o administrador."""
        self._autenticar(quotas={"planos_modelo": 1})
        services.marcar_como_modelo(self.plano, nome="Primeiro")
        outro = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra_b, descricao="Outro",
            data_inicio=date(2026, 6, 1),
        )
        Atividade.objects.create(
            tenant=self.tenant, cronograma=outro, codigo="1", nome="x",
            duracao_dias=1, profundidade=1,
        )
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{outro.pk}/marcar-modelo/",
            {"nome": "Segundo"}, format="json",
        )
        self.assertEqual(resposta.status_code, 402, resposta.content)
        self.assertEqual(resposta.json()["quota"], "planos_modelo")

    def test_renomear_o_proprio_modelo_nao_consome_outra_vaga(self):
        self._autenticar(quotas={"planos_modelo": 1})
        services.marcar_como_modelo(self.plano, nome="Primeiro")
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/marcar-modelo/",
            {"nome": "Primeiro renomeado"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)

    def test_aplicar_o_modelo_cria_o_plano_da_outra_obra(self):
        services.marcar_como_modelo(self.plano, nome="Torre padrão")
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/aplicar-modelo/",
            {"obra": self.obra_b.pk, "data_inicio": "2026-09-01",
             "descricao": "Plano da Torre B"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.content)
        novo = Cronograma.objects.get(pk=resposta.json()["cronograma_id"])
        self.assertEqual(novo.obra_id, self.obra_b.pk)
        self.assertEqual(novo.versao, 1)
        self.assertEqual(novo.status, Cronograma.Status.RASCUNHO)
        self.assertEqual(novo.atividades.count(), 3)
        self.assertEqual(
            Precedencia.objects.filter(origem__cronograma=novo).count(), 1,
        )

    def test_o_plano_aplicado_nao_nasce_modelo_nem_consome_quota(self):
        """Senão aplicar um padrão encheria a biblioteca de cópias — e a quota
        junto."""
        services.marcar_como_modelo(self.plano, nome="Torre padrão")
        self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/aplicar-modelo/",
            {"obra": self.obra_b.pk, "data_inicio": "2026-09-01"}, format="json",
        )
        self.assertEqual(
            Cronograma.objects.filter(tenant=self.tenant, eh_modelo=True).count(), 1,
        )

    def test_a_hierarquia_e_a_rede_atravessam_a_copia(self):
        services.marcar_como_modelo(self.plano, nome="Torre padrão")
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/aplicar-modelo/",
            {"obra": self.obra_b.pk, "data_inicio": "2026-09-01"}, format="json",
        )
        novo = Cronograma.objects.get(pk=resposta.json()["cronograma_id"])
        copias = {a.codigo: a for a in novo.atividades.all()}
        self.assertEqual(copias["1.1"].pai_id, copias["1"].atividade_id)
        self.assertEqual(copias["1.1"].duracao_dias, 4)
        seta = Precedencia.objects.get(origem__cronograma=novo)
        self.assertEqual(seta.origem_id, copias["1.1"].atividade_id)
        self.assertEqual(seta.destino_id, copias["1.2"].atividade_id)

    def test_os_vinculos_da_obra_de_origem_NAO_atravessam(self):
        """O erro que este teste existe para impedir não aparece na tela: um
        cronograma da Torre B ponderando o avanço pelo orçamento da Torre A sai
        errado no boletim de medição, e ninguém desconfia do vínculo."""
        etapa = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra_a, nome_etapa="Estrutura", ordem=1,
        )
        self.filha1.etapa = etapa
        self.filha1.calendario = self.calendario  # calendário DA obra A
        self.filha1.nao_comecar_antes_de = date(2026, 7, 1)
        self.filha1.save()

        services.marcar_como_modelo(self.plano, nome="Torre padrão")
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/aplicar-modelo/",
            {"obra": self.obra_b.pk, "data_inicio": "2026-09-01"}, format="json",
        )
        novo = Cronograma.objects.get(pk=resposta.json()["cronograma_id"])
        copia = novo.atividades.get(codigo="1.1")
        self.assertIsNone(copia.etapa_id, "a etapa da obra de origem viajou junto")
        self.assertIsNone(copia.calendario_id, "o calendário da outra obra viajou junto")
        self.assertIsNone(
            copia.nao_comecar_antes_de,
            "a restrição de data do plano antigo viajou para uma obra que começa noutro dia",
        )
        self.assertEqual(copia.duracao_dias, 4, "a duração é o que o modelo guarda")

    def test_aplicar_em_obra_que_ja_tem_plano_e_recusado(self):
        services.marcar_como_modelo(self.plano, nome="Torre padrão")
        Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra_b, descricao="Já existe",
            data_inicio=date(2026, 6, 1),
        )
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/aplicar-modelo/",
            {"obra": self.obra_b.pk, "data_inicio": "2026-09-01"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("replaneje", str(resposta.json()).lower())

    def test_aplicar_o_que_nao_e_modelo_e_recusado(self):
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/aplicar-modelo/",
            {"obra": self.obra_b.pk, "data_inicio": "2026-09-01"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_obra_de_outra_empresa_e_recusada(self):
        vizinha = Tenant.objects.create(slug="pdca-modelo-viz", nome="Vizinha")
        alheia = Obra.objects.create(tenant=vizinha, nome_obra="Alheia", endereco="Rua X")
        services.marcar_como_modelo(self.plano, nome="Torre padrão")
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/aplicar-modelo/",
            {"obra": alheia.pk, "data_inicio": "2026-09-01"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(Cronograma.objects.filter(obra=alheia).count(), 0)

    def test_desmarcar_devolve_a_vaga(self):
        services.marcar_como_modelo(self.plano, nome="Torre padrão")
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/desmarcar-modelo/", format="json",
        )
        self.assertEqual(resposta.status_code, 200)
        self.plano.refresh_from_db()
        self.assertFalse(self.plano.eh_modelo)
        self.assertEqual(self.plano.nome_modelo, "")


class EscritaEmLoteTests(APITestCase):
    """Colar planilha e renumerar a EAP — numa requisição, atomicamente."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-lote", nome="Construtora Lote")
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Obra", endereco="Rua 1")
        cls.usuario = Usuario.objects.create(username="cola", tenant=cls.tenant)

    def setUp(self):
        self.plano = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1),
        )
        self.a = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, codigo="1", nome="Um",
            duracao_dias=1, ordem=1, profundidade=1,
        )
        self.b = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, codigo="2", nome="Dois",
            duracao_dias=2, ordem=2, profundidade=1,
        )
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = ["pdca.cronograma.view", "pdca.cronograma.edit"]
        self.client.force_authenticate(user=self.usuario)

    def _lote(self, edicoes):
        return self.client.post(
            f"/api/pdca/cronogramas/{self.plano.pk}/lote/", {"edicoes": edicoes},
            format="json",
        )

    def test_muitas_celulas_numa_chamada(self):
        resposta = self._lote([
            {"atividade": self.a.pk, "campos": {"nome": "Fundação", "duracao_dias": 7}},
            {"atividade": self.b.pk, "campos": {"nome": "Estrutura"}},
        ])
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["atividades"], 2)
        self.a.refresh_from_db()
        self.assertEqual((self.a.nome, self.a.duracao_dias), ("Fundação", 7))

    def test_a_troca_de_codigos_nao_bate_na_unicidade(self):
        """O caso que obriga as duas passadas: trocar `1` por `2` e `2` por `1`
        na mesma chamada. Numa passada só, a primeira escrita colide."""
        resposta = self._lote([
            {"atividade": self.a.pk, "campos": {"codigo": "2"}},
            {"atividade": self.b.pk, "campos": {"codigo": "1"}},
        ])
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["renomeadas"], 2)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual((self.a.codigo, self.b.codigo), ("2", "1"))

    def test_o_teto_por_chamada_vem_do_payment(self):
        from payment.planos import PDCA_TETO_LINHAS_POR_LOTE
        demais = [
            {"atividade": self.a.pk, "campos": {"nome": f"n{i}"}}
            for i in range(PDCA_TETO_LINHAS_POR_LOTE + 1)
        ]
        resposta = self._lote(demais)
        self.assertEqual(resposta.status_code, 400)
        self.assertIn(str(PDCA_TETO_LINHAS_POR_LOTE), str(resposta.json()))

    def test_campo_fora_da_lista_branca_e_recusado(self):
        """`pai` muda a estrutura da árvore: não é gesto de planilha, e passar por
        aqui pularia a validação de profundidade e de ciclo."""
        resposta = self._lote([{"atividade": self.a.pk, "campos": {"pai": self.b.pk}}])
        self.assertEqual(resposta.status_code, 400)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.pai_id)

    def test_atividade_de_outro_cronograma_e_recusada(self):
        outra_obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Outra", endereco="Rua 2",
        )
        outro = Cronograma.objects.create(
            tenant=self.tenant, obra=outra_obra, descricao="Outro",
            data_inicio=date(2026, 6, 1),
        )
        alheia = Atividade.objects.create(
            tenant=self.tenant, cronograma=outro, codigo="9", nome="Alheia",
            duracao_dias=1, profundidade=1,
        )
        resposta = self._lote([{"atividade": alheia.pk, "campos": {"nome": "x"}}])
        self.assertEqual(resposta.status_code, 400)

    def test_o_lote_e_tudo_ou_nada(self):
        """Uma linha inválida no meio não deixa metade do bloco aplicada — quem
        colou 200 linhas não tem como saber onde parou."""
        resposta = self._lote([
            {"atividade": self.a.pk, "campos": {"nome": "Vai mudar"}},
            {"atividade": self.b.pk, "campos": {"duracao_dias": -5}},
        ])
        self.assertEqual(resposta.status_code, 400, resposta.content)
        self.a.refresh_from_db()
        self.assertEqual(self.a.nome, "Um")

    def test_plano_vigente_nao_aceita_lote(self):
        self.plano.status = Cronograma.Status.VIGENTE
        self.plano.save(update_fields=["status"])
        resposta = self._lote([{"atividade": self.a.pk, "campos": {"nome": "x"}}])
        self.assertEqual(resposta.status_code, 400)


class RenumerarEapTests(APITestCase):
    """A renumeração da árvore inteira — atômica, e fora do lote.

    Fatiar em blocos quebraria a única coisa que a faz funcionar: o código é
    único por cronograma, então todos os que mudam precisam ir para um nome
    temporário **antes** de qualquer definitivo ser assentado, e as duas passadas
    têm de caber na mesma transação.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-renum", nome="Construtora EAP")
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Obra", endereco="Rua 1")
        cls.usuario = Usuario.objects.create(username="renumera", tenant=cls.tenant)

    def setUp(self):
        self.plano = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1),
        )
        # Códigos fora de ordem de propósito: é o estado real depois de alguém
        # inserir e indentar meia dúzia de linhas no meio da árvore.
        self.pai = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, codigo="7", nome="Estrutura",
            ordem=1, profundidade=1,
        )
        self.f1 = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, pai=self.pai, codigo="7.4",
            nome="Fôrma", duracao_dias=3, ordem=1, profundidade=2,
        )
        self.f2 = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, pai=self.pai, codigo="7.9",
            nome="Concretagem", duracao_dias=2, ordem=2, profundidade=2,
        )
        self.solta = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.plano, codigo="99", nome="Canteiro",
            duracao_dias=5, ordem=2, profundidade=1,
        )
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = ["pdca.cronograma.view", "pdca.cronograma.edit"]
        self.client.force_authenticate(user=self.usuario)

    def _url(self):
        return f"/api/pdca/cronogramas/{self.plano.pk}/renumerar-eap/"

    def test_simular_conta_sem_escrever(self):
        resposta = self.client.post(self._url(), {"simular": True}, format="json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["mudancas"], 4)
        self.assertEqual(resposta.json()["aplicadas"], 0)
        self.f1.refresh_from_db()
        self.assertEqual(self.f1.codigo, "7.4")

    def test_a_arvore_sai_numerada_na_ordem(self):
        resposta = self.client.post(self._url(), {"simular": False}, format="json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        for atividade in (self.pai, self.f1, self.f2, self.solta):
            atividade.refresh_from_db()
        self.assertEqual(self.pai.codigo, "1")
        self.assertEqual(self.f1.codigo, "1.1")
        self.assertEqual(self.f2.codigo, "1.2")
        self.assertEqual(self.solta.codigo, "2")

    def test_a_troca_cruzada_nao_bate_na_unicidade(self):
        """O caso que obriga as duas passadas: o código novo de uma é o código
        atual da outra."""
        self.pai.codigo = "2"
        self.pai.save(update_fields=["codigo"])
        self.solta.codigo = "1"
        self.solta.save(update_fields=["codigo"])
        self.solta.ordem = 2
        self.pai.ordem = 1
        self.pai.save(update_fields=["ordem"])
        self.solta.save(update_fields=["ordem"])

        resposta = self.client.post(self._url(), {"simular": False}, format="json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.pai.refresh_from_db()
        self.solta.refresh_from_db()
        self.assertEqual((self.pai.codigo, self.solta.codigo), ("1", "2"))

    def test_arvore_ja_em_ordem_nao_escreve_nada(self):
        self.client.post(self._url(), {"simular": False}, format="json")
        resposta = self.client.post(self._url(), {"simular": False}, format="json")
        self.assertEqual(resposta.json()["mudancas"], 0)

    def test_plano_vigente_nao_renumera(self):
        self.plano.status = Cronograma.Status.VIGENTE
        self.plano.save(update_fields=["status"])
        self.assertEqual(
            self.client.post(self._url(), {"simular": False}, format="json").status_code, 400,
        )

    def test_simular_funciona_no_vigente(self):
        """Conferir não é escrever: quem olha um plano publicado pode perguntar
        quantos códigos sairiam do lugar antes de decidir replanejar."""
        self.plano.status = Cronograma.Status.VIGENTE
        self.plano.save(update_fields=["status"])
        resposta = self.client.post(self._url(), {"simular": True}, format="json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["mudancas"], 4)


# ---------------------------------------------------------------------------
# PDCA.2 — o avanço apontado
# ---------------------------------------------------------------------------
#
# O que estes testes protegem:
#
# - o livro **não se reescreve** — nem pelo model, nem pela API;
# - o avanço **sobe a árvore ponderado**, e folha sem peso fica de fora da média
#   com o denominador declarado (a régua do "número sem denominador mente");
# - as recusas do domínio acontecem **antes** da escrita: sintética, marco,
#   plano não vigente e acumulado fora de 0–100;
# - o avanço **atravessa o replanejamento** pelo código da EAP — sem isso, a v2
#   de uma obra 40% executada nasceria em zero;
# - a curva S realizada **para onde a obra parou de apontar**, e a granularidade
#   engrossa **declarando**;
# - o percentual da etapa vira **apurado**, e a caneta tem dono.


class AvancoPonderadoTests(TestCase):
    """A conta que transforma apontamento em percentual de obra."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-avanco", nome="Construtora Avanço")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra do avanço", endereco="Rua 10",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )

    def setUp(self):
        Feriado.objects.all().delete()
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )

    def _atividade(self, codigo, *, pai=None, duracao=5, peso=None, marco=False,
                   etapa=None):
        return Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, pai=pai, codigo=codigo,
            nome=f"Serviço {codigo}", duracao_dias=None if marco else duracao,
            eh_marco=marco, peso_informado=peso, etapa=etapa,
            profundidade=1 if pai is None else pai.profundidade + 1,
        )

    def _apontar(self, atividade, percentual, dia=date(2026, 6, 3)):
        return services.registrar_apontamento(
            atividade=atividade, percentual=Decimal(str(percentual)), data=dia,
            por="Teste",
        )

    # -- o livro não se reescreve -----------------------------------------

    def test_apontamento_nao_se_edita(self):
        """Append-only é propriedade do dado, não costume de quem chamou: a
        trava está no `save()`, e por isso vale para qualquer porta."""
        a = self._atividade("1")
        apontamento = self._apontar(a, 30)
        apontamento.percentual = Decimal("50")
        with self.assertRaises(ValueError):
            apontamento.save()

    def test_apontamento_de_zero_e_recusado_pelo_banco(self):
        a = self._atividade("1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ApontamentoAvanco.objects.create(
                    tenant=self.tenant, atividade=a, data=date(2026, 6, 3),
                    percentual=Decimal("0"),
                )

    # -- a conta -----------------------------------------------------------

    def test_a_folha_vale_a_soma_dos_seus_apontamentos(self):
        a = self._atividade("1", peso=Decimal("100"))
        self._apontar(a, 30)
        self._apontar(a, "25.5", dia=date(2026, 6, 5))
        leitura = services.avanco_do_cronograma(self.cronograma)
        self.assertEqual(leitura["por_atividade"][a.pk]["avanco"], 55.5)
        self.assertEqual(leitura["fisico"], 55.5)

    def test_o_pai_e_a_media_ponderada_pelo_peso_dos_filhos(self):
        """80% de uma frente que vale 3 e 0% de outra que vale 1 dão 60% — e não
        40%, que é o que a média simples diria."""
        pai = self._atividade("1")
        grande = self._atividade("1.1", pai=pai, peso=Decimal("300"))
        pequena = self._atividade("1.2", pai=pai, peso=Decimal("100"))
        self._apontar(grande, 80)
        leitura = services.avanco_do_cronograma(self.cronograma)
        self.assertEqual(leitura["por_atividade"][pai.pk]["avanco"], 60.0)
        self.assertEqual(leitura["por_atividade"][pequena.pk]["avanco"], 0.0)
        self.assertEqual(Decimal(leitura["por_atividade"][pai.pk]["peso"]), Decimal("400"))

    def test_folha_sem_peso_fica_fora_da_media_e_e_contada(self):
        """Ela não vira zero nem 'metade': sai da conta e aparece no
        denominador, que é a régua do `cobertura_do_orcamento`."""
        pai = self._atividade("1")
        com = self._atividade("1.1", pai=pai, peso=Decimal("100"))
        self._atividade("1.2", pai=pai)  # sem peso
        self._apontar(com, 50)
        leitura = services.avanco_do_cronograma(self.cronograma)
        self.assertEqual(leitura["fisico"], 50.0)
        self.assertEqual(leitura["folhas"], 2)
        self.assertEqual(leitura["folhas_sem_peso"], 1)

    def test_cronograma_sem_peso_nenhum_devolve_none_e_nao_zero(self):
        """Zero diria 'a obra não andou'; `None` diz 'não há como apurar'. São
        afirmações diferentes, e só uma delas é verdadeira aqui."""
        a = self._atividade("1")
        self._apontar(a, 40)
        leitura = services.avanco_do_cronograma(self.cronograma)
        self.assertIsNone(leitura["fisico"])
        self.assertIsNone(leitura["financeiro"])

    # -- as recusas --------------------------------------------------------

    def test_sintetica_nao_recebe_apontamento(self):
        pai = self._atividade("1")
        self._atividade("1.1", pai=pai, peso=Decimal("100"))
        with self.assertRaises(ValidationError) as erro:
            self._apontar(pai, 10)
        self.assertIn("sintética", " ".join(erro.exception.messages))

    def test_marco_so_aceita_cem_ou_menos_cem(self):
        marco = self._atividade("M1", marco=True, peso=Decimal("10"))
        with self.assertRaises(ValidationError):
            self._apontar(marco, 40)
        self._apontar(marco, 100)
        leitura = services.avanco_do_cronograma(self.cronograma)
        self.assertEqual(leitura["por_atividade"][marco.pk]["avanco"], 100.0)

    def test_plano_em_rascunho_nao_recebe_avanco(self):
        """Apontar num rascunho prenderia a execução a um plano que talvez nunca
        seja publicado."""
        self.cronograma.status = Cronograma.Status.RASCUNHO
        self.cronograma.save(update_fields=["status"])
        a = self._atividade("1")
        with self.assertRaises(ValidationError) as erro:
            self._apontar(a, 10)
        self.assertIn("vigente", " ".join(erro.exception.messages))

    def test_o_acumulado_nao_passa_de_cem(self):
        a = self._atividade("1", peso=Decimal("100"))
        self._apontar(a, 70)
        with self.assertRaises(ValidationError) as erro:
            self._apontar(a, 40)
        self.assertIn("100%", " ".join(erro.exception.messages))
        self.assertEqual(a.apontamentos.count(), 1)

    # -- o estorno ---------------------------------------------------------

    def test_estorno_e_um_apontamento_de_sinal_contrario(self):
        a = self._atividade("1", peso=Decimal("100"))
        errado = self._apontar(a, 30)
        estorno = services.estornar(errado, motivo="Frente trocada", por="Teste")
        self.assertEqual(estorno.percentual, Decimal("-30.0000"))
        self.assertEqual(estorno.estorna_id, errado.pk)
        # As duas linhas continuam no livro — o histórico não encolhe.
        self.assertEqual(a.apontamentos.count(), 2)
        leitura = services.avanco_do_cronograma(self.cronograma)
        self.assertEqual(leitura["por_atividade"][a.pk]["avanco"], 0.0)

    def test_estorno_sem_motivo_e_recusado(self):
        a = self._atividade("1", peso=Decimal("100"))
        apontamento = self._apontar(a, 30)
        with self.assertRaises(ValidationError):
            services.estornar(apontamento, motivo="   ")

    def test_nao_se_estorna_duas_vezes_nem_se_estorna_um_estorno(self):
        a = self._atividade("1", peso=Decimal("100"))
        apontamento = self._apontar(a, 30)
        estorno = services.estornar(apontamento, motivo="Erro de frente")
        with self.assertRaises(ValidationError):
            services.estornar(apontamento, motivo="De novo")
        with self.assertRaises(ValidationError):
            services.estornar(estorno, motivo="Corrigindo a correção")

    def test_o_avanco_nao_fica_negativo(self):
        a = self._atividade("1", peso=Decimal("100"))
        self._apontar(a, 10)
        with self.assertRaises(ValidationError):
            self._apontar(a, -40)

    # -- o lote ------------------------------------------------------------

    def test_o_lote_e_tudo_ou_nada_e_a_recusa_cita_a_linha(self):
        """Metade da semana no sistema e metade no caderno é pior que nada
        gravado — e a mensagem tem de dizer qual linha derrubou o bloco."""
        boa = self._atividade("1", peso=Decimal("100"))
        pai = self._atividade("2")
        self._atividade("2.1", pai=pai, peso=Decimal("50"))
        with self.assertRaises(ValidationError) as erro:
            services.apontar_em_lote(self.cronograma, [
                {"atividade": boa.pk, "data": date(2026, 6, 3), "percentual": Decimal("20")},
                {"atividade": pai.pk, "data": date(2026, 6, 3), "percentual": Decimal("10")},
            ])
        self.assertIn("Linha 2", " ".join(erro.exception.messages))
        self.assertEqual(ApontamentoAvanco.objects.count(), 0)

    def test_o_lote_le_o_teto_do_payment(self):
        a = self._atividade("1", peso=Decimal("100"))
        linhas = [
            {"atividade": a.pk, "data": date(2026, 6, 3), "percentual": Decimal("0.1")}
            for _ in range(PDCA_TETO_APONTAMENTOS_POR_LOTE + 1)
        ]
        with self.assertRaises(ValidationError) as erro:
            services.apontar_em_lote(self.cronograma, linhas)
        self.assertIn(str(PDCA_TETO_APONTAMENTOS_POR_LOTE), " ".join(erro.exception.messages))

    # -- a cadeia de versões ----------------------------------------------

    def test_o_avanco_atravessa_o_replanejamento_pelo_codigo(self):
        """É o caso que existe em toda obra depois do segundo mês: replanejar
        copia a árvore e gera ids novos. Sem o pareamento por código, a v2 de uma
        obra 40% executada nasceria em zero."""
        a = self._atividade("1", peso=Decimal("100"))
        self._apontar(a, 40)
        nova = services.replanejar(self.cronograma, motivo="Chuva de março")
        leitura = services.avanco_do_cronograma(nova)
        gemea = nova.atividades.get(codigo="1")
        self.assertEqual(leitura["por_atividade"][gemea.pk]["avanco"], 40.0)
        self.assertEqual(leitura["fisico"], 40.0)

    def test_o_apontamento_continua_preso_a_versao_em_que_nasceu(self):
        """A leitura atravessa versões; o registro, não. O que aconteceu na v1
        foi apontado na v1, e é assim que ele é auditado."""
        a = self._atividade("1", peso=Decimal("100"))
        apontamento = self._apontar(a, 40)
        services.replanejar(self.cronograma, motivo="Chuva")
        apontamento.refresh_from_db()
        self.assertEqual(apontamento.atividade.cronograma_id, self.cronograma.pk)


class CurvaSTests(TestCase):
    """As duas linhas do gráfico que o cliente confere na reunião."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-curva", nome="Construtora Curva")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra da curva", endereco="Rua 11",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )

    def setUp(self):
        Feriado.objects.all().delete()
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.a = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Fundação", duracao_dias=10, peso_informado=Decimal("100"),
            profundidade=1,
        )
        self.b = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="2",
            nome="Estrutura", duracao_dias=10, peso_informado=Decimal("100"),
            profundidade=1,
        )
        services.calcular_cpm(self.cronograma)

    def test_o_previsto_soma_cem_por_cento_no_fim(self):
        """A curva prevista é o peso inteiro distribuído no tempo: se o último
        ponto não fecha em 100%, o gráfico está mentindo sobre o plano."""
        curva = services.curva_s(self.cronograma)
        self.assertTrue(curva["pontos"])
        self.assertAlmostEqual(curva["pontos"][-1]["previsto"], 100.0, places=1)
        self.assertEqual(Decimal(curva["base_fisica"]), Decimal("200"))

    def test_o_previsto_cai_nos_dias_uteis_e_nao_no_fim_de_semana(self):
        """O peso é distribuído pelo calendário — a mesma régua com que o CPM
        produziu as datas. Num sábado não se prevê produção."""
        curva = services.curva_s(self.cronograma, granularidade="dia")
        por_dia = {p["iso"]: p["previsto_periodo"] for p in curva["pontos"]}
        self.assertEqual(por_dia.get("2026-06-06", 0.0), 0.0)  # sábado
        self.assertGreater(por_dia.get("2026-06-05", 0.0), 0.0)  # sexta

    def test_a_realizada_para_onde_a_obra_parou_de_apontar(self):
        """Linha reta até o fim do plano seria lida como 'em dia'. O que
        aconteceu foi que ninguém apontou — e `null` diz isso."""
        services.registrar_apontamento(
            atividade=self.a, percentual=Decimal("50"), data=date(2026, 6, 3),
        )
        curva = services.curva_s(self.cronograma)
        com_realizado = [p for p in curva["pontos"] if p["realizado"] is not None]
        self.assertTrue(com_realizado)
        self.assertAlmostEqual(com_realizado[-1]["realizado"], 25.0, places=1)
        self.assertIsNone(curva["pontos"][-1]["realizado"])

    def test_a_granularidade_engrossa_declarando_qual_valeu(self):
        """Engrossar calado faria a tela dizer 'por dia' desenhando meses."""
        longa = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="3",
            nome="Obra longa", duracao_dias=PDCA_TETO_PONTOS_CURVA_S + 50,
            peso_informado=Decimal("100"), profundidade=1,
        )
        services.calcular_cpm(self.cronograma)
        curva = services.curva_s(self.cronograma, granularidade="dia")
        self.assertEqual(curva["granularidade_pedida"], "dia")
        self.assertNotEqual(curva["granularidade"], "dia")
        self.assertLessEqual(len(curva["pontos"]), PDCA_TETO_PONTOS_CURVA_S)
        self.assertTrue(longa.pk)

    def test_sem_peso_a_curva_nao_e_desenhada_e_diz_por_que(self):
        Atividade.objects.filter(cronograma=self.cronograma).update(peso_informado=None)
        curva = services.curva_s(self.cronograma)
        self.assertEqual(curva["pontos"], [])
        self.assertIn("peso", curva["motivo_vazio"])

    def test_a_curva_financeira_so_existe_com_vinculo_de_orcamento(self):
        """Sem item orçado não há reais. Devolver zero desenharia uma curva
        financeira completa que ignora a obra inteira."""
        curva = services.curva_s(self.cronograma)
        self.assertIsNone(curva["base_financeira"])
        self.assertIsNone(curva["pontos"][-1]["previsto_reais"])


class PercentualDaEtapaTests(TestCase):
    """A tomada do `EtapaObra.percentual_conclusao` (planta §11.2)."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-etapa", nome="Construtora Etapa")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra da etapa", endereco="Rua 12",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )

    def setUp(self):
        Feriado.objects.all().delete()
        self.etapa = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Fundação", ordem=1,
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.a = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Sapatas", duracao_dias=5, peso_informado=Decimal("100"),
            etapa=self.etapa, profundidade=1,
        )

    def test_apontar_atualiza_o_percentual_da_etapa(self):
        """É o que faz o apontamento do campo chegar ao resumo da obra e ao
        portal do cliente sem que nenhum dos dois conheça o PDCA."""
        services.registrar_apontamento(
            atividade=self.a, percentual=Decimal("40"), data=date(2026, 6, 3),
        )
        self.etapa.refresh_from_db()
        self.assertEqual(self.etapa.percentual_conclusao, Decimal("40.00"))

    def test_a_etapa_ligada_ao_pai_e_a_filha_nao_conta_duas_vezes(self):
        """Somar pai e filha contaria a filha dentro do peso do pai e outra vez
        por fora — o erro clássico de agregação em árvore."""
        pai = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="2",
            nome="Estrutura", etapa=self.etapa, profundidade=1,
        )
        filha = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, pai=pai, codigo="2.1",
            nome="Pilares", duracao_dias=5, peso_informado=Decimal("100"),
            etapa=self.etapa, profundidade=2,
        )
        services.registrar_apontamento(
            atividade=filha, percentual=Decimal("50"), data=date(2026, 6, 3),
        )
        apurado = services.avanco_da_etapa(self.etapa)
        # 0% em uma frente de peso 100 e 50% na outra de peso 100 → 25%.
        self.assertEqual(apurado["percentual"], 25.0)
        self.assertEqual(apurado["atividades"], 2)

    def test_sem_cronograma_vigente_nao_ha_apuracao(self):
        self.cronograma.status = Cronograma.Status.SUBSTITUIDO
        self.cronograma.save(update_fields=["status"])
        self.assertIsNone(services.avanco_da_etapa(self.etapa))
        self.assertEqual(
            services.etapas_com_apuracao(obra_id=self.obra.pk, tenant_id=self.tenant.pk),
            frozenset(),
        )


class ApiDoAvancoTests(APITestCase):
    """As duas camadas de acesso, os verbos que existem e os que não existem."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-av-api", nome="Construtora API")
        cls.vizinha = Tenant.objects.create(slug="pdca-av-viz", nome="Vizinha")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra da API", endereco="Rua 13",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )
        cls.usuario = Usuario.objects.create(username="aponta", tenant=cls.tenant)

    def setUp(self):
        Feriado.objects.all().delete()
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.a = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Fundação", duracao_dias=5, peso_informado=Decimal("100"),
            profundidade=1,
        )

    def _autenticar(self, permissions=("pdca.avanco.view",)):
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = list(permissions)
        self.client.force_authenticate(user=self.usuario)

    def _apontar_pela_api(self, percentual=30):
        return self.client.post("/api/pdca/apontamentos/", {
            "atividade": self.a.pk, "data": "2026-06-03", "percentual": percentual,
        }, format="json")

    def test_sem_o_modulo_a_camada_1_barra(self):
        self.usuario.iam_modules = []
        self.usuario.iam_permissions = ["pdca.avanco.view"]
        self.client.force_authenticate(user=self.usuario)
        self.assertEqual(self.client.get("/api/pdca/apontamentos/").status_code, 403)

    def test_ver_nao_e_apontar(self):
        """Ler o avanço é do gestor; apontar é o ato de campo que vira dinheiro
        na medição. São permissões diferentes porque são pessoas diferentes."""
        self._autenticar(permissions=("pdca.avanco.view",))
        self.assertEqual(self.client.get("/api/pdca/apontamentos/").status_code, 200)
        self.assertEqual(self._apontar_pela_api().status_code, 403)

        self._autenticar(permissions=("pdca.avanco.view", "pdca.avanco.apontar"))
        self.assertEqual(self._apontar_pela_api().status_code, 201)

    def test_a_api_nao_tem_verbo_para_editar_nem_para_excluir(self):
        """A parede do model já existe; esta é a da porta. As duas, porque a
        segunda porta (bancada, importação, WhatsApp) não passa pela primeira."""
        self._autenticar(permissions=("pdca.avanco.view", "pdca.avanco.apontar"))
        criado = self._apontar_pela_api().json()
        url = f"/api/pdca/apontamentos/{criado['apontamento_id']}/"
        self.assertEqual(self.client.patch(url, {"percentual": 90}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_estornar_pela_api_exige_motivo_e_cria_a_linha_contraria(self):
        self._autenticar(permissions=("pdca.avanco.view", "pdca.avanco.apontar"))
        criado = self._apontar_pela_api().json()
        url = f"/api/pdca/apontamentos/{criado['apontamento_id']}/estornar/"
        self.assertEqual(self.client.post(url, {"motivo": ""}, format="json").status_code, 400)
        resposta = self.client.post(url, {"motivo": "Frente trocada"}, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(Decimal(resposta.json()["percentual"]), Decimal("-30.0000"))

    def test_o_lote_entra_numa_chamada(self):
        self._autenticar(permissions=("pdca.avanco.view", "pdca.avanco.apontar"))
        resposta = self.client.post("/api/pdca/apontamentos/lote/", {
            "cronograma": self.cronograma.pk,
            "linhas": [
                {"atividade": self.a.pk, "data": "2026-06-03", "percentual": "20"},
                {"atividade": self.a.pk, "data": "2026-06-04", "percentual": "30"},
            ],
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(resposta.json()["apontamentos"], 2)

    def test_o_gantt_leva_o_avanco_junto(self):
        """Buscá-lo numa segunda chamada faria a grade desenhar duas vezes, a
        segunda com as barras mudando de cor na frente de quem olha."""
        self._autenticar(permissions=(
            "pdca.avanco.view", "pdca.avanco.apontar", "pdca.cronograma.view",
        ))
        self._apontar_pela_api()
        dados = self.client.get(f"/api/pdca/cronogramas/{self.cronograma.pk}/gantt/").json()
        self.assertEqual(dados["avanco"]["por_atividade"][str(self.a.pk)]["avanco"], 30.0)

    def test_a_curva_s_responde_pelo_cronograma(self):
        self._autenticar(permissions=("pdca.cronograma.view",))
        resposta = self.client.get(
            f"/api/pdca/cronogramas/{self.cronograma.pk}/curva-s/",
            {"granularidade": "mes"},
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["granularidade"], "mes")

    def test_granularidade_inventada_e_recusada_com_as_que_existem(self):
        self._autenticar(permissions=("pdca.cronograma.view",))
        resposta = self.client.get(
            f"/api/pdca/cronogramas/{self.cronograma.pk}/curva-s/",
            {"granularidade": "quinzena"},
        )
        self.assertEqual(resposta.status_code, 400)

    def test_o_vizinho_nao_enxerga_nem_aponta(self):
        services.registrar_apontamento(
            atividade=self.a, percentual=Decimal("10"), data=date(2026, 6, 3),
        )
        intruso = Usuario.objects.create(username="intruso", tenant=self.vizinha)
        intruso.iam_modules = ["pdca"]
        intruso.iam_permissions = ["pdca.avanco.view", "pdca.avanco.apontar"]
        self.client.force_authenticate(user=intruso)
        self.assertEqual(self.client.get("/api/pdca/apontamentos/").json()["count"], 0)
        resposta = self.client.post("/api/pdca/apontamentos/", {
            "atividade": self.a.pk, "data": "2026-06-03", "percentual": 5,
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        # A contagem é lida **de dentro do tenant vizinho** (é dele a sessão da
        # RLS neste ponto), e é essa a pergunta que importa: o intruso não
        # gravou nada — nem no plano alheio, nem no próprio.
        self.assertEqual(ApontamentoAvanco.objects.filter(tenant=self.vizinha).count(), 0)


#: Os bytes iniciais de um PNG. A porta única reconhece formato pelo conteúdo
#: (D65), não pela extensão — um arquivo de teste com bytes de mentira seria
#: recusado antes de chegar ao que estes testes medem.
ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"


class FotoDoApontamentoTests(APITestCase):
    """D120 — a foto de campo sai pela porta única, e não por `/media/`.

    O [teste do D70](../funcoesimpexp/test_d70_portas_de_midia.py) cobra a
    **declaração** da porta: ele varre os `FileField` e exige que cada prefixo
    tenha recurso. O que ele não sabe fazer é abrir a porta — e uma porta
    declarada que não abre continua deixando a foto inalcançável, que era
    metade do achado. É o que está escrito aqui.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-foto", nome="Construtora Foto")
        cls.vizinha = Tenant.objects.create(slug="pdca-foto-viz", nome="Vizinha")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra da Foto", endereco="Rua 14",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )
        cls.usuario = Usuario.objects.create(username="fotografo", tenant=cls.tenant)

    def setUp(self):
        Feriado.objects.all().delete()
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.a = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Fundação", duracao_dias=5, peso_informado=Decimal("100"),
            profundidade=1,
        )

    def _autenticar(self, usuario=None, permissions=("pdca.avanco.view",)):
        usuario = usuario or self.usuario
        usuario.iam_modules = ["pdca"]
        usuario.iam_permissions = list(permissions)
        self.client.force_authenticate(user=usuario)

    def _apontar_com_foto(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        apontamento = services.registrar_apontamento(
            atividade=self.a, percentual=Decimal("30"), data=date(2026, 6, 3),
        )
        apontamento.foto.save(
            "frente.png", SimpleUploadedFile("frente.png", ASSINATURA_PNG + b" conteudo"),
            save=False,
        )
        # `save()` do model é a parede do append-only — o `update` é o caminho
        # honesto para anexar o binário a uma linha que já existe num teste.
        ApontamentoAvanco.objects.filter(pk=apontamento.pk).update(foto=apontamento.foto.name)
        apontamento.refresh_from_db()
        return apontamento

    def test_a_api_nunca_publica_media(self):
        """O vazamento em si: com `DEBUG=True` a URL de `/media/` entrega o
        binário fora de auth, de entitlement e da RLS."""
        apontamento = self._apontar_com_foto()
        self._autenticar()
        dados = self.client.get(f"/api/pdca/apontamentos/{apontamento.pk}/").json()

        self.assertNotIn("/media/", dados["foto"])
        self.assertEqual(
            dados["foto"],
            f"/api/impexp/pdca.avanco_foto/arquivo/foto/{apontamento.pk}/",
        )

    def test_apontamento_sem_foto_devolve_nulo_e_nao_uma_url_que_da_404(self):
        apontamento = services.registrar_apontamento(
            atividade=self.a, percentual=Decimal("10"), data=date(2026, 6, 4),
        )
        self._autenticar()
        dados = self.client.get(f"/api/pdca/apontamentos/{apontamento.pk}/").json()
        self.assertIsNone(dados["foto"])

    def test_a_porta_abre_para_quem_so_le_o_avanco(self):
        """`planejador` e `diretoria` não apontam — e precisam ver a evidência
        do avanço que estão conferindo (planta §8)."""
        apontamento = self._apontar_com_foto()
        self._autenticar(permissions=("pdca.avanco.view",))

        resposta = self.client.get(
            f"/api/impexp/pdca.avanco_foto/arquivo/foto/{apontamento.pk}/"
        )
        # `FileResponse` não tem `.content` — é streaming, e é o que prova que
        # o binário está saindo pela porta em vez de um JSON de erro.
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b"".join(resposta.streaming_content), ASSINATURA_PNG + b" conteudo")
        self.assertIn("attachment", resposta["Content-Disposition"])
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
        # Tipo declarado por NÓS, do mapa fechado — e não adivinhado pelo nome
        # que veio no upload.
        self.assertEqual(resposta["Content-Type"], "image/png")

    def test_sem_a_permissao_de_ler_o_avanco_a_porta_nao_abre(self):
        apontamento = self._apontar_com_foto()
        self._autenticar(permissions=("pdca.cronograma.view",))
        resposta = self.client.get(
            f"/api/impexp/pdca.avanco_foto/arquivo/foto/{apontamento.pk}/"
        )
        self.assertIn(resposta.status_code, (403, 404))

    def test_a_foto_do_vizinho_nao_abre(self):
        """404 e não 403 de propósito: responder 403 a um id de outro tenant
        confirmaria que ele existe."""
        apontamento = self._apontar_com_foto()
        intruso = Usuario.objects.create(username="intruso-foto", tenant=self.vizinha)
        self._autenticar(usuario=intruso, permissions=("pdca.avanco.view",))

        resposta = self.client.get(
            f"/api/impexp/pdca.avanco_foto/arquivo/foto/{apontamento.pk}/"
        )
        self.assertEqual(resposta.status_code, 404)


class PercentualManualPelaApiTests(APITestCase):
    """A caneta do percentual apurado tem dono (planta §11.2)."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-caneta", nome="Construtora Caneta")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra da caneta", endereco="Rua 14",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )
        cls.usuario = Usuario.objects.create(username="engenheiro", tenant=cls.tenant)

    def setUp(self):
        Feriado.objects.all().delete()
        self.etapa = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Estrutura", ordem=1,
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.a = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Pilares", duracao_dias=5, peso_informado=Decimal("100"),
            etapa=self.etapa, profundidade=1,
        )

    def _autenticar(self, permissions):
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = list(permissions)
        self.client.force_authenticate(user=self.usuario)

    def test_a_etapa_diz_de_onde_veio_o_numero(self):
        self._autenticar(("obra.obra.view",))
        dados = self.client.get(f"/api/etapas-obras/{self.etapa.pk}/").json()
        self.assertEqual(dados["percentual_origem"], "apurado")

        self.a.etapa = None
        self.a.save(update_fields=["etapa"])
        dados = self.client.get(f"/api/etapas-obras/{self.etapa.pk}/").json()
        self.assertEqual(dados["percentual_origem"], "informado")

    def test_digitar_o_percentual_apurado_exige_a_permissao(self):
        self._autenticar(("obra.obra.view", "obra.obra.edit"))
        url = f"/api/etapas-obras/{self.etapa.pk}/"
        resposta = self.client.patch(url, {"percentual_conclusao": "80.00"}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("percentual_conclusao", resposta.json())

        self._autenticar((
            "obra.obra.view", "obra.obra.edit", "obra.etapa.percentual_manual",
        ))
        resposta = self.client.patch(url, {"percentual_conclusao": "80.00"}, format="json")
        self.assertEqual(resposta.status_code, 200, resposta.content)

    def test_a_etapa_sem_apuracao_continua_livre(self):
        """A permissão nova não pode virar pedágio na etapa que o PDCA não
        alcança — ela existe só onde o número passou a ter outra fonte."""
        solta = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Acabamento", ordem=2,
        )
        self._autenticar(("obra.obra.view", "obra.obra.edit"))
        resposta = self.client.patch(
            f"/api/etapas-obras/{solta.pk}/", {"percentual_conclusao": "15.00"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)


class CalendariosQueServemAObraTests(APITestCase):
    """D118 — o select do plano novo e a pergunta que ele faz.

    `?obra=7` é filtro exato e **exclui** os calendários da empresa (`obra`
    nulo), que existem justamente para valer em todas as obras. A tela ficava
    vazia numa empresa com expediente cadastrado, e o plano nascia sem
    calendário — que é o plano que o CPM recusa calcular.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-cal", nome="Construtora Calendário")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra com plano", endereco="Rua 15",
        )
        cls.vizinha_obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra ao lado", endereco="Rua 16",
        )
        cls.da_empresa = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Expediente padrão da empresa", obra=None, padrao=True,
        )
        cls.da_obra = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Turno com sábado", obra=cls.obra, trabalha_sabado=True,
        )
        cls.da_vizinha = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Expediente da obra ao lado", obra=cls.vizinha_obra,
        )
        cls.usuario = Usuario.objects.create(username="planeja-cal", tenant=cls.tenant)

    def setUp(self):
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = ["pdca.calendario.view"]
        self.client.force_authenticate(user=self.usuario)

    def _nomes(self, url):
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200, resposta.content)
        return [c["nome"] for c in resposta.json()["results"]]

    def test_para_obra_traz_o_da_obra_e_o_da_empresa(self):
        nomes = self._nomes(f"/api/pdca/calendarios/?para_obra={self.obra.pk}")
        self.assertIn("Turno com sábado", nomes)
        self.assertIn("Expediente padrão da empresa", nomes)

    def test_para_obra_nunca_traz_o_de_outra_obra(self):
        """Oferecer o calendário da obra vizinha seria oferecer o que o
        serializer recusa depois — erro que só aparece no submit."""
        nomes = self._nomes(f"/api/pdca/calendarios/?para_obra={self.obra.pk}")
        self.assertNotIn("Expediente da obra ao lado", nomes)

    def test_a_obra_sem_expediente_proprio_ainda_ve_o_da_empresa(self):
        """É o caso da obra nova — e era o que voltava vazio."""
        sozinha = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra recém-cadastrada", endereco="Rua 17",
        )
        nomes = self._nomes(f"/api/pdca/calendarios/?para_obra={sozinha.pk}")
        self.assertEqual(nomes, ["Expediente padrão da empresa"])

    def test_o_especifico_vem_antes_do_geral(self):
        """A ordem da lista é a ordem em que eles vencem no cálculo
        (`services.calendario_da_obra`): o da obra manda no da empresa."""
        nomes = self._nomes(f"/api/pdca/calendarios/?para_obra={self.obra.pk}")
        self.assertEqual(nomes[0], "Turno com sábado")

    def test_o_filtro_exato_continua_exato(self):
        """`?obra=` não mudou: quem quer só os daquela obra continua tendo."""
        nomes = self._nomes(f"/api/pdca/calendarios/?obra={self.obra.pk}")
        self.assertEqual(nomes, ["Turno com sábado"])


# ===========================================================================
# PDCA.3 — contrato, medição e o título que sai para o ERP
# ===========================================================================
#
# O que estes testes protegem, em uma frase cada:
#
# - a medição **nasce do avanço**, e o ajuste do gestor fica visível;
# - o **acumulado não estoura o contratado**, nem por duas medições em paralelo;
# - a medição aprovada **congela** e vira **um título líquido** no ERP;
# - a **retenção** é descontada, somada na leitura e liberada só até o saldo;
# - **quem apura não ateste**, com e sem escada configurada;
# - contrato com pagamento **não é purgado** da lixeira.


class BaseContrato(TestCase):
    """Cenário comum da PDCA.3: obra, plano vigente com duas frentes apontadas,
    e um contrato de preço unitário sobre elas."""

    @classmethod
    def setUpTestData(cls):
        from fornecedores.models import Fornecedor

        cls.tenant = Tenant.objects.create(slug="pdca-ctr", nome="Construtora Contrato")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra do contrato", endereco="Rua da Medição",
        )
        cls.fornecedor = Fornecedor.objects.create(
            tenant=cls.tenant, razao_social="Empreiteira Alfa",
            email="alfa@example.com",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )

    def setUp(self):
        Feriado.objects.all().delete()
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.alvenaria = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Alvenaria", duracao_dias=20, profundidade=1,
        )
        self.reboco = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="2",
            nome="Reboco", duracao_dias=15, profundidade=1,
        )
        self.contrato = self.criar_contrato()
        self.item_alv = self.criar_item(
            "1.1", "Alvenaria de blocos", qtd="1000", preco="80",
            atividade=self.alvenaria,
        )
        self.item_reb = self.criar_item(
            "1.2", "Reboco interno", qtd="500", preco="40",
            atividade=self.reboco,
        )

    def criar_contrato(self, **extra):
        campos = dict(
            tenant=self.tenant, obra=self.obra, fornecedor=self.fornecedor,
            numero=extra.pop("numero", "001/2026"),
            objeto="Alvenaria e revestimento",
            data_inicio=date(2026, 6, 1), data_fim=date(2026, 12, 31),
            status=ContratoObra.Status.VIGENTE,
        )
        campos.update(extra)
        return ContratoObra.objects.create(**campos)

    def criar_item(self, codigo, descricao, *, qtd, preco, contrato=None, **extra):
        return ItemContrato.objects.create(
            tenant=self.tenant, contrato=contrato or self.contrato,
            codigo=codigo, descricao=descricao, unidade="m2",
            quantidade_contratada=Decimal(qtd), preco_unitario=Decimal(preco),
            **extra,
        )

    def apontar(self, atividade, percentual, dia):
        return ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=atividade,
            data=dia, percentual=Decimal(percentual),
        )


class PropostaDeMedicaoTests(BaseContrato):
    """§11.4 — a medição **nasce do avanço**, e não ao lado dele."""

    def test_a_proposta_converte_avanco_do_periodo_em_quantidade(self):
        """30% de 1.000 m² apontados em junho propõem 300 m² na medição de junho.

        É a fatia inteira em uma asserção: o número que o gestor confere não foi
        digitado por ninguém — saiu do livro do canteiro.
        """
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        proposta = services.propor_medicao(
            self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        linha = next(l for l in proposta["linhas"] if l["codigo"] == "1.1")
        self.assertEqual(linha["quantidade_proposta"], Decimal("300"))
        self.assertEqual(linha["percentual_avanco_periodo"], Decimal("30"))

    def test_o_apontamento_fora_da_janela_nao_entra(self):
        """A data do apontamento é o dia em que o serviço **andou**, não o dia em
        que alguém digitou — é por ela que a janela corta."""
        self.apontar(self.alvenaria, "30", date(2026, 5, 20))
        self.apontar(self.alvenaria, "10", date(2026, 6, 15))
        proposta = services.propor_medicao(
            self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        linha = next(l for l in proposta["linhas"] if l["codigo"] == "1.1")
        self.assertEqual(linha["quantidade_proposta"], Decimal("100"))

    def test_o_estorno_se_cancela_sozinho_dentro_da_janela(self):
        """O avanço é delta e o estorno é negativo: somar a janela já é a conta
        certa. Subtrair acumulados de duas datas reabriria a porta que o
        append-only fechou."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 10))
        self.apontar(self.alvenaria, "-10", date(2026, 6, 12))
        proposta = services.propor_medicao(
            self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        linha = next(l for l in proposta["linhas"] if l["codigo"] == "1.1")
        self.assertEqual(linha["quantidade_proposta"], Decimal("200"))

    def test_item_sem_vinculo_aparece_declarado_e_nao_como_zero(self):
        """Zero é 'não andou'; sem vínculo é 'ninguém mediu isto pelo avanço'.

        A grade tem de distinguir os dois, senão o gestor assina uma linha
        achando que o serviço parou quando o que faltou foi o cadastro.
        """
        solto = self.criar_item("1.3", "Serviço avulso", qtd="10", preco="5")
        proposta = services.propor_medicao(
            self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        linha = next(l for l in proposta["linhas"] if l["codigo"] == "1.3")
        self.assertEqual(linha["criterio"], "sem_vinculo")
        self.assertIsNone(linha["percentual_avanco_periodo"])
        self.assertEqual(proposta["cobertura"]["sem_vinculo"], 1)
        self.assertIn("1.3", proposta["cobertura"]["codigos_sem_vinculo"])
        self.assertEqual(solto.medicoes.count(), 0)

    def test_a_proposta_mostra_o_contrato_inteiro_mesmo_sem_avanco(self):
        """"Não medi isto" tem de ser uma decisão visível, e não uma linha que
        sumiu da grade."""
        proposta = services.propor_medicao(
            self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        self.assertEqual(len(proposta["linhas"]), 2)

    def test_a_proposta_nao_passa_do_saldo_e_diz_que_limitou(self):
        """Avanço errado não propaga para uma proposta impossível — e o corte é
        **declarado**, senão o gestor confere um número que o servidor mudou."""
        self.apontar(self.alvenaria, "80", date(2026, 6, 10))
        primeira = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        # **Aprovada**, e não em rascunho: o rascunho não ocupa saldo por
        # desenho (ver `saldo_do_contrato`) — ele é intenção, e um saldo que
        # encolhe quando o gestor abre uma medição para estudar seria pior que
        # o corte que este teste protege.
        services._congelar_medicao(primeira, aprovada=True)
        self.apontar(self.alvenaria, "40", date(2026, 7, 10))
        proposta = services.propor_medicao(
            self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
        )
        linha = next(l for l in proposta["linhas"] if l["codigo"] == "1.1")
        # 80% já medidos; 40% pediriam 400 m², mas só restam 200.
        self.assertEqual(linha["quantidade_proposta"], Decimal("200"))
        self.assertTrue(linha["limitada_pelo_saldo"])

    def test_duas_atividades_no_mesmo_item_ponderam_pelo_peso(self):
        """Duas frentes de tamanhos diferentes não contribuem igual para uma
        linha de contrato — é o mesmo `peso_de` da árvore do avanço."""
        grande = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="3",
            nome="Frente grande", duracao_dias=10, profundidade=1,
            peso_informado=Decimal("300"),
        )
        pequena = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="4",
            nome="Frente pequena", duracao_dias=10, profundidade=1,
            peso_informado=Decimal("100"),
        )
        self.apontar(grande, "40", date(2026, 6, 10))
        self.apontar(pequena, "80", date(2026, 6, 10))
        percentual, criterio = services.avanco_do_periodo(
            [grande, pequena], date(2026, 6, 1), date(2026, 6, 30),
        )
        self.assertEqual(criterio, "ponderado")
        # (300×40 + 100×80) / 400 = 50
        self.assertEqual(percentual, Decimal("50"))


class GradeDaMedicaoTests(BaseContrato):
    """O boletim aberto, conferido e reescrito — e o ajuste ficando visível."""

    def test_abrir_sem_linhas_aceita_a_proposta_inteira(self):
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        self.apontar(self.reboco, "20", date(2026, 6, 20))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        quantidades = {
            item.item_contrato.codigo: item.quantidade
            for item in medicao.itens.all()
        }
        self.assertEqual(quantidades, {
            "1.1": Decimal("300"), "1.2": Decimal("100"),
        })

    def test_a_linha_zerada_nao_vira_registro(self):
        """O contrato inteiro aparece na **proposta**; gravar um `ItemMedicao` de
        zero encheria o documento de linhas que não pagam nada."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        self.assertEqual(medicao.itens.count(), 1)

    def test_o_ajuste_do_gestor_fica_visivel_ao_lado_da_proposta(self):
        """Sem isto a proposta automática vira caixa preta que ninguém audita."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("250")}],
        )
        linha = medicao.itens.get()
        self.assertEqual(linha.quantidade, Decimal("250"))
        self.assertEqual(linha.quantidade_proposta, Decimal("300"))
        self.assertEqual(linha.origem, ItemMedicao.Origem.MANUAL)

    def test_reescrever_substitui_e_nao_soma(self):
        """Dois envios acidentais não podem dobrar a medição — e a tela mostra o
        documento inteiro, então o endpoint substitui."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        for _ in range(2):
            services.reescrever_linhas(medicao=medicao, linhas=[
                {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("100")},
            ])
        self.assertEqual(medicao.itens.count(), 1)
        self.assertEqual(medicao.itens.get().quantidade, Decimal("100"))

    def test_reescrever_preserva_a_memoria_da_proposta(self):
        """Apagar o que o sistema tinha calculado transformaria 'ajustou de 300
        para 100' em apenas '100'."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services.reescrever_linhas(medicao=medicao, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("100")},
        ])
        linha = medicao.itens.get()
        self.assertEqual(linha.quantidade_proposta, Decimal("300"))
        self.assertEqual(linha.percentual_avanco_periodo, Decimal("30"))

    def test_medir_contrato_em_rascunho_e_recusado(self):
        """Título a pagar de documento que ninguém assinou."""
        self.contrato.status = ContratoObra.Status.RASCUNHO
        self.contrato.save(update_fields=["status"])
        with self.assertRaises(ValidationError) as erro:
            services.criar_medicao(
                contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            )
        self.assertIn("vigente", str(erro.exception))

    def test_medir_antes_do_inicio_da_vigencia_e_recusado(self):
        with self.assertRaises(ValidationError) as erro:
            services.criar_medicao(
                contrato=self.contrato, inicio=date(2026, 5, 1), fim=date(2026, 5, 31),
            )
        self.assertIn("vigência", str(erro.exception))

    def test_a_numeracao_e_sequencial_por_contrato(self):
        """"3ª medição" é como o empreiteiro numera — e o número é do contrato,
        não da empresa."""
        outro = self.criar_contrato(numero="002/2026")
        self.criar_item("1", "Outro serviço", qtd="10", preco="10", contrato=outro)
        self.apontar(self.alvenaria, "10", date(2026, 6, 15))
        primeira = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        segunda = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
        )
        do_outro = services.criar_medicao(
            contrato=outro, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        self.assertEqual([primeira.numero, segunda.numero], [1, 2])
        self.assertEqual(do_outro.numero, 1)


class TravaDoAcumuladoTests(BaseContrato):
    """A trava que o mercado ensina (§4.4): medido acumulado ≤ contratado."""

    def test_o_acumulado_acima_do_contratado_e_recusado_com_o_excesso(self):
        self.apontar(self.alvenaria, "100", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("1200")}],
        )
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(medicao)
        mensagem = str(erro.exception)
        self.assertIn("1200", mensagem)
        self.assertIn("1000", mensagem)
        self.assertIn("aditivo", mensagem)

    def test_duas_medicoes_na_escada_nao_estouram_o_contratado_juntas(self):
        """**A razão de o acumulado contar as `EM_APROVACAO`.** Contar só as
        aprovadas deixaria as duas passarem sozinhas e estourarem juntas — e o
        estouro só apareceria depois de os dois títulos existirem."""
        fluxo, _ = _escada_de_medicao(self.tenant)
        aprovador = Usuario.objects.create(username="aprov-acum", tenant=self.tenant)
        solicitante = Usuario.objects.create(username="solic-acum", tenant=self.tenant)

        self.apontar(self.alvenaria, "60", date(2026, 6, 10))
        primeira = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services.submeter_medicao(medicao=primeira, solicitante=solicitante)
        self.assertEqual(
            Medicao.objects.get(pk=primeira.pk).status, Medicao.Status.EM_APROVACAO,
        )

        segunda = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("500")}],
        )
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(segunda)
        self.assertIn("excede o contratado", str(erro.exception))
        self.assertIsNotNone(aprovador)
        self.assertIsNotNone(fluxo)

    def test_a_validacao_junta_todos_os_problemas_de_uma_vez(self):
        """Parar no primeiro faria o gestor corrigir uma linha, resubmeter e
        descobrir a segunda — três idas e vindas para um documento que ele vê
        inteiro na tela."""
        self.apontar(self.alvenaria, "100", date(2026, 6, 10))
        self.apontar(self.reboco, "100", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[
                {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("1200")},
                {"item_contrato_id": self.item_reb.pk, "quantidade": Decimal("700")},
            ],
        )
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(medicao)
        self.assertEqual(len(erro.exception.messages), 2)

    def test_revalidar_a_propria_medicao_nao_a_conta_duas_vezes(self):
        """Sem o `excluir_medicao_id`, uma medição em aprovação reprovaria contra
        si mesma no momento do último atesto."""
        self.apontar(self.alvenaria, "100", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        medicao.status = Medicao.Status.EM_APROVACAO
        medicao.save(update_fields=["status"])
        services.validar_medicao(medicao)  # não levanta


class TituloNoErpTests(BaseContrato):
    """A fronteira com o ERP — a §6 da planta: *medição aprovada → título
    líquido → `ContaPagar`*."""

    def test_a_medicao_aprovada_congela_e_gera_um_titulo_liquido(self):
        from moduloerp.models import ContaPagar

        self.contrato.retencao_percentual = Decimal("5")
        self.contrato.retencao_natureza = NaturezaRetencao.TECNICA
        self.contrato.prazo_pagamento_dias = 30
        self.contrato.save()

        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)

        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.APROVADA)
        self.assertIsNotNone(medicao.congelada_em)
        self.assertIsNotNone(medicao.conta_pagar_ref)

        conta = ContaPagar.objects.get(pk=medicao.conta_pagar_ref)
        # 300 m² × R$ 80 = R$ 24.000 bruto; 5% de retenção = R$ 1.200.
        self.assertEqual(conta.valor, Decimal("22800.00"))
        self.assertEqual(conta.fornecedor_id, self.fornecedor.pk)
        self.assertIn("Medição 1", conta.descricao)
        self.assertIn("retenção", conta.descricao)

    def test_o_primeiro_titulo_de_verdade_da_plataforma_e_este(self):
        """O `conta_pagar_ref` do SCM existe desde 07/2026 e nunca foi
        preenchido por ninguém. Esta é a primeira escrita real na fronteira — o
        teste existe para que ela não volte a ser seam inerte."""
        self.apontar(self.alvenaria, "10", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        self.assertIsNotNone(medicao.conta_pagar_ref)

    def test_a_medicao_reprovada_congela_sem_gerar_titulo(self):
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=False)
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.REPROVADA)
        self.assertIsNone(medicao.conta_pagar_ref)

    def test_medicao_de_valor_zero_nao_gera_titulo(self):
        """Caso real — a retificadora que zera uma anterior. Um `ContaPagar` de
        R$ 0,00 é documento que ninguém consegue baixar nem explicar."""
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        self.assertIsNone(services.gerar_titulo_de_medicao(medicao))

    def test_o_vencimento_sai_do_prazo_do_contrato(self):
        """É cláusula comercial do contrato, não teto de plano (§5.6)."""
        from moduloerp.models import ContaPagar
        from django.utils import timezone as tz

        self.contrato.prazo_pagamento_dias = 45
        self.contrato.save(update_fields=["prazo_pagamento_dias"])
        self.apontar(self.alvenaria, "10", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        conta = ContaPagar.objects.get(pk=medicao.conta_pagar_ref)
        self.assertEqual(
            conta.data_vencimento, tz.localdate() + timedelta(days=45),
        )


class RetencaoTests(BaseContrato):
    """Reter e liberar — o ciclo inteiro do dinheiro que fica parado."""

    def setUp(self):
        super().setUp()
        self.contrato.retencao_percentual = Decimal("5")
        self.contrato.retencao_natureza = NaturezaRetencao.CAUCAO
        self.contrato.retencao_condicao_liberacao = (
            "Recebimento definitivo da obra pelo contratante."
        )
        self.contrato.save()
        self.usuario = Usuario.objects.create(username="gestor-ret", tenant=self.tenant)

    def _medir_e_aprovar(self, percentual="30"):
        self.apontar(self.alvenaria, percentual, date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        return medicao

    def test_o_percentual_de_retencao_e_congelado_no_nascimento(self):
        """Mudar a cláusula em 2027 não pode reescrever o líquido de uma medição
        paga em 2026."""
        medicao = self._medir_e_aprovar()
        self.contrato.retencao_percentual = Decimal("10")
        self.contrato.save(update_fields=["retencao_percentual"])
        medicao.refresh_from_db()
        self.assertEqual(medicao.retencao_percentual_aplicado, Decimal("5.00"))
        self.assertEqual(
            services.totais_da_medicao(medicao)["retencao"], Decimal("1200.00"),
        )

    def test_o_retido_e_somado_na_leitura_e_nao_guardado(self):
        """§4.9 — saldo de contrato é derivado. Não há coluna de 'retido'."""
        self._medir_e_aprovar()
        saldo = services.retencao_disponivel(self.contrato)
        self.assertEqual(saldo["retido"], Decimal("1200.00"))
        self.assertEqual(saldo["liberado"], Decimal("0.00"))
        self.assertEqual(saldo["disponivel"], Decimal("1200.00"))

    def test_medicao_em_aprovacao_nao_conta_como_retida(self):
        """Retenção de medição que ainda sobe a escada não foi descontada de
        nada — contá-la ofereceria para liberação um dinheiro que ninguém
        segurou ainda."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        medicao.status = Medicao.Status.EM_APROVACAO
        medicao.save(update_fields=["status"])
        self.assertEqual(
            services.retencao_disponivel(self.contrato)["retido"], Decimal("0.00"),
        )

    def test_liberar_gera_titulo_proprio_e_nao_mexe_no_da_medicao(self):
        """A retenção volta meses depois, com vencimento próprio — e a conta da
        medição pode já estar quitada. O extrato do empreiteiro mostra duas
        entradas porque houve dois pagamentos."""
        from moduloerp.models import ContaPagar

        medicao = self._medir_e_aprovar()
        resultado = services.solicitar_liberacao(
            contrato=self.contrato, valor=Decimal("1200"), data=date(2027, 1, 15),
            condicao_atendida="Obra recebida em 20/12/2026, termo anexo.",
            solicitante=self.usuario,
        )
        liberacao = resultado["liberacao"]
        liberacao.refresh_from_db()
        self.assertEqual(liberacao.status, LiberacaoRetencao.Status.APROVADA)
        self.assertIsNotNone(liberacao.conta_pagar_ref)
        self.assertNotEqual(liberacao.conta_pagar_ref, medicao.conta_pagar_ref)

        conta = ContaPagar.objects.get(pk=liberacao.conta_pagar_ref)
        self.assertEqual(conta.valor, Decimal("1200.00"))
        self.assertEqual(conta.data_vencimento, date(2027, 1, 15))
        self.assertIn("Liberação de retenção", conta.descricao)

    def test_liberar_acima_do_retido_e_recusado_com_as_tres_parcelas(self):
        """O teto é o saldo, e ele é derivado. A mensagem diz as parcelas porque
        'saldo insuficiente' não deixa o gestor conferir contra o extrato."""
        self._medir_e_aprovar()
        with self.assertRaises(ValidationError) as erro:
            services.solicitar_liberacao(
                contrato=self.contrato, valor=Decimal("5000"), data=date(2027, 1, 15),
                condicao_atendida="Obra recebida.", solicitante=self.usuario,
            )
        mensagem = str(erro.exception)
        self.assertIn("1200", mensagem)
        self.assertIn("5000", mensagem)

    def test_liberar_sem_declarar_a_condicao_e_recusado(self):
        """Valor liberado sem a condição escrita é o achado que uma auditoria de
        contrato registra — o campo existe para que ele não exista."""
        self._medir_e_aprovar()
        with self.assertRaises(ValidationError) as erro:
            services.solicitar_liberacao(
                contrato=self.contrato, valor=Decimal("100"), data=date(2027, 1, 15),
                condicao_atendida="   ", solicitante=self.usuario,
            )
        # A recusa mostra a cláusula do contrato, para quem pede saber o que
        # precisa declarar em vez de adivinhar. É por causa desta frase que o
        # `SolicitarLiberacaoSerializer` aceita texto em branco: o `CharField`
        # padrão recusaria antes, com "este campo não pode ser em branco", e
        # esta mensagem nunca chegaria a quem está liberando caução.
        self.assertIn("Recebimento definitivo", str(erro.exception))

    def test_duas_liberacoes_nao_devolvem_mais_do_que_foi_retido(self):
        self._medir_e_aprovar()
        services.solicitar_liberacao(
            contrato=self.contrato, valor=Decimal("1000"), data=date(2027, 1, 15),
            condicao_atendida="Parcial.", solicitante=self.usuario,
        )
        with self.assertRaises(ValidationError):
            services.solicitar_liberacao(
                contrato=self.contrato, valor=Decimal("500"), data=date(2027, 2, 15),
                condicao_atendida="Restante.", solicitante=self.usuario,
            )


class RegimesDeContratoTests(BaseContrato):
    """Três regimes, três matemáticas — e a honestidade do custo digitado."""

    def test_no_unitario_o_valor_do_contrato_e_a_soma_dos_itens(self):
        """E não um total guardado ao lado dela, que seria a segunda verdade."""
        self.assertEqual(
            services.valor_contratado(self.contrato), Decimal("100000.00"),
        )

    def test_no_global_a_soma_dos_itens_precisa_fechar_com_o_valor(self):
        """É a planilha contratual que diz quanto cada frente vale; divergir
        dela faria a medição por percentual mentir sobre o todo."""
        contrato = self.criar_contrato(
            numero="003/2026", regime=RegimeContrato.GLOBAL,
            valor_global=Decimal("50000"),
        )
        self.criar_item(
            "1", "Empreitada", qtd="1", preco="40000", contrato=contrato,
            atividade=self.alvenaria,
        )
        self.apontar(self.alvenaria, "50", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(medicao)
        self.assertIn("não fecha", str(erro.exception))

    def test_na_administracao_o_bruto_e_custo_mais_taxa(self):
        contrato = self.criar_contrato(
            numero="004/2026", regime=RegimeContrato.ADMINISTRACAO,
            valor_global=Decimal("200000"), taxa_administracao=Decimal("12"),
        )
        medicao = services.criar_medicao(
            contrato=contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[], custo_reembolsavel=Decimal("30000"),
        )
        totais = services.totais_da_medicao(medicao)
        self.assertEqual(totais["bruto"], Decimal("33600.00"))

    def test_o_custo_digitado_viaja_com_a_origem_declarada(self):
        """**A régua de dado honesto é cumprida pelo REGISTRO, não por um aviso.**

        O dono decidiu que o regime de administração entra com custo manual
        (14/09/2026), e a saída não é recusar o regime: é gravar **de onde veio
        o número**, para o boletim imprimir "custo informado pelo gestor" ao
        lado de quem o informou. Quem ateste lê isso no documento que está
        assinando.

        O que saiu daqui foi o **aviso** que repetia a mesma frase em toda
        submissão — *"a apropriação de HH (PDCA.9) ainda não está ligada"*. Ele
        não pedia ação nenhuma, aparecia sempre, e falava a língua do roadmap e
        não a de quem mede a obra (*"que mensagem bosta pro usuário final"*,
        15/09/2026). Aviso que aparece sempre e não pede nada ensina a ignorar a
        faixa de avisos — onde um dia aparece algo que importa.
        """
        contrato = self.criar_contrato(
            numero="005/2026", regime=RegimeContrato.ADMINISTRACAO,
            valor_global=Decimal("200000"), taxa_administracao=Decimal("10"),
        )
        medicao = services.criar_medicao(
            contrato=contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[], custo_reembolsavel=Decimal("10000"),
        )
        # O registro: fica no documento, e o boletim o imprime.
        self.assertEqual(medicao.custo_origem, OrigemCusto.INFORMADO)
        self.assertEqual(medicao.get_custo_origem_display(), "Informado pelo gestor")

        # E a submissão não gasta a faixa de avisos com isso.
        avisos = services.validar_medicao(medicao)["avisos"]
        self.assertFalse(
            any("apropriação" in a or "PDCA" in a for a in avisos),
            f"aviso de roadmap na tela do gestor: {avisos}",
        )

    def test_administracao_sem_custo_e_recusada(self):
        contrato = self.criar_contrato(
            numero="006/2026", regime=RegimeContrato.ADMINISTRACAO,
            valor_global=Decimal("200000"), taxa_administracao=Decimal("10"),
        )
        medicao = services.criar_medicao(
            contrato=contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(medicao)
        self.assertIn("custo reembolsável", str(erro.exception))

    def test_o_banco_recusa_valor_global_no_regime_errado(self):
        """A `CheckConstraint` é a rede de baixo — vale para o comando de
        bancada e para a importação, não só para o formulário."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ContratoObra.objects.create(
                    tenant=self.tenant, obra=self.obra, fornecedor=self.fornecedor,
                    numero="099/2026", objeto="Erro",
                    regime=RegimeContrato.GLOBAL, valor_global=None,
                    data_inicio=date(2026, 6, 1),
                )


class RetificacaoTests(BaseContrato):
    """§11.5 — aprovada congela; a correção é um documento novo."""

    def test_so_medicao_aprovada_se_retifica(self):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        with self.assertRaises(ValidationError) as erro:
            services.retificar(medicao=medicao, motivo="qualquer")
        self.assertIn("aprovada", str(erro.exception))

    def test_a_retificadora_nasce_vazia_e_aponta_para_a_corrigida(self):
        """Copiar as linhas com sinal trocado pareceria conveniência e seria uma
        armadilha: a retificação quase nunca é 'estorna tudo'."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        original = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(original, aprovada=True)
        nova = services.retificar(
            medicao=original, motivo="O item 1.1 mediu 300 e eram 250.",
        )
        self.assertEqual(nova.retifica_id, original.pk)
        self.assertEqual(nova.itens.count(), 0)
        self.assertEqual(nova.periodo_inicio, original.periodo_inicio)
        self.assertIn("mediu 300", nova.observacao)

    def test_nao_se_retifica_a_mesma_medicao_duas_vezes(self):
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        original = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(original, aprovada=True)
        services.retificar(medicao=original, motivo="primeira")
        with self.assertRaises(ValidationError) as erro:
            services.retificar(medicao=original, motivo="segunda")
        self.assertIn("já está sendo retificada", str(erro.exception))

    def test_a_retificadora_devolve_quantidade_com_linha_negativa(self):
        """Quantidade negativa **é** permitida, e só no item de medição: é como
        a retificadora devolve o que foi medido a mais. O piso de zero mora no
        acumulado."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        original = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(original, aprovada=True)
        nova = services.retificar(medicao=original, motivo="mediu a mais")
        services.reescrever_linhas(medicao=nova, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("-50")},
        ])
        services.validar_medicao(nova)  # não levanta: 300 − 50 = 250 ≤ 1000
        self.assertEqual(
            services.totais_da_medicao(nova)["bruto"], Decimal("-4000.00"),
        )

    def test_a_retificadora_nao_devolve_mais_do_que_foi_medido(self):
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        original = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(original, aprovada=True)
        nova = services.retificar(medicao=original, motivo="exagerada")
        services.reescrever_linhas(medicao=nova, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("-500")},
        ])
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(nova)
        self.assertIn("negativo", str(erro.exception))


def _escada_de_medicao(tenant, permissao="pdca.medicao.atestar", niveis=1):
    """Monta o fluxo padrão de medição do tenant, com N degraus."""
    from django.contrib.contenttypes.models import ContentType
    from nucleo.models import FluxoAprovacao, NivelAprovacao

    fluxo = FluxoAprovacao.objects.create(
        tenant=tenant, codigo="medicao", nome="Aprovação de medição",
        alvo=ContentType.objects.get_for_model(Medicao), padrao=True, ativo=True,
    )
    criados = [
        NivelAprovacao.objects.create(
            tenant=tenant, fluxo=fluxo, ordem=i + 1,
            nome=f"Degrau {i + 1}", permissao_exigida=permissao,
        )
        for i in range(niveis)
    ]
    return fluxo, criados


class EscadaDeAtestoTests(BaseContrato):
    """A PDCA.3 é o **primeiro cliente real** da máquina do `nucleo` (PDCA.0)."""

    def setUp(self):
        super().setUp()
        self.solicitante = Usuario.objects.create(
            username="apurador", tenant=self.tenant,
        )
        self.solicitante.iam_permissions = ["pdca.medicao.apurar"]
        self.aprovador = Usuario.objects.create(
            username="fiscal", tenant=self.tenant,
        )
        self.aprovador.iam_permissions = ["pdca.medicao.atestar"]
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))

    def _medicao(self):
        return services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )

    def test_sem_escada_configurada_submeter_aprova_em_um_passo(self):
        """É o contrato escrito do motor: `fluxo_para` devolvendo `None` é
        resposta legítima, não erro de configuração."""
        medicao = self._medicao()
        resultado = services.submeter_medicao(
            medicao=medicao, solicitante=self.solicitante,
        )
        self.assertEqual(resultado["estado"], "aprovada")
        self.assertIsNone(resultado["escada"])
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.APROVADA)
        self.assertIsNotNone(medicao.conta_pagar_ref)

    def test_com_escada_a_medicao_fica_parada_no_degrau(self):
        _escada_de_medicao(self.tenant)
        medicao = self._medicao()
        resultado = services.submeter_medicao(
            medicao=medicao, solicitante=self.solicitante,
        )
        self.assertEqual(resultado["estado"], "em_aprovacao")
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.EM_APROVACAO)
        # Nada de título ainda: o dinheiro só sai depois do último degrau.
        self.assertIsNone(medicao.conta_pagar_ref)

    def test_o_ultimo_degrau_congela_e_gera_o_titulo_pelo_sinal(self):
        """**O contrato do `nucleo` fechando o ciclo:** o motor não sabe o que
        aprovou; quem congela e gera o título é o receptor do `modulopdca`."""
        from nucleo import aprovacao as motor

        _escada_de_medicao(self.tenant)
        medicao = self._medicao()
        services.submeter_medicao(medicao=medicao, solicitante=self.solicitante)

        pedido = motor.pedido_de(medicao)
        motor.decidir(pedido=pedido, usuario=self.aprovador, aprovar=True)

        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.APROVADA)
        self.assertIsNotNone(medicao.conta_pagar_ref)

    def test_quem_solicitou_nao_ateste_o_proprio_pedido(self):
        """A segregação da §8, vinda de graça do motor — mas o teste existe
        porque é ela que a fatia inteira protege."""
        from django.core.exceptions import PermissionDenied
        from nucleo import aprovacao as motor

        _escada_de_medicao(self.tenant)
        self.solicitante.iam_permissions = [
            "pdca.medicao.apurar", "pdca.medicao.atestar",
        ]
        medicao = self._medicao()
        services.submeter_medicao(medicao=medicao, solicitante=self.solicitante)
        pedido = motor.pedido_de(medicao)
        with self.assertRaises(PermissionDenied):
            motor.decidir(pedido=pedido, usuario=self.solicitante, aprovar=True)

    def test_o_degrau_intermediario_nao_gera_titulo(self):
        from nucleo import aprovacao as motor

        _escada_de_medicao(self.tenant, niveis=2)
        medicao = self._medicao()
        services.submeter_medicao(medicao=medicao, solicitante=self.solicitante)

        pedido = motor.pedido_de(medicao)
        motor.decidir(pedido=pedido, usuario=self.aprovador, aprovar=True)
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.EM_APROVACAO)
        self.assertIsNone(medicao.conta_pagar_ref)

        outro = Usuario.objects.create(username="gerente", tenant=self.tenant)
        outro.iam_permissions = ["pdca.medicao.atestar"]
        motor.decidir(pedido=motor.pedido_de(medicao), usuario=outro, aprovar=True)
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.APROVADA)
        self.assertIsNotNone(medicao.conta_pagar_ref)

    def test_reprovar_encerra_e_nao_gera_titulo(self):
        from nucleo import aprovacao as motor

        _escada_de_medicao(self.tenant)
        medicao = self._medicao()
        services.submeter_medicao(medicao=medicao, solicitante=self.solicitante)
        motor.decidir(
            pedido=motor.pedido_de(medicao), usuario=self.aprovador, aprovar=False,
        )
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.REPROVADA)
        self.assertIsNone(medicao.conta_pagar_ref)

    def test_o_sinal_reenviado_nao_gera_um_segundo_titulo(self):
        """Idempotência do receptor: a escada tem `select_for_update` contra a
        corrida de milissegundos, mas o replay de fila entra por fora."""
        from nucleo import aprovacao as motor
        from moduloerp.models import ContaPagar

        _escada_de_medicao(self.tenant)
        medicao = self._medicao()
        services.submeter_medicao(medicao=medicao, solicitante=self.solicitante)
        pedido = motor.pedido_de(medicao)
        motor.decidir(pedido=pedido, usuario=self.aprovador, aprovar=True)
        antes = ContaPagar.objects.count()

        medicao.refresh_from_db()
        motor.aprovacao_concluida.send(
            sender=Medicao, pedido=pedido, alvo=medicao, aprovado=True,
        )
        self.assertEqual(ContaPagar.objects.count(), antes)

    def test_submeter_algo_que_nao_e_rascunho_e_recusado(self):
        medicao = self._medicao()
        services.submeter_medicao(medicao=medicao, solicitante=self.solicitante)
        medicao.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.submeter_medicao(medicao=medicao, solicitante=self.solicitante)


class ApiDaMedicaoTests(APITestCase):
    """As duas camadas de acesso e a segregação dos três verbos, pela API."""

    @classmethod
    def setUpTestData(cls):
        from fornecedores.models import Fornecedor

        cls.tenant = Tenant.objects.create(slug="pdca-med-api", nome="Construtora Med")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra API", endereco="Rua 9",
        )
        cls.fornecedor = Fornecedor.objects.create(
            tenant=cls.tenant, razao_social="Empreiteira API", email="api@example.com",
        )
        cls.contrato = ContratoObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, fornecedor=cls.fornecedor,
            numero="010/2026", objeto="Serviços", data_inicio=date(2026, 6, 1),
            status=ContratoObra.Status.VIGENTE,
        )
        cls.cronograma = Cronograma.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), status=Cronograma.Status.VIGENTE,
        )
        cls.atividade = Atividade.objects.create(
            tenant=cls.tenant, cronograma=cls.cronograma, codigo="1",
            nome="Serviço", duracao_dias=10, profundidade=1,
        )
        cls.item = ItemContrato.objects.create(
            tenant=cls.tenant, contrato=cls.contrato, codigo="1.1",
            descricao="Serviço", unidade="m2", atividade=cls.atividade,
            quantidade_contratada=Decimal("100"), preco_unitario=Decimal("10"),
        )
        # **A planilha contratual só se edita em rascunho** (achado do dono,
        # 15/09/2026). Os testes que exercitam o cadastro de item usam este
        # contrato; o vigente acima serve para provar a recusa.
        cls.contrato_rascunho = ContratoObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, fornecedor=cls.fornecedor,
            numero="011/2026", objeto="Contrato ainda em montagem",
            data_inicio=date(2026, 6, 1),
            status=ContratoObra.Status.RASCUNHO,
        )
        cls.item_rascunho = ItemContrato.objects.create(
            tenant=cls.tenant, contrato=cls.contrato_rascunho, codigo="1.1",
            descricao="Serviço", unidade="m2",
            quantidade_contratada=Decimal("100"), preco_unitario=Decimal("10"),
        )
        ApontamentoAvanco.objects.create(
            tenant=cls.tenant, atividade=cls.atividade,
            data=date(2026, 6, 10), percentual=Decimal("50"),
        )
        cls.usuario = Usuario.objects.create(username="gestor-api", tenant=cls.tenant)

    def _autenticar(self, permissions=("pdca.medicao.view",), modules=("pdca",)):
        self.usuario.iam_modules = list(modules)
        self.usuario.iam_permissions = list(permissions)
        self.client.force_authenticate(user=self.usuario)

    def test_sem_o_modulo_a_camada_1_barra(self):
        self._autenticar(modules=())
        self.assertEqual(self.client.get("/api/pdca/medicoes/").status_code, 403)

    def test_criar_item_de_contrato_pela_api_grava_o_tenant(self):
        """**Achado pelo E2E, e o teste de unidade não pegava.**

        O `perform_create` do `ItemContratoViewSet` confere o teto e o estado do
        contrato antes de gravar — e a primeira escrita dele chamava
        `serializer.save()` direto, engolindo a injeção de `tenant_id` do
        `TenantScopedViewSetMixin`. A linha nascia sem tenant e a RLS
        fail-closed recusava o INSERT com um **500 seco**.

        Os testes desta fatia criavam `ItemContrato` pelo ORM (com `tenant=`
        explícito) e por isso passavam por cima do buraco. Este entra pela API,
        que é o caminho que a tela usa.
        """
        self._autenticar(permissions=("pdca.contrato.view", "pdca.contrato.edit"))
        resposta = self.client.post("/api/pdca/itens-contrato/", {
            "contrato": self.contrato_rascunho.pk, "codigo": "9.9",
            "descricao": "Item criado pela API", "unidade": "m3",
            "quantidade_contratada": "10", "preco_unitario": "25",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        criado = ItemContrato.objects.get(pk=resposta.json()["item_contrato_id"])
        self.assertEqual(criado.tenant_id, self.tenant.pk)

    def test_item_sem_quantidade_e_recusado_com_mensagem_e_nao_com_500(self):
        """**D133 — achado pelo dono cadastrando um item sem quantidade.**

        A `CheckConstraint` do model recusava (e é ela que protege o comando de
        bancada e a importação), mas era a **primeira** a falar: a recusa subia
        como `IntegrityError` e o cliente recebia **500 com página de
        depuração** — a mesma classe de defeito que o `ProtectedError` motivou
        em `nucleo/excecoes.py`.

        O que se cobra aqui é o par: **400**, e a mensagem no **campo certo**.
        """
        self._autenticar(permissions=("pdca.contrato.view", "pdca.contrato.edit"))
        resposta = self.client.post("/api/pdca/itens-contrato/", {
            "contrato": self.contrato_rascunho.pk, "codigo": "8.8",
            "descricao": "Item sem quantidade", "unidade": "",
            "quantidade_contratada": "0", "preco_unitario": "0.00",
        }, format="json")
        self.assertEqual(resposta.status_code, 400, resposta.content)
        corpo = resposta.json()
        self.assertIn("quantidade_contratada", corpo)
        self.assertIn("maior que zero", str(corpo["quantidade_contratada"]))

    def test_preco_negativo_e_recusado_apontando_o_aditivo(self):
        """Negativo é supressão, e supressão é aditivo — não linha de contrato."""
        self._autenticar(permissions=("pdca.contrato.view", "pdca.contrato.edit"))
        resposta = self.client.post("/api/pdca/itens-contrato/", {
            "contrato": self.contrato_rascunho.pk, "codigo": "8.9",
            "descricao": "Item de preço negativo",
            "quantidade_contratada": "10", "preco_unitario": "-5.00",
        }, format="json")
        self.assertEqual(resposta.status_code, 400, resposta.content)
        self.assertIn("aditivo", str(resposta.json()["preco_unitario"]))

    def test_atualizar_item_pela_api_nao_perde_o_tenant(self):
        """O irmão do anterior: `perform_update` reforça o tenant, e sobrescrevê-lo
        sem `super()` deixaria o `PATCH` mover a linha para tenant nenhum."""
        self._autenticar(permissions=("pdca.contrato.view", "pdca.contrato.edit"))
        resposta = self.client.patch(
            f"/api/pdca/itens-contrato/{self.item_rascunho.pk}/",
            {"descricao": "Renomeado"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.item_rascunho.refresh_from_db()
        self.assertEqual(self.item_rascunho.tenant_id, self.tenant.pk)
        self.assertEqual(self.item_rascunho.descricao, "Renomeado")

    def test_a_planilha_fecha_quando_alguem_ja_mediu_contra_ela(self):
        """**Achado do dono, 15/09/2026 — e a régua certa levou duas tentativas.**

        A tela dizia *"a planilha não se edita mais aqui"* e a API aceitava a
        edição do mesmo jeito: ele mudou uma quantidade contratada de 53.150
        para 631.500 num contrato com medição em aprovação. Regra que mora só na
        interface não é regra: é aviso.

        A **primeira** correção fechou a planilha assim que o contrato saía de
        rascunho, e criou um beco pior que o defeito: contrato vigente sem itens
        ficava impossível de preencher, com a tela pedindo os itens e nenhum
        caminho para cadastrá-los. A régua certa é **se alguém já mediu**: antes
        da primeira medição não há nada a preservar; depois, mudar a planilha
        reescreveria o denominador de um documento assinado.
        """
        self._autenticar(permissions=("pdca.contrato.view", "pdca.contrato.edit"))

        # Contrato vigente e SEM medição: a planilha continua aberta — é o beco
        # que a primeira versão desta trava criou.
        livre = self.client.patch(
            f"/api/pdca/itens-contrato/{self.item.pk}/",
            {"descricao": "ainda dá para ajustar"}, format="json",
        )
        self.assertEqual(livre.status_code, 200, livre.content)
        self.assertTrue(
            self.client.get(
                f"/api/pdca/contratos/{self.contrato.pk}/",
            ).json()["planilha_editavel"],
        )

        # Agora alguém mede contra ela.
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)

        corpo = self.client.get(f"/api/pdca/contratos/{self.contrato.pk}/").json()
        self.assertFalse(corpo["planilha_editavel"])
        self.assertIn("aditivo", corpo["planilha_fechada_porque"])

        alterar = self.client.patch(
            f"/api/pdca/itens-contrato/{self.item.pk}/",
            {"quantidade_contratada": "631500"}, format="json",
        )
        self.assertEqual(alterar.status_code, 400, alterar.content)
        self.assertIn("aditivo", str(alterar.json()))
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade_contratada, Decimal("100.0000"))
        # E medição **cancelada** não fecha a planilha: ela não ocupa saldo e
        # não produziu efeito nenhum.

        incluir = self.client.post("/api/pdca/itens-contrato/", {
            "contrato": self.contrato.pk, "codigo": "7.7",
            "descricao": "Item que deveria ser aditivo", "unidade": "m2",
            "quantidade_contratada": "10", "preco_unitario": "5",
        }, format="json")
        self.assertEqual(incluir.status_code, 400, incluir.content)

        apagar = self.client.delete(f"/api/pdca/itens-contrato/{self.item.pk}/")
        self.assertEqual(apagar.status_code, 400, apagar.content)

    def test_a_previa_nao_grava_nada(self):
        """Abrir a medição só para ver a proposta encheria o contrato de
        rascunhos que o gestor teria de apagar depois."""
        # A prévia é leitura **de medição**, não de contrato: ela mostra o que
        # se pagaria. Quem só cadastra planilha contratual não precisa ver isso.
        self._autenticar(permissions=("pdca.contrato.view", "pdca.medicao.view"))
        resposta = self.client.get(
            f"/api/pdca/contratos/{self.contrato.pk}/proposta-de-medicao/"
            f"?inicio=2026-06-01&fim=2026-06-30"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            Decimal(resposta.json()["linhas"][0]["quantidade_proposta"]),
            Decimal("50"),
        )
        self.assertEqual(Medicao.objects.count(), 0)

    def test_apurar_nao_da_o_direito_de_aprovar_sem_escada(self):
        """**A trava de segregação da fatia.** Sem escada configurada, submeter
        aprova em um passo — então submeter exige `atestar`, não `apurar`. Sem
        isto, quem apura aprovaria o próprio boletim em todo tenant que ainda
        não montou o fluxo, que é a maioria no primeiro dia."""
        self._autenticar(permissions=("pdca.medicao.view", "pdca.medicao.apurar"))
        criar = self.client.post("/api/pdca/medicoes/abrir/", {
            "contrato": self.contrato.pk,
            "inicio": "2026-06-01", "fim": "2026-06-30",
        }, format="json")
        self.assertEqual(criar.status_code, 201)
        medicao_id = criar.json()["medicao_id"]

        resposta = self.client.post(
            f"/api/pdca/medicoes/{medicao_id}/submeter/", {}, format="json",
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertIn("atestar", resposta.json()["detail"])

    def test_com_atestar_o_caminho_de_um_passo_funciona(self):
        self._autenticar(permissions=(
            "pdca.medicao.view", "pdca.medicao.apurar", "pdca.medicao.atestar",
        ))
        criar = self.client.post("/api/pdca/medicoes/abrir/", {
            "contrato": self.contrato.pk,
            "inicio": "2026-06-01", "fim": "2026-06-30",
        }, format="json")
        medicao_id = criar.json()["medicao_id"]
        resposta = self.client.post(
            f"/api/pdca/medicoes/{medicao_id}/submeter/", {}, format="json",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["estado"], "aprovada")

    def test_com_escada_configurada_apurar_basta_para_submeter(self):
        """Havendo escada, submeter não aprova nada — quem decide é o degrau."""
        _escada_de_medicao(self.tenant)
        self._autenticar(permissions=("pdca.medicao.view", "pdca.medicao.apurar"))
        criar = self.client.post("/api/pdca/medicoes/abrir/", {
            "contrato": self.contrato.pk,
            "inicio": "2026-06-01", "fim": "2026-06-30",
        }, format="json")
        medicao_id = criar.json()["medicao_id"]
        resposta = self.client.post(
            f"/api/pdca/medicoes/{medicao_id}/submeter/", {}, format="json",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["estado"], "em_aprovacao")

    def test_a_medicao_nao_aceita_put_nem_patch(self):
        """O documento tem ciclo de vida; um `PATCH` genérico publicaria um
        caminho que atravessa o congelamento."""
        self._autenticar(permissions=("pdca.medicao.view", "pdca.medicao.apurar"))
        medicao = Medicao.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=1,
            periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 6, 30),
        )
        for verbo in (self.client.put, self.client.patch):
            resposta = verbo(
                f"/api/pdca/medicoes/{medicao.pk}/", {"numero": 9}, format="json",
            )
            self.assertEqual(resposta.status_code, 405)

    def test_o_dinheiro_sai_como_string_e_nao_como_float(self):
        """O `float` do JSON tem 53 bits de mantissa e **não representa centavo
        exatamente** — R$ 1.234,57 viraria 1234.5699999999999 na tela."""
        self._autenticar(permissions=("pdca.contrato.view",))
        dados = self.client.get(
            f"/api/pdca/contratos/{self.contrato.pk}/saldo/"
        ).json()
        self.assertIsInstance(dados["valor_contratado"], str)
        self.assertIsInstance(dados["retencao"]["retido"], str)

    def test_o_tenant_vizinho_nao_ve_contrato_nenhum(self):
        vizinha = Tenant.objects.create(slug="pdca-med-viz", nome="Vizinha")
        intruso = Usuario.objects.create(username="intruso-med", tenant=vizinha)
        intruso.iam_modules = ["pdca"]
        intruso.iam_permissions = ["pdca.contrato.view", "pdca.medicao.view"]
        self.client.force_authenticate(user=intruso)
        self.assertEqual(
            self.client.get("/api/pdca/contratos/").json()["count"], 0,
        )
        self.assertEqual(
            self.client.get(
                f"/api/pdca/contratos/{self.contrato.pk}/saldo/"
            ).status_code, 404,
        )


class SaldoDoContratoTests(BaseContrato):
    """§4.9 — derivado inteiro, sem uma coluna guardada."""

    def test_o_saldo_separa_aprovado_de_escada_de_rascunho(self):
        """O rascunho fica **fora** do saldo e aparece à parte: ele é intenção, e
        somá-lo mostraria um saldo que some quando o gestor abre uma medição
        só para estudar."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        aprovada = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(aprovada, aprovada=True)
        services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("100")}],
        )
        saldo = services.saldo_do_contrato(self.contrato)
        self.assertEqual(saldo["valor_contratado"], Decimal("100000.00"))
        self.assertEqual(saldo["medido_aprovado"], Decimal("24000.00"))
        self.assertEqual(saldo["medido_rascunho"], Decimal("8000.00"))
        self.assertEqual(saldo["saldo"], Decimal("76000.00"))

    def test_o_item_totalmente_medido_conta_como_fechado(self):
        self.apontar(self.alvenaria, "100", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        saldo = services.saldo_do_contrato(self.contrato)
        self.assertEqual(saldo["itens_fechados"], 1)
        self.assertEqual(saldo["itens"], 2)


class LixeiraDoContratoTests(BaseContrato):
    """A lixeira dá o direito de desfazer; ela não dá o direito de apagar a
    prova de para onde o dinheiro foi."""

    def test_contrato_com_titulo_nao_e_purgado(self):
        from nucleo import lixo

        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)

        usuario = Usuario.objects.create(username="quem-apagou", tenant=self.tenant)
        item = lixo.mover_para_lixo(self.contrato, usuario=usuario)
        item = lixo.purgar(item, usuario=usuario)

        self.assertIsNone(item.purgado_em)
        self.assertIn("título no financeiro", item.falha_na_purga)
        self.assertTrue(ContratoObra.todos.filter(pk=self.contrato.pk).exists())

    def test_contrato_sem_titulo_purga_normalmente(self):
        """A trava é sobre o rastro financeiro, não sobre contrato em geral."""
        from nucleo import lixo

        limpo = self.criar_contrato(numero="777/2026")
        usuario = Usuario.objects.create(username="quem-apagou-2", tenant=self.tenant)
        item = lixo.purgar(
            lixo.mover_para_lixo(limpo, usuario=usuario), usuario=usuario,
        )
        self.assertIsNotNone(item.purgado_em)
        self.assertFalse(ContratoObra.todos.filter(pk=limpo.pk).exists())


class TetosDaPdca3Tests(BaseContrato):
    """Todo teto vive em `payment/planos.py` — e o teste prende constante a
    consumidor, senão o número vira intenção."""

    def test_o_teto_de_itens_por_contrato_e_cobrado(self):
        from payment.planos import PDCA_TETO_ITENS_POR_CONTRATO

        with self.assertRaises(ValidationError) as erro:
            services.validar_teto_de_itens(
                self.contrato, acrescentando=PDCA_TETO_ITENS_POR_CONTRATO,
            )
        self.assertIn(str(PDCA_TETO_ITENS_POR_CONTRATO)[:1], str(erro.exception))

    def test_o_teto_de_linhas_por_medicao_e_cobrado(self):
        from payment.planos import PDCA_TETO_LINHAS_POR_MEDICAO

        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        demais = [
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("1")}
        ] * (PDCA_TETO_LINHAS_POR_MEDICAO + 1)
        with self.assertRaises(ValidationError) as erro:
            services.reescrever_linhas(medicao=medicao, linhas=demais)
        self.assertIn("no máximo", str(erro.exception))

    def test_o_status_publica_os_tetos_da_fatia(self):
        """A tela lê o que vale hoje em vez de carregar uma cópia que envelhece
        no bundle."""
        from payment.planos import (
            PDCA_TETO_ITENS_POR_CONTRATO, PDCA_TETO_LINHAS_POR_MEDICAO,
        )

        usuario = Usuario.objects.create(username="leitor-teto", tenant=self.tenant)
        usuario.iam_modules = ["pdca"]
        usuario.iam_permissions = ["pdca.contrato.view"]
        from rest_framework.test import APIClient

        cliente = APIClient()
        cliente.force_authenticate(user=usuario)
        tetos = cliente.get("/api/pdca/status/").json()["tetos"]
        self.assertEqual(tetos["itens_por_contrato"], PDCA_TETO_ITENS_POR_CONTRATO)
        self.assertEqual(tetos["linhas_por_medicao"], PDCA_TETO_LINHAS_POR_MEDICAO)


class ContextoDaMedicaoTests(BaseContrato):
    """**O defeito que originou a reescrita da tela**, agora com rede.

    A página montava `saldo = contratado − já medido` no navegador, com dados de
    uma prévia que só era buscada quando *não* havia medição aberta. Quem
    entrasse pelo link direto de um boletim (`/medicoes/14`) via "já medido"
    **negativo**, saldo acima do contratado e — porque a trava de excesso
    compara contra esse saldo — a trava desligada.

    O conserto foi mover a conta inteira para o servidor. Estes testes são o que
    impede a aritmética de voltar para a tela.
    """

    def test_o_contexto_exclui_a_propria_medicao_do_acumulado(self):
        self.apontar(self.alvenaria, "30", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        contexto = services.contexto_de_medicao(medicao)
        linha = next(
            l for l in contexto["linhas"] if l["item_contrato_id"] == self.item_alv.pk
        )
        # 300 m² estão NESTA medição: o acumulado "anterior" é zero, e o saldo é
        # o contratado inteiro. Nunca negativo, nunca acima do contratado.
        self.assertEqual(linha["quantidade_ja_medida"], Decimal("0"))
        self.assertEqual(linha["saldo"], Decimal("1000"))
        self.assertEqual(linha["quantidade_medida"], Decimal("300"))
        self.assertGreaterEqual(linha["quantidade_ja_medida"], 0)

    def test_o_contexto_conta_as_medicoes_anteriores(self):
        self.apontar(self.alvenaria, "30", date(2026, 6, 10))
        primeira = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(primeira, aprovada=True)
        self.apontar(self.alvenaria, "20", date(2026, 7, 10))
        segunda = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
        )
        linha = next(
            l for l in services.contexto_de_medicao(segunda)["linhas"]
            if l["item_contrato_id"] == self.item_alv.pk
        )
        self.assertEqual(linha["quantidade_ja_medida"], Decimal("300"))
        self.assertEqual(linha["saldo"], Decimal("700"))

    def test_o_contexto_traz_o_contrato_inteiro_e_a_memoria(self):
        """A grade mostra o contrato inteiro para que "não medi isto" seja uma
        decisão visível — e cada linha diz de onde a proposta saiu."""
        self.apontar(self.alvenaria, "10", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        contexto = services.contexto_de_medicao(medicao)
        self.assertEqual(len(contexto["linhas"]), 2)
        linha = next(
            l for l in contexto["linhas"] if l["item_contrato_id"] == self.item_alv.pk
        )
        self.assertEqual(len(linha["memoria"]), 1)
        self.assertEqual(linha["memoria"][0]["nome"], "Alvenaria")
        self.assertEqual(linha["memoria"][0]["percentual"], Decimal("10"))


class PeriodoEncadeadoTests(BaseContrato):
    """Medição de obra é uma corrente: um período começa onde o outro acabou."""

    def test_o_periodo_sugerido_comeca_no_dia_seguinte_ao_ultimo(self):
        self.apontar(self.alvenaria, "10", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        sugerido = services.sugerir_periodo(self.contrato)
        self.assertEqual(sugerido["inicio"], date(2026, 7, 1))
        self.assertEqual(sugerido["ultima_medicao"]["numero"], 1)

    def test_o_primeiro_periodo_comeca_na_vigencia(self):
        self.assertEqual(
            services.sugerir_periodo(self.contrato)["inicio"], self.contrato.data_inicio,
        )

    def test_periodo_sobreposto_e_recusado(self):
        """Dois períodos que se cruzam pagam o mesmo avanço duas vezes — e a
        trava do acumulado só perceberia quando a soma estourasse o contratado,
        que pode ser muitos meses depois."""
        self.apontar(self.alvenaria, "10", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        with self.assertRaises(ValidationError) as erro:
            services.criar_medicao(
                contrato=self.contrato, inicio=date(2026, 6, 15), fim=date(2026, 7, 15),
            )
        self.assertIn("sobrepõe", str(erro.exception))

    def test_a_retificadora_repete_o_periodo_de_proposito(self):
        """A exceção declarada: ela **corrige** aquele período."""
        self.apontar(self.alvenaria, "10", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        nova = services.retificar(medicao=medicao, motivo="mediu a mais")
        self.assertEqual(nova.periodo_inicio, medicao.periodo_inicio)
        self.assertEqual(nova.periodo_fim, medicao.periodo_fim)


class DeducoesDaMedicaoTests(BaseContrato):
    """O que sai do bruto **além** da retenção — e não volta."""

    def medicao_de_8000(self):
        self.apontar(self.alvenaria, "10", date(2026, 6, 10))
        return services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )

    def test_o_liquido_desconta_retencao_e_deducoes(self):
        self.contrato.retencao_percentual = Decimal("5")
        self.contrato.save()
        medicao = self.medicao_de_8000()
        services.reescrever_deducoes(medicao=medicao, deducoes=[
            {"tipo": "inss", "percentual": Decimal("11")},
            {"tipo": "multa", "valor": Decimal("500")},
        ])
        totais = services.totais_da_medicao(medicao)
        self.assertEqual(totais["bruto"], Decimal("8000.00"))
        self.assertEqual(totais["retencao"], Decimal("400.00"))
        # 11% de 8.000 = 880, mais 500 de multa.
        self.assertEqual(totais["total_deducoes"], Decimal("1380.00"))
        self.assertEqual(totais["liquido"], Decimal("6220.00"))

    def test_a_base_declarada_manda_no_percentual(self):
        """Sem base, o percentual incide sobre o bruto. Com base, sobre a
        parcela declarada — que é como o INSS de fato funciona."""
        medicao = self.medicao_de_8000()
        services.reescrever_deducoes(medicao=medicao, deducoes=[
            {"tipo": "inss", "percentual": Decimal("11"),
             "base_calculo": Decimal("2000")},
        ])
        self.assertEqual(
            services.totais_da_medicao(medicao)["total_deducoes"], Decimal("220.00"),
        )

    def test_percentual_e_valor_juntos_sao_recusados(self):
        medicao = self.medicao_de_8000()
        with self.assertRaises(ValidationError):
            services.reescrever_deducoes(medicao=medicao, deducoes=[
                {"tipo": "iss", "percentual": Decimal("5"), "valor": Decimal("100")},
            ])
        with self.assertRaises(ValidationError):
            services.reescrever_deducoes(medicao=medicao, deducoes=[{"tipo": "iss"}])

    def test_outros_exige_descricao(self):
        medicao = self.medicao_de_8000()
        with self.assertRaises(ValidationError) as erro:
            services.reescrever_deducoes(medicao=medicao, deducoes=[
                {"tipo": "outros", "valor": Decimal("100")},
            ])
        self.assertIn("descrição", str(erro.exception))

    def test_deducao_maior_que_o_bruto_nao_passa_na_validacao(self):
        """Título negativo é documento que ninguém consegue baixar."""
        medicao = self.medicao_de_8000()
        services.reescrever_deducoes(medicao=medicao, deducoes=[
            {"tipo": "multa", "valor": Decimal("9000")},
        ])
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(medicao)
        self.assertIn("líquido ficaria negativo", str(erro.exception))

    def test_o_titulo_sai_pelo_liquido_com_deducoes(self):
        medicao = self.medicao_de_8000()
        services.reescrever_deducoes(medicao=medicao, deducoes=[
            {"tipo": "iss", "percentual": Decimal("5")},
        ])
        services._congelar_medicao(medicao, aprovada=True)
        medicao.refresh_from_db()
        from moduloerp.models import ContaPagar

        conta = ContaPagar.objects.get(pk=medicao.conta_pagar_ref)
        self.assertEqual(conta.valor, Decimal("7600.00"))
        self.assertIn("deduções", conta.descricao)

    def test_so_o_rascunho_aceita_deducao(self):
        medicao = self.medicao_de_8000()
        services._congelar_medicao(medicao, aprovada=True)
        with self.assertRaises(ValidationError):
            services.reescrever_deducoes(medicao=medicao, deducoes=[
                {"tipo": "iss", "percentual": Decimal("5")},
            ])


class MaterialEstocadoTests(BaseContrato):
    """A coluna E da G703 — material posto na obra e ainda não aplicado.

    **É saldo, não delta**: cada medição declara o estoque que existe naquele
    momento, e o que se paga é a diferença contra o que a anterior declarava.
    """

    def test_o_estoque_paga_a_diferenca_e_nao_o_saldo(self):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("0"),
                     "quantidade_estocada": Decimal("100")}],
        )
        self.assertEqual(
            services.totais_da_medicao(medicao)["bruto"], Decimal("8000.00"),
        )
        services._congelar_medicao(medicao, aprovada=True)

        # Segunda medição: o MESMO estoque de 100 continua lá. Não se paga de novo.
        segunda = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("0"),
                     "quantidade_estocada": Decimal("100")}],
        )
        self.assertEqual(
            services.totais_da_medicao(segunda)["bruto"], Decimal("0.00"),
        )

    def test_material_aplicado_sai_do_estoque_e_entra_como_servico(self):
        """O material vira serviço: o estoque cai, a quantidade sobe, e as duas
        diferenças se cancelam — ninguém paga duas vezes pela mesma unidade."""
        primeira = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("0"),
                     "quantidade_estocada": Decimal("100")}],
        )
        services._congelar_medicao(primeira, aprovada=True)
        segunda = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
            linhas=[{"item_contrato_id": self.item_alv.pk,
                     "quantidade": Decimal("100"),
                     "quantidade_estocada": Decimal("0")}],
        )
        totais = services.totais_da_medicao(segunda)
        self.assertEqual(totais["executado"], Decimal("8000.00"))
        self.assertEqual(totais["material_estocado"], Decimal("-8000.00"))
        self.assertEqual(totais["bruto"], Decimal("0.00"))

    def test_executado_mais_estocado_nao_passam_do_contratado(self):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item_alv.pk,
                     "quantidade": Decimal("600"),
                     "quantidade_estocada": Decimal("500")}],
        )
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(medicao)
        self.assertIn("excede o contratado", str(erro.exception))

    def test_o_saldo_da_grade_desconta_o_material_ja_estocado(self):
        primeira = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("0"),
                     "quantidade_estocada": Decimal("400")}],
        )
        services._congelar_medicao(primeira, aprovada=True)
        proposta = services.propor_medicao(
            self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
        )
        linha = next(
            l for l in proposta["linhas"] if l["item_contrato_id"] == self.item_alv.pk
        )
        self.assertEqual(linha["saldo"], Decimal("600"))
        self.assertEqual(linha["estocado_anterior"], Decimal("400"))


class AditivoTests(BaseContrato):
    """PDCA.4 — o contrato mudando por escrito.

    A régua é uma só, e vale para toda linha: **contratado atual = original +
    Σ deltas de aditivos aprovados**. O campo do `ItemContrato` nunca é
    reescrito, e é ele o denominador do limite legal.
    """

    def aditivo(self, **extra):
        campos = dict(
            contrato=self.contrato, objeto="Acréscimo de alvenaria",
            justificativa="Projeto revisado aumentou a área do bloco B",
        )
        campos.update(extra)
        return services.criar_aditivo(**campos)

    def test_o_aditivo_em_rascunho_nao_move_saldo(self):
        antes = services.valor_contratado(self.contrato)
        self.aditivo(itens=[{
            "acao": "acrescimo", "item_contrato_id": self.item_alv.pk,
            "quantidade_delta": Decimal("200"),
        }])
        self.assertEqual(services.valor_contratado(self.contrato), antes)

    def test_o_acrescimo_aprovado_aumenta_o_contratado_e_o_saldo(self):
        aditivo = self.aditivo(itens=[{
            "acao": "acrescimo", "item_contrato_id": self.item_alv.pk,
            "quantidade_delta": Decimal("200"),
        }])
        services._congelar_aditivo(aditivo, aprovado=True)

        atual = services.contratado_atual_por_item(self.contrato)
        self.assertEqual(atual[self.item_alv.pk], Decimal("1200"))
        # O campo do item continua sendo o do dia da assinatura.
        self.item_alv.refresh_from_db()
        self.assertEqual(self.item_alv.quantidade_contratada, Decimal("1000"))
        # 1200 × 80 + 500 × 40 = 116.000
        self.assertEqual(services.valor_contratado(self.contrato), Decimal("116000.00"))

    def test_a_supressao_nao_pode_cair_abaixo_do_ja_medido(self):
        self.apontar(self.alvenaria, "50", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)  # 500 m² medidos

        aditivo = self.aditivo(itens=[{
            "acao": "supressao", "item_contrato_id": self.item_alv.pk,
            "quantidade_delta": Decimal("-600"),
        }])
        with self.assertRaises(ValidationError) as erro:
            services.validar_aditivo(aditivo)
        self.assertIn("abaixo do que já foi medido", str(erro.exception))

    def test_a_inclusao_cria_item_com_original_zero(self):
        """A regra `atual = original + Σ deltas` vale **sem exceção**: item novo
        tem original zero e a quantidade inteira no `ItemAditivo`."""
        aditivo = self.aditivo(itens=[{
            "acao": "inclusao", "codigo_novo": "1.3",
            "descricao_nova": "Impermeabilização", "unidade_nova": "m2",
            "quantidade_delta": Decimal("300"), "preco_unitario": Decimal("60"),
        }])
        services._congelar_aditivo(aditivo, aprovado=True)

        novo = self.contrato.itens.get(codigo="1.3")
        self.assertEqual(novo.quantidade_contratada, Decimal("0"))
        self.assertEqual(novo.aditivo_origem_id, aditivo.pk)
        atual = services.contratado_atual_por_item(self.contrato)
        self.assertEqual(atual[novo.pk], Decimal("300"))

    def test_a_inclusao_recusa_codigo_que_ja_existe(self):
        with self.assertRaises(ValidationError) as erro:
            self.aditivo(itens=[{
                "acao": "inclusao", "codigo_novo": "1.1",
                "descricao_nova": "Duplicata", "quantidade_delta": Decimal("10"),
                "preco_unitario": Decimal("10"),
            }])
        self.assertIn("já existe", str(erro.exception))

    def test_a_revisao_de_preco_nao_reescreve_medicao_congelada(self):
        self.apontar(self.alvenaria, "10", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        antes = services.totais_da_medicao(medicao)["bruto"]

        aditivo = self.aditivo(
            objeto="Reajuste", itens=[{
                "acao": "preco", "item_contrato_id": self.item_alv.pk,
                "preco_unitario": Decimal("100"),
            }],
        )
        services._congelar_aditivo(aditivo, aprovado=True)

        self.item_alv.refresh_from_db()
        self.assertEqual(self.item_alv.preco_unitario, Decimal("100.0000"))
        # O documento pago continua valendo o que valia.
        self.assertEqual(services.totais_da_medicao(medicao)["bruto"], antes)
        linha = aditivo.itens.get(item_contrato=self.item_alv)
        self.assertEqual(linha.preco_unitario_anterior, Decimal("80.0000"))

    def test_o_regime_publico_confere_contra_o_limite_digitado(self):
        self.contrato.regime_publico = True
        self.contrato.limite_acrescimo_percentual = Decimal("25")
        self.contrato.save()
        # Contratado original: 1000×80 + 500×40 = 100.000. 25% = 25.000.
        aditivo = self.aditivo(itens=[{
            "acao": "acrescimo", "item_contrato_id": self.item_alv.pk,
            "quantidade_delta": Decimal("400"),  # 32.000
        }])
        with self.assertRaises(ValidationError) as erro:
            services.validar_aditivo(aditivo)
        self.assertIn("acima do limite de 25", str(erro.exception))

    def test_o_limite_publico_conta_contra_o_ORIGINAL_e_nao_o_aditado(self):
        """20% + 20% são 44% do assinado, não 40% — e é por isso que o
        denominador é o contratado original."""
        self.contrato.regime_publico = True
        self.contrato.limite_acrescimo_percentual = Decimal("25")
        self.contrato.save()
        primeiro = self.aditivo(itens=[{
            "acao": "acrescimo", "item_contrato_id": self.item_alv.pk,
            "quantidade_delta": Decimal("200"),  # 16.000 = 16%
        }])
        services._congelar_aditivo(primeiro, aprovado=True)

        # +16% = 32% do ORIGINAL (não 32% do já aditado, que daria menos).
        segundo = self.aditivo(itens=[{
            "acao": "acrescimo", "item_contrato_id": self.item_alv.pk,
            "quantidade_delta": Decimal("200"),
        }])
        with self.assertRaises(ValidationError) as erro:
            services.validar_aditivo(segundo)
        self.assertIn("32", str(erro.exception))

    def test_a_prorrogacao_move_a_vigencia(self):
        aditivo = self.aditivo(
            objeto="Prorrogação", nova_data_fim=date(2027, 3, 31), itens=[],
        )
        services._congelar_aditivo(aditivo, aprovado=True)
        self.contrato.refresh_from_db()
        self.assertEqual(self.contrato.data_fim, date(2027, 3, 31))

    def test_o_aditivo_vazio_e_recusado(self):
        aditivo = self.aditivo(itens=[])
        with self.assertRaises(ValidationError) as erro:
            services.validar_aditivo(aditivo)
        self.assertIn("não muda nada", str(erro.exception))

    def test_a_medicao_mede_contra_o_contratado_ADITADO(self):
        """O fecho da fatia: aditivo aprovado abre saldo para medir."""
        self.apontar(self.alvenaria, "100", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)  # 1000 m², item fechado

        aditivo = self.aditivo(itens=[{
            "acao": "acrescimo", "item_contrato_id": self.item_alv.pk,
            "quantidade_delta": Decimal("200"),
        }])
        services._congelar_aditivo(aditivo, aprovado=True)

        segunda = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 7, 1), fim=date(2026, 7, 31),
            linhas=[{"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("200")}],
        )
        # Passa: 1000 + 200 = 1200 = contratado atual.
        self.assertEqual(services.validar_medicao(segunda)["avisos"], [])

    def test_o_teto_de_aditivos_abertos_morde(self):
        from payment.planos import PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO

        for n in range(PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO):
            services.criar_aditivo(
                contrato=self.contrato, objeto=f"Aditivo {n}",
                justificativa="teste do teto",
            )
        with self.assertRaises(ValidationError) as erro:
            services.criar_aditivo(
                contrato=self.contrato, objeto="Um a mais",
                justificativa="teste do teto",
            )
        self.assertIn("em aberto", str(erro.exception))


class ApiDaPdca4Tests(APITestCase):
    """As portas novas, pelo HTTP — inclusive as permissões."""

    def setUp(self):
        from fornecedores.models import Fornecedor

        self.tenant = Tenant.objects.create(slug="pdca4-api", nome="Construtora API")
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra API", endereco="Rua API",
        )
        fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Empreiteira API", email="api@example.com",
        )
        self.contrato = ContratoObra.objects.create(
            tenant=self.tenant, obra=self.obra, fornecedor=fornecedor,
            numero="API/2026", objeto="Serviços", data_inicio=date(2026, 6, 1),
            status=ContratoObra.Status.VIGENTE,
        )
        self.item = ItemContrato.objects.create(
            tenant=self.tenant, contrato=self.contrato, codigo="1.1",
            descricao="Serviço", unidade="m2",
            quantidade_contratada=Decimal("100"), preco_unitario=Decimal("10"),
        )
        self.usuario = Usuario.objects.create(username="gestor4", tenant=self.tenant)
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = [
            "pdca.contrato.view", "pdca.contrato.edit", "pdca.medicao.view",
            "pdca.medicao.apurar", "pdca.medicao.atestar", "pdca.aditivo.edit",
            "pdca.aditivo.aprovar",
        ]
        self.client.force_authenticate(user=self.usuario)

    def test_o_contexto_responde_a_grade_inteira(self):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item.pk, "quantidade": Decimal("10")}],
        )
        resposta = self.client.get(f"/api/pdca/medicoes/{medicao.pk}/contexto/")
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["numero"], medicao.numero)
        self.assertTrue(corpo["editavel"])
        self.assertEqual(len(corpo["linhas"]), 1)
        # Dinheiro e quantidade viajam como STRING — float não representa centavo.
        self.assertIsInstance(corpo["linhas"][0]["saldo"], str)
        self.assertIsInstance(corpo["totais"]["liquido"], str)

    def test_a_lista_resumida_nao_traz_as_linhas(self):
        services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item.pk, "quantidade": Decimal("10")}],
        )
        completa = self.client.get(
            f"/api/pdca/medicoes/?contrato={self.contrato.pk}&resumo=0",
        ).json()["results"][0]
        self.assertIn("itens", completa)

        resumida = self.client.get(
            f"/api/pdca/medicoes/?contrato={self.contrato.pk}&resumo=1",
        ).json()["results"][0]
        self.assertNotIn("itens", resumida)
        self.assertIn("totais", resumida)

    def test_o_cabecalho_grava_o_custo_do_regime_de_administracao(self):
        self.contrato.regime = RegimeContrato.ADMINISTRACAO
        self.contrato.valor_global = Decimal("50000")
        self.contrato.taxa_administracao = Decimal("12")
        self.contrato.save()
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        resposta = self.client.post(
            f"/api/pdca/medicoes/{medicao.pk}/cabecalho/",
            {"custo_reembolsavel": "10000.00"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200)
        medicao.refresh_from_db()
        self.assertEqual(medicao.custo_reembolsavel, Decimal("10000.00"))
        self.assertEqual(resposta.json()["totais"]["bruto"], "11200.00")

    def test_reprovar_sem_motivo_e_recusado(self):
        """A planta manda registrar o atesto com autor, data e **observação**."""
        _escada_de_medicao(self.tenant)
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item.pk, "quantidade": Decimal("10")}],
        )
        self.client.post(f"/api/pdca/medicoes/{medicao.pk}/submeter/", {}, format="json")

        # **Quem apurou não ateste** — o motor recusa o autoatesto por padrão,
        # e é a segregação da §8. A decisão vem de outra pessoa.
        fiscal = Usuario.objects.create(username="fiscal4", tenant=self.tenant)
        fiscal.iam_modules = ["pdca"]
        fiscal.iam_permissions = ["pdca.medicao.view", "pdca.medicao.atestar"]
        self.client.force_authenticate(user=fiscal)

        recusa = self.client.post(
            f"/api/pdca/medicoes/{medicao.pk}/atestar/",
            {"aprovar": False}, format="json",
        )
        self.assertEqual(recusa.status_code, 400)
        self.assertIn("observacao", recusa.json())

        ok = self.client.post(
            f"/api/pdca/medicoes/{medicao.pk}/atestar/",
            {"aprovar": False, "observacao": "o item 1.1 não bate com o diário"},
            format="json",
        )
        self.assertEqual(ok.status_code, 200)

    def test_o_aditivo_abre_submete_e_aplica_pela_api(self):
        resposta = self.client.post("/api/pdca/aditivos/abrir/", {
            "contrato": self.contrato.pk,
            "objeto": "Acréscimo",
            "justificativa": "projeto revisado",
            "itens": [{
                "acao": "acrescimo", "item_contrato_id": self.item.pk,
                "quantidade_delta": "50",
            }],
        }, format="json")
        self.assertEqual(resposta.status_code, 201)
        aditivo_id = resposta.json()["aditivo_id"]
        self.assertEqual(resposta.json()["resumo"]["acrescimo"], "500.00")

        submissao = self.client.post(
            f"/api/pdca/aditivos/{aditivo_id}/submeter/", {}, format="json",
        )
        self.assertEqual(submissao.status_code, 200)
        self.assertEqual(submissao.json()["estado"], "aprovado")

        atual = services.contratado_atual_por_item(self.contrato)
        self.assertEqual(atual[self.item.pk], Decimal("150"))

    def test_quem_so_monta_aditivo_nao_aprova_sozinho(self):
        """Sem escada configurada, submeter aprova em um passo — e por isso
        exige `pdca.aditivo.aprovar`, não o `edit` que montou o documento."""
        self.usuario.iam_permissions = [
            "pdca.contrato.view", "pdca.medicao.view", "pdca.aditivo.edit",
        ]
        aditivo = services.criar_aditivo(
            contrato=self.contrato, objeto="Acréscimo", justificativa="x",
            itens=[{"acao": "acrescimo", "item_contrato_id": self.item.pk,
                    "quantidade_delta": Decimal("10")}],
        )
        resposta = self.client.post(
            f"/api/pdca/aditivos/{aditivo.pk}/submeter/", {}, format="json",
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertIn("pdca.aditivo.aprovar", resposta.json()["detail"])

    def test_os_totais_nao_achatam_a_lista_de_deducoes(self):
        """**A estrutura sobrevive à serialização, e só o `Decimal` vira string.**

        A primeira escrita do `get_totais` fazia `str(valor)` num nível só, e
        isso transformava a lista de deduções na string `"[]"`. O boletim
        percorre essa lista: a tela da medição ficava **em branco**
        (`r.deducoes.map is not a function`), e foi assim que o dono achou —
        clicando numa medição da lista.

        O mesmo vale para o resumo do aditivo, que carrega inteiro e decimal
        lado a lado.
        """
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[{"item_contrato_id": self.item.pk, "quantidade": Decimal("10")}],
        )
        services.reescrever_deducoes(medicao=medicao, deducoes=[
            {"tipo": "iss", "percentual": Decimal("5")},
        ])

        corpo = self.client.get(f"/api/pdca/medicoes/{medicao.pk}/").json()
        totais = corpo["totais"]
        self.assertIsInstance(totais["deducoes"], list)
        self.assertEqual(len(totais["deducoes"]), 1)
        self.assertEqual(totais["deducoes"][0]["tipo"], "iss")
        # Dinheiro continua string — o float do JSON não representa centavo.
        self.assertIsInstance(totais["deducoes"][0]["valor"], str)
        self.assertIsInstance(totais["liquido"], str)

        # E na lista resumida, que é outro caminho de serialização.
        resumida = self.client.get(
            f"/api/pdca/medicoes/?contrato={self.contrato.pk}&resumo=1",
        ).json()["results"][0]
        self.assertIsInstance(resumida["totais"]["deducoes"], list)

        # O resumo do aditivo: decimais viram string, a contagem continua int.
        aditivo = services.criar_aditivo(
            contrato=self.contrato, objeto="x", justificativa="y",
            itens=[{"acao": "acrescimo", "item_contrato_id": self.item.pk,
                    "quantidade_delta": Decimal("5")}],
        )
        resumo = self.client.get(f"/api/pdca/aditivos/{aditivo.pk}/").json()["resumo"]
        self.assertIsInstance(resumo["acrescimo"], str)
        self.assertIsInstance(resumo["itens"], int)

    def test_o_periodo_sugerido_responde_pelo_contrato(self):
        resposta = self.client.get(
            f"/api/pdca/contratos/{self.contrato.pk}/periodo-sugerido/",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["inicio"], "2026-06-01")
