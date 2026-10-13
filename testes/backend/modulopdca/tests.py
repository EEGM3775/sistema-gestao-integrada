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
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from modulocalendar.models import Feriado
from nucleo.models import Tenant, Usuario
from obras.models import EtapaObra, Obra
from payment.planos import (
    PDCA_PROFUNDIDADE_MAXIMA_LOCAL, PDCA_TETO_APONTAMENTOS_POR_LOTE,
    PDCA_TETO_LOCAIS_POR_GERACAO, PDCA_TETO_PONTOS_CURVA_S,
    PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO,
    PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA, PDCA_TETO_LINHAS_POR_FRENTE,
    PDCA_TETO_OBRAS_NA_CARTEIRA,
    PDCA_TETO_RESULTADOS_POR_ESPECIE,
    PDCA_TETO_CONTRATOS_NO_POSTO,
)

from modulopdca import services
from modulopdca.models import (
    AditivoContrato,
    ApontamentoAvanco, Atividade, CalendarioTrabalho, CausaNaoCumprimento,
    ContratoObra, Cronograma,
    ExcecaoCalendario, ItemContrato, ItemMedicao, LiberacaoRetencao, LocalObra,
    ItemProgramacao, Medicao, NaturezaRetencao, NivelLocal, OrigemCusto,
    Precedencia, ProgramacaoSemanal, Restricao, TipoRestricao,
    RegimeContrato,
    DominioVerificacao, GravidadeNC, ItemModeloVerificacao, ItemVerificacao,
    ModeloVerificacao, NaoConformidade, PlanoAcao, ResultadoItem, Verificacao,
    VerificacaoEficacia,
    AnexoOcorrencia, ClassificacaoOcorrencia, DialogoSeguranca, Lateralidade,
    Ocorrencia, ParticipanteDDS, TipoCAT, TipoOcorrencia,
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
        #: **Não se crava o número da fatia corrente aqui.** Um `== "PDCA.6"`
        #: envelhece na entrega seguinte e passa a acusar falha no que é
        #: sucesso — foi o que este teste fez quando a PDCA.7 saiu, e é a mesma
        #: armadilha que o README dos E2E já nomeava do outro lado. O que
        #: importa provar é que o módulo **declara** uma fatia; quais
        #: capacidades estão de pé são as asserções abaixo, uma a uma.
        self.assertTrue(dados["fatia"].startswith("PDCA."))
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
        # PDCA.5: o Check e o Act. A restrição bloqueia o compromisso, o
        # compromisso vira PPC e o PPC vira ranking de causa — e o seam do SCM
        # é vivo, o que a tela precisa saber para oferecer o botão.
        self.assertTrue(dados["recursos"]["restricao"])
        # PDCA.6: o plano visto pelo ritmo. Sem tabela nova — a LOB é
        # derivada de `Atividade` × `LocalObra` (§4.9).
        self.assertTrue(dados["recursos"]["linha_de_balanco"])
        self.assertTrue(dados["recursos"]["conflito_de_equipe"])
        self.assertTrue(dados["recursos"]["programacao_semanal"])
        self.assertTrue(dados["recursos"]["ppc"])
        self.assertTrue(dados["recursos"]["ranking_de_causas"])
        self.assertTrue(dados["recursos"]["restricao_gera_demanda"])
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

    def test_replanejar_com_rascunho_aberto_e_recusado(self):
        """A tela abria o vigente depois de replanejar; a pessoa replanejava de
        novo e a obra juntava rascunhos órfãos (achado no teste do dono)."""
        self.atividade("1", duracao=2)
        services.publicar(self.cronograma)
        services.replanejar(self.cronograma, motivo="Chuva")
        with self.assertRaises(ValidationError) as ctx:
            services.replanejar(self.cronograma, motivo="De novo")
        self.assertIn("versão 2 em rascunho", str(ctx.exception))
        self.assertEqual(
            Cronograma.objects.filter(obra=self.obra, status=Cronograma.Status.RASCUNHO).count(), 1,
        )

    def test_os_feriados_sao_os_do_lugar_da_obra_mesmo_com_a_tabela_vazia(self):
        """Achado do dono: o expediente sem UF/IBGE só via o nacional, e a obra
        na Bahia perdia o 2 de Julho que a Agenda mostrava. Agora vale o lugar
        da obra (pelo endereço) e a lei é calculada se a tabela não tem o ano."""
        self.assertFalse(Feriado.objects.exists())
        lugar = {"cidade": "Nazaré", "uf": "BA", "ibge": "2922508", "fonte": "ibge_nome"}
        with patch("nucleo.geo.resolver", return_value=lugar):
            self.assertEqual(services.localidade_dos_feriados(self.calendario)["uf"], "BA")
            feriados = services.feriados_do_periodo(self.calendario, date(2026, 7, 1), date(2026, 7, 31))
        self.assertIn(date(2026, 7, 2), feriados)  # Independência da Bahia (estadual)
        # Sem lugar resolvível, só o nacional — e o 7 de setembro vem do cálculo.
        with patch("nucleo.geo.resolver", return_value=None):
            feriados = services.feriados_do_periodo(self.calendario, date(2026, 7, 1), date(2026, 9, 30))
        self.assertNotIn(date(2026, 7, 2), feriados)
        self.assertIn(date(2026, 9, 7), feriados)

    def test_uf_digitado_no_expediente_vence_o_endereco_da_obra(self):
        cal = CalendarioTrabalho.objects.create(tenant=self.tenant, nome="Turno SP", uf="SP")
        with patch("nucleo.geo.resolver") as resolver:
            self.assertEqual(services.localidade_dos_feriados(cal, self.obra)["fonte"], "expediente")
        resolver.assert_not_called()

    def test_publicar_leva_as_restricoes_abertas_para_a_versao_nova(self):
        """Sem isto o make-ready ficava preso à v1 e a semana da v2 não via trava."""
        a = self.atividade("1", duracao=2)
        services.publicar(self.cronograma)
        aberta = Restricao.objects.create(
            tenant=self.tenant, atividade=a, tipo=TipoRestricao.MATERIAL, descricao="Aço",
        )
        resolvida = Restricao.objects.create(
            tenant=self.tenant, atividade=a, tipo=TipoRestricao.PROJETO, descricao="Planta",
        )
        services.remover_restricao(restricao=resolvida, por="Ana", nota="liberada")
        nova = services.replanejar(self.cronograma, motivo="Chuva")
        services.publicar(nova)
        aberta.refresh_from_db()
        resolvida.refresh_from_db()
        self.assertEqual(aberta.atividade.cronograma_id, nova.pk)
        self.assertEqual(aberta.atividade.codigo, "1")
        self.assertEqual(resolvida.atividade_id, a.pk)

    def test_descartado_o_rascunho_replaneja_de_novo(self):
        self.atividade("1", duracao=2)
        services.publicar(self.cronograma)
        services.replanejar(self.cronograma, motivo="Chuva").delete()
        nova = services.replanejar(self.cronograma, motivo="Agora sim")
        self.assertEqual(nova.status, Cronograma.Status.RASCUNHO)

    def test_o_gantt_leva_os_dias_parados_do_expediente(self):
        """O CPM pulava o feriado e a barra não mostrava; o Gantt recebe a
        regra da semana e as datas avulsas para cortar a barra nelas."""
        Feriado.objects.create(data=date(2026, 6, 4), nome="Corpus Christi", escopo="nacional")
        ExcecaoCalendario.objects.create(
            tenant=self.tenant, calendario=self.calendario, data=date(2026, 6, 5),
            trabalha=False, motivo="Recesso",
        )
        a = self.atividade("1", duracao=5)
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db()
        bloco = services.expedientes_do_plano(self.cronograma, [a])
        self.assertEqual(bloco["calendario_do_plano"], self.calendario.pk)
        cal = bloco["calendarios"][str(self.calendario.pk)]
        self.assertEqual(cal["dias_da_semana"], [True] * 5 + [False] * 2)
        self.assertEqual(cal["feriados"], [{"data": date(2026, 6, 4), "nome": "Corpus Christi"}])
        self.assertEqual(cal["excecoes"][0]["motivo"], "Recesso")


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

    def test_a_seta_de_fase_entre_etapas_e_aceita(self):
        """Desde 09/10/2026 a etapa se liga (decisão do dono: "dependências de
        fases") — o CPM a expande nas folhas."""
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, pai=self.a,
            codigo="1.1", nome="Sapata", duracao_dias=2, profundidade=2,
        )
        outra = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="2",
            nome="Estrutura", duracao_dias=3, profundidade=1,
        )
        resposta = self.client.post("/api/pdca/precedencias/", {
            "origem": self.a.pk, "destino": outra.pk, "tipo": "FS",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.content)

    def test_a_etapa_nao_se_liga_ao_que_ela_contem(self):
        self._autenticar(permissions=("pdca.cronograma.view", "pdca.cronograma.edit"))
        filho = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, pai=self.a,
            codigo="1.1", nome="Sapata", duracao_dias=2, profundidade=2,
        )
        resposta = self.client.post("/api/pdca/precedencias/", {
            "origem": self.a.pk, "destino": filho.pk, "tipo": "FS",
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("dentro", str(resposta.json()))

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


class CancelarMedicaoELevarOTituloTests(BaseContrato):
    """**Cancelar a medição não cancelava o pagamento** *(achado do dono,
    15/09/2026)*.

    O `cancelar/` mexia só no PDCA: a medição virava `CANCELADA` e a
    `ContaPagar` que ela gerou continuava aberta no financeiro, com a descrição
    apontando para um boletim que não existe mais. O empreiteiro recebia por uma
    medição retirada, e a conciliação só percebia no fim do mês.
    """

    def _aprovada(self):
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(medicao, aprovada=True)
        medicao.refresh_from_db()
        return medicao

    def test_cancelar_a_aprovada_leva_o_titulo_junto(self):
        from moduloerp.models import ContaPagar

        medicao = self._aprovada()
        resultado = services.cancelar_medicao(
            medicao=medicao, motivo="Quantidade do item 1.1 estava errada.",
            por="Ana",
        )
        medicao.refresh_from_db()
        conta = ContaPagar.objects.get(pk=medicao.conta_pagar_ref)
        self.assertEqual(medicao.status, Medicao.Status.CANCELADA)
        self.assertEqual(conta.status, "CANCELADO")
        self.assertEqual(resultado["titulo_cancelado"], conta.pk)

    def test_o_titulo_JA_PAGO_tranca_o_cancelamento(self):
        """O dinheiro que saiu do caixa não se apaga cancelando o papel que o
        justificou: existe uma `Transacao` lançada, e um título cancelado com
        baixa em cima é um buraco que a conciliação não fecha nunca."""
        from moduloerp.models import ContaPagar

        medicao = self._aprovada()
        conta = ContaPagar.objects.get(pk=medicao.conta_pagar_ref)
        conta.dar_baixa(valor=conta.valor, data=date(2026, 7, 5))
        with self.assertRaises(ValidationError) as ctx:
            services.cancelar_medicao(
                medicao=medicao, motivo="tentando cancelar depois de pago",
                por="Ana",
            )
        mensagem = " ".join(ctx.exception.messages)
        self.assertIn("retificadora", mensagem)
        medicao.refresh_from_db()
        conta.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.APROVADA)
        self.assertEqual(conta.status, "QUITADO")

    def test_a_baixa_PARCIAL_tranca_do_mesmo_jeito(self):
        """O caso traiçoeiro: o status ainda não é `QUITADO`, o título parece
        vivo, e já saiu dinheiro."""
        from moduloerp.models import ContaPagar

        medicao = self._aprovada()
        conta = ContaPagar.objects.get(pk=medicao.conta_pagar_ref)
        conta.dar_baixa(valor=Decimal("1000.00"), data=date(2026, 7, 5))
        conta.refresh_from_db()
        self.assertEqual(conta.status, "PARCIAL")
        with self.assertRaises(ValidationError):
            services.cancelar_medicao(
                medicao=medicao, motivo="parcial", por="Ana",
            )

    def test_cancelar_aprovada_exige_motivo(self):
        medicao = self._aprovada()
        with self.assertRaises(ValidationError) as ctx:
            services.cancelar_medicao(medicao=medicao, por="Ana")
        self.assertIn("motivo", " ".join(ctx.exception.messages).lower())

    def test_o_rascunho_cancela_sem_motivo_porque_nao_produziu_efeito(self):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        resultado = services.cancelar_medicao(medicao=medicao, por="Ana")
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.CANCELADA)
        self.assertIsNone(resultado["titulo_cancelado"])

    def test_cancelada_nao_se_cancela_de_novo(self):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        services.cancelar_medicao(medicao=medicao, por="Ana")
        with self.assertRaises(ValidationError):
            services.cancelar_medicao(medicao=medicao, por="Ana")

    def test_o_motivo_fica_escrito_na_observacao(self):
        """O financeiro precisa da frase que explica por que o título sumiu."""
        medicao = self._aprovada()
        services.cancelar_medicao(
            medicao=medicao, motivo="Item 1.1 mediu 300 e eram 180.", por="Ana",
        )
        medicao.refresh_from_db()
        self.assertIn("mediu 300 e eram 180", medicao.observacao)

    def test_a_tela_sabe_ANTES_de_clicar_se_da_para_cancelar(self):
        """O aviso da tela e a trava do servidor saem do mesmo lugar — dois
        lugares divergiriam na primeira mudança de regra."""
        from moduloerp.models import ContaPagar

        medicao = self._aprovada()
        self.assertTrue(services.estado_do_titulo(medicao)["pode_cancelar"])
        conta = ContaPagar.objects.get(pk=medicao.conta_pagar_ref)
        conta.dar_baixa(valor=conta.valor, data=date(2026, 7, 5))
        self.assertFalse(services.estado_do_titulo(medicao)["pode_cancelar"])

    def test_medicao_sem_titulo_nao_tem_estado_de_titulo(self):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        self.assertIsNone(services.estado_do_titulo(medicao))

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
    """§11.5 — aprovada congela; a correção é um documento novo que **substitui**
    a original *(decisão do dono, 11/10/2026)*."""

    def _aprovada(self):
        """300 × R$ 80 = R$ 24.000, aprovada, com título no ERP."""
        self.apontar(self.alvenaria, "30", date(2026, 6, 15))
        original = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        services._congelar_medicao(original, aprovada=True)
        original.refresh_from_db()
        return original

    def _retificada_com_desconto(self, *, pagar: Decimal | None):
        """Original de R$ 24.000 e retificadora com R$ 600 de multa."""
        from moduloerp.models import ContaPagar

        original = self._aprovada()
        antigo = ContaPagar.objects.get(pk=original.conta_pagar_ref)
        if pagar is not None:
            antigo.dar_baixa(valor=pagar, data=date(2026, 7, 5))
        nova = services.retificar(medicao=original, motivo="Multa não lançada.")
        services.reescrever_deducoes(medicao=nova, deducoes=[
            {"tipo": "multa", "valor": Decimal("600")},
        ])
        return original, antigo, nova

    def test_a_retificadora_nasce_como_copia_inteira_da_original(self):
        original = self._aprovada()
        nova = services.retificar(
            medicao=original, motivo="O item 1.1 mediu 300 e eram 250.",
        )
        self.assertEqual(nova.retifica_id, original.pk)
        self.assertEqual(
            [(l.item_contrato_id, l.quantidade) for l in nova.itens.all()],
            [(l.item_contrato_id, l.quantidade) for l in original.itens.all()],
        )
        self.assertEqual(nova.periodo_inicio, original.periodo_inicio)
        self.assertEqual(nova.retencao_percentual_aplicado, original.retencao_percentual_aplicado)
        self.assertIn("mediu 300", nova.observacao)

    def test_o_liquido_e_o_da_medicao_corrigida_e_nao_a_diferenca(self):
        original, _antigo, nova = self._retificada_com_desconto(pagar=None)
        liquido_original = services.totais_da_medicao(original)["liquido"]
        totais = services.totais_da_medicao(nova)
        self.assertEqual(totais["liquido"], liquido_original - Decimal("600.00"))
        self.assertEqual(totais["diferenca_liquido"], Decimal("-600.00"))
        self.assertEqual(totais["original"]["liquido"], liquido_original)

    def test_sem_correcao_nenhuma_a_retificadora_nao_sobe(self):
        original = self._aprovada()
        nova = services.retificar(medicao=original, motivo="nada")
        with self.assertRaises(ValidationError) as erro:
            services.validar_medicao(nova)
        self.assertIn("não corrige nada", str(erro.exception))

    def test_aprovada_a_retificadora_a_original_vira_retificada_e_so_uma_vale(self):
        original = self._aprovada()
        nova = services.retificar(medicao=original, motivo="eram 250")
        services.reescrever_linhas(medicao=nova, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("250")},
        ])
        services._congelar_medicao(nova, aprovada=True)
        original.refresh_from_db()
        self.assertEqual(original.status, Medicao.Status.RETIFICADA)
        self.assertEqual(
            self.contrato.medicoes.filter(status=Medicao.Status.APROVADA).count(), 1,
        )
        self.assertEqual(
            services.medido_por_item(self.contrato)[self.item_alv.pk], Decimal("250"),
        )

    def test_em_aprovacao_a_retificadora_nao_soma_com_a_original(self):
        original = self._aprovada()
        nova = services.retificar(medicao=original, motivo="eram 250")
        services.reescrever_linhas(medicao=nova, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("250")},
        ])
        Medicao.objects.filter(pk=nova.pk).update(status=Medicao.Status.EM_APROVACAO)
        self.assertEqual(
            services.medido_por_item(self.contrato)[self.item_alv.pk], Decimal("250"),
        )

    def test_titulo_em_aberto_cancela_o_antigo_e_gera_o_do_liquido_inteiro(self):
        from moduloerp.models import ContaPagar

        _original, antigo, nova = self._retificada_com_desconto(pagar=None)
        liquido = services.totais_da_medicao(nova)["liquido"]
        services._congelar_medicao(nova, aprovada=True)
        nova.refresh_from_db()
        antigo.refresh_from_db()
        self.assertEqual(antigo.status, "CANCELADO")
        novo = ContaPagar.objects.get(pk=nova.conta_pagar_ref)
        self.assertEqual(novo.valor, liquido)
        self.assertEqual(novo.status, "ABERTO")

    def test_paga_a_maior_gera_complemento_e_aviso_de_nivel_3(self):
        from moduloerp.models import ContaPagar
        from nucleo.models import Notificacao

        original = self._aprovada()
        antigo = ContaPagar.objects.get(pk=original.conta_pagar_ref)
        antigo.dar_baixa(valor=antigo.valor, data=date(2026, 7, 5))
        nova = services.retificar(medicao=original, motivo="eram 350")
        services.reescrever_linhas(medicao=nova, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("350")},
        ])
        services._congelar_medicao(nova, aprovada=True)
        nova.refresh_from_db()
        complemento = ContaPagar.objects.get(pk=nova.conta_pagar_ref)
        self.assertNotEqual(complemento.pk, antigo.pk)
        self.assertEqual(complemento.valor, Decimal("4000.00"))
        self.assertIn("complemento", complemento.descricao)
        for aviso in Notificacao.objects.filter(titulo__icontains="retificada"):
            self.assertEqual(aviso.nivel, Notificacao.Nivel.AGIR_JA)

    def test_paga_inteira_e_corrigida_para_menos_avisa_a_devolucao(self):
        from nucleo.models import Notificacao

        original, antigo, nova = self._retificada_com_desconto(pagar=Decimal("24000"))
        services._congelar_medicao(nova, aprovada=True)
        nova.refresh_from_db()
        antigo.refresh_from_db()
        self.assertEqual(antigo.status, "QUITADO")
        self.assertEqual(nova.conta_pagar_ref, antigo.pk)
        for aviso in Notificacao.objects.filter(titulo__icontains="retificada"):
            self.assertIn("600", aviso.mensagem)

    def test_paga_em_parte_e_corrigida_para_menos_abate_o_saldo_do_titulo(self):
        _original, antigo, nova = self._retificada_com_desconto(pagar=Decimal("10000"))
        services._congelar_medicao(nova, aprovada=True)
        antigo.refresh_from_db()
        self.assertEqual(antigo.valor, Decimal("23400.00"))
        self.assertEqual(antigo.status, "PARCIAL")

    def test_retificadora_retirada_antes_de_valer_e_apagada(self):
        original = self._aprovada()
        nova = services.retificar(medicao=original, motivo="engano")
        resultado = services.cancelar_medicao(medicao=nova, por="Ana")
        self.assertTrue(resultado["excluida"])
        self.assertFalse(Medicao.todos.filter(pk=nova.pk).exists())
        original.refresh_from_db()
        self.assertEqual(original.status, Medicao.Status.APROVADA)
        # E a original pode ser retificada de novo.
        services.retificar(medicao=original, motivo="agora sim")

    def test_retificadora_aprovada_nao_se_cancela(self):
        original = self._aprovada()
        nova = services.retificar(medicao=original, motivo="eram 250")
        services.reescrever_linhas(medicao=nova, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("250")},
        ])
        services._congelar_medicao(nova, aprovada=True)
        nova.refresh_from_db()
        with self.assertRaises(ValidationError) as erro:
            services.cancelar_medicao(medicao=nova, motivo="desfazer", por="Ana")
        self.assertIn("retifique esta", str(erro.exception))

    def test_so_medicao_aprovada_se_retifica(self):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[],
        )
        with self.assertRaises(ValidationError) as erro:
            services.retificar(medicao=medicao, motivo="qualquer")
        self.assertIn("aprovada", str(erro.exception))

    def test_nao_se_retifica_a_mesma_medicao_duas_vezes(self):
        original = self._aprovada()
        services.retificar(medicao=original, motivo="primeira")
        with self.assertRaises(ValidationError) as erro:
            services.retificar(medicao=original, motivo="segunda")
        self.assertIn("já está sendo retificada", str(erro.exception))

    def test_a_retificadora_pode_zerar_a_medicao(self):
        original = self._aprovada()
        nova = services.retificar(medicao=original, motivo="não era deste período")
        services.reescrever_linhas(medicao=nova, linhas=[])
        services.validar_medicao(nova)
        self.assertEqual(services.totais_da_medicao(nova)["bruto"], Decimal("0.00"))

    def test_a_migracao_0036_converte_a_retificadora_antiga_e_acerta_o_titulo(self):
        """O caso do staging (11/10/2026): retificadora aprovada no formato antigo
        (sem linhas, só o desconto de R$ 600), original ainda aprovada com título
        aberto, e duas retificadoras canceladas de lixo."""
        import importlib

        from django.apps import apps as registro
        from django.db import connection
        from moduloerp.models import ContaPagar

        from modulopdca.models import DeducaoMedicao

        mig = importlib.import_module("modulopdca.migrations.0036_converter_retificadoras")
        original = self._aprovada()
        antigo = ContaPagar.objects.get(pk=original.conta_pagar_ref)
        comum = dict(
            tenant=self.tenant, contrato=self.contrato,
            periodo_inicio=original.periodo_inicio, periodo_fim=original.periodo_fim,
            retifica=original,
        )
        lixo = Medicao.objects.create(numero=2, status=Medicao.Status.CANCELADA, **comum)
        velha = Medicao.objects.create(numero=3, status=Medicao.Status.APROVADA, **comum)
        DeducaoMedicao.objects.create(
            tenant=self.tenant, medicao=velha, tipo="outros", valor=Decimal("600"),
        )

        class Editor:
            pass
        editor = Editor()
        editor.connection = connection
        mig.converter(registro, editor)
        mig.fechar(registro, editor)

        self.assertFalse(Medicao.todos.filter(pk=lixo.pk).exists())
        velha.refresh_from_db()
        original.refresh_from_db()
        antigo.refresh_from_db()
        self.assertEqual(
            [(l.item_contrato_id, l.quantidade) for l in velha.itens.all()],
            [(l.item_contrato_id, l.quantidade) for l in original.itens.all()],
        )
        self.assertEqual(original.status, Medicao.Status.RETIFICADA)
        self.assertEqual(antigo.status, "CANCELADO")
        novo = ContaPagar.objects.get(pk=velha.conta_pagar_ref)
        self.assertEqual(novo.valor, Decimal("23400.00"))
        self.assertEqual(
            services.medido_por_item(self.contrato)[self.item_alv.pk], Decimal("300"),
        )

    def test_mexer_no_erp_avisa_quem_da_baixa_uma_vez_por_fato(self):
        """Regra do dono (11/10/2026): alteração que interfere em outro módulo
        tem notificação. Medição aprovada → título → aviso ao financeiro; a
        retificação → "título trocado"; repetir o mesmo fato não duplica."""
        from nucleo.models import Notificacao
        from nucleo.notificacoes import avisar_quem_pode

        financeiro = Usuario.objects.create(
            username="financeiro", tenant=self.tenant, is_superuser=True,
        )
        original = self._aprovada()
        avisos = Notificacao.objects.filter(user=financeiro)
        self.assertTrue(avisos.filter(titulo__contains="virou título").exists())
        nova = services.retificar(medicao=original, motivo="eram 250")
        services.reescrever_linhas(medicao=nova, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("250")},
        ])
        services._congelar_medicao(nova, aprovada=True)
        trocado = avisos.get(titulo__contains="título trocado")
        self.assertIn("cancelado", trocado.mensagem)
        antes = avisos.count()
        avisar_quem_pode(
            tenant_id=self.tenant.pk, permissao="erp.conta_pagar.baixar",
            titulo=trocado.titulo, mensagem="de novo",
        )
        self.assertEqual(avisos.count(), antes)

    def test_a_ficha_conta_o_titulo_uma_vez_e_mostra_a_retificada(self):
        _original, antigo, nova = self._retificada_com_desconto(pagar=Decimal("24000"))
        services._congelar_medicao(nova, aprovada=True)
        ficha = services.ficha_do_contrato(self.contrato)
        self.assertEqual(ficha["financeiro"]["titulos"], 1)
        self.assertEqual(ficha["financeiro"]["pago"], Decimal("24000.00"))
        medicoes = [e for e in ficha["linha_do_tempo"] if e["tipo"] == "medicao"]
        self.assertEqual(
            [e["status"] for e in medicoes],
            [Medicao.Status.RETIFICADA, Medicao.Status.APROVADA],
        )
        self.assertIn(f"substituída pela {nova.numero}", medicoes[0]["detalhe"])

    def test_o_proximo_periodo_continua_depois_da_retificada(self):
        original = self._aprovada()
        nova = services.retificar(medicao=original, motivo="eram 250")
        services.reescrever_linhas(medicao=nova, linhas=[
            {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("250")},
        ])
        services._congelar_medicao(nova, aprovada=True)
        self.assertEqual(
            services.sugerir_periodo(self.contrato)["inicio"], date(2026, 7, 1),
        )


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

    # --- Cancelar: o degrau depende do ESTADO, e o portão é só o piso --------
    #
    # **Este par existe por causa de um buraco fechado antes de sair da bancada.**
    # A primeira escrita do cancelamento da medição aprovada pôs
    # `"cancelar": "pdca.medicao.apurar"` no `action_permission_map` — o que
    # parecia o piso natural e **fechava a porta para a pessoa certa**: as
    # personas `diretoria` e `fiscal_de_obra` têm `medicao.atestar` e **não** têm
    # `apurar` (é a segregação da §8, de propósito), então o portão as barrava
    # antes de a ação rodar. O portão virou `view`, e cada degrau é cobrado
    # dentro da ação.

    def _medicao(self, status=None):
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        if status is not None:
            medicao.status = status
            medicao.save(update_fields=["status"])
        return medicao

    def test_quem_so_ATESTA_cancela_a_medicao_aprovada(self):
        """A `diretoria` e o `fiscal_de_obra` são exatamente este caso."""
        medicao = self._medicao(Medicao.Status.APROVADA)
        self._autenticar(permissions=("pdca.medicao.view", "pdca.medicao.atestar"))
        resposta = self.client.post(
            f"/api/pdca/medicoes/{medicao.pk}/cancelar/",
            {"motivo": "Boletim emitido para o contrato errado."}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.CANCELADA)

    def test_quem_so_APURA_nao_cancela_a_aprovada(self):
        """Derrubar um título a pagar é alçada de dinheiro, não de quem monta o
        boletim — é a mesma separação que já vale entre apurar e atestar."""
        medicao = self._medicao(Medicao.Status.APROVADA)
        self._autenticar(permissions=("pdca.medicao.view", "pdca.medicao.apurar"))
        resposta = self.client.post(
            f"/api/pdca/medicoes/{medicao.pk}/cancelar/",
            {"motivo": "tentando"}, format="json",
        )
        self.assertEqual(resposta.status_code, 403, resposta.content)
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.APROVADA)

    def test_quem_so_LE_nao_retira_nem_um_rascunho(self):
        """O portão baixou para `view`; sem esta cobrança dentro da ação, baixar
        o piso teria deixado qualquer leitor retirar um documento."""
        medicao = self._medicao()
        self._autenticar(permissions=("pdca.medicao.view",))
        resposta = self.client.post(
            f"/api/pdca/medicoes/{medicao.pk}/cancelar/", {}, format="json",
        )
        self.assertEqual(resposta.status_code, 403, resposta.content)

    def test_quem_APURA_retira_o_rascunho(self):
        medicao = self._medicao()
        self._autenticar(permissions=("pdca.medicao.view", "pdca.medicao.apurar"))
        resposta = self.client.post(
            f"/api/pdca/medicoes/{medicao.pk}/cancelar/", {}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        medicao.refresh_from_db()
        self.assertEqual(medicao.status, Medicao.Status.CANCELADA)

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

    def test_o_aditivo_aprovado_muda_a_retencao_do_contrato_para_a_frente(self):
        aditivo = self.aditivo(retencao_percentual_nova=Decimal("5"))
        services._congelar_aditivo(aditivo, aprovado=True)
        self.contrato.refresh_from_db()
        self.assertEqual(self.contrato.retencao_percentual, Decimal("5"))
        self.apontar(self.alvenaria, "10", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
        )
        # 100 × 80 = 8.000 × 5%
        self.assertEqual(services.totais_da_medicao(medicao)["retencao"], Decimal("400.00"))

    def test_o_item_novo_do_aditivo_retem_pela_regra_propria(self):
        aditivo = self.aditivo(itens=[{
            "acao": "inclusao", "codigo_novo": "9.1", "descricao_nova": "Muro",
            "unidade_nova": "m", "quantidade_delta": Decimal("100"),
            "preco_unitario": Decimal("50"), "retencao_percentual": Decimal("10"),
        }])
        services._congelar_aditivo(aditivo, aprovado=True)
        muro = self.contrato.itens.get(codigo="9.1")
        self.assertEqual(muro.retencao_percentual, Decimal("10"))
        self.apontar(self.alvenaria, "10", date(2026, 6, 10))
        medicao = services.criar_medicao(
            contrato=self.contrato, inicio=date(2026, 6, 1), fim=date(2026, 6, 30),
            linhas=[
                {"item_contrato_id": self.item_alv.pk, "quantidade": Decimal("100")},
                {"item_contrato_id": muro.pk, "quantidade": Decimal("20")},
            ],
        )
        totais = services.totais_da_medicao(medicao)
        # Contrato sem retenção: só o muro retém — 20 × 50 = 1.000 × 10%.
        self.assertEqual(totais["retencao"], Decimal("100.00"))
        self.assertTrue(totais["retencao_por_item"])

    def test_o_cabecalho_do_rascunho_se_edita_e_o_aprovado_nao(self):
        aditivo = self.aditivo()
        services.editar_aditivo(
            aditivo=aditivo, objeto="Prorrogação", nova_data_fim=date(2027, 3, 31),
        )
        aditivo.refresh_from_db()
        self.assertEqual(aditivo.objeto, "Prorrogação")
        services._congelar_aditivo(aditivo, aprovado=True)
        with self.assertRaises(ValidationError):
            services.editar_aditivo(aditivo=aditivo, objeto="outra coisa")

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


# ===========================================================================
# PDCA.5 — Last Planner: make-ready, compromisso da semana, PPC e causa
# ===========================================================================
# O que estes testes protegem, em uma frase cada:
#
# - **a regra que separa o LPS de uma lista de tarefas**: atividade com restrição
#   aberta não entra na programação, e a trava é conferida duas vezes (ao puxar o
#   cartão e ao assumir a semana) porque a trava pode nascer entre as duas;
# - **o PPC é derivado e honesto**: não existe enquanto a semana não encerra, e a
#   tela recebe `None`, nunca 0% — fabricar um fracasso que ainda não aconteceu é
#   o mesmo pecado do avanço sem apontamento;
# - **não cumprido exige causa**, e a regra vale no banco, não só na aplicação;
# - **o seam do SCM é vivo e idempotente** — restrição de material vira demanda,
#   e clicar duas vezes não compra o material duas vezes.


class _BaseLastPlanner(TestCase):
    """Fixture comum: uma obra com plano vigente e duas atividades folha."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-lps", nome="Construtora LPS")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Compromisso", endereco="Rua 5",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, obra=cls.obra, nome="Padrão",
        )
        cls.cronograma = Cronograma.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=cls.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        cls.a1 = Atividade.objects.create(
            tenant=cls.tenant, cronograma=cls.cronograma, codigo="1",
            nome="Alvenaria do 4º", duracao_dias=5, profundidade=1,
        )
        cls.a2 = Atividade.objects.create(
            tenant=cls.tenant, cronograma=cls.cronograma, codigo="2",
            nome="Contrapiso do 4º", duracao_dias=3, profundidade=1,
        )

    def _restricao(self, atividade=None, tipo=TipoRestricao.MATERIAL, **extra):
        return Restricao.objects.create(
            tenant=self.tenant, atividade=atividade or self.a1, tipo=tipo,
            descricao=extra.pop("descricao", "Bloco cerâmico não entregue"),
            **extra,
        )

    def _programacao(self, semana=date(2026, 6, 1), **extra):
        return services.abrir_programacao(
            obra=self.obra, semana_inicio=semana, tenant_id=self.tenant.pk, **extra
        )

    def _item(self, programacao, atividade=None, **extra):
        return ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=programacao,
            atividade=atividade or self.a1, **extra,
        )


class MakeReadyTests(_BaseLastPlanner):
    """A restrição — e a regra que dá sentido a ela."""

    def test_atividade_com_restricao_aberta_nao_entra_na_programacao(self):
        """**É a regra que separa o LPS de uma lista de tarefas** (planta §4.3)."""
        self._restricao(self.a1)
        with self.assertRaises(ValidationError) as ctx:
            services.validar_pode_comprometer(self.a1, tenant_id=self.tenant.pk)
        self.assertIn("restrição", " ".join(ctx.exception.messages).lower())

    def test_a_recusa_nomeia_o_que_trava(self):
        """Dizer só "não pode" obrigaria a pessoa a procurar; a mensagem traz o
        tipo e a descrição, que é o que ela precisa para ir destravar."""
        self._restricao(self.a1, descricao="Projeto estrutural revisão 3 não liberado",
                        tipo=TipoRestricao.PROJETO)
        with self.assertRaises(ValidationError) as ctx:
            services.validar_pode_comprometer(self.a1, tenant_id=self.tenant.pk)
        mensagem = " ".join(ctx.exception.messages)
        self.assertIn("Projeto estrutural", mensagem)

    def test_restricao_removida_libera_a_atividade(self):
        r = self._restricao(self.a1)
        services.remover_restricao(
            restricao=r, por="Ana", nota="Entrega recebida na 3ª feira",
        )
        services.validar_pode_comprometer(self.a1, tenant_id=self.tenant.pk)
        r.refresh_from_db()
        self.assertEqual(r.status, Restricao.Status.REMOVIDA)
        self.assertIsNotNone(r.removida_em)

    def test_remover_sem_dizer_como_e_recusado(self):
        """Restrição que some sem explicação deixa a reunião seguinte sem saber
        se ela foi resolvida ou esquecida."""
        r = self._restricao(self.a1)
        with self.assertRaises(ValidationError):
            services.remover_restricao(restricao=r, por="Ana", nota="   ")

    def test_restricao_ja_removida_nao_se_remove_de_novo(self):
        r = self._restricao(self.a1)
        services.remover_restricao(restricao=r, por="Ana", nota="ok")
        with self.assertRaises(ValidationError):
            services.remover_restricao(restricao=r, por="Ana", nota="de novo")

    def test_a_trava_e_por_atividade_e_nao_por_obra(self):
        """Travar a obra inteira porque uma frente está parada seria o oposto do
        make-ready: o time deixaria de se comprometer com o que pode fazer."""
        self._restricao(self.a1)
        services.validar_pode_comprometer(self.a2, tenant_id=self.tenant.pk)

    def test_o_agregado_de_travas_sai_em_uma_consulta(self):
        """300 cartões perguntando cada um "estou travado?" seriam 300
        consultas para desenhar uma parede (a lição do D136)."""
        self._restricao(self.a1)
        self._restricao(self.a1, tipo=TipoRestricao.AREA)
        self._restricao(self.a2)
        with self.assertNumQueries(1):
            mapa = services.restricoes_abertas_por_atividade(
                [self.a1.pk, self.a2.pk], tenant_id=self.tenant.pk,
            )
        self.assertEqual(mapa, {self.a1.pk: 2, self.a2.pk: 1})


class CicloDaSemanaTests(_BaseLastPlanner):
    """Abrir → comprometer → julgar → encerrar, e as recusas de cada degrau."""

    def test_a_semana_ancora_na_segunda(self):
        """Qualquer dia serve na entrada; a âncora é do servidor. Deixar o
        cliente calcular a segunda produziria uma semana diferente por fuso de
        navegador."""
        prog = self._programacao(semana=date(2026, 6, 3))  # uma quarta-feira
        self.assertEqual(prog.semana_inicio, date(2026, 6, 1))
        self.assertEqual(prog.semana_fim, date(2026, 6, 7))

    def test_abrir_duas_vezes_devolve_a_mesma_semana(self):
        a = self._programacao(semana=date(2026, 6, 1))
        b = self._programacao(semana=date(2026, 6, 4))
        self.assertEqual(a.pk, b.pk)

    def test_abrir_semeia_o_catalogo_de_fabrica(self):
        """Catálogo vazio faria a primeira reunião inventar rótulos livres — que
        é exatamente o que o modelo existe para impedir."""
        self._programacao()
        self.assertEqual(
            CausaNaoCumprimento.objects.filter(
                tenant=self.tenant, de_fabrica=True
            ).count(),
            len(services.CAUSAS_DE_FABRICA),
        )

    def test_semana_vazia_nao_se_compromete(self):
        prog = self._programacao()
        with self.assertRaises(ValidationError):
            services.comprometer(programacao=prog, por="Ana")

    def test_a_trava_e_conferida_de_novo_no_comprometer(self):
        """Entre montar o quadro na segunda e assumi-lo pode ter aparecido uma
        trava — assumir por cima dela é o erro que o make-ready evita."""
        prog = self._programacao()
        self._item(prog, self.a1)
        self._restricao(self.a1)  # nasce DEPOIS de o cartão entrar
        with self.assertRaises(ValidationError):
            services.comprometer(programacao=prog, por="Ana")

    def test_comprometida_nao_recebe_cartao_novo(self):
        """Acrescentar compromisso depois que a semana andou é escrever a aposta
        depois do resultado."""
        prog = self._programacao()
        self._item(prog, self.a1)
        services.comprometer(programacao=prog, por="Ana")
        prog.refresh_from_db()
        self.assertFalse(prog.esta_aberta_para_montagem)

    def test_nao_encerra_com_item_por_julgar(self):
        """Contar o nulo como falha puniria a equipe por um julgamento que não se
        fez; ignorá-lo inflaria o índice."""
        prog = self._programacao()
        self._item(prog, self.a1)
        self._item(prog, self.a2)
        services.comprometer(programacao=prog, por="Ana")
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": prog.itens.first().pk, "cumprido": True},
        ])
        with self.assertRaises(ValidationError) as ctx:
            services.encerrar(programacao=prog, por="Ana")
        self.assertIn("julgamento", " ".join(ctx.exception.messages).lower())

    def test_o_ciclo_inteiro_fecha_e_produz_ppc(self):
        prog = self._programacao()
        i1 = self._item(prog, self.a1)
        i2 = self._item(prog, self.a2)
        services.comprometer(programacao=prog, por="Ana")
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": True},
            {"item": i2.pk, "cumprido": False, "causa": causa.pk,
             "nota": "Bloco não chegou"},
        ])
        resultado = services.encerrar(programacao=prog, por="Ana")
        self.assertEqual(resultado["comprometidos"], 2)
        self.assertEqual(resultado["cumpridos"], 1)
        #: **Um de dois cartões, e o índice não é 50%** — o PPC é ponderado
        #: (decisão do dono, 15/09/2026). Nenhuma das duas atividades tem
        #: orçamento nem peso informado, então o peso é a duração: a alvenaria
        #: dura 5 dias e o contrapiso 3. Saiu a alvenaria: 5/8 = 62,5%.
        #: Contar cartões diria 50% e trataria os dois serviços como iguais,
        #: que é o que esta mudança existe para deixar de fazer.
        self.assertEqual(resultado["ppc"], Decimal("62.5"))
        self.assertEqual(resultado["peso_bases"], ["duracao"])
        self.assertTrue(resultado["apurado"])


class PpcHonestoTests(_BaseLastPlanner):
    """O índice só existe depois do encerramento — a régua de dado honesto."""

    def test_semana_aberta_nao_tem_ppc(self):
        """Uma semana comprometida na segunda tem zero cumpridos por construção.
        Exibir "PPC 0%" seria fabricar um fracasso que ainda não aconteceu."""
        prog = self._programacao()
        self._item(prog, self.a1)
        services.comprometer(programacao=prog, por="Ana")
        leitura = services.ppc_de(prog)
        self.assertIsNone(leitura["ppc"])
        self.assertFalse(leitura["apurado"])
        self.assertEqual(leitura["por_julgar"], 1)

    def test_o_denominador_e_o_comprometido_e_nao_o_plano(self):
        """A pergunta do Last Planner é *daquilo que o time disse que ia fazer,
        quanto saiu?* — e não "de tudo que o cronograma previa"."""
        prog = self._programacao()
        i1 = self._item(prog, self.a1)  # só UMA das duas atividades entra
        services.comprometer(programacao=prog, por="Ana")
        services.julgar_itens(
            programacao=prog, julgamentos=[{"item": i1.pk, "cumprido": True}],
        )
        leitura = services.encerrar(programacao=prog, por="Ana")
        self.assertEqual(leitura["comprometidos"], 1)
        self.assertEqual(leitura["ppc"], Decimal("100.0"))

    def test_o_ppc_nao_e_coluna(self):
        """Derivado, nunca gravado (§4.9): guardá-lo obrigaria a reescrevê-lo a
        cada item julgado, e a primeira escrita fora desse caminho o faria
        mentir."""
        campos = {f.name for f in ProgramacaoSemanal._meta.get_fields()}
        self.assertNotIn("ppc", campos)

    def test_a_serie_so_traz_semana_encerrada(self):
        fechada = self._programacao(semana=date(2026, 6, 1))
        i = self._item(fechada, self.a1)
        services.comprometer(programacao=fechada, por="Ana")
        services.julgar_itens(
            programacao=fechada, julgamentos=[{"item": i.pk, "cumprido": True}],
        )
        services.encerrar(programacao=fechada, por="Ana")

        aberta = self._programacao(semana=date(2026, 6, 8))
        self._item(aberta, self.a2)
        services.comprometer(programacao=aberta, por="Ana")

        serie = services.serie_ppc(obra_id=self.obra.pk, tenant_id=self.tenant.pk)
        self.assertEqual(len(serie), 1)
        self.assertEqual(serie[0]["semana_inicio"], date(2026, 6, 1))

    def test_a_serie_vem_em_ordem_cronologica(self):
        """O gráfico lê da esquerda para a direita; devolver do mais novo para o
        mais antigo faria a tendência aparecer invertida."""
        for n, semana in enumerate([date(2026, 6, 1), date(2026, 6, 8)]):
            prog = self._programacao(semana=semana)
            i = self._item(prog, self.a1 if n == 0 else self.a2)
            services.comprometer(programacao=prog, por="Ana")
            services.julgar_itens(
                programacao=prog, julgamentos=[{"item": i.pk, "cumprido": True}],
            )
            services.encerrar(programacao=prog, por="Ana")
        serie = services.serie_ppc(obra_id=self.obra.pk, tenant_id=self.tenant.pk)
        self.assertEqual(
            [linha["semana_inicio"] for linha in serie],
            [date(2026, 6, 1), date(2026, 6, 8)],
        )


class CausaEhObrigatoriaTests(_BaseLastPlanner):
    """Sem causa o Last Planner degenera em marcar caixinhas."""

    def _causa(self):
        services.semear_causas_de_fabrica(self.tenant.pk)
        return CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )

    def test_nao_cumprido_sem_causa_salva_com_aviso_e_nao_deixa_encerrar(self):
        """Salvar nunca é barrado (dono, 11/10/2026): o julgamento incompleto é
        guardado como «por julgar» e o aviso volta na resposta. Quem trava é o
        `encerrar`."""
        prog = self._programacao()
        i = self._item(prog, self.a1)
        services.comprometer(programacao=prog, por="Ana")
        r = services.julgar_itens(
            programacao=prog, julgamentos=[{"item": i.pk, "cumprido": False}],
        )
        self.assertIn("causa", " ".join(r["avisos"]).lower())
        i.refresh_from_db()
        self.assertIsNone(i.cumprido)
        with self.assertRaises(ValidationError):
            services.encerrar(programacao=prog, por="Ana")

    def _julgado_por_percentual_sem_causa(self):
        prog = self._programacao()
        i = self._item(prog, self.a1)
        services.comprometer(programacao=prog, por="Ana")
        r = services.julgar_itens(
            programacao=prog, julgamentos=[{"item": i.pk, "percentual_concluido": 60}],
        )
        return prog, i, r

    def test_abaixo_da_meta_sem_causa_grava_o_avanco_e_avisa(self):
        _, i, r = self._julgado_por_percentual_sem_causa()
        self.assertEqual(len(r["avisos"]), 1)
        i.refresh_from_db()
        self.assertEqual(i.percentual_concluido, 60)
        self.assertIsNone(i.cumprido)

    def test_encerrar_com_item_sem_causa_avisa_e_bloqueia_quem_nao_tem_alcada(self):
        prog, _, _ = self._julgado_por_percentual_sem_causa()
        with self.assertRaises(services.EncerramentoSemCausa) as ctx:
            services.encerrar(programacao=prog, por="Ana")
        self.assertFalse(ctx.exception.pode)
        self.assertEqual(len(ctx.exception.itens), 1)

    def test_quem_tem_alcada_encerra_assim_mesmo_e_o_ranking_mostra_a_falta(self):
        prog, i, _ = self._julgado_por_percentual_sem_causa()
        services.encerrar(
            programacao=prog, por="Ana", aceitar_sem_causa=True, pode_aceitar_sem_causa=True,
        )
        i.refresh_from_db()
        self.assertIs(i.cumprido, False)
        self.assertEqual(i.causa.codigo, "SEM-CAUSA")

    def test_aceitar_sem_causa_sem_a_alcada_e_recusado(self):
        prog, _, _ = self._julgado_por_percentual_sem_causa()
        with self.assertRaises(ValidationError) as ctx:
            services.encerrar(programacao=prog, por="Ana", aceitar_sem_causa=True)
        self.assertNotIsInstance(ctx.exception, services.EncerramentoSemCausa)

    def test_nao_cumprido_sem_causa_e_recusado_pelo_BANCO(self):
        """A trava mora no banco, e não só no `services`: o comando de bancada e
        a importação entram por outras portas — a mesma lição do append-only."""
        prog = self._programacao()
        i = self._item(prog, self.a1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ItemProgramacao.objects.filter(pk=i.pk).update(
                    cumprido=False, causa=None,
                )

    def test_cumprido_com_causa_de_falha_e_recusado(self):
        """O outro lado da mesma regra — sem ele a grade de causas contaria
        falhas que não houve."""
        prog = self._programacao()
        i = self._item(prog, self.a1)
        services.comprometer(programacao=prog, por="Ana")
        with self.assertRaises(ValidationError):
            services.julgar_itens(programacao=prog, julgamentos=[
                {"item": i.pk, "cumprido": True, "causa": self._causa().pk},
            ])

    def test_o_ranking_de_causas_e_o_Act(self):
        causa = self._causa()
        outra = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="EXT-CLIMA",
        )
        prog = self._programacao()
        i1 = self._item(prog, self.a1)
        i2 = self._item(prog, self.a2)
        services.comprometer(programacao=prog, por="Ana")
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": False, "causa": causa.pk},
            {"item": i2.pk, "cumprido": False, "causa": outra.pk},
        ])
        services.encerrar(programacao=prog, por="Ana")

        ranking = services.ranking_de_causas(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(ranking["total_falhas"], 2)
        codigos = {linha["codigo"] for linha in ranking["causas"]}
        self.assertEqual(codigos, {"MAT-FALTA", "EXT-CLIMA"})
        categorias = {linha["categoria"] for linha in ranking["categorias"]}
        self.assertEqual(categorias, {"material", "externo"})

    def test_causa_usada_nao_se_apaga(self):
        """Apagá-la deixaria o histórico de PPC sem rótulo."""
        causa = self._causa()
        prog = self._programacao()
        i = self._item(prog, self.a1)
        services.comprometer(programacao=prog, por="Ana")
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i.pk, "cumprido": False, "causa": causa.pk},
        ])
        with self.assertRaises(Exception):
            with transaction.atomic():
                causa.delete()


class SeamDoScmTests(_BaseLastPlanner):
    """Restrição de material → demanda no SCM. A integração visível da régua."""

    def test_restricao_de_material_vira_demanda(self):
        from moduloscm.models import Demanda

        r = self._restricao(self.a1, tipo=TipoRestricao.MATERIAL)
        demanda_id = services.gerar_demanda_scm(restricao=r, unidade="mil")
        demanda = Demanda.objects.get(pk=demanda_id)
        self.assertEqual(demanda.origem, Demanda.Origem.RESTRICAO)
        self.assertEqual(demanda.tenant_id, self.tenant.pk)
        self.assertEqual(demanda.itens.count(), 1)
        r.refresh_from_db()
        self.assertEqual(r.demanda_scm_id, demanda_id)

    def test_gerar_duas_vezes_nao_compra_duas_vezes(self):
        """O botão fica na tela e alguém clica duas vezes; duas demandas para a
        mesma falta produzem duas cotações e, no fim, duas compras."""
        from moduloscm.models import Demanda

        r = self._restricao(self.a1, tipo=TipoRestricao.MATERIAL)
        primeiro = services.gerar_demanda_scm(restricao=r)
        segundo = services.gerar_demanda_scm(restricao=r)
        self.assertEqual(primeiro, segundo)
        self.assertEqual(Demanda.objects.filter(tenant=self.tenant).count(), 1)

    def test_restricao_de_projeto_nao_vira_compra(self):
        """Oferecer o botão em todas faria a demanda virar lixeira de pendência."""
        r = self._restricao(self.a1, tipo=TipoRestricao.PROJETO)
        with self.assertRaises(ValidationError):
            services.gerar_demanda_scm(restricao=r)

    def test_restricao_ja_removida_nao_vira_compra(self):
        r = self._restricao(self.a1, tipo=TipoRestricao.MATERIAL)
        services.remover_restricao(restricao=r, por="Ana", nota="chegou")
        with self.assertRaises(ValidationError):
            services.gerar_demanda_scm(restricao=r)

    def test_equipamento_e_mao_de_obra_viram_contratacao_de_servico(self):
        """Toda restrição que se destrava comprando leva à compra — não só a de
        material. Locação e empreitada abrem demanda de serviço."""
        from moduloscm.models import Demanda

        for tipo in (TipoRestricao.EQUIPAMENTO, TipoRestricao.MAO_DE_OBRA):
            r = self._restricao(self.a1, tipo=tipo, descricao=f"Falta {tipo}")
            demanda = Demanda.objects.get(pk=services.gerar_demanda_scm(restricao=r))
            self.assertEqual(demanda.tipo, Demanda.Tipo.SERVICO)
            self.assertEqual(demanda.origem, Demanda.Origem.RESTRICAO)


class ReabrirRestricaoTests(_BaseLastPlanner):
    """A resolvida fica na lista e pode voltar a ser aberta — carimbada."""

    def test_resolvida_volta_a_aberta_e_a_nota_fica(self):
        r = self._restricao(self.a1)
        services.remover_restricao(restricao=r, por="Ana", nota="chegou na sexta")
        services.reabrir_restricao(restricao=r, por="Bia")
        r.refresh_from_db()
        self.assertEqual(r.status, Restricao.Status.ABERTA)
        self.assertEqual(r.reaberta_por, "Bia")
        self.assertIsNotNone(r.reaberta_em)
        self.assertEqual(r.vezes_reaberta, 1)
        self.assertEqual(r.nota_remocao, "chegou na sexta")

    def test_reaberta_volta_a_travar_o_compromisso(self):
        r = self._restricao(self.a1)
        services.remover_restricao(restricao=r, por="Ana", nota="chegou")
        services.validar_pode_comprometer(self.a1, tenant_id=self.tenant.pk)
        services.reabrir_restricao(restricao=r, por="Ana")
        with self.assertRaises(ValidationError):
            services.validar_pode_comprometer(self.a1, tenant_id=self.tenant.pk)

    def test_so_a_resolvida_reabre(self):
        aberta = self._restricao(self.a1)
        cancelada = self._restricao(self.a1, status=Restricao.Status.CANCELADA)
        for r in (aberta, cancelada):
            with self.assertRaises(ValidationError):
                services.reabrir_restricao(restricao=r, por="Ana")

    def test_reabrir_respeita_o_teto_de_abertas(self):
        r = self._restricao(self.a1)
        services.remover_restricao(restricao=r, por="Ana", nota="chegou")
        with patch.object(services, "PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA", 0):
            with self.assertRaises(ValidationError):
                services.reabrir_restricao(restricao=r, por="Ana")


class TetosDoLastPlannerNoServicoTests(_BaseLastPlanner):
    """Os tetos da §5.5j exercidos onde eles mordem."""

    def test_o_quadro_respeita_o_teto_de_cartoes(self):
        from payment.planos import PDCA_TETO_ITENS_POR_PROGRAMACAO

        prog = self._programacao()
        with self.assertRaises(ValidationError):
            services.validar_teto_de_itens_da_programacao(
                prog, acrescentando=PDCA_TETO_ITENS_POR_PROGRAMACAO + 1,
            )

    def test_o_log_de_restricao_respeita_o_teto(self):
        from payment.planos import PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA

        with self.assertRaises(ValidationError):
            services.validar_teto_de_restricoes(
                self.obra.pk, tenant_id=self.tenant.pk,
                acrescentando=PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA + 1,
            )

    def test_o_catalogo_respeita_o_teto(self):
        from payment.planos import PDCA_TETO_CAUSAS_POR_TENANT

        services.semear_causas_de_fabrica(self.tenant.pk)
        with self.assertRaises(ValidationError):
            services.validar_teto_de_causas(
                self.tenant.pk, acrescentando=PDCA_TETO_CAUSAS_POR_TENANT,
            )

    def test_semear_e_idempotente(self):
        services.semear_causas_de_fabrica(self.tenant.pk)
        criadas = services.semear_causas_de_fabrica(self.tenant.pk)
        self.assertEqual(criadas, 0)

    def test_interdicao_de_seguranca_tem_causa_propria_fora_de_externo(self):
        """D192 — a frente interditada por risco não pode cair em "externo"."""
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(tenant=self.tenant, codigo="SEG-INTERD")
        self.assertTrue(causa.de_fabrica)
        self.assertEqual(causa.categoria, CausaNaoCumprimento.Categoria.PLANEJAMENTO)

    def test_tenant_antigo_recebe_a_causa_nova_na_proxima_semeadura(self):
        """Quem semeou antes do D192 ganha a SEG-INTERD sem perder nada."""
        services.semear_causas_de_fabrica(self.tenant.pk)
        CausaNaoCumprimento.objects.filter(tenant=self.tenant, codigo="SEG-INTERD").delete()
        self.assertEqual(services.semear_causas_de_fabrica(self.tenant.pk), 1)


class ApiDaPdca5Tests(APITestCase):
    """As portas novas do Last Planner, **pelo HTTP** — e ela existe por um
    defeito que a suíte inteira não via.

    As classes acima montam `Restricao` e `CausaNaoCumprimento` pelo ORM, com o
    tenant na mão, e testam o serviço. Nenhuma atravessava o `perform_create` do
    viewset — e os dois sobrescreviam o do `TenantScopedViewSetMixin` **sem
    repetir o `tenant_id`**, então a linha nascia sem tenant e a RLS recusava o
    INSERT com 500. Passou por 309 testes verdes e caiu no primeiro POST real,
    no [pdca5_programacao_test.py](../../testes/e2e/pdca5_programacao_test.py).

    A régua que fica: **porta nova se exerce pela porta**, e não só pelo serviço
    que está atrás dela.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(slug="pdca5-api", nome="Construtora LPS API")
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra LPS", endereco="Rua API",
        )
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Padrão",
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.atividade = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Alvenaria do 4º", duracao_dias=5, profundidade=1,
        )
        self.usuario = Usuario.objects.create(username="lps5", tenant=self.tenant)
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = [
            "pdca.restricao.view", "pdca.restricao.edit", "pdca.restricao.remover",
            "pdca.programacao.view", "pdca.programacao.comprometer",
            "pdca.programacao.encerrar",
        ]
        self.client.force_authenticate(user=self.usuario)

    def test_a_restricao_criada_pela_api_nasce_com_tenant(self):
        """O defeito de 15/09: sem isto a RLS recusa o INSERT em produção."""
        resposta = self.client.post("/api/pdca/restricoes/", {
            "atividade": self.atividade.pk, "tipo": TipoRestricao.MATERIAL,
            "descricao": "Bloco cerâmico não entregue",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        restricao = Restricao.objects.get(pk=resposta.json()["restricao_id"])
        self.assertEqual(restricao.tenant_id, self.tenant.pk)
        # E quem criou fica registrado — é o outro efeito do `perform_create`.
        self.assertTrue(restricao.criada_por)

    def test_a_causa_criada_pela_api_nasce_com_tenant(self):
        resposta = self.client.post("/api/pdca/causas/", {
            "codigo": "CASA-PARADA", "nome": "Frente parada por decisão interna",
            "categoria": CausaNaoCumprimento.Categoria.PLANEJAMENTO,
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        causa = CausaNaoCumprimento.objects.get(pk=resposta.json()["causa_id"])
        self.assertEqual(causa.tenant_id, self.tenant.pk)
        self.assertFalse(causa.de_fabrica)

    def test_o_cartao_criado_pela_api_nasce_com_tenant(self):
        """O irmão que já estava certo — herda o `perform_create` do mixin.

        Fica no teste porque é a contraprova: prova que o defeito era da
        sobrescrita, e não do caminho.
        """
        prog = services.abrir_programacao(
            obra=self.obra, semana_inicio=date(2026, 6, 1), tenant_id=self.tenant.pk,
        )
        resposta = self.client.post("/api/pdca/itens-programacao/", {
            "programacao": prog.pk, "atividade": self.atividade.pk, "ordem": 1,
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        item = ItemProgramacao.objects.get(pk=resposta.json()["item_programacao_id"])
        self.assertEqual(item.tenant_id, self.tenant.pk)

    def test_a_semana_aberta_pela_api_nasce_com_tenant(self):
        resposta = self.client.post("/api/pdca/programacoes/abrir/", {
            "obra": self.obra.pk, "semana": "2026-06-03",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        prog = ProgramacaoSemanal.objects.get(
            pk=resposta.json()["programacao_id"],
        )
        self.assertEqual(prog.tenant_id, self.tenant.pk)
        # Ancorou na segunda, mesmo tendo pedido uma quarta-feira.
        self.assertEqual(prog.semana_inicio, date(2026, 6, 1))
        # E o catálogo de fábrica veio junto, que é o que faz a primeira
        # reunião ter de onde escolher.
        self.assertTrue(
            CausaNaoCumprimento.objects.filter(
                tenant_id=self.tenant.pk, de_fabrica=True,
            ).exists()
        )


class ExecucaoParcialTests(_BaseLastPlanner):
    """**O compromisso é binário; a execução não é.**

    O Last Planner julga "saiu" ou "não saiu" de propósito — é a definição do
    PPC, e contar 80% como 0,8 faria o time aprender a prometer demais e mostrar
    sempre uns 70%, com o índice deixando de medir a confiabilidade do plano.

    Mas a obra que assumiu 20 pontos e entregou 12 **fez 12**. Estes testes
    prendem as duas coisas ao mesmo tempo: o índice continua binário, e o que
    andou aparece **ao lado** dele, vindo do apontamento do campo (PDCA.2) — não
    digitado de novo.
    """

    def _semana_com_apontamento(self, pontos, *, local=None, dia=None):
        prog = self._programacao(semana=date(2026, 6, 1))
        item = self._item(prog, atividade=self.a1, percentual_previsto=Decimal("20"))
        if local is not None:
            item.local = local
            item.save(update_fields=["local"])
        if pontos is not None:
            ApontamentoAvanco.objects.create(
                tenant=self.tenant, atividade=self.a1, local=local,
                data=dia or date(2026, 6, 3), percentual=Decimal(pontos),
            )
        return prog, item

    def test_o_apontado_da_semana_chega_ao_cartao(self):
        prog, item = self._semana_com_apontamento("12")
        mapa = services.avanco_apontado_dos_itens(prog)
        self.assertEqual(mapa[item.pk], Decimal("12"))

    def test_apontamento_FORA_da_semana_nao_conta(self):
        """A janela é a da programação — o que andou na semana passada é da
        semana passada."""
        prog, item = self._semana_com_apontamento("12", dia=date(2026, 5, 20))
        self.assertEqual(services.avanco_apontado_dos_itens(prog), {})

    def test_sem_apontamento_o_cartao_recebe_NULO_e_nao_zero(self):
        """Nulo é 'o campo não apontou nada', que é diferente de 'apontou e
        nada andou' — e a tela precisa das duas leituras."""
        prog, item = self._semana_com_apontamento(None)
        self.assertNotIn(item.pk, services.avanco_apontado_dos_itens(prog))

    def test_estorno_cancela_sozinho_porque_o_apontamento_e_delta(self):
        """Nada de subtrair acumulados de duas datas: o estorno é um lançamento
        de sinal contrário, e ele se cancela na soma da janela."""
        prog, item = self._semana_com_apontamento("12")
        original = ApontamentoAvanco.objects.filter(atividade=self.a1).first()
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.a1, data=date(2026, 6, 4),
            percentual=Decimal("-12"), estorna=original,
        )
        self.assertEqual(services.avanco_apontado_dos_itens(prog)[item.pk], Decimal("0"))

    def test_cartao_COM_local_conta_so_o_apontamento_daquele_local(self):
        """Somar o da atividade inteira faria o mesmo apontamento pesar em dois
        cartões."""
        torre = LocalObra.objects.create(
            tenant=self.tenant, obra=self.obra, nivel=NivelLocal.BLOCO,
            codigo="T9", nome="Torre 9", profundidade=0,
        )
        prog, item = self._semana_com_apontamento("8", local=torre)
        #: E um apontamento da atividade sem local, na mesma semana, fica de fora
        #: deste cartão — ele é de outro endereço.
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.a1, local=None,
            data=date(2026, 6, 3), percentual=Decimal("30"),
        )
        self.assertEqual(services.avanco_apontado_dos_itens(prog)[item.pk], Decimal("8"))

    def test_o_PPC_continua_BINARIO_com_execucao_parcial(self):
        """**A regra que não se dobra.** Prometeu 20, andou 12, não terminou:
        para o PPC isso é zero — e é assim que o índice continua medindo a
        confiabilidade do plano em vez da boa vontade da equipe."""
        prog, item = self._semana_com_apontamento("12")
        services.comprometer(programacao=prog, por="m")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="PLAN-MAL-DIM",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": item.pk, "cumprido": False, "causa": causa.pk},
        ])
        services.encerrar(programacao=prog, por="m")
        ppc = services.ppc_de(prog)
        self.assertEqual(ppc["ppc"], Decimal("0.0"))

    def test_mas_o_que_ANDOU_aparece_ao_lado_do_indice(self):
        """Sem isto o sistema diria à equipe que ela não fez nada."""
        prog, item = self._semana_com_apontamento("12")
        services.comprometer(programacao=prog, por="m")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MO-PRODUT",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": item.pk, "cumprido": False, "causa": causa.pk},
        ])
        services.encerrar(programacao=prog, por="m")
        ppc = services.ppc_de(prog)
        self.assertEqual(ppc["pontos_previstos"], Decimal("20.00"))
        self.assertEqual(ppc["pontos_apontados"], Decimal("12"))
        #: E continuam **separados** do índice: quem lê vê 0% de PPC e 12 de 20
        #: pontos andados, e as duas coisas são verdade.
        self.assertEqual(ppc["ppc"], Decimal("0.0"))

    def test_semana_sem_ninguem_prometer_numero_nao_inventa_um(self):
        """Muito compromisso de LPS é binário ('concretar a laje'), e obrigar um
        número faria o time inventar um."""
        prog = self._programacao(semana=date(2026, 6, 1))
        self._item(prog, atividade=self.a1)
        services.comprometer(programacao=prog, por="m")
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": prog.itens.first().pk, "cumprido": True},
        ])
        services.encerrar(programacao=prog, por="m")
        ppc = services.ppc_de(prog)
        self.assertIsNone(ppc["pontos_previstos"])
        self.assertIsNone(ppc["pontos_apontados"])


class ApiDaExecucaoParcialTests(APITestCase):
    """O cartão, pelo HTTP — e o agregado resolvido uma vez por página."""

    def setUp(self):
        self.tenant = Tenant.objects.create(slug="pdca5-parcial", nome="LPS Parcial")
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra Parcial", endereco="Rua P",
        )
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Padrão",
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.atividade = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Alvenaria", duracao_dias=5, profundidade=1,
        )
        self.prog = services.abrir_programacao(
            obra=self.obra, semana_inicio=date(2026, 6, 1), tenant_id=self.tenant.pk,
        )
        self.item = ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=self.prog, atividade=self.atividade,
            percentual_previsto=Decimal("20"),
        )
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.atividade, data=date(2026, 6, 3),
            percentual=Decimal("12"),
        )
        self.usuario = Usuario.objects.create(username="lps5p", tenant=self.tenant)
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = [
            "pdca.programacao.view", "pdca.programacao.comprometer",
            "pdca.programacao.encerrar",
        ]
        self.client.force_authenticate(user=self.usuario)

    def test_a_listagem_do_quadro_traz_o_apontado_de_cada_cartao(self):
        resposta = self.client.get(
            f"/api/pdca/itens-programacao/?programacao={self.prog.pk}",
        )
        self.assertEqual(resposta.status_code, 200)
        linha = resposta.json()["results"][0]
        #: String, como todo `Decimal` que atravessa — a régua do D151.
        #: O apontamento tem **4 casas** (`decimal_places=4`) e o previsto tem
        #: 2 — cada campo atravessa com a precisão que tem, e é por isso que a
        #: comparação aqui é numérica: assumir o formato do outro seria fixar no
        #: teste um acoplamento que o modelo não promete.
        self.assertEqual(Decimal(linha["percentual_apontado"]), Decimal("12"))
        self.assertEqual(Decimal(linha["percentual_previsto"]), Decimal("20"))

    def test_o_quadro_inteiro_vem_resolvido_do_servidor(self):
        """O quadro comporta 300 cartões, e o agregado é resolvido **uma vez por
        página** — 300 consultas para desenhar uma parede é o D136 do outro
        lado. O que se prende aqui é o contrato: **todo** cartão chega com o
        campo, e nenhum deles exige uma segunda chamada do cliente."""
        for n in range(2, 8):
            atividade = Atividade.objects.create(
                tenant=self.tenant, cronograma=self.cronograma, codigo=str(n),
                nome=f"Serviço {n}", duracao_dias=3, profundidade=1,
            )
            ItemProgramacao.objects.create(
                tenant=self.tenant, programacao=self.prog, atividade=atividade,
            )
        resposta = self.client.get(
            f"/api/pdca/itens-programacao/?programacao={self.prog.pk}",
        )
        linhas = resposta.json()["results"]
        self.assertEqual(len(linhas), 7)
        self.assertTrue(all("percentual_apontado" in l for l in linhas))
        #: O cartão sem apontamento recebe `null`, e não zero — nulo é "o campo
        #: não apontou nada", que é diferente de "apontou e nada andou".
        self.assertEqual(
            [l["percentual_apontado"] for l in linhas].count(None), 6,
        )


class ReabrirASemanaTests(_BaseLastPlanner):
    """**A semana errada tem volta — e a volta fica registrada.**

    Antes disto, `encerrar` era um beco: `julgar_itens` só aceita programação
    comprometida, então um julgamento errado ficava para sempre. E o que estraga
    não é o índice: é o ranking de causas, que é o que decide o que a empresa
    muda.
    """

    def _semana_encerrada(self):
        prog = self._programacao()
        i1 = self._item(prog, atividade=self.a1)
        i2 = self._item(prog, atividade=self.a2)
        services.comprometer(programacao=prog, por="mestre")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": True},
            {"item": i2.pk, "cumprido": False, "causa": causa.pk},
        ])
        services.encerrar(programacao=prog, por="mestre")
        return prog, i1, i2, causa

    def test_a_semana_encerrada_reabre_para_COMPROMETIDA(self):
        prog, _, _, _ = self._semana_encerrada()
        self.assertEqual(prog.status, ProgramacaoSemanal.Status.ENCERRADA)
        resultado = services.reabrir(
            programacao=prog, por="mestre",
            motivo="A elétrica saiu na sexta e ninguém avisou a tempo.",
        )
        prog.refresh_from_db()
        self.assertEqual(prog.status, ProgramacaoSemanal.Status.COMPROMETIDA)
        self.assertEqual(resultado["de"], "encerrada")
        self.assertEqual(resultado["para"], "comprometida")
        #: O encerramento é desfeito; o carimbo de quem encerrou sai junto,
        #: porque ele voltará a ser posto por quem encerrar de novo.
        self.assertIsNone(prog.encerrada_em)

    def test_e_o_julgamento_FICA_para_corrigir_so_o_que_esta_errado(self):
        """Refazer a semana inteira para trocar uma causa seria a pior forma de
        oferecer a correção — a pessoa desistiria e o erro ficaria."""
        prog, i1, i2, _ = self._semana_encerrada()
        services.reabrir(programacao=prog, por="mestre", motivo="causa trocada")
        i1.refresh_from_db()
        i2.refresh_from_db()
        self.assertIs(i1.cumprido, True)
        self.assertIs(i2.cumprido, False)
        self.assertIsNotNone(i2.causa_id)

    def test_reaberta_ela_aceita_julgamento_de_novo(self):
        prog, i1, i2, causa = self._semana_encerrada()
        services.reabrir(programacao=prog, por="mestre", motivo="errei a causa")
        outra = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="EXT-CLIMA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i2.pk, "cumprido": False, "causa": outra.pk},
        ])
        i2.refresh_from_db()
        self.assertEqual(i2.causa_id, outra.pk)
        #: E encerra de novo, com o PPC recalculado do zero — ele é derivado.
        services.encerrar(programacao=prog, por="mestre")
        prog.refresh_from_db()
        self.assertEqual(prog.status, ProgramacaoSemanal.Status.ENCERRADA)

    def test_o_PPC_recalcula_sozinho_porque_nunca_foi_gravado(self):
        prog, i1, i2, _ = self._semana_encerrada()
        #: 62,5% e não 50%: ponderado pela duração (5 e 3 dias) — ver
        #: `CicloDaSemanaTests.test_o_ciclo_inteiro_fecha_e_produz_ppc`.
        self.assertEqual(services.ppc_de(prog)["ppc"], Decimal("62.5"))
        services.reabrir(programacao=prog, por="mestre", motivo="o 2 saiu sim")
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i2.pk, "cumprido": True},
        ])
        services.encerrar(programacao=prog, por="mestre")
        self.assertEqual(services.ppc_de(prog)["ppc"], Decimal("100.0"))

    def test_a_comprometida_reabre_para_RASCUNHO_e_apaga_o_julgamento(self):
        """Rascunho quer dizer *a semana ainda não foi assumida*. Julgamento
        pendurado numa semana que ninguém assumiu não é dado — é entulho que o
        próximo encerramento contaria."""
        prog, i1, i2, _ = self._semana_encerrada()
        services.reabrir(programacao=prog, por="mestre", motivo="1")
        resultado = services.reabrir(
            programacao=prog, por="mestre", motivo="faltou um serviço no quadro",
        )
        prog.refresh_from_db()
        self.assertEqual(prog.status, ProgramacaoSemanal.Status.RASCUNHO)
        self.assertEqual(resultado["julgamentos_apagados"], 2)
        i1.refresh_from_db()
        i2.refresh_from_db()
        self.assertIsNone(i1.cumprido)
        self.assertIsNone(i2.cumprido)
        #: A causa sai junto, senão a `CheckConstraint` do item recusaria a linha
        #: (cumprido nulo com causa preenchida é o estado que ela proíbe).
        self.assertIsNone(i2.causa_id)
        self.assertIsNone(prog.comprometida_em)

    def test_e_no_rascunho_o_quadro_volta_a_receber_cartao(self):
        prog, _, _, _ = self._semana_encerrada()
        services.reabrir(programacao=prog, por="m", motivo="1")
        services.reabrir(programacao=prog, por="m", motivo="2")
        self.assertTrue(prog.esta_aberta_para_montagem)

    def test_reabrir_SEM_motivo_e_recusado(self):
        prog, _, _, _ = self._semana_encerrada()
        with self.assertRaises(ValidationError) as erro:
            services.reabrir(programacao=prog, por="mestre", motivo="   ")
        self.assertIn("em silêncio", str(erro.exception))
        prog.refresh_from_db()
        self.assertEqual(prog.status, ProgramacaoSemanal.Status.ENCERRADA)

    def test_o_rascunho_nao_tem_degrau_abaixo(self):
        prog = self._programacao()
        with self.assertRaises(ValidationError) as erro:
            services.reabrir(programacao=prog, por="m", motivo="tentando")
        self.assertIn("rascunho", str(erro.exception).lower())

    def test_cada_reabertura_e_CONTADA_e_carimbada(self):
        """Contador, e não booleano: uma semana reaberta cinco vezes não é a
        mesma coisa que uma reaberta uma vez, e é o tipo de padrão que só
        aparece se alguém contar."""
        prog, _, _, _ = self._semana_encerrada()
        services.reabrir(programacao=prog, por="joana", motivo="primeira")
        prog.refresh_from_db()
        self.assertEqual(prog.vezes_reaberta, 1)
        self.assertEqual(prog.reaberta_por, "joana")
        self.assertEqual(prog.motivo_reabertura, "primeira")
        self.assertIsNotNone(prog.reaberta_em)

        services.encerrar(programacao=prog, por="joana")
        services.reabrir(programacao=prog, por="joana", motivo="segunda")
        prog.refresh_from_db()
        self.assertEqual(prog.vezes_reaberta, 2)
        self.assertEqual(prog.motivo_reabertura, "segunda")

    def test_o_PPC_DIZ_que_foi_corrigido(self):
        """Um PPC rejulgado depois de a reunião ter olhado para ele não pode
        passar por número virgem."""
        prog, _, _, _ = self._semana_encerrada()
        self.assertEqual(services.ppc_de(prog)["vezes_reaberta"], 0)
        services.reabrir(programacao=prog, por="m", motivo="a causa estava errada")
        services.encerrar(programacao=prog, por="m")
        ppc = services.ppc_de(prog)
        self.assertEqual(ppc["vezes_reaberta"], 1)
        self.assertEqual(ppc["motivo_reabertura"], "a causa estava errada")

    def test_a_SERIE_historica_marca_o_ponto_corrigido(self):
        """A série é o que a diretoria lê, e um ponto corrigido tem de se
        anunciar ali."""
        prog, _, _, _ = self._semana_encerrada()
        services.reabrir(programacao=prog, por="m", motivo="x")
        services.encerrar(programacao=prog, por="m")
        serie = services.serie_ppc(obra_id=self.obra.pk, tenant_id=self.tenant.pk)
        self.assertEqual(len(serie), 1)
        self.assertEqual(serie[0]["vezes_reaberta"], 1)

    def test_a_semana_reaberta_SAI_da_serie_ate_encerrar_de_novo(self):
        """Ela deixou de ser apurada: contá-la com o julgamento velho seria
        publicar um número que o próprio sistema declarou em revisão."""
        prog, _, _, _ = self._semana_encerrada()
        self.assertEqual(
            len(services.serie_ppc(obra_id=self.obra.pk, tenant_id=self.tenant.pk)), 1,
        )
        services.reabrir(programacao=prog, por="m", motivo="revisando")
        self.assertEqual(
            services.serie_ppc(obra_id=self.obra.pk, tenant_id=self.tenant.pk), [],
        )

    def test_o_ranking_de_causas_tambem_solta_a_semana_reaberta(self):
        """Pelo mesmo motivo: o ranking conta falha de semana **encerrada**, e
        uma em revisão não é conclusão de nada."""
        prog, _, _, _ = self._semana_encerrada()
        antes = services.ranking_de_causas(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(antes["total_falhas"], 1)
        services.reabrir(programacao=prog, por="m", motivo="revisando")
        depois = services.ranking_de_causas(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(depois["total_falhas"], 0)


class PpcPonderadoTests(_BaseLastPlanner):
    """**O PPC deixou de contar cartões** *(decisão do dono, 15/09/2026)*.

    Contar cartões dizia que assumir a concretagem da laje e assumir a limpeza
    do canteiro valem o mesmo: a semana que entrega a laje e perde a limpeza
    marcava os mesmos 50% da que entrega a limpeza e perde a laje. Agora o
    numerador e o denominador são **peso**, e o peso sai do planejamento — do
    orçamento, do peso informado ou da duração, nessa ordem.
    """

    def _semana_julgada(self, julgamentos):
        prog = self._programacao()
        services.comprometer(programacao=prog, por="Ana")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": pk, "cumprido": ok,
             **({} if ok else {"causa": causa.pk})}
            for pk, ok in julgamentos
        ])
        return services.encerrar(programacao=prog, por="Ana", arrastar=False)

    def test_o_peso_e_congelado_quando_o_cartao_nasce(self):
        """Como o `retencao_percentual_aplicado` da medição, e pelo mesmo motivo:
        reprecificar o orçamento em dezembro não pode reescrever o PPC de agosto."""
        prog = self._programacao()
        item = self._item(prog, atividade=self.a1)
        self.assertEqual(item.peso, Decimal("5"))
        self.assertEqual(item.peso_origem, "duracao")

    def test_o_peso_informado_ganha_da_duracao(self):
        """A escada é orçamento → peso do planejador → duração. Quem digitou um
        peso disse quanto aquilo vale, e a duração é o degrau de quem não disse."""
        self.a2.peso_informado = Decimal("40")
        self.a2.save(update_fields=["peso_informado"])
        prog = self._programacao()
        item = self._item(prog, atividade=self.a2)
        self.assertEqual(item.peso, Decimal("40"))
        self.assertEqual(item.peso_origem, "informado")

    def test_o_indice_pesa_o_que_saiu_e_nao_conta_cartoes(self):
        """Duas atividades, uma cumprida. Contagem diria 50%; a alvenaria dura 5
        dias e o contrapiso 3, então saiu 5 de 8."""
        prog = self._programacao()
        i1 = self._item(prog, atividade=self.a1)
        i2 = self._item(prog, atividade=self.a2)
        services.comprometer(programacao=prog, por="Ana")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": True},
            {"item": i2.pk, "cumprido": False, "causa": causa.pk},
        ])
        leitura = services.encerrar(
            programacao=prog, por="Ana", arrastar=False,
        )
        self.assertEqual(leitura["ppc"], Decimal("62.5"))
        self.assertEqual(leitura["peso_total"], Decimal("8"))
        self.assertEqual(leitura["peso_cumprido"], Decimal("5"))

    def test_o_inverso_do_mesmo_quadro_da_outro_indice(self):
        """A prova de que o peso mudou alguma coisa: trocar **qual** dos dois
        saiu deixava o índice igual antes, e agora não deixa."""
        prog = self._programacao()
        i1 = self._item(prog, atividade=self.a1)
        i2 = self._item(prog, atividade=self.a2)
        services.comprometer(programacao=prog, por="Ana")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": False, "causa": causa.pk},
            {"item": i2.pk, "cumprido": True},
        ])
        leitura = services.encerrar(
            programacao=prog, por="Ana", arrastar=False,
        )
        self.assertEqual(leitura["ppc"], Decimal("37.5"))

    def test_cartao_sem_regua_fica_FORA_da_divisao_e_e_contado_a_parte(self):
        """Marco tem duração zero e nenhum vínculo: não há como pesá-lo. Ele
        conta em `comprometidos`, fica fora da conta e aparece em `sem_peso` —
        a régua do `folhas_sem_peso` do avanço do cronograma."""
        marco = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="3",
            nome="Laje liberada", duracao_dias=0, eh_marco=True, profundidade=1,
        )
        prog = self._programacao()
        i1 = self._item(prog, atividade=self.a1)
        im = self._item(prog, atividade=marco)
        self.assertIsNone(im.peso)
        services.comprometer(programacao=prog, por="Ana")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": True},
            {"item": im.pk, "cumprido": False, "causa": causa.pk},
        ])
        leitura = services.encerrar(
            programacao=prog, por="Ana", arrastar=False,
        )
        self.assertEqual(leitura["comprometidos"], 2)
        self.assertEqual(leitura["sem_peso"], 1)
        #: Só a alvenaria tem peso, e ela saiu: 100% do que dava para pesar.
        self.assertEqual(leitura["ppc"], Decimal("100.0"))

    def test_quadro_sem_peso_nenhum_cai_na_base_IGUAL(self):
        """A obra que ainda não vinculou o cronograma ao orçamento e não digitou
        duração não pode ficar sem índice — ela volta a contar cartões, e a
        resposta **diz** que é isso que está fazendo."""
        m1 = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="4",
            nome="Alvará", duracao_dias=0, eh_marco=True, profundidade=1,
        )
        m2 = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="5",
            nome="Habite-se", duracao_dias=0, eh_marco=True, profundidade=1,
        )
        prog = self._programacao()
        i1 = self._item(prog, atividade=m1)
        i2 = self._item(prog, atividade=m2)
        services.comprometer(programacao=prog, por="Ana")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": True},
            {"item": i2.pk, "cumprido": False, "causa": causa.pk},
        ])
        leitura = services.encerrar(
            programacao=prog, por="Ana", arrastar=False,
        )
        self.assertEqual(leitura["ppc"], Decimal("50.0"))
        self.assertEqual(leitura["peso_bases"], ["igual"])

    def test_a_serie_usa_a_MESMA_conta_da_tela(self):
        """Ponto de série que discorda do ponto da tela é o defeito que o D138
        já custou caro na grade de medição."""
        prog = self._programacao()
        i1 = self._item(prog, atividade=self.a1)
        i2 = self._item(prog, atividade=self.a2)
        services.comprometer(programacao=prog, por="Ana")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": True},
            {"item": i2.pk, "cumprido": False, "causa": causa.pk},
        ])
        da_tela = services.encerrar(
            programacao=prog, por="Ana", arrastar=False,
        )
        serie = services.serie_ppc(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(len(serie), 1)
        self.assertEqual(serie[0]["ppc"], da_tela["ppc"])
        self.assertEqual(serie[0]["peso_bases"], ["duracao"])


class SemanaQueAindaNaoAcabouTests(_BaseLastPlanner):
    """**Dava para fechar a semana que não tinha acontecido** *(achado do dono,
    15/09/2026)*.

    `encerrar` só olhava o status: na segunda de manhã dava para julgar os cinco
    compromissos como "não saiu" e fechar, com a semana inteira pela frente. O
    índice que sai daí entra na série valendo o mesmo que os outros, e quem a lê
    depois não consegue distinguir.
    """

    def _semana_julgada(self, semana):
        prog = self._programacao(semana=semana)
        i1 = self._item(prog, atividade=self.a1)
        services.comprometer(programacao=prog, por="Ana")
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": True},
        ])
        return prog

    def _semana_futura(self):
        return services.segunda_da_semana(
            timezone.localdate() + timedelta(days=14)
        )

    def test_a_semana_futura_e_recusada_sem_a_permissao(self):
        prog = self._semana_julgada(self._semana_futura())
        with self.assertRaises(ValidationError) as ctx:
            services.encerrar(programacao=prog, por="Ana")
        mensagem = " ".join(ctx.exception.messages)
        self.assertIn("encerrar_antecipado", mensagem)

    def test_com_a_permissao_ainda_exige_motivo(self):
        """A trava que importa não é a de quem pode — é a do motivo por escrito,
        que é o que a reunião seguinte lê para saber por que aquele ponto foi
        apurado mais cedo."""
        prog = self._semana_julgada(self._semana_futura())
        with self.assertRaises(ValidationError) as ctx:
            services.encerrar(
                programacao=prog, por="Ana", pode_antecipar=True,
            )
        self.assertIn("motivo", " ".join(ctx.exception.messages).lower())

    def test_com_permissao_e_motivo_encerra_E_FICA_MARCADA(self):
        prog = self._semana_julgada(self._semana_futura())
        leitura = services.encerrar(
            programacao=prog, por="Ana", pode_antecipar=True,
            motivo_antecipado="Obra parada na quinta — feriado prolongado.",
            arrastar=False,
        )
        prog.refresh_from_db()
        self.assertEqual(prog.status, ProgramacaoSemanal.Status.ENCERRADA)
        self.assertTrue(prog.encerrada_antes_do_fim)
        self.assertIn("feriado", prog.motivo_encerramento_antecipado)
        self.assertTrue(leitura["encerrada_antes_do_fim"])

    def test_a_semana_que_ja_acabou_encerra_sem_cerimonia(self):
        """Encerrar a semana passada é o gesto normal — não pede permissão extra
        nem justificativa, e pedir faria a sexta-feira à noite virar burocracia."""
        prog = self._semana_julgada(date(2026, 6, 1))
        leitura = services.encerrar(
            programacao=prog, por="Ana", arrastar=False,
        )
        prog.refresh_from_db()
        self.assertEqual(prog.status, ProgramacaoSemanal.Status.ENCERRADA)
        self.assertFalse(prog.encerrada_antes_do_fim)
        self.assertFalse(leitura["encerrada_antes_do_fim"])


class ArrastoDoQueNaoSaiuTests(_BaseLastPlanner):
    """**Serviço que não saiu não deixou de ser preciso** *(decisão do dono,
    15/09/2026)*.

    A semana encerrada era um fim de linha: o cartão "não saiu" ficava no quadro
    de trás e a seguinte nascia vazia. O que se perdia não era o clique de puxar
    de novo — era **o fato de aquele compromisso estar na segunda semana
    seguida**, que é o que faz a reunião perguntar o que está travando.
    """

    def _semana_com_falha(self, previsto=None, apontado=None):
        prog = self._programacao(semana=date(2026, 6, 1))
        i1 = self._item(prog, atividade=self.a1, responsavel="Encarregado João",
                        percentual_previsto=previsto)
        i2 = self._item(prog, atividade=self.a2)
        if apontado is not None:
            ApontamentoAvanco.objects.create(
                tenant=self.tenant, atividade=self.a1,
                data=date(2026, 6, 3), percentual=Decimal(apontado),
            )
        services.comprometer(programacao=prog, por="Ana")
        services.semear_causas_de_fabrica(self.tenant.pk)
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=prog, julgamentos=[
            {"item": i1.pk, "cumprido": False, "causa": causa.pk,
             "nota": "Bloco não chegou"},
            {"item": i2.pk, "cumprido": True},
        ])
        return prog, i1, i2

    def test_encerrar_leva_o_que_nao_saiu_para_a_semana_seguinte(self):
        prog, i1, _ = self._semana_com_falha()
        leitura = services.encerrar(programacao=prog, por="Ana")
        self.assertEqual(leitura["arrasto"]["arrastados"], 1)
        destino = ProgramacaoSemanal.objects.get(
            pk=leitura["arrasto"]["programacao_destino"],
        )
        self.assertEqual(destino.semana_inicio, date(2026, 6, 8))
        self.assertEqual(destino.status, ProgramacaoSemanal.Status.RASCUNHO)
        novo = destino.itens.get()
        self.assertEqual(novo.atividade_id, self.a1.pk)
        self.assertEqual(novo.arrastado_de_id, i1.pk)
        self.assertEqual(novo.vezes_arrastado, 1)
        self.assertEqual(novo.responsavel, "Encarregado João")

    def test_o_cumprido_NAO_e_arrastado(self):
        prog, _, _ = self._semana_com_falha()
        leitura = services.encerrar(programacao=prog, por="Ana")
        destino = ProgramacaoSemanal.objects.get(
            pk=leitura["arrasto"]["programacao_destino"],
        )
        self.assertEqual(
            list(destino.itens.values_list("atividade_id", flat=True)),
            [self.a1.pk],
        )

    def test_o_cartao_novo_nasce_POR_JULGAR_e_sem_a_causa_antiga(self):
        """O julgamento é da semana que passou. Levar a causa junto faria o
        ranking contar a mesma falha de novo antes de ela acontecer."""
        prog, _, _ = self._semana_com_falha()
        leitura = services.encerrar(programacao=prog, por="Ana")
        novo = ItemProgramacao.objects.get(
            programacao_id=leitura["arrasto"]["programacao_destino"],
        )
        self.assertIsNone(novo.cumprido)
        self.assertIsNone(novo.causa_id)
        self.assertEqual(novo.nota, "")

    def test_arrasta_o_QUE_FALTA_quando_a_execucao_foi_parcial(self):
        """A equipe que assumiu 20 pontos e apontou 12 **fez 12**: o que segue
        para a semana seguinte são os 8 que ficaram."""
        prog, i1, _ = self._semana_com_falha(previsto=Decimal("20"), apontado="12")
        leitura = services.encerrar(programacao=prog, por="Ana")
        novo = ItemProgramacao.objects.get(
            programacao_id=leitura["arrasto"]["programacao_destino"],
        )
        self.assertEqual(novo.percentual_previsto, Decimal("8"))

    def test_previsto_nulo_continua_nulo(self):
        """Compromisso binário ("concretar a laje") não ganha número inventado
        no arrasto."""
        prog, _, _ = self._semana_com_falha()
        leitura = services.encerrar(programacao=prog, por="Ana")
        novo = ItemProgramacao.objects.get(
            programacao_id=leitura["arrasto"]["programacao_destino"],
        )
        self.assertIsNone(novo.percentual_previsto)

    def test_o_contador_soma_a_cada_semana_arrastada(self):
        """Quatro semanas arrastado não é o mesmo problema que uma — e ninguém
        veria esse padrão cruzando quadros à mão."""
        prog, _, _ = self._semana_com_falha()
        leitura = services.encerrar(programacao=prog, por="Ana")
        destino = ProgramacaoSemanal.objects.get(
            pk=leitura["arrasto"]["programacao_destino"],
        )
        segundo = destino.itens.get()
        services.comprometer(programacao=destino, por="Ana")
        causa = CausaNaoCumprimento.objects.get(
            tenant=self.tenant, codigo="MAT-FALTA",
        )
        services.julgar_itens(programacao=destino, julgamentos=[
            {"item": segundo.pk, "cumprido": False, "causa": causa.pk},
        ])
        leitura2 = services.encerrar(programacao=destino, por="Ana")
        terceiro = ItemProgramacao.objects.get(
            programacao_id=leitura2["arrasto"]["programacao_destino"],
        )
        self.assertEqual(terceiro.vezes_arrastado, 2)

    def test_rodar_duas_vezes_nao_duplica_cartao(self):
        prog, _, _ = self._semana_com_falha()
        services.encerrar(programacao=prog, por="Ana")
        segundo = services.arrastar_pendentes(programacao=prog, por="Ana")
        self.assertEqual(segundo["arrastados"], 0)
        self.assertEqual(segundo["ja_no_quadro"], 1)

    def test_nao_arrasta_para_semana_ja_comprometida(self):
        """Acrescentar compromisso a um quadro assumido é escrever a aposta
        depois do resultado."""
        seguinte = self._programacao(semana=date(2026, 6, 8))
        self._item(seguinte, atividade=self.a2)
        services.comprometer(programacao=seguinte, por="Ana")
        prog, _, _ = self._semana_com_falha()
        leitura = services.encerrar(programacao=prog, por="Ana")
        self.assertTrue(leitura["arrasto"]["destino_fechado"])
        self.assertEqual(leitura["arrasto"]["arrastados"], 0)

    def test_arrastar_so_vale_para_semana_encerrada(self):
        prog, _, _ = self._semana_com_falha()
        with self.assertRaises(ValidationError):
            services.arrastar_pendentes(programacao=prog, por="Ana")

    def test_encerrar_com_arrastar_falso_nao_mexe_na_semana_seguinte(self):
        prog, _, _ = self._semana_com_falha()
        leitura = services.encerrar(
            programacao=prog, por="Ana", arrastar=False,
        )
        self.assertIsNone(leitura["arrasto"])
        self.assertFalse(
            ProgramacaoSemanal.objects.filter(
                obra=self.obra, semana_inicio=date(2026, 6, 8),
            ).exists()
        )


class ApiDaReaberturaTests(APITestCase):
    """A porta da reabertura — **e a permissão que muda com o degrau**."""

    def setUp(self):
        self.tenant = Tenant.objects.create(slug="pdca5-reabrir", nome="LPS Reabrir")
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra Reabrir", endereco="Rua R",
        )
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Padrão",
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.atividade = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Alvenaria", duracao_dias=5, profundidade=1,
        )
        self.prog = services.abrir_programacao(
            obra=self.obra, semana_inicio=date(2026, 6, 1), tenant_id=self.tenant.pk,
        )
        self.item = ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=self.prog, atividade=self.atividade,
        )
        services.comprometer(programacao=self.prog, por="x")
        services.julgar_itens(programacao=self.prog, julgamentos=[
            {"item": self.item.pk, "cumprido": True},
        ])
        services.encerrar(programacao=self.prog, por="x")

        self.usuario = Usuario.objects.create(username="lps5r", tenant=self.tenant)
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = [
            "pdca.programacao.view", "pdca.programacao.comprometer",
            "pdca.programacao.encerrar",
        ]
        self.client.force_authenticate(user=self.usuario)

    def _url(self):
        return f"/api/pdca/programacoes/{self.prog.pk}/reabrir/"

    def test_reabrir_pela_api_devolve_o_documento_atualizado(self):
        resposta = self.client.post(
            self._url(), {"motivo": "a causa estava errada"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        corpo = resposta.json()
        self.assertEqual(corpo["para"], "comprometida")
        self.assertEqual(corpo["programacao_dados"]["status"], "comprometida")
        self.assertEqual(corpo["programacao_dados"]["vezes_reaberta"], 1)
        self.assertEqual(
            corpo["programacao_dados"]["motivo_reabertura"], "a causa estava errada",
        )

    def test_sem_motivo_a_recusa_fala_a_lingua_da_casa(self):
        resposta = self.client.post(self._url(), {"motivo": "   "}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("em silêncio", str(resposta.json()))

    def test_quem_so_COMPROMETE_nao_desfaz_o_encerramento(self):
        """Desfazer o encerramento é desfazer o julgamento, e isso é de quem
        julga. Sem esta trava, quem monta a parede poderia apagar o índice que
        ela produziu."""
        self.usuario.iam_permissions = [
            "pdca.programacao.view", "pdca.programacao.comprometer",
        ]
        resposta = self.client.post(self._url(), {"motivo": "tentando"}, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_quem_so_ENCERRA_nao_desfaz_o_compromisso(self):
        """E o contrário: desfazer o compromisso devolve o quadro ao rascunho,
        e isso é de quem assume."""
        self.client.post(self._url(), {"motivo": "primeira"}, format="json")
        self.usuario.iam_permissions = [
            "pdca.programacao.view", "pdca.programacao.encerrar",
        ]
        resposta = self.client.post(self._url(), {"motivo": "segunda"}, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_quem_so_LE_nao_reabre_nada(self):
        self.usuario.iam_permissions = ["pdca.programacao.view"]
        resposta = self.client.post(self._url(), {"motivo": "tentando"}, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_o_status_declara_a_capacidade(self):
        corpo = self.client.get("/api/pdca/status/").json()
        self.assertIs(corpo["recursos"]["reabrir_semana"], True)


# ---------------------------------------------------------------------------
# PDCA.6 — a linha de balanço: ritmo, sincronia de equipes e gargalo
# ---------------------------------------------------------------------------
# O que estes testes prendem:
#
# - **a LOB é derivada, e não tem tabela** (§4.9): ela lê `Atividade` × `LocalObra`
#   e nunca grava inclinação. Guardar o ritmo criaria a segunda verdade, que
#   envelheceria no instante em que alguém arrastasse uma barra no Gantt;
# - **o eixo Y é a árvore construtiva em ordem de leitura**, e não o código em
#   ordem alfabética — "P10" depois de "P9", não antes;
# - **a precedência do traço é `SS` com atraso**, que é o que faz a inclinação
#   ser o ritmo pedido e não a duração;
# - **o conflito é fato, não geometria**: dois serviços diferentes com janelas
#   que se sobrepõem no mesmo local;
# - **a leitura diz o que não está mostrando** — atividade sem local fica de
#   fora, e o número dela vem no corpo.


class _BaseLinhaDeBalanco(TestCase):
    """Uma torre de quatro pavimentos, e um cronograma em rascunho."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-lob", nome="Construtora LOB")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Torre do Ritmo", endereco="Rua 6",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, obra=cls.obra, nome="Padrão",
        )
        cls.torre = LocalObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, nivel=NivelLocal.BLOCO,
            codigo="T1", nome="Torre 1", ordem=1, profundidade=0,
        )
        #: Os códigos vão a "P10" de propósito: ordenados por texto, "P10" viria
        #: antes de "P9" e a reta do serviço desceria no meio do gráfico.
        cls.pavimentos = [
            LocalObra.objects.create(
                tenant=cls.tenant, obra=cls.obra, pai=cls.torre,
                nivel=NivelLocal.PAVIMENTO, codigo=f"P{n}", nome=f"{n}º pavimento",
                ordem=n, profundidade=1,
            )
            for n in (1, 2, 9, 10)
        ]
        cls.cronograma = Cronograma.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=cls.calendario,
        )

    def _tracar(self, nome="Alvenaria", codigo="1", duracao=4, ritmo=None,
                locais=None, **extra):
        return services.gerar_ritmo(
            cronograma=self.cronograma,
            locais=locais if locais is not None else [p.pk for p in self.pavimentos],
            inicio=date(2026, 6, 1),
            duracao_por_local=duracao, ritmo_dias=ritmo,
            nome=nome, codigo=codigo, tenant_id=self.tenant.pk, **extra,
        )


class DesenharALinhaTests(_BaseLinhaDeBalanco):
    """O gesto que a planta §5.2 põe no lugar do arrastar."""

    def test_o_traco_cria_a_fileira_de_atividades_com_local(self):
        resultado = self._tracar()
        self.assertEqual(resultado["criar"], 4)
        criadas = Atividade.objects.filter(
            tenant=self.tenant, cronograma=self.cronograma, pai__isnull=False,
        ).order_by("ordem")
        self.assertEqual(criadas.count(), 4)
        self.assertEqual(
            [a.local_id for a in criadas], [p.pk for p in self.pavimentos],
        )
        self.assertTrue(all(a.duracao_dias == 4 for a in criadas))
        #: O nome de cada folha diz **onde** — é o que a torna legível no Gantt,
        #: onde não há eixo de localização.
        self.assertIn("1º pavimento", criadas.first().nome)

    def test_a_precedencia_e_SS_com_o_ritmo_como_atraso(self):
        """**A diferença entre uma LOB e uma fila.**

        Com `FS` o pavimento seguinte começaria depois de o anterior terminar, e
        o ritmo passaria a ser a duração — impossível representar a equipe que
        sobe a cada dois dias um serviço que leva quatro.
        """
        self._tracar(duracao=4, ritmo=2)
        ligacoes = Precedencia.objects.filter(tenant=self.tenant)
        self.assertEqual(ligacoes.count(), 3)
        self.assertTrue(all(p.tipo == Precedencia.Tipo.SS for p in ligacoes))
        self.assertTrue(all(p.atraso_dias == 2 for p in ligacoes))

    def test_o_ritmo_nulo_herda_a_duracao_e_vira_fluxo_continuo(self):
        self._tracar(duracao=3, ritmo=None)
        self.assertTrue(all(
            p.atraso_dias == 3 for p in Precedencia.objects.filter(tenant=self.tenant)
        ))

    def test_simular_nao_escreve_nada(self):
        """A régua do gerador de locais da PDCA.0: a mesma conta, sem gravar."""
        resultado = self._tracar(simular=True)
        self.assertTrue(resultado["simulado"])
        self.assertEqual(resultado["criar"], 4)
        self.assertEqual(len(resultado["previa"]), 4)
        self.assertEqual(
            Atividade.objects.filter(cronograma=self.cronograma).count(), 0,
        )

    def test_a_simulacao_diz_o_prazo_do_traco_antes_de_gravar(self):
        #: 4 locais, ritmo 2, duração 4 → o último começa 6 dias depois do
        #: primeiro e leva 4: 10 dias úteis.
        resultado = self._tracar(duracao=4, ritmo=2, simular=True)
        self.assertEqual(resultado["dias_uteis_total"], 10)

    def test_o_plano_vigente_nao_recebe_traco_novo(self):
        self.cronograma.status = Cronograma.Status.VIGENTE
        self.cronograma.save()
        with self.assertRaises(ValidationError) as erro:
            self._tracar()
        self.assertIn("rascunho", str(erro.exception).lower())

    def test_local_de_outra_obra_e_recusado(self):
        outra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Outra", endereco="Rua 7",
        )
        alheio = LocalObra.objects.create(
            tenant=self.tenant, obra=outra, nivel=NivelLocal.BLOCO,
            codigo="X", nome="Torre alheia", profundidade=0,
        )
        with self.assertRaises(ValidationError):
            self._tracar(locais=[self.pavimentos[0].pk, alheio.pk])

    def test_servico_sem_nome_e_sem_pai_e_recusado(self):
        with self.assertRaises(ValidationError) as erro:
            self._tracar(nome="", codigo="1")
        self.assertIn("serviço", str(erro.exception).lower())

    def test_duracao_zero_e_recusada_porque_marco_nao_tem_ritmo(self):
        with self.assertRaises(ValidationError) as erro:
            self._tracar(duracao=0)
        self.assertIn("marco", str(erro.exception).lower())

    def test_o_segundo_traco_continua_a_numeracao_do_servico(self):
        """Desenhar a segunda torre não pode renumerar a primeira por cima."""
        primeiro = self._tracar(locais=[self.pavimentos[0].pk, self.pavimentos[1].pk])
        services.gerar_ritmo(
            cronograma=self.cronograma, locais=[self.pavimentos[2].pk],
            inicio=date(2026, 7, 1), duracao_por_local=4,
            pai_id=primeiro["pai"], tenant_id=self.tenant.pk,
        )
        codigos = list(
            Atividade.objects.filter(
                tenant=self.tenant, pai_id=primeiro["pai"],
            ).order_by("ordem").values_list("codigo", flat=True)
        )
        self.assertEqual(codigos, ["1.1", "1.2", "1.3"])


class LerALinhaDeBalancoTests(_BaseLinhaDeBalanco):
    """A leitura derivada — eixo, retas, ritmo, gargalo e choques."""

    def test_o_eixo_segue_a_arvore_e_nao_o_alfabeto(self):
        """P10 depois de P9 — ordenar por código os inverteria."""
        self._tracar()
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertEqual(
            [l["codigo"] for l in lob["eixo"]], ["P1", "P2", "P9", "P10"],
        )

    def test_a_reta_do_servico_tem_um_ponto_por_local(self):
        self._tracar()
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertEqual(len(lob["linhas"]), 1)
        linha = lob["linhas"][0]
        self.assertEqual(linha["nome"], "Alvenaria")
        self.assertEqual(len(linha["pontos"]), 4)
        #: Ordenados pelo eixo, para a reta ser desenhada sem o cliente ordenar.
        self.assertEqual([p["y"] for p in linha["pontos"]], [0, 1, 2, 3])

    def test_o_ritmo_e_a_inclinacao_pedida(self):
        self._tracar(duracao=4, ritmo=2)
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        linha = lob["linhas"][0]
        #: Dias **corridos** entre os inícios, que é o que o eixo X desenha — a
        #: conversão de dias úteis para calendário é do CPM, e a LOB lê o
        #: resultado dele, não a intenção.
        self.assertIsNotNone(linha["dias_por_local"])
        self.assertIsNotNone(linha["locais_por_semana"])
        self.assertGreater(linha["locais_por_semana"], 0)

    def test_um_ponto_so_NAO_tem_ritmo(self):
        """Uma reta precisa de dois pontos. Devolver o inverso da duração diria
        que o serviço tem ritmo quando o que existe é um serviço em um lugar."""
        self._tracar(locais=[self.pavimentos[0].pk])
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertIsNone(lob["linhas"][0]["dias_por_local"])
        self.assertIsNone(lob["linhas"][0]["locais_por_semana"])
        self.assertIsNone(lob["gargalo"])

    def test_o_gargalo_e_o_servico_mais_lento(self):
        """**A leitura que a LOB tem e o Gantt não.** Acelerar qualquer outro
        serviço não adianta: o trem anda na velocidade do vagão mais lento."""
        rapido = self._tracar(nome="Alvenaria", codigo="1", duracao=2, ritmo=2)
        lento = self._tracar(nome="Contrapiso", codigo="2", duracao=8, ritmo=8)
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertEqual(lob["gargalo"], lento["pai"])
        self.assertNotEqual(lob["gargalo"], rapido["pai"])

    def test_dois_servicos_no_mesmo_local_ao_mesmo_tempo_e_CONFLITO(self):
        """O que a LOB existe para achar — duas equipes no mesmo lugar."""
        self._tracar(nome="Alvenaria", codigo="1", duracao=10, ritmo=10)
        self._tracar(nome="Elétrica", codigo="2", duracao=10, ritmo=10)
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertTrue(lob["conflitos"])
        choque = lob["conflitos"][0]
        self.assertNotEqual(choque["servico_a"], choque["servico_b"])
        self.assertGreaterEqual(choque["dias"], 1)
        self.assertIn("pavimento", choque["local_rotulo"].lower())

    def test_o_mesmo_servico_duas_vezes_no_local_NAO_e_conflito(self):
        """Duas frentes do mesmo empreiteiro são a mesma equipe — o choque é
        entre ofícios, não dentro de um."""
        traco = self._tracar(duracao=10, ritmo=10)
        Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, pai_id=traco["pai"],
            codigo="1.9", nome="Alvenaria — reforço", duracao_dias=10,
            local=self.pavimentos[0], profundidade=2, ordem=99,
        )
        services.calcular_cpm(self.cronograma)
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertEqual(lob["conflitos"], [])

    def test_a_leitura_declara_o_que_NAO_esta_mostrando(self):
        """Um gráfico que desenha 1 de 2 serviços sem avisar é pior que gráfico
        nenhum — quem olha conclui que a obra tem uma frente só."""
        self._tracar()
        Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="9",
            nome="Canteiro (sem endereço)", duracao_dias=5, profundidade=1,
        )
        services.calcular_cpm(self.cronograma)
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertEqual(lob["atividades_sem_local"], 1)

    def test_cronograma_sem_CPM_devolve_LOB_vazia_e_nao_quebra(self):
        Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Sem datas", duracao_dias=5, profundidade=1,
            local=self.pavimentos[0],
        )
        lob = services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertEqual(lob["linhas"], [])
        self.assertEqual(lob["eixo"], [])
        self.assertIsNone(lob["gargalo"])

    def test_a_LOB_nao_grava_nada(self):
        """Ela é derivada (§4.9). Ler duas vezes não muda o banco."""
        self._tracar()
        antes = Atividade.objects.filter(cronograma=self.cronograma).count()
        services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        services.linha_de_balanco(self.cronograma, tenant_id=self.tenant.pk)
        self.assertEqual(
            Atividade.objects.filter(cronograma=self.cronograma).count(), antes,
        )


class TetosDaLinhaDeBalancoNoServicoTests(_BaseLinhaDeBalanco):
    """Os tetos da §5.5k exercidos onde eles mordem."""

    def test_o_traco_respeita_o_teto_de_locais(self):
        from payment.planos import PDCA_TETO_LOCAIS_POR_RITMO

        with self.assertRaises(ValidationError):
            services.validar_teto_de_locais_do_ritmo(PDCA_TETO_LOCAIS_POR_RITMO + 1)


class ApiDaPdca6Tests(APITestCase):
    """As duas portas novas, **pelo HTTP** — a régua que o D149 escreveu."""

    def setUp(self):
        self.tenant = Tenant.objects.create(slug="pdca6-api", nome="Construtora LOB API")
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra LOB", endereco="Rua API",
        )
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Padrão",
        )
        self.torre = LocalObra.objects.create(
            tenant=self.tenant, obra=self.obra, nivel=NivelLocal.BLOCO,
            codigo="T1", nome="Torre 1", profundidade=0,
        )
        self.pavimentos = [
            LocalObra.objects.create(
                tenant=self.tenant, obra=self.obra, pai=self.torre,
                nivel=NivelLocal.PAVIMENTO, codigo=f"P{n}", nome=f"{n}º pavimento",
                ordem=n, profundidade=1,
            )
            for n in (1, 2, 3)
        ]
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
        )
        self.usuario = Usuario.objects.create(username="lob6", tenant=self.tenant)
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = [
            "pdca.cronograma.view", "pdca.cronograma.edit",
        ]
        self.client.force_authenticate(user=self.usuario)

    def _url(self, sufixo):
        return f"/api/pdca/cronogramas/{self.cronograma.pk}/{sufixo}"

    def test_o_traco_pela_api_cria_as_atividades_com_tenant(self):
        resposta = self.client.post(self._url("ritmo/"), {
            "nome": "Alvenaria", "codigo": "1",
            "locais": [p.pk for p in self.pavimentos],
            "inicio": "2026-06-01", "duracao_por_local": 4, "ritmo_dias": 2,
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        criadas = Atividade.objects.filter(
            cronograma=self.cronograma, pai__isnull=False,
        )
        self.assertEqual(criadas.count(), 3)
        self.assertTrue(all(a.tenant_id == self.tenant.pk for a in criadas))

    def test_simular_responde_200_e_nao_grava(self):
        resposta = self.client.post(self._url("ritmo/"), {
            "nome": "Alvenaria", "codigo": "1",
            "locais": [p.pk for p in self.pavimentos],
            "inicio": "2026-06-01", "duracao_por_local": 4, "simular": True,
        }, format="json")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["simulado"])
        self.assertEqual(Atividade.objects.filter(cronograma=self.cronograma).count(), 0)

    def test_a_leitura_responde_a_lob_inteira(self):
        self.client.post(self._url("ritmo/"), {
            "nome": "Alvenaria", "codigo": "1",
            "locais": [p.pk for p in self.pavimentos],
            "inicio": "2026-06-01", "duracao_por_local": 4, "ritmo_dias": 2,
        }, format="json")
        resposta = self.client.get(self._url("linha-de-balanco/"))
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(len(corpo["eixo"]), 3)
        self.assertEqual(len(corpo["linhas"]), 1)
        #: O ritmo é `Decimal`, e atravessa como **string** — a régua do D151.
        self.assertIsInstance(corpo["linhas"][0]["dias_por_local"], str)

    def test_quem_so_le_o_plano_nao_desenha_a_linha(self):
        """O traço **cria atividades**: é `edit`, não `view`."""
        self.usuario.iam_permissions = ["pdca.cronograma.view"]
        resposta = self.client.post(self._url("ritmo/"), {
            "nome": "Alvenaria", "codigo": "1",
            "locais": [self.pavimentos[0].pk],
            "inicio": "2026-06-01", "duracao_por_local": 4,
        }, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_o_status_declara_a_fatia_e_os_tetos_novos(self):
        corpo = self.client.get("/api/pdca/status/").json()
        #: O número da fatia **não** se afirma aqui, pela mesma razão do
        #: `AcessoAoModuloTests`: este é o teste da PDCA.6, e ele quebraria na
        #: PDCA.7 sem nada da PDCA.6 ter parado de funcionar. O que ele tem de
        #: provar são as capacidades e os tetos que a PDCA.6 acrescentou.
        self.assertTrue(corpo["fatia"].startswith("PDCA."))
        self.assertIs(corpo["recursos"]["linha_de_balanco"], True)
        self.assertIs(corpo["recursos"]["conflito_de_equipe"], True)
        self.assertIsInstance(corpo["tetos"]["locais_por_ritmo"], int)


# ---------------------------------------------------------------------------
# PDCA.7 — a máquina de verificação: FVS, NC, 5W2H e eficácia
# ---------------------------------------------------------------------------
# O que estes testes protegem, em uma frase cada:
#
# - **a pergunta respondida é a pergunta feita**: apertar o critério do modelo no
#   ano seguinte não reescreve nenhuma inspeção passada — é o congelamento que
#   torna a ficha uma prova, e é o teste mais importante da fatia;
# - **desvio exige explicação**, e a trava vale no banco, não só na aplicação:
#   sem ela o "não aplicável" em tudo aprova o serviço sem mentir em campo algum;
# - **a conformidade é derivada e honesta** — não existe enquanto nada foi
#   respondido, e o não aplicável fica fora do denominador;
# - **a NC não encerra por carimbo**: só com eficácia verificada, e a eficácia
#   negativa devolve o defeito ao tratamento em vez de fechá-lo;
# - **o seam do Last Planner é vivo**: NC grave vira restrição, e a restrição
#   trava de verdade o compromisso da semana na PDCA.5.


class _BaseVerificacao(TestCase):
    """Fixture comum: uma obra com plano vigente e um modelo de FVS de 3 itens."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-qua", nome="Construtora Qualidade")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Conforme", endereco="Rua 7",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, obra=cls.obra, nome="Padrão",
        )
        cls.cronograma = Cronograma.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=cls.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        cls.atividade = Atividade.objects.create(
            tenant=cls.tenant, cronograma=cls.cronograma, codigo="1",
            nome="Alvenaria do 4º", duracao_dias=5, profundidade=1,
        )
        cls.local = LocalObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, codigo="T1-4",
            nome="Torre 1 · 4º pavimento", nivel=NivelLocal.PAVIMENTO,
        )

    def setUp(self):
        self.modelo = ModeloVerificacao.objects.create(
            tenant=self.tenant, codigo="FVS-ALV", nome="FVS — Alvenaria",
            dominio=DominioVerificacao.QUALIDADE,
        )
        self.i1 = ItemModeloVerificacao.objects.create(
            tenant=self.tenant, modelo=self.modelo, ordem=1,
            texto="Prumo da parede", criterio="Desvio até 3 mm em 2 m",
        )
        self.i2 = ItemModeloVerificacao.objects.create(
            tenant=self.tenant, modelo=self.modelo, ordem=2,
            texto="Espessura da junta", criterio="10 mm ± 2 mm",
        )
        self.i3 = ItemModeloVerificacao.objects.create(
            tenant=self.tenant, modelo=self.modelo, ordem=3,
            texto="Limpeza da frente", obrigatorio=False,
        )

    def _ficha(self, **extra):
        return services.aplicar_verificacao(
            modelo=self.modelo, obra=self.obra, data=date(2026, 6, 10),
            tenant_id=self.tenant.pk, **extra,
        )

    def _responder(self, ficha, pares, por="tecnico"):
        """`pares` = [(ordem, resultado, observacao)] ou com gravidade no fim.

        **A gravidade cai para `menor` quando o teste não a declara.** Ela é
        obrigatória no reprovado (§11.15), mas a maioria destes testes não trata
        de gravidade — repetir `MENOR` em trinta tuplas esconderia o que cada um
        está realmente provando. Os que testam a gradação passam a quarta
        posição, e os que testam a **exigência** chamam o serviço direto.
        """
        por_ordem = {i.ordem: i for i in ficha.itens.all()}
        respostas = []
        for par in pares:
            ordem, resultado, obs = par[0], par[1], par[2]
            peso = par[3] if len(par) > 3 else (
                GravidadeNC.MENOR if resultado == ResultadoItem.NAO_CONFORME
                else None
            )
            respostas.append({
                "item_verificacao": por_ordem[ordem].pk,
                "resultado": resultado,
                "observacao": obs,
                "gravidade": peso,
            })
        return services.responder_itens(
            verificacao=ficha, por=por, respostas=respostas,
        )

    def _nc(self, **extra):
        return NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra,
            descricao=extra.pop("descricao", "Parede fora de prumo"),
            **extra,
        )


class MaquinaDeVerificacaoTests(_BaseVerificacao):
    """A ficha aplicada — e o congelamento que a torna prova."""

    def test_aplicar_copia_as_perguntas_para_dentro_da_ficha(self):
        ficha = self._ficha()
        self.assertEqual(ficha.itens.count(), 3)
        primeiro = ficha.itens.order_by("ordem").first()
        self.assertEqual(primeiro.texto, "Prumo da parede")
        self.assertEqual(primeiro.criterio, "Desvio até 3 mm em 2 m")
        # E todas nascem pendentes — nunca reprovadas.
        self.assertEqual(
            ficha.itens.filter(resultado=ResultadoItem.PENDENTE).count(), 3,
        )

    def test_apertar_o_criterio_do_modelo_NAO_reescreve_a_inspecao_passada(self):
        """**O teste mais importante da fatia.**

        A empresa aperta o prumo de 3 mm para 2 mm no ano seguinte, e faz bem. Se
        a ficha lesse o texto pelo FK, toda inspeção do ano anterior passaria a
        afirmar que conferiu 2 mm — e a auditoria do PBQP-H encontraria um
        sistema que reescreve o passado sozinho.
        """
        ficha = self._ficha()
        self.i1.criterio = "Desvio até 2 mm em 2 m"
        self.i1.texto = "Prumo e planeza da parede"
        self.i1.save()

        congelado = ficha.itens.order_by("ordem").first()
        congelado.refresh_from_db()
        self.assertEqual(congelado.criterio, "Desvio até 3 mm em 2 m")
        self.assertEqual(congelado.texto, "Prumo da parede")
        # E o vínculo continua de pé, para quem quiser ver de onde veio.
        self.assertEqual(congelado.item_modelo_id, self.i1.pk)

    def test_modelo_inativo_nao_se_aplica(self):
        self.modelo.ativo = False
        self.modelo.save()
        with self.assertRaises(ValidationError) as erro:
            self._ficha()
        self.assertIn("inativo", str(erro.exception).lower())

    def test_modelo_sem_pergunta_nao_se_aplica(self):
        """Ficha vazia conclui com 100% sem ninguém ter olhado nada."""
        vazio = ModeloVerificacao.objects.create(
            tenant=self.tenant, codigo="VAZIO", nome="Sem itens",
        )
        with self.assertRaises(ValidationError) as erro:
            services.aplicar_verificacao(
                modelo=vazio, obra=self.obra, data=date(2026, 6, 10),
                tenant_id=self.tenant.pk,
            )
        self.assertIn("nenhuma pergunta", str(erro.exception))

    def test_os_dois_enderecos_sao_opcionais(self):
        """A inspeção de segurança do canteiro não aponta para local nem
        atividade — obrigar qualquer um excluiria um dos quatro domínios."""
        ficha = self._ficha()
        self.assertIsNone(ficha.local_id)
        self.assertIsNone(ficha.atividade_id)

        com_endereco = self._ficha(
            local_id=self.local.pk, atividade_id=self.atividade.pk,
        )
        self.assertEqual(com_endereco.local_id, self.local.pk)

    def test_duplicar_copia_a_ficha_inteira(self):
        copia = services.duplicar_modelo(
            modelo=self.modelo, codigo="FVS-ALV-CONC",
            nome="FVS — Alvenaria de concreto", por="qualidade",
        )
        self.assertEqual(copia.itens.count(), 3)
        self.assertEqual(
            list(copia.itens.order_by("ordem").values_list("texto", flat=True)),
            ["Prumo da parede", "Espessura da junta", "Limpeza da frente"],
        )
        # A cópia é independente: mexer nela não toca na original.
        copia.itens.filter(ordem=1).update(criterio="Outro critério")
        self.i1.refresh_from_db()
        self.assertEqual(self.i1.criterio, "Desvio até 3 mm em 2 m")


class RespostaDaFichaTests(_BaseVerificacao):
    """O desvio exige explicação — e a conformidade é honesta."""

    def test_nao_conforme_sem_observacao_e_recusado(self):
        ficha = self._ficha()
        with self.assertRaises(ValidationError) as erro:
            self._responder(ficha, [(1, ResultadoItem.NAO_CONFORME, "")])
        self.assertIn("sem explicação", str(erro.exception))

    def test_nao_aplicavel_sem_observacao_tambem_e_recusado(self):
        """**É a porta pela qual uma ficha inteira passa sem ninguém verificar
        nada**: marcar N/A em tudo aprova o serviço sem mentir em campo algum."""
        ficha = self._ficha()
        with self.assertRaises(ValidationError):
            self._responder(ficha, [(1, ResultadoItem.NAO_APLICAVEL, "")])

    def test_a_trava_do_desvio_vale_no_BANCO(self):
        """A aplicação dá a mensagem; o banco é quem impede a segunda porta —
        importação e comando de bancada não passam pelo `services`."""
        ficha = self._ficha()
        item = ficha.itens.order_by("ordem").first()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ItemVerificacao.objects.filter(pk=item.pk).update(
                    resultado=ResultadoItem.NAO_CONFORME, observacao="",
                )

    def test_ficha_concluida_nao_recebe_mais_resposta(self):
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.CONFORME, ""), (2, ResultadoItem.CONFORME, ""),
        ])
        services.concluir_verificacao(verificacao=ficha, por="tecnico")
        ficha.refresh_from_db()
        with self.assertRaises(ValidationError) as erro:
            self._responder(ficha, [(3, ResultadoItem.CONFORME, "")])
        self.assertIn("já foi concluída", str(erro.exception))

    def test_conformidade_e_None_enquanto_nada_foi_respondido(self):
        """A régua do PPC e do avanço: "sem apuração", nunca 0%."""
        ficha = self._ficha()
        resultado = services.resultado_da_verificacao(ficha)
        self.assertIsNone(resultado["conformidade"])
        self.assertEqual(resultado["pendentes"], 3)

    def test_nao_aplicavel_fica_fora_do_denominador(self):
        """Um item que não se aplica não é acerto nem erro. Contá-lo como
        conforme inflaria toda ficha longa aplicada a um serviço pequeno."""
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.CONFORME, ""),
            (2, ResultadoItem.NAO_CONFORME, "Junta com 15 mm"),
            (3, ResultadoItem.NAO_APLICAVEL, "Frente ainda não liberada"),
        ])
        resultado = services.resultado_da_verificacao(ficha)
        # 1 conforme de 2 julgados = 50%, e não 1 de 3 = 33%.
        self.assertEqual(resultado["conformidade"], Decimal("50.00"))
        self.assertEqual(resultado["nao_aplicaveis"], 1)

    def test_o_agregado_da_pagina_bate_com_o_da_ficha(self):
        """O atalho de uma consulta só (D136) não pode dar outro número."""
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.CONFORME, ""),
            (2, ResultadoItem.NAO_CONFORME, "Junta com 15 mm"),
        ])
        um = services.resultado_da_verificacao(ficha)
        varios = services.resultados_das_verificacoes(
            [ficha], tenant_id=self.tenant.pk,
        )
        self.assertEqual(um, varios[ficha.pk])


class ConclusaoDaFichaTests(_BaseVerificacao):
    """Concluir é assinar — e não se assina com o essencial em branco."""

    def test_obrigatorio_pendente_impede_a_conclusao(self):
        ficha = self._ficha()
        self._responder(ficha, [(1, ResultadoItem.CONFORME, "")])
        with self.assertRaises(ValidationError) as erro:
            services.concluir_verificacao(verificacao=ficha, por="tecnico")
        self.assertIn("obrigatórios 2", str(erro.exception))

    def test_nao_obrigatorio_pendente_nao_impede(self):
        """É o que permite a ficha longa ser concluída sem a pergunta acessória
        sobre a qual ninguém tem o que dizer."""
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.CONFORME, ""), (2, ResultadoItem.CONFORME, ""),
        ])
        services.concluir_verificacao(verificacao=ficha, por="tecnico")
        ficha.refresh_from_db()
        self.assertEqual(ficha.status, Verificacao.Status.CONCLUIDA)
        self.assertTrue(ficha.concluida_em)

    def test_a_conclusao_devolve_os_reprovados_que_ainda_nao_viraram_nc(self):
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.CONFORME, ""),
            (2, ResultadoItem.NAO_CONFORME, "Junta com 15 mm"),
        ])
        saida = services.concluir_verificacao(verificacao=ficha, por="tecnico")
        self.assertEqual(len(saida["reprovados_sem_nc"]), 1)
        self.assertEqual(saida["reprovados_sem_nc"][0]["ordem"], 2)


class NaoConformidadeTests(_BaseVerificacao):
    """O defeito nasce de um item reprovado **ou avulsa** — as duas portas."""

    def test_abrir_ncs_dos_reprovados_leva_endereco_e_pergunta(self):
        ficha = self._ficha(
            local_id=self.local.pk, atividade_id=self.atividade.pk,
        )
        self._responder(ficha, [
            (1, ResultadoItem.NAO_CONFORME, "Desvio de 12 mm"),
            (2, ResultadoItem.CONFORME, ""),
        ])
        saida = services.abrir_ncs_dos_reprovados(
            verificacao=ficha, por="tecnico",
        )
        self.assertEqual(saida["abertas"], 1)

        nc = NaoConformidade.objects.get(pk=saida["ncs"][0])
        self.assertEqual(nc.local_id, self.local.pk)
        self.assertEqual(nc.atividade_id, self.atividade.pk)
        # A descrição junta a pergunta congelada com a observação do técnico.
        self.assertIn("Prumo da parede", nc.descricao)
        self.assertIn("Desvio de 12 mm", nc.descricao)

    def test_cada_NC_nasce_com_a_gravidade_do_SEU_item(self):
        """**A correção de 16/09/2026**, e é o ponto inteiro desta regra.

        *(Decisão do dono, olhando o painel: "essa pergunta deveria ser feita em
        cada item e não no final, porque aí fica parecendo que um
        desalinhamento na porta é grave igual a falta de uma maçaneta".)*

        A primeira escrita desta fatia recebia uma gravidade em
        `abrir_ncs_dos_reprovados` e a carimbava em todas — o painel somava "3
        maiores" sobre três coisas de tamanhos diferentes.
        """
        ficha = self._ficha(atividade_id=self.atividade.pk)
        self._responder(ficha, [
            (1, ResultadoItem.NAO_CONFORME, "Desalinhamento de 2 mm na porta",
             GravidadeNC.MENOR),
            (2, ResultadoItem.NAO_CONFORME, "Falta a maçaneta inteira",
             GravidadeNC.MAIOR),
        ])
        saida = services.abrir_ncs_dos_reprovados(
            verificacao=ficha, por="tecnico",
        )
        self.assertEqual(saida["abertas"], 2)

        por_gravidade = {
            nc.gravidade: nc
            for nc in NaoConformidade.objects.filter(pk__in=saida["ncs"])
        }
        self.assertEqual(set(por_gravidade), {"menor", "maior"})
        self.assertIn("Desalinhamento", por_gravidade["menor"].descricao)
        self.assertIn("maçaneta", por_gravidade["maior"].descricao)

    def test_reprovar_sem_dizer_quanto_pesa_e_recusado(self):
        """Um defeito sem peso não dá para triar, e o peso é o que decide o que
        a obra trata primeiro. Mesma família da observação obrigatória."""
        ficha = self._ficha()
        with self.assertRaises(ValidationError) as erro:
            services.responder_itens(
                verificacao=ficha, por="tecnico",
                respostas=[{
                    "item_verificacao": ficha.itens.first().pk,
                    "resultado": ResultadoItem.NAO_CONFORME,
                    "observacao": "Torto",
                }],
            )
        self.assertIn("quanto** pesa", str(erro.exception))

    def test_corrigir_para_conforme_LIMPA_a_gravidade(self):
        """O outro lado da trava, e o menos óbvio.

        Quem marca "não conforme", escolhe o peso e depois corrige para
        "conforme" deixaria uma gravidade órfã pendurada — contada no painel
        como um defeito que não existe.
        """
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.NAO_CONFORME, "Torto", GravidadeNC.CRITICA),
        ])
        item = ficha.itens.order_by("ordem").first()
        item.refresh_from_db()
        self.assertEqual(item.gravidade, GravidadeNC.CRITICA)

        self._responder(ficha, [(1, ResultadoItem.CONFORME, "")])
        item.refresh_from_db()
        self.assertIsNone(item.gravidade)

    def test_a_trava_da_gravidade_vale_no_BANCO(self):
        """A aplicação dá a mensagem; o banco fecha a segunda porta."""
        ficha = self._ficha()
        item = ficha.itens.order_by("ordem").first()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ItemVerificacao.objects.filter(pk=item.pk).update(
                    resultado=ResultadoItem.NAO_CONFORME,
                    observacao="Torto", gravidade=None,
                )
        # E o contrário também: conforme não carrega peso.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ItemVerificacao.objects.filter(pk=item.pk).update(
                    resultado=ResultadoItem.CONFORME,
                    gravidade=GravidadeNC.MAIOR,
                )

    def test_a_conclusao_devolve_a_gravidade_de_cada_reprovado(self):
        """A tela de conclusão **mostra** o que vai abrir e com que peso, em vez
        de perguntar um peso só para todos."""
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.NAO_CONFORME, "Trinca fina", GravidadeNC.MENOR),
            (2, ResultadoItem.NAO_CONFORME, "Armadura exposta", GravidadeNC.CRITICA),
        ])
        saida = services.concluir_verificacao(verificacao=ficha, por="tecnico")
        pesos = {
            linha["ordem"]: linha["gravidade"]
            for linha in saida["reprovados_sem_nc"]
        }
        self.assertEqual(pesos, {1: "menor", 2: "critica"})
        self.assertTrue(
            all(l["gravidade_rotulo"] for l in saida["reprovados_sem_nc"])
        )

    def test_abrir_ncs_duas_vezes_nao_duplica(self):
        ficha = self._ficha()
        self._responder(ficha, [(1, ResultadoItem.NAO_CONFORME, "Torto")])
        primeira = services.abrir_ncs_dos_reprovados(verificacao=ficha)
        segunda = services.abrir_ncs_dos_reprovados(verificacao=ficha)
        self.assertEqual(primeira["abertas"], 1)
        self.assertEqual(segunda["abertas"], 0)

    def test_a_nc_avulsa_nao_precisa_de_ficha(self):
        """O encarregado vê a trinca a caminho do almoxarifado — obrigá-lo a
        abrir uma ficha inteira é o que faz a trinca não ser registrada."""
        nc = self._nc(gravidade=GravidadeNC.MAIOR)
        self.assertIsNone(nc.item_verificacao_id)
        self.assertTrue(nc.esta_aberta)

    def test_o_primeiro_plano_de_acao_poe_a_nc_em_tratamento(self):
        """O degrau que separa "ninguém pegou" de "está sendo consertado" na
        fila de decisão. Aqui pelo serviço da view — ver `ApiDaPdca7Tests`."""
        nc = self._nc()
        self.assertEqual(nc.status, NaoConformidade.Status.ABERTA)


class LacoDaEficaciaTests(_BaseVerificacao):
    """**A regra que separa tratar de arquivar** (planta §4.5)."""

    def setUp(self):
        super().setUp()
        self.nc = self._nc(atividade=self.atividade, gravidade=GravidadeNC.MAIOR)
        self.plano = PlanoAcao.objects.create(
            tenant=self.tenant, nao_conformidade=self.nc,
            tipo=PlanoAcao.Tipo.CORRETIVA,
            o_que="Refazer o trecho fora de prumo", quem="Empreiteira Alfa",
            quando=date(2026, 6, 20),
        )

    def test_nc_nao_encerra_sem_eficacia_verificada(self):
        """Mesmo com o plano de ação concluído. É o ponto inteiro da fatia."""
        services.concluir_acao(plano=self.plano, por="engenharia")
        with self.assertRaises(ValidationError) as erro:
            services.encerrar_nc(nc=self.nc, por="fiscal")
        self.assertIn("eficácia", str(erro.exception))
        self.nc.refresh_from_db()
        self.assertNotEqual(self.nc.status, NaoConformidade.Status.ENCERRADA)

    def test_eficacia_negativa_devolve_a_nc_ao_tratamento(self):
        """O "não" é o resultado mais útil dos dois: o plano anterior
        comprovadamente não resolveu, e o que vem a seguir é um plano novo."""
        services.concluir_acao(plano=self.plano, por="engenharia")
        saida = services.registrar_eficacia(
            nc=self.nc, data=date(2026, 6, 25), eficaz=False,
            evidencia="A parede continua fora de prumo no mesmo trecho.",
            por="fiscal",
        )
        self.assertFalse(saida["pode_encerrar"])
        self.nc.refresh_from_db()
        self.assertEqual(self.nc.status, NaoConformidade.Status.EM_TRATAMENTO)

        with self.assertRaises(ValidationError) as erro:
            services.encerrar_nc(nc=self.nc, por="fiscal")
        self.assertIn("não** funcionou", str(erro.exception))

    def test_eficacia_positiva_permite_encerrar(self):
        services.concluir_acao(plano=self.plano, por="engenharia")
        services.registrar_eficacia(
            nc=self.nc, data=date(2026, 6, 25), eficaz=True,
            evidencia="Trecho refeito e conferido com régua: 2 mm.",
            por="fiscal",
        )
        services.encerrar_nc(nc=self.nc, por="fiscal", nota="Conferido em obra.")
        self.nc.refresh_from_db()
        self.assertEqual(self.nc.status, NaoConformidade.Status.ENCERRADA)
        self.assertTrue(self.nc.encerrada_em)

    def test_a_ultima_eficacia_e_a_que_vale(self):
        """Verificada como eficaz em março e reaberta em maio por ter voltado a
        falhar não pode encerrar pela leitura de março."""
        services.registrar_eficacia(
            nc=self.nc, data=date(2026, 6, 20), eficaz=True,
            evidencia="Parecia resolvido.", por="fiscal",
        )
        services.registrar_eficacia(
            nc=self.nc, data=date(2026, 7, 20), eficaz=False,
            evidencia="A trinca voltou no mesmo ponto.", por="fiscal",
        )
        self.assertEqual(self.nc.eficacias.count(), 2)
        with self.assertRaises(ValidationError):
            services.encerrar_nc(nc=self.nc, por="fiscal")

    def test_eficacia_sem_evidencia_e_recusada(self):
        with self.assertRaises(ValidationError) as erro:
            services.registrar_eficacia(
                nc=self.nc, data=date(2026, 6, 25), eficaz=True,
                evidencia="   ", por="fiscal",
            )
        self.assertIn("evidência", str(erro.exception).lower())

    def test_concluir_acao_NAO_encerra_a_nc(self):
        """"Ação concluída" é quem consertou dizendo que consertou."""
        services.concluir_acao(plano=self.plano, por="engenharia")
        self.nc.refresh_from_db()
        self.assertNotEqual(self.nc.status, NaoConformidade.Status.ENCERRADA)

    def test_o_estado_diz_o_que_falta_a_seguir(self):
        estado = services.estado_da_nc(self.nc)
        self.assertEqual(estado["falta"], "executar o plano de ação")

        services.concluir_acao(plano=self.plano, por="engenharia")
        self.assertEqual(
            services.estado_da_nc(self.nc)["falta"], "verificar a eficácia",
        )

        services.registrar_eficacia(
            nc=self.nc, data=date(2026, 6, 25), eficaz=True,
            evidencia="Refeito.", por="fiscal",
        )
        self.assertEqual(services.estado_da_nc(self.nc)["falta"], "encerrar")


class SeamDoLastPlannerTests(_BaseVerificacao):
    """**O que dá dente à gravidade** — NC crítica para o serviço de verdade."""

    def test_a_nc_vira_restricao_e_a_restricao_trava_o_compromisso(self):
        """O elo inteiro, ponta a ponta: sem ele o sistema diria "crítica" e a
        equipe se comprometeria com o serviço na segunda-feira seguinte."""
        nc = self._nc(atividade=self.atividade, gravidade=GravidadeNC.CRITICA)
        # Antes: a atividade entra no quadro da semana sem problema.
        services.validar_pode_comprometer(
            self.atividade, tenant_id=self.tenant.pk,
        )

        restricao_id = services.gerar_restricao_da_nc(
            nc=nc, prazo=date(2026, 6, 30), responsavel="Empreiteira Alfa",
            por="qualidade",
        )
        restricao = Restricao.objects.get(pk=restricao_id)
        self.assertEqual(restricao.atividade_id, self.atividade.pk)
        self.assertEqual(restricao.tipo, TipoRestricao.AREA)
        self.assertIn(f"NC #{nc.nc_id}", restricao.descricao)

        # Depois: o quadro da PDCA.5 recusa o compromisso.
        with self.assertRaises(ValidationError):
            services.validar_pode_comprometer(
                self.atividade, tenant_id=self.tenant.pk,
            )

    def test_nc_sem_atividade_nao_gera_restricao(self):
        """Restrição sem alvo não bloqueia nada — é a regra da PDCA.5."""
        nc = self._nc(gravidade=GravidadeNC.CRITICA)
        with self.assertRaises(ValidationError) as erro:
            services.gerar_restricao_da_nc(nc=nc, por="qualidade")
        self.assertIn("atividade", str(erro.exception))

    def test_gerar_restricao_duas_vezes_devolve_a_mesma(self):
        """O botão fica na tela e alguém clica duas vezes — a régua do
        `gerar_demanda_scm`."""
        nc = self._nc(atividade=self.atividade)
        primeira = services.gerar_restricao_da_nc(nc=nc, por="qualidade")
        segunda = services.gerar_restricao_da_nc(nc=nc, por="qualidade")
        self.assertEqual(primeira, segunda)
        self.assertEqual(Restricao.objects.count(), 1)

    def test_nc_encerrada_nao_trava_mais_nada(self):
        nc = self._nc(atividade=self.atividade)
        services.registrar_eficacia(
            nc=nc, data=date(2026, 6, 25), eficaz=True,
            evidencia="Refeito.", por="fiscal",
        )
        services.encerrar_nc(nc=nc, por="fiscal")
        with self.assertRaises(ValidationError) as erro:
            services.gerar_restricao_da_nc(nc=nc, por="qualidade")
        self.assertIn("aberta", str(erro.exception))

    def test_nao_encerra_por_cima_de_frente_interditada(self):
        """D191 — a restrição não sai em cascata, e encerrar recusa e diz qual é."""
        nc = self._nc(atividade=self.atividade, gravidade=GravidadeNC.CRITICA)
        restricao_id = services.gerar_restricao_da_nc(nc=nc, por="qualidade")
        services.registrar_eficacia(
            nc=nc, data=date(2026, 6, 25), eficaz=True,
            evidencia="Refeito.", por="fiscal",
        )
        nc.refresh_from_db()

        with self.assertRaises(ValidationError) as erro:
            services.encerrar_nc(nc=nc, por="fiscal")
        self.assertIn(str(restricao_id), str(erro.exception))
        nc.refresh_from_db()
        self.assertNotEqual(nc.status, NaoConformidade.Status.ENCERRADA)

        # Removida a trava pelo verbo de quem responde pela obra, encerra.
        services.remover_restricao(
            restricao=Restricao.objects.get(pk=restricao_id),
            por="engenharia", nota="Frente liberada.",
        )
        nc.refresh_from_db()
        services.encerrar_nc(nc=nc, por="fiscal")
        nc.refresh_from_db()
        self.assertEqual(nc.status, NaoConformidade.Status.ENCERRADA)


class LeituraDaQualidadeTests(_BaseVerificacao):
    """A fila de decisão e o "Act" — as duas leituras derivadas."""

    def test_a_fila_separa_quem_ninguem_pegou_de_quem_espera_conferencia(self):
        sem_plano = self._nc(descricao="Trinca na viga")
        com_plano = self._nc(descricao="Junta irregular")
        plano = PlanoAcao.objects.create(
            tenant=self.tenant, nao_conformidade=com_plano,
            o_que="Refazer junta", quando=date(2026, 6, 20),
        )
        com_plano.status = NaoConformidade.Status.EM_TRATAMENTO
        com_plano.save()
        services.concluir_acao(plano=plano, por="engenharia")

        fila = services.fila_da_qualidade(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(
            [linha["nc"] for linha in fila["ncs_sem_plano"]], [sem_plano.pk],
        )
        self.assertEqual(
            [linha["nc"] for linha in fila["ncs_esperando_eficacia"]],
            [com_plano.pk],
        )

    def test_a_ficha_parada_em_andamento_entra_na_fila(self):
        ficha = self._ficha()
        fila = services.fila_da_qualidade(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(
            [linha["verificacao"] for linha in fila["fichas_em_andamento"]],
            [ficha.pk],
        )

    def test_o_painel_ranqueia_o_item_que_mais_reprova(self):
        """**É a leitura que decide alguma coisa**: qual pergunta reprova mais
        aponta o processo a corrigir, não o serviço a refazer."""
        for dia in (10, 11, 12):
            ficha = self._ficha()
            self._responder(ficha, [
                (1, ResultadoItem.NAO_CONFORME, "Fora de prumo"),
                (2, ResultadoItem.CONFORME, ""),
            ])
            services.concluir_verificacao(verificacao=ficha, por="tecnico")

        painel = services.painel_de_conformidade(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(painel["fichas_concluidas"], 3)
        topo = painel["itens_que_mais_reprovam"][0]
        self.assertEqual(topo["item_modelo"], self.i1.pk)
        self.assertEqual(topo["reprovas"], 3)
        # 3 conformes e 3 não conformes = 50% no domínio qualidade.
        qualidade = next(
            linha for linha in painel["por_dominio"]
            if linha["dominio"] == DominioVerificacao.QUALIDADE
        )
        self.assertEqual(qualidade["conformidade"], Decimal("50.00"))

    def test_o_ranking_diz_a_situacao_de_HOJE_de_cada_reprova(self):
        """**O achado do dono, 16/09/2026**: "aqui fica parecendo que ainda tá
        em não conformidade, ao invés de dizer a real situação".

        O ranking conta história — é isso que aponta o processo a corrigir, e um
        ranking que descartasse o tratado zeraria toda vez que a obra
        funcionasse. O que faltava era a outra metade: daquelas reprovas,
        quantas ainda estão abertas, quantas foram resolvidas, e quantas ninguém
        sequer registrou como NC.
        """
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.NAO_CONFORME, "Fora de prumo"),
            (2, ResultadoItem.NAO_CONFORME, "Junta irregular"),
        ])
        services.concluir_verificacao(verificacao=ficha, por="tecnico")
        # Só o primeiro vira NC, e ela é tratada até o fim.
        item1 = ficha.itens.order_by("ordem").first()
        nc = NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, item_verificacao=item1,
            descricao="Fora de prumo", gravidade=GravidadeNC.MAIOR,
        )
        services.registrar_eficacia(
            nc=nc, data=date(2026, 6, 25), eficaz=True,
            evidencia="Refeito e conferido.", por="fiscal",
        )
        services.encerrar_nc(nc=nc, por="fiscal")

        painel = services.painel_de_conformidade(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        por_item = {
            l["item_modelo"]: l for l in painel["itens_que_mais_reprovam"]
        }
        resolvido = por_item[self.i1.pk]
        self.assertEqual(resolvido["reprovas"], 1)
        self.assertEqual(resolvido["encerradas"], 1)
        self.assertEqual(resolvido["em_aberto"], 0)

        #: E o que ninguém registrou aparece **como tal**, em vez de sumir entre
        #: "aberto" e "encerrado" — é um defeito que ninguém está tratando.
        esquecido = por_item[self.i2.pk]
        self.assertEqual(esquecido["reprovas"], 1)
        self.assertEqual(esquecido["sem_nc"], 1)
        self.assertEqual(esquecido["em_aberto"], 0)
        self.assertEqual(esquecido["encerradas"], 0)

        #: As três partes somam o total — a barra da tela é a reprova inteira,
        #: partida; se não somassem, ela mentiria pela largura.
        for linha in painel["itens_que_mais_reprovam"]:
            self.assertEqual(
                linha["em_aberto"] + linha["encerradas"] + linha["sem_nc"],
                linha["reprovas"],
            )

    def test_a_reprova_tratada_CONTINUA_no_ranking(self):
        """O outro lado, e é a razão de o número ser cumulativo.

        Some do ranking o que foi consertado e a pergunta que mais dá trabalho
        na obra desaparece justamente quando a equipe está funcionando — o
        ranking passaria a medir o que está atrasado, não o que é difícil.
        """
        ficha = self._ficha()
        self._responder(ficha, [
            (1, ResultadoItem.NAO_CONFORME, "Fora de prumo"),
            # A 2 é obrigatória: sem ela a ficha não fecha, e o painel só conta
            # ficha concluída.
            (2, ResultadoItem.CONFORME, ""),
        ])
        services.concluir_verificacao(verificacao=ficha, por="tecnico")
        item = ficha.itens.order_by("ordem").first()
        nc = NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, item_verificacao=item,
            descricao="Fora de prumo",
        )
        services.registrar_eficacia(
            nc=nc, data=date(2026, 6, 25), eficaz=True, evidencia="ok",
            por="fiscal",
        )
        services.encerrar_nc(nc=nc, por="fiscal")

        painel = services.painel_de_conformidade(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(len(painel["itens_que_mais_reprovam"]), 1)
        self.assertEqual(painel["itens_que_mais_reprovam"][0]["reprovas"], 1)

    def test_a_ficha_em_andamento_nao_entra_no_painel(self):
        """O painel lê **só ficha concluída**: contar inspeção pela metade faria
        a conformidade da obra oscilar ao sabor de quem está caminhando."""
        ficha = self._ficha()
        self._responder(ficha, [(1, ResultadoItem.NAO_CONFORME, "Torto")])
        painel = services.painel_de_conformidade(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(painel["fichas_concluidas"], 0)
        self.assertEqual(painel["itens_que_mais_reprovam"], [])

    def test_ncs_abertas_por_atividade_e_uma_consulta(self):
        """O que põe a qualidade na tela do Last Planner."""
        self._nc(atividade=self.atividade)
        self._nc(atividade=self.atividade)
        mapa = services.ncs_abertas_por_atividade(
            [self.atividade.pk], tenant_id=self.tenant.pk,
        )
        self.assertEqual(mapa, {self.atividade.pk: 2})


class TetosDaPdca7NoServicoTests(_BaseVerificacao):
    """Os quatro números da §5.5l, exercidos onde eles recusam."""

    def test_o_teto_de_itens_do_modelo_recusa_com_a_razao(self):
        with patch.object(
            services, "PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO", 3,
        ):
            with self.assertRaises(ValidationError) as erro:
                services.validar_teto_de_itens_do_modelo(self.modelo)
        self.assertIn("Quebre-a em duas", str(erro.exception))

    def test_o_teto_de_modelos_recusa_com_a_razao(self):
        with patch.object(services, "PDCA_TETO_MODELOS_POR_TENANT", 1):
            with self.assertRaises(ValidationError) as erro:
                services.validar_teto_de_modelos(self.tenant.pk)
        self.assertIn("comparável", str(erro.exception))

    def test_o_teto_de_ncs_conta_so_as_abertas(self):
        nc = self._nc()
        services.registrar_eficacia(
            nc=nc, data=date(2026, 6, 25), eficaz=True,
            evidencia="Refeito.", por="fiscal",
        )
        services.encerrar_nc(nc=nc, por="fiscal")
        with patch.object(services, "PDCA_TETO_NCS_ABERTAS_POR_OBRA", 1):
            # A encerrada não conta, então ainda cabe uma.
            services.validar_teto_de_ncs(
                self.obra.pk, tenant_id=self.tenant.pk,
            )
            self._nc()
            with self.assertRaises(ValidationError):
                services.validar_teto_de_ncs(
                    self.obra.pk, tenant_id=self.tenant.pk,
                )

    def test_o_teto_de_acoes_recusa_com_a_razao(self):
        nc = self._nc()
        PlanoAcao.objects.create(
            tenant=self.tenant, nao_conformidade=nc, o_que="Refazer",
        )
        with patch.object(services, "PDCA_TETO_ACOES_POR_NC", 1):
            with self.assertRaises(ValidationError) as erro:
                services.validar_teto_de_acoes(nc)
        self.assertIn("quebrado em vários", str(erro.exception))


class ApiDaPdca7Tests(APITestCase):
    """As portas novas **pelo HTTP** — a régua que o D149 deixou.

    Porta nova se exerce pela porta, e não só pelo serviço que está atrás dela:
    os 309 testes verdes da PDCA.5 não pegaram que dois `perform_create`
    sobrescritos faziam a linha nascer sem tenant, e a fatia era inutilizável em
    produção porque a RLS recusava o INSERT.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="pdca7-api", nome="Construtora Qualidade API",
        )
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra FVS", endereco="Rua API",
        )
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Padrão",
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.atividade = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Alvenaria do 4º", duracao_dias=5, profundidade=1,
        )
        self.usuario = Usuario.objects.create(username="qua7", tenant=self.tenant)
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = [
            "pdca.verificacao.view", "pdca.verificacao.modelo_edit",
            "pdca.verificacao.aplicar",
            "pdca.nc.view", "pdca.nc.abrir", "pdca.nc.tratar",
            "pdca.nc.verificar_eficacia",
        ]
        self.client.force_authenticate(user=self.usuario)

    def _modelo_pela_api(self):
        resposta = self.client.post("/api/pdca/modelos-verificacao/", {
            "codigo": "FVS-ALV", "nome": "FVS — Alvenaria",
            "dominio": DominioVerificacao.QUALIDADE,
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        modelo_id = resposta.json()["modelo_id"]
        item = self.client.post("/api/pdca/itens-modelo-verificacao/", {
            "modelo": modelo_id, "ordem": 1, "texto": "Prumo da parede",
            "criterio": "Até 3 mm em 2 m",
        }, format="json")
        self.assertEqual(item.status_code, 201, item.data)
        return modelo_id, item.json()["item_modelo_id"]

    def test_o_status_declara_as_capacidades_da_verificacao(self):
        """**A asserção do número da fatia saiu daqui, e foi de propósito.**

        Ela morou nesta classe até a PDCA.8 (20/09/2026), e a docstring antiga
        já dizia que era assim que ia ser: quem afirma o número é o teste da
        fatia **mais nova**, porque o teste de uma fatia antiga que crava
        `== "PDCA.7"` acusaria falha na entrega seguinte sem nada ter parado de
        funcionar. Agora ela vive em `ApiDaPdca8Tests`.

        O que continua aqui é o que é **desta** fatia: as capacidades da
        máquina de verificação, e o que ela declara não fazer.
        """
        corpo = self.client.get("/api/pdca/status/").json()
        recursos = corpo["recursos"]
        for capacidade in (
            "modelo_verificacao", "verificacao", "nao_conformidade",
            "plano_acao_5w2h", "verificacao_eficacia", "nc_gera_restricao",
        ):
            self.assertTrue(recursos[capacidade], capacidade)
        #: E o que a fatia **não** faz é declarado, para a tela não oferecer
        #: botão morto — a mesma honestidade de capacidade da PDCA.4.
        self.assertFalse(recursos["nc_cria_marcacao_na_prancheta"])
        self.assertFalse(recursos["modelos_de_fabrica"])
        tetos = corpo["tetos"]
        self.assertEqual(
            tetos["itens_por_modelo_verificacao"],
            PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO,
        )
        #: E **não** existe meta de conformidade entre eles: resultado medido
        #: não é teto de plano (§5.6).
        self.assertFalse([
            k for k in tetos if "conformidade" in k or "meta" in k
        ])

    def test_o_modelo_criado_pela_api_nasce_com_tenant(self):
        """O defeito que a PDCA.5 pagou caro — sem isto a RLS recusa o INSERT."""
        modelo_id, item_id = self._modelo_pela_api()
        modelo = ModeloVerificacao.objects.get(pk=modelo_id)
        self.assertEqual(modelo.tenant_id, self.tenant.pk)
        self.assertTrue(modelo.criado_por)
        self.assertEqual(
            ItemModeloVerificacao.objects.get(pk=item_id).tenant_id,
            self.tenant.pk,
        )

    def test_a_ficha_aplicada_pela_api_nasce_com_tenant_e_com_itens(self):
        modelo_id, _ = self._modelo_pela_api()
        resposta = self.client.post("/api/pdca/verificacoes/aplicar/", {
            "modelo": modelo_id, "obra": self.obra.pk, "data": "2026-06-10",
            "atividade": self.atividade.pk, "inspetor": "Téc. Ana",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)

        ficha = Verificacao.objects.get(pk=resposta.json()["verificacao_id"])
        self.assertEqual(ficha.tenant_id, self.tenant.pk)
        self.assertEqual(ficha.itens.count(), 1)
        self.assertEqual(ficha.itens.first().tenant_id, self.tenant.pk)
        # E o resultado vem derivado junto, sem apuração ainda.
        self.assertIsNone(resposta.json()["resultado"]["conformidade"])

    def test_responder_pela_api_e_o_patch_do_item_e_ele_devolve_o_novo_estado(self):
        """A física do instrumento: uma pergunta por vez. E a resposta do
        `PATCH` tem de já vir respondida — senão a tela do campo mostra a
        pergunta ainda pendente logo depois de respondê-la."""
        modelo_id, _ = self._modelo_pela_api()
        ficha_id = self.client.post("/api/pdca/verificacoes/aplicar/", {
            "modelo": modelo_id, "obra": self.obra.pk, "data": "2026-06-10",
        }, format="json").json()["verificacao_id"]
        item = Verificacao.objects.get(pk=ficha_id).itens.first()

        resposta = self.client.patch(
            f"/api/pdca/itens-verificacao/{item.pk}/",
            {"resultado": "nao_conforme", "observacao": "Desvio de 12 mm",
             "gravidade": "maior"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.json()["resultado"], "nao_conforme")
        self.assertTrue(resposta.json()["respondido_em"])
        #: O peso deste defeito volta resolvido — a tela do campo mostra a
        #: pílula sem uma segunda chamada, e a conclusão lista o que vai abrir.
        self.assertEqual(resposta.json()["gravidade"], "maior")
        self.assertTrue(resposta.json()["gravidade_rotulo"])

    def test_o_patch_recusa_reprovar_sem_dizer_quanto_pesa(self):
        """**A pergunta é do item, não da ficha** (§11.15), e a porta cobra.

        Antes de 16/09/2026 este `PATCH` passava e a gravidade era escolhida
        uma vez na conclusão, para todos os reprovados de uma vez.
        """
        modelo_id, _ = self._modelo_pela_api()
        ficha_id = self.client.post("/api/pdca/verificacoes/aplicar/", {
            "modelo": modelo_id, "obra": self.obra.pk, "data": "2026-06-10",
        }, format="json").json()["verificacao_id"]
        item = Verificacao.objects.get(pk=ficha_id).itens.first()

        resposta = self.client.patch(
            f"/api/pdca/itens-verificacao/{item.pk}/",
            {"resultado": "nao_conforme", "observacao": "Torto"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertIn("pesa", str(resposta.data))

    def test_o_patch_recusa_desvio_sem_observacao_pela_porta(self):
        modelo_id, _ = self._modelo_pela_api()
        ficha_id = self.client.post("/api/pdca/verificacoes/aplicar/", {
            "modelo": modelo_id, "obra": self.obra.pk, "data": "2026-06-10",
        }, format="json").json()["verificacao_id"]
        item = Verificacao.objects.get(pk=ficha_id).itens.first()

        resposta = self.client.patch(
            f"/api/pdca/itens-verificacao/{item.pk}/",
            {"resultado": "nao_conforme", "observacao": ""}, format="json",
        )
        self.assertEqual(resposta.status_code, 400, resposta.data)

    def test_a_nc_criada_pela_api_nasce_com_tenant(self):
        resposta = self.client.post("/api/pdca/ncs/", {
            "obra": self.obra.pk, "atividade": self.atividade.pk,
            "gravidade": "maior", "descricao": "Parede fora de prumo",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        nc = NaoConformidade.objects.get(pk=resposta.json()["nc_id"])
        self.assertEqual(nc.tenant_id, self.tenant.pk)
        self.assertTrue(nc.aberta_por)

    def test_o_plano_de_acao_pela_api_poe_a_nc_em_tratamento(self):
        nc_id = self.client.post("/api/pdca/ncs/", {
            "obra": self.obra.pk, "descricao": "Trinca",
        }, format="json").json()["nc_id"]
        resposta = self.client.post("/api/pdca/planos-acao/", {
            "nao_conformidade": nc_id, "tipo": "corretiva",
            "o_que": "Refazer o trecho", "quem": "Alfa", "quando": "2026-06-30",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        plano = PlanoAcao.objects.get(pk=resposta.json()["plano_id"])
        self.assertEqual(plano.tenant_id, self.tenant.pk)
        self.assertEqual(
            NaoConformidade.objects.get(pk=nc_id).status,
            NaoConformidade.Status.EM_TRATAMENTO,
        )

    def test_o_laco_inteiro_pela_porta(self):
        """Abrir → tratar → concluir → verificar → encerrar, tudo por HTTP."""
        nc_id = self.client.post("/api/pdca/ncs/", {
            "obra": self.obra.pk, "descricao": "Trinca na viga",
        }, format="json").json()["nc_id"]
        plano_id = self.client.post("/api/pdca/planos-acao/", {
            "nao_conformidade": nc_id, "o_que": "Grautear", "quando": "2026-06-30",
        }, format="json").json()["plano_id"]
        self.assertEqual(
            self.client.post(
                f"/api/pdca/planos-acao/{plano_id}/concluir/", {}, format="json",
            ).status_code, 200,
        )

        # Sem eficácia, encerrar é recusado — e a recusa é 400, não 500.
        recusa = self.client.post(
            f"/api/pdca/ncs/{nc_id}/encerrar/", {}, format="json",
        )
        self.assertEqual(recusa.status_code, 400, recusa.data)

        eficacia = self.client.post(f"/api/pdca/ncs/{nc_id}/eficacia/", {
            "data": "2026-07-05", "eficaz": True,
            "evidencia": "Trecho grauteado e conferido.",
        }, format="json")
        self.assertEqual(eficacia.status_code, 201, eficacia.data)
        self.assertEqual(
            VerificacaoEficacia.objects.get(
                pk=eficacia.json()["eficacia"],
            ).tenant_id,
            self.tenant.pk,
        )

        fechou = self.client.post(
            f"/api/pdca/ncs/{nc_id}/encerrar/", {"nota": "ok"}, format="json",
        )
        self.assertEqual(fechou.status_code, 200, fechou.data)
        self.assertEqual(
            NaoConformidade.objects.get(pk=nc_id).status,
            NaoConformidade.Status.ENCERRADA,
        )

    def test_gerar_restricao_exige_a_permissao_de_travar_a_obra(self):
        """A porta lateral que a segregação fecha: `pdca.nc.tratar` sozinho não
        pode travar o quadro da semana."""
        nc_id = self.client.post("/api/pdca/ncs/", {
            "obra": self.obra.pk, "atividade": self.atividade.pk,
            "gravidade": "critica", "descricao": "Armadura exposta",
        }, format="json").json()["nc_id"]

        recusa = self.client.post(
            f"/api/pdca/ncs/{nc_id}/gerar-restricao/", {}, format="json",
        )
        self.assertEqual(recusa.status_code, 403, recusa.data)

        self.usuario.iam_permissions = [
            *self.usuario.iam_permissions, "pdca.restricao.edit",
        ]
        aceita = self.client.post(
            f"/api/pdca/ncs/{nc_id}/gerar-restricao/", {}, format="json",
        )
        self.assertEqual(aceita.status_code, 201, aceita.data)
        self.assertEqual(
            Restricao.objects.get(pk=aceita.json()["restricao"]).tenant_id,
            self.tenant.pk,
        )

    def test_quem_so_trata_nao_verifica_a_propria_eficacia(self):
        """**A segregação inteira da fatia**, exercida pela porta."""
        self.usuario.iam_permissions = [
            "pdca.nc.view", "pdca.nc.abrir", "pdca.nc.tratar",
        ]
        nc_id = self.client.post("/api/pdca/ncs/", {
            "obra": self.obra.pk, "descricao": "Trinca",
        }, format="json").json()["nc_id"]

        recusa = self.client.post(f"/api/pdca/ncs/{nc_id}/eficacia/", {
            "data": "2026-07-05", "eficaz": True, "evidencia": "Refeito.",
        }, format="json")
        self.assertEqual(recusa.status_code, 403, recusa.data)
        self.assertEqual(
            self.client.post(
                f"/api/pdca/ncs/{nc_id}/encerrar/", {}, format="json",
            ).status_code, 403,
        )

    def test_quem_aplica_ficha_nao_edita_o_metodo_da_empresa(self):
        """Um `edit` único daria ao campo o poder de afrouxar o critério da FVS
        no momento exato em que ela reprovasse."""
        modelo_id, _ = self._modelo_pela_api()
        self.usuario.iam_permissions = [
            "pdca.verificacao.view", "pdca.verificacao.aplicar",
        ]
        recusa = self.client.patch(
            f"/api/pdca/modelos-verificacao/{modelo_id}/",
            {"nome": "Outro nome"}, format="json",
        )
        self.assertEqual(recusa.status_code, 403, recusa.data)

    def test_o_modelo_ja_aplicado_nao_se_apaga(self):
        modelo_id, _ = self._modelo_pela_api()
        self.client.post("/api/pdca/verificacoes/aplicar/", {
            "modelo": modelo_id, "obra": self.obra.pk, "data": "2026-06-10",
        }, format="json")
        recusa = self.client.delete(
            f"/api/pdca/modelos-verificacao/{modelo_id}/",
        )
        self.assertEqual(recusa.status_code, 400, recusa.data)

    def test_a_fila_e_o_painel_respondem_pela_obra(self):
        self.client.post("/api/pdca/ncs/", {
            "obra": self.obra.pk, "descricao": "Trinca",
        }, format="json")
        fila = self.client.get(f"/api/pdca/ncs/fila/?obra={self.obra.pk}")
        self.assertEqual(fila.status_code, 200, fila.data)
        self.assertEqual(len(fila.json()["ncs_sem_plano"]), 1)

        painel = self.client.get(f"/api/pdca/ncs/painel/?obra={self.obra.pk}")
        self.assertEqual(painel.status_code, 200, painel.data)
        self.assertEqual(painel.json()["ncs_abertas"], 1)

    def test_a_obra_de_outra_empresa_e_recusada(self):
        """A fronteira do tenant, e **quem a fecha primeiro é a RLS**.

        O `_minha_obra` tem duas redes: o banco e a conferência explícita. Sob
        RLS ligada quem responde é a primeira, e por isso a mensagem é *"não
        encontrada"* e não *"não é desta empresa"* — a linha alheia não existe
        para esta conexão. A conferência do `_minha_obra` continua valendo para
        o caminho em que a RLS esteja desligada (SQLite de dev, comando de
        bancada), que é a razão de ela existir.

        O que este teste prende é o que importa: a fila da qualidade de uma obra
        alheia **não responde**, e recusa com 400 em vez de vazar ou dar 500.
        """
        outro = Tenant.objects.create(slug="pdca7-outro", nome="Outra")
        alheia = Obra.objects.create(
            tenant=outro, nome_obra="Obra alheia", endereco="Rua X",
        )
        resposta = self.client.get(f"/api/pdca/ncs/fila/?obra={alheia.pk}")
        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertIn("obra", str(resposta.data).lower())
        self.assertNotIn("Obra alheia", str(resposta.data))


# ---------------------------------------------------------------------------
# PDCA.8 — SSMA: o diálogo de segurança e a ocorrência
# ---------------------------------------------------------------------------
# O que estes testes protegem, em uma frase cada:
#   · a lista de presença fecha quando o DDS encerra, e um DDS vazio não encerra;
#   · registrar é barato e classificar é que pesa — os dois verbos são separados,
#     e a classificação nasce pendente;
#   · a CAT é devida mesmo sem afastamento, o prazo é o 1º dia útil, e o sistema
#     conta a verdade quando ela sai fora do prazo em vez de recusá-la;
#   · o acidente grave interdita a frente pela mesma corrente da NC crítica;
#   · a ocorrência não encerra por cima de uma frente ainda interditada;
#   · as taxas voltam nulas com motivo — nunca zero;
#   · o EPI é lido do SIL e a indisponibilidade é declarada.


class _BaseSsma(TestCase):
    """Fixture comum: uma obra com plano vigente, uma atividade e um local."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-ssma", nome="Construtora Segura")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Seguro", endereco="Rua 9",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, obra=cls.obra, nome="Padrão",
        )
        cls.cronograma = Cronograma.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=cls.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        cls.atividade = Atividade.objects.create(
            tenant=cls.tenant, cronograma=cls.cronograma, codigo="1",
            nome="Estrutura do 8º", duracao_dias=10, profundidade=1,
        )
        cls.local = LocalObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, codigo="T1-8",
            nome="Torre 1 · 8º pavimento", nivel=NivelLocal.PAVIMENTO,
        )

    # -- helpers ------------------------------------------------------------
    def _dds(self, **extra):
        return services.abrir_dds(
            obra=self.obra, data=date(2026, 6, 10), tema="Trabalho em altura",
            tenant_id=self.tenant.pk, por="encarregado", **extra,
        )

    def _ocorrencia(self, **extra):
        """**Quase-acidente por padrão**, e é de propósito.

        O caso comum do módulo é o registro que não tem vítima — pôr o acidente
        no default faria metade destes testes exercitarem o caminho da CAT sem
        estarem falando dela.
        """
        campos = {
            "tipo": TipoOcorrencia.QUASE_ACIDENTE,
            "descricao": "Tábua caiu do 8º, sem atingir ninguém.",
            "ocorrido_em": timezone.now() - timedelta(days=1),
        }
        campos.update(extra)
        return services.registrar_ocorrencia(
            obra=self.obra, tenant_id=self.tenant.pk, por="encarregado", **campos,
        )


class DialogoDeSegurancaTests(_BaseSsma):
    """O DDS — a roda, a lista e o que fecha as duas."""

    def test_o_dds_nasce_em_rascunho_e_sem_ninguem(self):
        dds = self._dds()
        self.assertEqual(dds.status, DialogoSeguranca.Status.RASCUNHO)
        self.assertEqual(dds.participantes.count(), 0)
        self.assertTrue(dds.esta_aberto)

    def test_dds_sem_tema_nao_abre(self):
        """'DDS realizado' não é tema, e é o que a fiscalização vai ler."""
        with self.assertRaises(ValidationError):
            services.abrir_dds(
                obra=self.obra, data=date(2026, 6, 10), tema="   ",
                tenant_id=self.tenant.pk,
            )

    def test_a_presenca_aceita_funcionario_e_nome_solto(self):
        """Metade do canteiro é de terceiro e não tem cadastro no RH."""
        dds = self._dds()
        resultado = services.registrar_presenca(dds=dds, participantes=[
            {"nome": "José da Silva", "assinou": True},
            {"nome": "Maria Souza"},
        ])
        self.assertEqual(resultado["registrados"], 2)
        self.assertEqual(dds.participantes.count(), 2)

    def test_participante_sem_funcionario_e_sem_nome_e_recusado(self):
        dds = self._dds()
        with self.assertRaises(ValidationError):
            services.registrar_presenca(dds=dds, participantes=[{"nome": "  "}])

    def test_dds_sem_presente_nao_encerra(self):
        """A lista é a única parte do DDS que prova alguma coisa."""
        dds = self._dds()
        services.registrar_presenca(dds=dds, participantes=[
            {"nome": "José da Silva", "presente": False},
        ])
        with self.assertRaises(ValidationError):
            services.encerrar_dds(dds=dds, por="tst", publicar_no_diario=False)

    def test_encerrado_nao_recebe_nome_novo(self):
        """A trava que faz a lista ser prova de quem estava lá."""
        dds = self._dds()
        services.registrar_presenca(dds=dds, participantes=[{"nome": "José"}])
        services.encerrar_dds(dds=dds, por="tst", publicar_no_diario=False)
        dds.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.registrar_presenca(dds=dds, participantes=[{"nome": "Ana"}])

    def test_o_encerramento_escreve_no_diario_da_obra(self):
        """PDCA §7 — 'não substitui o Diário: escreve e lê nele'."""
        from modulodiario.models import DiarioObra, EntradaDiario

        dds = self._dds()
        services.registrar_presenca(dds=dds, participantes=[
            {"nome": "José"}, {"nome": "Maria"},
        ])
        resultado = services.encerrar_dds(dds=dds, por="tst")

        self.assertTrue(resultado["publicado_no_diario"])
        diario = DiarioObra.objects.get(obra=self.obra, data=dds.data)
        entrada = EntradaDiario.objects.get(diario_obra=diario)
        self.assertIn("Trabalho em altura", entrada.texto)
        self.assertIn("Participantes presentes: 2", entrada.texto)

    def test_o_teto_de_participantes_vem_do_payment(self):
        from payment.planos import PDCA_TETO_PARTICIPANTES_POR_DDS

        dds = self._dds()
        muitos = [
            {"nome": f"Trabalhador {i}"}
            for i in range(PDCA_TETO_PARTICIPANTES_POR_DDS + 1)
        ]
        with self.assertRaises(ValidationError):
            services.registrar_presenca(dds=dds, participantes=muitos)


class RegistroDaOcorrenciaTests(_BaseSsma):
    """Registrar é barato — e cada ausência de trava aqui é uma decisão."""

    def test_a_ocorrencia_nasce_sem_classificacao(self):
        """O nulo que diz 'ainda não se julgou' é informação; o zero é mentira."""
        ocorrencia = self._ocorrencia()
        self.assertEqual(
            ocorrencia.classificacao, ClassificacaoOcorrencia.PENDENTE,
        )
        self.assertIsNone(ocorrencia.dias_perdidos)
        self.assertTrue(ocorrencia.esta_aberta)

    def test_ocorrencia_no_futuro_e_recusada(self):
        with self.assertRaises(ValidationError):
            self._ocorrencia(ocorrido_em=timezone.now() + timedelta(days=1))

    def test_ocorrencia_sem_descricao_e_recusada(self):
        with self.assertRaises(ValidationError):
            self._ocorrencia(descricao="   ")

    def test_NAO_existe_teto_de_ocorrencias_abertas(self):
        """**A ausência mais importante da fatia.**

        Um teto aqui recusaria o registro de um acidente porque a obra já tem
        registros demais — e o incentivo que ele criaria (não registrar para não
        estourar) é o oposto exato do que a fatia existe para produzir.
        """
        for i in range(40):
            self._ocorrencia(descricao=f"Quase-acidente {i}")
        self.assertEqual(
            Ocorrencia.objects.filter(tenant=self.tenant, obra=self.obra).count(),
            40,
        )


class ClassificacaoDaOcorrenciaTests(_BaseSsma):
    """A segregação da fatia: quem é medido não classifica a própria medida."""

    def test_classificar_carimba_quem_e_quando(self):
        ocorrencia = self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        services.classificar_ocorrencia(
            ocorrencia=ocorrencia,
            classificacao=ClassificacaoOcorrencia.COM_AFASTAMENTO,
            dias_perdidos=9, por="tst",
        )
        ocorrencia.refresh_from_db()
        self.assertEqual(ocorrencia.dias_perdidos, 9)
        self.assertEqual(ocorrencia.classificada_por, "tst")
        self.assertIsNotNone(ocorrencia.classificada_em)

    def test_afastamento_sem_dias_e_recusado(self):
        """É desse número que a taxa de gravidade nasce."""
        ocorrencia = self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        with self.assertRaises(ValidationError):
            services.classificar_ocorrencia(
                ocorrencia=ocorrencia,
                classificacao=ClassificacaoOcorrencia.COM_AFASTAMENTO,
            )

    def test_obito_cobra_dias_debitados_e_nao_perdidos(self):
        """A NBR 14280 fixa 6.000 dias de **débito** para o óbito."""
        ocorrencia = self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        with self.assertRaises(ValidationError):
            services.classificar_ocorrencia(
                ocorrencia=ocorrencia,
                classificacao=ClassificacaoOcorrencia.OBITO, dias_perdidos=1,
            )
        services.classificar_ocorrencia(
            ocorrencia=ocorrencia, classificacao=ClassificacaoOcorrencia.OBITO,
            dias_debitados=6000, por="tst",
        )
        ocorrencia.refresh_from_db()
        self.assertEqual(ocorrencia.dias_debitados, 6000)

    def test_quase_acidente_nao_tem_afastamento(self):
        """Se houve alguém ferido, o **tipo** é que está errado."""
        ocorrencia = self._ocorrencia()
        with self.assertRaises(ValidationError):
            services.classificar_ocorrencia(
                ocorrencia=ocorrencia,
                classificacao=ClassificacaoOcorrencia.COM_AFASTAMENTO,
                dias_perdidos=3,
            )


class ComunicacaoDeAcidenteTests(_BaseSsma):
    """A CAT — Lei 8.213/91 art. 22 e a Portaria SEPRT/ME 4.334/2021."""

    def test_quase_acidente_e_incidente_nao_geram_cat(self):
        self.assertFalse(self._ocorrencia().exige_cat)
        self.assertFalse(
            self._ocorrencia(tipo=TipoOcorrencia.INCIDENTE).exige_cat,
        )

    def test_a_cat_e_devida_mesmo_SEM_afastamento(self):
        """O erro mais comum do mercado — comunicar só o que afasta."""
        ocorrencia = self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        services.classificar_ocorrencia(
            ocorrencia=ocorrencia,
            classificacao=ClassificacaoOcorrencia.SEM_AFASTAMENTO, por="tst",
        )
        ocorrencia.refresh_from_db()
        self.assertTrue(ocorrencia.exige_cat)
        self.assertTrue(services.prazo_da_cat(ocorrencia)["exige"])

    def test_o_prazo_e_o_proximo_dia_util(self):
        """Sexta-feira vence na segunda, não no sábado."""
        sexta = timezone.make_aware(datetime(2026, 6, 12, 14, 0))
        ocorrencia = self._ocorrencia(
            tipo=TipoOcorrencia.ACIDENTE_TIPICO, ocorrido_em=sexta,
        )
        prazo = services.prazo_da_cat(ocorrencia)
        self.assertEqual(prazo["vence_em"], date(2026, 6, 15))
        self.assertEqual(prazo["base_legal"], "Lei 8.213/91, art. 22")

    def test_o_obito_vence_no_mesmo_dia(self):
        """'De imediato', diz a lei — não no dia seguinte."""
        ocorrencia = self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        services.classificar_ocorrencia(
            ocorrencia=ocorrencia, classificacao=ClassificacaoOcorrencia.OBITO,
            dias_debitados=6000, por="tst",
        )
        ocorrencia.refresh_from_db()
        prazo = services.prazo_da_cat(ocorrencia)
        self.assertTrue(prazo["imediata"])
        self.assertEqual(
            prazo["vence_em"], timezone.localtime(ocorrencia.ocorrido_em).date(),
        )

    def test_o_prazo_declara_que_a_base_de_feriados_pode_estar_vazia(self):
        """D179 — sem a base sincronizada o desvio é só de fim de semana."""
        ocorrencia = self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        self.assertIn("feriados_carregados", services.prazo_da_cat(ocorrencia))

    def test_a_cat_fora_do_prazo_e_registrada_e_contada_como_atrasada(self):
        """**Recusá-la apagaria o registro de que ela foi feita.**"""
        ocorrencia = self._ocorrencia(
            tipo=TipoOcorrencia.ACIDENTE_TIPICO,
            ocorrido_em=timezone.now() - timedelta(days=20),
        )
        resultado = services.registrar_cat(
            ocorrencia=ocorrencia, tipo=TipoCAT.INICIAL,
            emitida_em=timezone.localdate(), protocolo="123456", por="rh",
        )
        self.assertFalse(resultado["dentro_do_prazo"])
        ocorrencia.refresh_from_db()
        self.assertEqual(ocorrencia.cat_protocolo, "123456")

    def test_cat_em_ocorrencia_sem_vitima_e_recusada(self):
        ocorrencia = self._ocorrencia()
        with self.assertRaises(ValidationError):
            services.registrar_cat(
                ocorrencia=ocorrencia, tipo=TipoCAT.INICIAL,
                emitida_em=timezone.localdate(),
            )


class SeamsDaSsmaTests(_BaseSsma):
    """O dente e o laço — a corrente que a PDCA.5 e a PDCA.7 já montaram."""

    def test_a_ocorrencia_grave_interdita_a_frente(self):
        ocorrencia = self._ocorrencia(
            tipo=TipoOcorrencia.ACIDENTE_TIPICO, atividade=self.atividade,
            local=self.local,
        )
        restricao = services.gerar_restricao_da_ocorrencia(
            ocorrencia=ocorrencia, por="tst",
        )
        self.assertEqual(restricao.tipo, TipoRestricao.AREA)
        self.assertEqual(restricao.status, Restricao.Status.ABERTA)
        # E a atividade sai do quadro da semana pela trava que já existia.
        with self.assertRaises(ValidationError):
            services.validar_pode_comprometer(
                self.atividade, tenant_id=self.tenant.pk,
            )

    def test_gerar_restricao_e_idempotente(self):
        ocorrencia = self._ocorrencia(
            tipo=TipoOcorrencia.ACIDENTE_TIPICO, atividade=self.atividade,
        )
        primeira = services.gerar_restricao_da_ocorrencia(ocorrencia=ocorrencia)
        segunda = services.gerar_restricao_da_ocorrencia(ocorrencia=ocorrencia)
        self.assertEqual(primeira.pk, segunda.pk)

    def test_ocorrencia_sem_atividade_nao_interdita_nada(self):
        ocorrencia = self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        with self.assertRaises(ValidationError):
            services.gerar_restricao_da_ocorrencia(ocorrencia=ocorrencia)

    def test_a_investigacao_reusa_a_maquina_da_pdca7(self):
        """A ocorrência é o fato; a NC é o tratamento dele."""
        ocorrencia = self._ocorrencia(
            tipo=TipoOcorrencia.ACIDENTE_TIPICO, atividade=self.atividade,
        )
        nc = services.abrir_nc_da_ocorrencia(ocorrencia=ocorrencia, por="tst")
        self.assertEqual(nc.gravidade, GravidadeNC.CRITICA)
        ocorrencia.refresh_from_db()
        self.assertEqual(ocorrencia.status, Ocorrencia.Status.EM_INVESTIGACAO)
        # Idempotente, como o irmão da restrição.
        self.assertEqual(
            services.abrir_nc_da_ocorrencia(ocorrencia=ocorrencia).pk, nc.pk,
        )

    def test_ocorrencias_abertas_por_atividade_numa_consulta(self):
        self._ocorrencia(atividade=self.atividade)
        self._ocorrencia(atividade=self.atividade)
        mapa = services.ocorrencias_abertas_por_atividade(
            [self.atividade.pk], tenant_id=self.tenant.pk,
        )
        self.assertEqual(mapa, {self.atividade.pk: 2})


class EncerramentoDaOcorrenciaTests(_BaseSsma):
    """As duas recusas — e as duas existem por um defeito medido no irmão."""

    def test_nao_encerra_sem_classificar(self):
        """Sem classificação ela some da fila **e** do indicador."""
        ocorrencia = self._ocorrencia()
        with self.assertRaises(ValidationError):
            services.encerrar_ocorrencia(ocorrencia=ocorrencia, por="tst")

    def test_nao_encerra_por_cima_de_frente_interditada(self):
        """**A restrição não sai em cascata, e isso é deliberado.**

        `encerrar_nc` não remove a restrição que a NC abriu, e ninguém o faz em
        cascata — copiar isso aqui deixaria a frente travada depois de a
        ocorrência ser dada por resolvida. Remover a trava é ato de quem
        responde pela obra, não efeito colateral de um encerramento.
        """
        ocorrencia = self._ocorrencia(
            tipo=TipoOcorrencia.ACIDENTE_TIPICO, atividade=self.atividade,
        )
        services.classificar_ocorrencia(
            ocorrencia=ocorrencia,
            classificacao=ClassificacaoOcorrencia.SEM_AFASTAMENTO, por="tst",
        )
        ocorrencia.refresh_from_db()
        restricao = services.gerar_restricao_da_ocorrencia(ocorrencia=ocorrencia)

        with self.assertRaises(ValidationError) as erro:
            services.encerrar_ocorrencia(ocorrencia=ocorrencia, por="tst")
        self.assertIn(str(restricao.pk), str(erro.exception))

        # Removida a trava pelo verbo de quem responde pela obra, encerra.
        services.remover_restricao(
            restricao=restricao, por="engenharia", nota="Frente liberada.",
        )
        ocorrencia.refresh_from_db()
        services.encerrar_ocorrencia(ocorrencia=ocorrencia, por="tst")
        ocorrencia.refresh_from_db()
        self.assertEqual(ocorrencia.status, Ocorrencia.Status.ENCERRADA)


class IndicadoresDeSsmaTests(_BaseSsma):
    """Os números — e os dois que o sistema declara não saber."""

    def test_as_taxas_voltam_nulas_com_motivo(self):
        """**Nunca zero.** 'Taxa de frequência 0,00' é a mentira mais cara.

        A frase diz o que falta (homem-hora) e cita a norma que o técnico de
        segurança conhece — e **não** cita o número da fatia. Esta asserção
        cobrava `PDCA.9` dentro de uma string de tela até 20/09/2026, que é
        literalmente o exemplo do que a §9 das convenções de frontend proíbe:
        número de fatia responde à pergunta de quem escreveu o software, não à
        de quem está olhando o painel.
        """
        self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        painel = services.indicadores_de_ssma(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertIsNone(painel["taxa_frequencia"])
        self.assertIsNone(painel["taxa_gravidade"])
        motivo = painel["taxas_indisponiveis_porque"]
        self.assertIn("homem-hora", motivo)
        self.assertIn("NBR 14280", motivo)
        self.assertNotIn("PDCA.", motivo)

    def test_a_piramide_conta_aviso_por_acidente(self):
        for _ in range(6):
            self._ocorrencia()
        self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        painel = services.indicadores_de_ssma(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(painel["quase_acidentes"], 6)
        self.assertEqual(painel["acidentes"], 1)
        self.assertEqual(painel["avisos_por_acidente"], 6.0)

    def test_sem_acidente_a_razao_da_piramide_e_nula_e_nao_infinita(self):
        self._ocorrencia()
        painel = services.indicadores_de_ssma(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertIsNone(painel["avisos_por_acidente"])

    def test_o_indicador_proativo_conta_dds_encerrado(self):
        """Mede o que a obra faz **antes** — e só o encerrado conta."""
        aberto = self._dds()
        fechado = self._dds()
        services.registrar_presenca(dds=fechado, participantes=[{"nome": "José"}])
        services.encerrar_dds(dds=fechado, por="tst", publicar_no_diario=False)
        painel = services.indicadores_de_ssma(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(painel["dds_encerrados"], 1)
        self.assertTrue(aberto.esta_aberto)

    def test_a_fila_poe_a_cat_na_frente(self):
        """A única parada com prazo em lei e multa."""
        self._ocorrencia(tipo=TipoOcorrencia.ACIDENTE_TIPICO)
        fila = services.fila_da_ssma(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(len(fila["cat_por_comunicar"]), 1)
        self.assertEqual(len(fila["sem_classificacao"]), 1)
        self.assertEqual(len(fila["sem_tratamento"]), 1)
        self.assertFalse(fila["truncada"])


class EpiLidoDoSilTests(_BaseSsma):
    """O seam do EPI — a PDCA.8 lê, não duplica *(decisão do dono, 20/09/2026)*."""

    def test_a_pdca8_nao_tem_tabela_de_epi(self):
        """A prova da decisão: o modelo mora no SIL e em nenhum outro lugar."""
        from django.apps import apps

        nomes = {m.__name__ for m in apps.get_app_config("modulopdca").get_models()}
        self.assertNotIn("EntregaEPI", nomes)

    def test_le_o_epi_vencido_da_obra_pelo_modulo_dono(self):
        from catalogo.models import Item
        from modulosil.models import EntregaEPI

        capacete = Item.objects.create(
            tenant=self.tenant, codigo_interno="EPI-CAP",
            descricao="Capacete classe B", tipo=Item.Tipo.EPI, unidade="un",
        )
        EntregaEPI.objects.create(
            tenant=self.tenant, item=capacete, colaborador_nome="José da Silva",
            obra=self.obra, ca_numero="34521",
            ca_validade=timezone.localdate() - timedelta(days=5),
        )
        leitura = services.epi_vencido_da_obra(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertTrue(leitura["disponivel"])
        self.assertEqual(leitura["total"], 1)
        self.assertEqual(leitura["vencidos"][0]["colaborador"], "José da Silva")
        # **O grão é declarado**: frente exige `Efetivo`, que é da PDCA.9.
        self.assertEqual(leitura["grao"], "obra")


class ApiDaPdca8Tests(APITestCase):
    """As portas da SSMA **pelo HTTP** — a régua que o D149 deixou.

    Porta nova se exerce pela porta, e não só pelo serviço que está atrás dela:
    foi assim que se descobriu que dois `perform_create` sobrescritos faziam a
    linha nascer sem tenant, e a fatia era inutilizável em produção porque a RLS
    recusava o INSERT.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="pdca8-api", nome="Construtora Segura API",
        )
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra SSMA", endereco="Rua API",
        )
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Padrão",
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
            status=Cronograma.Status.VIGENTE,
        )
        self.atividade = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Estrutura do 8º", duracao_dias=10, profundidade=1,
        )
        self.usuario = Usuario.objects.create(username="tst8", tenant=self.tenant)
        self.usuario.iam_modules = ["pdca"]
        #: O **técnico de segurança** de fábrica: registra e classifica, e não
        #: emite CAT nem abre o bloco clínico.
        self.usuario.iam_permissions = [
            "pdca.dds.view", "pdca.dds.registrar",
            "pdca.ocorrencia.view", "pdca.ocorrencia.registrar",
            "pdca.ocorrencia.classificar",
            "pdca.restricao.edit", "pdca.nc.abrir",
        ]
        self.client.force_authenticate(user=self.usuario)

    # -- o número da fatia --------------------------------------------------

    def test_o_status_declara_a_fatia_corrente_e_o_que_ela_NAO_faz(self):
        """**O número da fatia se afirma aqui, e só aqui.**

        Veio de `ApiDaPdca7Tests` com a PDCA.8, pela régua que a docstring de lá
        escreveu: quem crava o número é o teste da fatia mais nova. Quando a
        PDCA.9 sair, é esta asserção que se move.
        """
        corpo = self.client.get("/api/pdca/status/").json()
        self.assertEqual(corpo["fatia"], "PDCA.8")
        recursos = corpo["recursos"]
        for capacidade in (
            "dialogo_seguranca", "ocorrencia", "classificacao_segregada",
            "cat_prazo_e_protocolo", "ocorrencia_interdita_frente",
            "ocorrencia_gera_investigacao",
        ):
            self.assertTrue(recursos[capacidade], capacidade)
        #: E o que ela **não** faz, para a tela não oferecer botão morto.
        self.assertFalse(recursos["taxa_frequencia"])
        self.assertFalse(recursos["taxa_gravidade"])
        self.assertFalse(recursos["epi_proprio"])
        self.assertFalse(recursos["transmite_esocial"])

    def test_os_tetos_da_fatia_saem_do_payment_e_o_ausente_continua_ausente(self):
        from payment.planos import (
            PDCA_TETO_ANEXOS_POR_OCORRENCIA, PDCA_TETO_PARTICIPANTES_POR_DDS,
        )

        tetos = self.client.get("/api/pdca/status/").json()["tetos"]
        self.assertEqual(
            tetos["participantes_por_dds"], PDCA_TETO_PARTICIPANTES_POR_DDS,
        )
        self.assertEqual(
            tetos["anexos_por_ocorrencia"], PDCA_TETO_ANEXOS_POR_OCORRENCIA,
        )
        #: **A ausência é o contrato.** Um teto de ocorrências abertas recusaria
        #: o registro de um acidente, e não existe nenhum.
        self.assertNotIn("ocorrencias_abertas_por_obra", tetos)
        #: E não há meta de segurança: resultado medido não é teto (§5.6).
        self.assertFalse([
            k for k in tetos
            if "frequencia" in k or "gravidade" in k or "meta" in k
        ])

    # -- o DDS pela porta ---------------------------------------------------

    def test_o_dds_nasce_com_tenant_pela_porta(self):
        """A asserção que o D149 comprou: a linha nasce escopada."""
        resposta = self.client.post("/api/pdca/dds/", {
            "obra": self.obra.pk, "data": "2026-06-10",
            "tema": "Trabalho em altura", "assunto": "Cinto e talabarte.",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)
        dds = DialogoSeguranca.objects.get(pk=resposta.json()["dds_id"])
        self.assertEqual(dds.tenant_id, self.tenant.pk)
        self.assertEqual(dds.registrado_por, "tst8")

    def test_o_ciclo_do_dds_pela_porta_ate_o_diario(self):
        from modulodiario.models import DiarioObra

        criado = self.client.post("/api/pdca/dds/", {
            "obra": self.obra.pk, "data": "2026-06-10", "tema": "Escavação",
        }, format="json").json()
        dds_id = criado["dds_id"]

        presenca = self.client.post(
            f"/api/pdca/dds/{dds_id}/presenca/",
            {"participantes": [
                {"nome": "José da Silva", "assinou": True},
                {"nome": "Maria Souza"},
            ]},
            format="json",
        )
        self.assertEqual(presenca.status_code, 201, presenca.data)
        self.assertEqual(presenca.json()["registrados"], 2)
        #: Os participantes nascem escopados — o inline também passa pelo tenant.
        self.assertEqual(
            ParticipanteDDS.objects.filter(tenant=self.tenant).count(), 2,
        )

        encerrado = self.client.post(
            f"/api/pdca/dds/{dds_id}/encerrar/", {}, format="json",
        )
        self.assertEqual(encerrado.status_code, 200, encerrado.data)
        self.assertTrue(encerrado.json()["publicado_no_diario"])
        self.assertTrue(
            DiarioObra.objects.filter(obra=self.obra, data=date(2026, 6, 10)).exists()
        )

    # -- a ocorrência pela porta -------------------------------------------

    def _ocorrencia_pela_api(self, **extra):
        dados = {
            "obra": self.obra.pk,
            "ocorrido_em": (timezone.now() - timedelta(hours=3)).isoformat(),
            "tipo": TipoOcorrencia.ACIDENTE_TIPICO,
            "descricao": "Queda de nível na periferia da laje.",
            "atividade": self.atividade.pk,
        }
        dados.update(extra)
        resposta = self.client.post(
            "/api/pdca/ocorrencias/", dados, format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        return resposta.json()

    def test_a_ocorrencia_no_futuro_e_recusada_PELA_PORTA(self):
        """D203 — a trava morava só no serviço, e a porta gravava pelo
        serializer: o acidente datado de amanhã entrava pelo HTTP."""
        resposta = self.client.post(
            "/api/pdca/ocorrencias/",
            {
                "obra": self.obra.pk,
                "ocorrido_em": (timezone.now() + timedelta(days=1)).isoformat(),
                "tipo": TipoOcorrencia.QUASE_ACIDENTE,
                "descricao": "Datado de amanhã por engano.",
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertIn("futuro", str(resposta.data))
        self.assertFalse(
            Ocorrencia.objects.filter(descricao="Datado de amanhã por engano.").exists()
        )

    def test_a_ocorrencia_nasce_com_tenant_e_prazo_de_cat_resolvido(self):
        corpo = self._ocorrencia_pela_api()
        ocorrencia = Ocorrencia.objects.get(pk=corpo["ocorrencia_id"])
        self.assertEqual(ocorrencia.tenant_id, self.tenant.pk)
        self.assertEqual(ocorrencia.registrada_por, "tst8")
        #: **O prazo vem decidido pelo servidor**, não pela tela.
        self.assertTrue(corpo["exige_cat"])
        self.assertTrue(corpo["prazo_cat"]["exige"])
        self.assertIn("vence_em", corpo["prazo_cat"])

    def test_classificar_pela_porta_e_o_afastamento_cobra_os_dias(self):
        corpo = self._ocorrencia_pela_api()
        pk = corpo["ocorrencia_id"]

        incompleta = self.client.post(
            f"/api/pdca/ocorrencias/{pk}/classificar/",
            {"classificacao": ClassificacaoOcorrencia.COM_AFASTAMENTO},
            format="json",
        )
        self.assertEqual(incompleta.status_code, 400, incompleta.data)

        completa = self.client.post(
            f"/api/pdca/ocorrencias/{pk}/classificar/",
            {
                "classificacao": ClassificacaoOcorrencia.COM_AFASTAMENTO,
                "dias_perdidos": 9,
            },
            format="json",
        )
        self.assertEqual(completa.status_code, 200, completa.data)
        self.assertEqual(completa.json()["dias_perdidos"], 9)

    def test_a_CAT_exige_o_verbo_do_RH_e_este_usuario_nao_o_tem(self):
        """**A segregação, pela porta.** O TST classifica; o RH comunica."""
        pk = self._ocorrencia_pela_api()["ocorrencia_id"]
        resposta = self.client.post(
            f"/api/pdca/ocorrencias/{pk}/cat/",
            {"tipo": TipoCAT.INICIAL, "emitida_em": "2026-06-11"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 403, resposta.data)

    def test_o_bloco_clinico_vem_mascarado_sem_o_verbo_proprio(self):
        """A primeira PII do grupo `pdca`, e ela não sai para quem não pode."""
        pk = self._ocorrencia_pela_api(
            natureza_lesao="Fratura exposta", cid10="S52.5",
        )["ocorrencia_id"]
        corpo = self.client.get(f"/api/pdca/ocorrencias/{pk}/").json()
        self.assertNotEqual(corpo["natureza_lesao"], "Fratura exposta")
        self.assertNotEqual(corpo["cid10"], "S52.5")

        #: Com o verbo, sai inteiro — a máscara é por permissão, não por campo.
        self.usuario.iam_permissions = (
            self.usuario.iam_permissions + ["pdca.ocorrencia.dado_medico"]
        )
        self.client.force_authenticate(user=self.usuario)
        aberto = self.client.get(f"/api/pdca/ocorrencias/{pk}/").json()
        self.assertEqual(aberto["cid10"], "S52.5")

    def test_a_listagem_nao_carrega_o_bloco_clinico_de_ninguem(self):
        """O jeito mais seguro de não vazar um campo é não o serializar."""
        self._ocorrencia_pela_api(natureza_lesao="Fratura", cid10="S52.5")
        corpo = self.client.get(
            f"/api/pdca/ocorrencias/?obra={self.obra.pk}",
        ).json()
        linha = corpo["results"][0] if "results" in corpo else corpo[0]
        for campo in ("natureza_lesao", "cid10", "atestado_dias"):
            self.assertNotIn(campo, linha)

    def test_interditar_a_frente_pela_porta_tira_a_atividade_do_quadro(self):
        pk = self._ocorrencia_pela_api()["ocorrencia_id"]
        resposta = self.client.post(
            f"/api/pdca/ocorrencias/{pk}/interditar/", {}, format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        restricao = Restricao.objects.get(pk=resposta.json()["restricao"])
        self.assertEqual(restricao.tipo, TipoRestricao.AREA)
        self.assertEqual(restricao.tenant_id, self.tenant.pk)

    def test_interditar_sem_o_verbo_de_travar_a_obra_e_recusado(self):
        """Sem isso a SSMA vira porta lateral para o quadro da semana."""
        pk = self._ocorrencia_pela_api()["ocorrencia_id"]
        self.usuario.iam_permissions = [
            p for p in self.usuario.iam_permissions if p != "pdca.restricao.edit"
        ]
        self.client.force_authenticate(user=self.usuario)
        resposta = self.client.post(
            f"/api/pdca/ocorrencias/{pk}/interditar/", {}, format="json",
        )
        self.assertEqual(resposta.status_code, 403, resposta.data)

    def test_a_fila_e_o_painel_respondem_pela_porta(self):
        self._ocorrencia_pela_api()
        fila = self.client.get(f"/api/pdca/ocorrencias/fila/?obra={self.obra.pk}")
        self.assertEqual(fila.status_code, 200, fila.data)
        self.assertEqual(len(fila.json()["cat_por_comunicar"]), 1)

        painel = self.client.get(
            f"/api/pdca/ocorrencias/painel/?obra={self.obra.pk}",
        )
        self.assertEqual(painel.status_code, 200, painel.data)
        #: **As taxas saem nulas com motivo, pela porta também** — e o motivo
        #: fala a língua da obra (homem-hora, NBR), não a do repositório.
        self.assertIsNone(painel.json()["taxa_frequencia"])
        motivo = painel.json()["taxas_indisponiveis_porque"]
        self.assertIn("homem-hora", motivo)
        self.assertNotIn("PDCA.", motivo)

    def test_o_epi_exige_a_permissao_do_modulo_dono(self):
        """Ler dado protegido do SIL sem o verbo dele seria porta lateral."""
        resposta = self.client.get(
            f"/api/pdca/ocorrencias/epi-vencido/?obra={self.obra.pk}",
        )
        self.assertEqual(resposta.status_code, 403, resposta.data)

        self.usuario.iam_permissions = (
            self.usuario.iam_permissions + ["sil.epi.view"]
        )
        self.client.force_authenticate(user=self.usuario)
        liberado = self.client.get(
            f"/api/pdca/ocorrencias/epi-vencido/?obra={self.obra.pk}",
        )
        self.assertEqual(liberado.status_code, 200, liberado.data)
        self.assertTrue(liberado.json()["disponivel"])

    def test_a_obra_de_outra_empresa_nao_vaza_pelo_nome(self):
        outro = Tenant.objects.create(slug="pdca8-outro", nome="Outra")
        alheia = Obra.objects.create(
            tenant=outro, nome_obra="Obra alheia", endereco="Rua X",
        )
        resposta = self.client.get(f"/api/pdca/ocorrencias/fila/?obra={alheia.pk}")
        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertNotIn("Obra alheia", str(resposta.data))


# ===========================================================================
# O cockpit — carteira, fila do dia, pulso e busca única
# ===========================================================================
#
# O que estes testes protegem:
#
# - a fila **junta** os assuntos e os ordena por consequência, com a CAT em
#   cima — e um canteiro cheio de restrição vencida não empurra a CAT para
#   fora, porque o teto é por faixa;
# - o recorte de permissão é **por bloco**: quem não pode ver a SSMA recebe a
#   fila da qualidade e uma frase, nunca 403 na página inteira nem uma fila
#   vazia que parece "não há nada";
# - **nenhum número é fabricado** — avanço sem apontamento, PPC sem semana
#   encerrada e dias sem afastamento numa obra que nunca teve acidente voltam
#   `None` com a frase, e zero nunca aparece no lugar;
# - a carteira **cruza obras** (a leitura que não existia) e **não soma o que
#   não se soma**: discrimina as pendências e nomeia a pior;
# - a busca acha sem acento, corta por espécie e **não vaza o bloco clínico**;
# - e as três portas são `APIView` pura, então o teste cobra a RLS que o
#   achado S1 ensinou a armar.


class _BaseCockpit(TestCase):
    """Uma obra com plano vigente e uma pendência de cada consequência."""

    @classmethod
    def setUpTestData(cls):
        from fornecedores.models import Fornecedor

        cls.tenant = Tenant.objects.create(
            slug="pdca-cockpit", nome="Construtora Cockpit",
        )
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Fundação", endereco="Rua 11",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, obra=cls.obra, nome="Padrão",
        )
        cls.cronograma = Cronograma.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=cls.calendario,
            status=Cronograma.Status.VIGENTE,
            termino_calculado=date(2026, 12, 20),
        )
        cls.atividade = Atividade.objects.create(
            tenant=cls.tenant, cronograma=cls.cronograma, codigo="1",
            nome="Alvenaria do 4º", duracao_dias=5, profundidade=1,
            peso_informado=Decimal("10"),
        )
        cls.local = LocalObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, codigo="T1-4",
            nome="Torre 1 · 4º pavimento", nivel=NivelLocal.PAVIMENTO,
        )
        cls.fornecedor = Fornecedor.objects.create(
            tenant=cls.tenant, razao_social="Empreiteira Cockpit",
            email="cockpit@example.com",
        )
        cls.contrato = ContratoObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, fornecedor=cls.fornecedor,
            numero="CT-100", objeto="Alvenaria e revestimento",
            data_inicio=date(2026, 6, 1), status=ContratoObra.Status.VIGENTE,
        )

    # -- as pendências, uma por consequência ---------------------------------

    def _ocorrencia_com_cat(self):
        """Acidente típico sem CAT emitida — a única linha com prazo em lei."""
        return Ocorrencia.objects.create(
            tenant=self.tenant, obra=self.obra,
            tipo=TipoOcorrencia.ACIDENTE_TIPICO,
            ocorrido_em=timezone.now() - timedelta(days=3),
            descricao="Queda de tábua sobre o pé do servente.",
        )

    def _medicao_em_atesto(self):
        return Medicao.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=1,
            periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 6, 30),
            status=Medicao.Status.EM_APROVACAO,
        )

    def _restricao_vencida(self, dias=4):
        return Restricao.objects.create(
            tenant=self.tenant, atividade=self.atividade,
            tipo=TipoRestricao.MATERIAL, descricao="Bloco cerâmico não entregue",
            prazo=timezone.localdate() - timedelta(days=dias),
        )

    def _nc_sem_plano(self, descricao="Parede fora de prumo"):
        return NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, local=self.local,
            gravidade=GravidadeNC.MAIOR, descricao=descricao,
        )

    def _semana_por_encerrar(self):
        inicio = services.segunda_da_semana(
            timezone.localdate() - timedelta(days=14),
        )
        return ProgramacaoSemanal.objects.create(
            tenant=self.tenant, obra=self.obra, semana_inicio=inicio,
            semana_fim=inicio + timedelta(days=6),
            status=ProgramacaoSemanal.Status.COMPROMETIDA,
        )

    def _fila(self, **extra):
        return services.fila_do_dia(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk, **extra
        )


class FilaDoDiaTests(_BaseCockpit):
    """B2 — o que espera alguém nesta obra, numa ordenação só."""

    def test_a_obra_sem_nada_pendente_devolve_fila_vazia_e_diz_quantas_varreu(self):
        """Estado vazio **não** é a mesma coisa que fila não apurada.

        `faixas` vem vazia e `faixas_varridas` diz 11 — é o que permite a tela
        escrever "nenhuma das onze filas tem alguém esperando" em vez de abrir
        uma página em branco que se lê como defeito.
        """
        fila = self._fila()
        self.assertEqual(fila["faixas"], [])
        self.assertEqual(fila["total"], 0)
        self.assertEqual(fila["faixas_varridas"], 11)

    def test_a_faixa_vazia_nao_entra_na_resposta(self):
        """Aviso que aparece sempre e não pede ação é ruído (convenções §9)."""
        self._nc_sem_plano()
        fila = self._fila()
        self.assertEqual([f["codigo"] for f in fila["faixas"]], ["ncs_sem_plano"])

    def test_a_CAT_vem_antes_do_dinheiro_e_o_dinheiro_antes_do_retrabalho(self):
        """**A ordem é por consequência, e é o coração da fatia.**

        Ordenar no navegador daria a ordem errada: ele não sabe que a CAT tem
        prazo em lei e multa, e que um defeito de pintura pode esperar.
        """
        self._ocorrencia_com_cat()
        self._medicao_em_atesto()
        self._restricao_vencida()
        self._nc_sem_plano()

        fila = self._fila()
        consequencias = [f["consequencia"] for f in fila["faixas"]]
        self.assertEqual(consequencias[0], "prazo_legal")
        self.assertLess(
            consequencias.index("dinheiro"), consequencias.index("retrabalho"),
        )
        self.assertLess(
            consequencias.index("compromisso"),
            consequencias.index("retrabalho"),
        )

    def test_toda_linha_diz_o_que_e_ha_quanto_tempo_espera_e_o_que_decidir(self):
        """A régua de pronto §12.1: fila é isto, e contagem não é fila."""
        self._nc_sem_plano()
        faixa = self._fila()["faixas"][0]
        self.assertTrue(faixa["o_que_decidir"])
        linha = faixa["linhas"][0]
        self.assertEqual(linha["tipo"], "nc")
        self.assertTrue(linha["titulo"])
        self.assertEqual(linha["dias"], 0)
        self.assertIsNotNone(linha["desde"])
        self.assertEqual(linha["onde"], "Torre 1 · 4º pavimento")

    def test_o_prazo_da_restricao_vencida_vem_negativo_e_marcado(self):
        self._restricao_vencida(dias=4)
        faixa = next(
            f for f in self._fila()["faixas"] if f["codigo"] == "restricoes_vencidas"
        )
        prazo = faixa["linhas"][0]["prazo"]
        self.assertTrue(prazo["vencido"])
        self.assertEqual(prazo["dias_restantes"], -4)

    def test_a_semana_que_acabou_e_nao_foi_julgada_entra_na_fila(self):
        self._semana_por_encerrar()
        codigos = [f["codigo"] for f in self._fila()["faixas"]]
        self.assertIn("semanas_a_encerrar", codigos)

    def test_o_teto_corta_a_FAIXA_e_declara_o_total_verdadeiro(self):
        """**Por faixa, e não do total** — senão a faixa grande come a CAT."""
        for i in range(PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA + 3):
            self._nc_sem_plano(descricao=f"Defeito {i}")
        self._ocorrencia_com_cat()

        fila = self._fila()
        defeitos = next(
            f for f in fila["faixas"] if f["codigo"] == "ncs_sem_plano"
        )
        self.assertEqual(
            len(defeitos["linhas"]), PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA,
        )
        self.assertTrue(defeitos["truncada"])
        self.assertEqual(
            defeitos["total"], PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA + 3,
        )
        #: E a CAT continua lá, que é o ponto do corte ser por faixa.
        self.assertEqual(fila["faixas"][0]["codigo"], "cat_por_comunicar")

    def test_quem_nao_ve_a_SSMA_recebe_a_qualidade_e_a_frase_do_que_falta(self):
        """Omitir × trancar dentro de um agregado.

        Recusar a página inteira esconderia o trabalho que a pessoa pode
        fazer; omitir em silêncio faria a fila parecer vazia — e é a pior das
        três saídas, porque não parece falha.
        """
        self._ocorrencia_com_cat()
        self._nc_sem_plano()

        fila = self._fila(pode=lambda p: p == "pdca.nc.view")
        self.assertEqual([f["codigo"] for f in fila["faixas"]], ["ncs_sem_plano"])
        negadas = {n["permissao"] for n in fila["sem_permissao"]}
        self.assertIn("pdca.ocorrencia.view", negadas)
        frase = next(
            n for n in fila["sem_permissao"]
            if n["permissao"] == "pdca.ocorrencia.view"
        )["motivo"]
        self.assertIn("administrador", frase)

    def test_a_obra_vizinha_nao_entra_na_fila(self):
        outro = Tenant.objects.create(slug="pdca-cockpit-2", nome="Outra")
        alheia = Obra.objects.create(
            tenant=outro, nome_obra="Obra alheia", endereco="Rua X",
        )
        NaoConformidade.objects.create(
            tenant=outro, obra=alheia, gravidade=GravidadeNC.MAIOR,
            descricao="Defeito da vizinha",
        )
        self.assertEqual(self._fila()["total"], 0)


class PulsoDaObraTests(_BaseCockpit):
    """B6 — as quatro leituras, e os `None` que **não** são zero."""

    def _pulso(self, **extra):
        return services.pulso_da_obra(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk, **extra
        )

    def test_avanco_sem_apontamento_e_None_com_frase_e_nunca_zero(self):
        """§5.1: "avanço sem apontamento é *sem apuração*, nunca 0%"."""
        avanco = self._pulso()["avanco"]
        self.assertIsNone(avanco["fisico"])
        self.assertIn("apontou", avanco["sem_apuracao_porque"])

    def test_o_avanco_apontado_acende_o_numero_e_cala_a_frase(self):
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.atividade,
            data=date(2026, 6, 10), percentual=Decimal("40"),
        )
        avanco = self._pulso()["avanco"]
        self.assertEqual(avanco["fisico"], 40.0)
        self.assertEqual(avanco["sem_apuracao_porque"], "")

    def test_ppc_sem_semana_encerrada_e_None_com_frase(self):
        ppc = self._pulso()["ppc"]
        self.assertIsNone(ppc["ppc"])
        self.assertIn("encerrada", ppc["sem_apuracao_porque"])

    def test_dias_sem_afastamento_e_None_quando_nunca_houve_acidente(self):
        """**Zero aqui seria a mentira mais cara do módulo.**

        Obra que nunca registrou acidente com afastamento não tem "0 dias" —
        ela não tem a série. Contar desde o início da obra seria fabricar.
        """
        seguranca = self._pulso()["seguranca"]
        self.assertIsNone(seguranca["dias_sem_afastamento"])
        self.assertIn("Nenhum acidente", seguranca["sem_apuracao_porque"])

    def test_o_afastamento_registrado_acende_a_contagem(self):
        Ocorrencia.objects.create(
            tenant=self.tenant, obra=self.obra,
            tipo=TipoOcorrencia.ACIDENTE_TIPICO,
            ocorrido_em=timezone.now() - timedelta(days=12),
            descricao="Corte profundo na mão.",
            classificacao=ClassificacaoOcorrencia.COM_AFASTAMENTO,
            #: O banco exige os dias junto da classificação que os pressupõe
            #: (`pdca_ocorrencia_afastamento_tem_dias`) — afastamento sem dias
            #: é registro que não fecha a conta de gravidade.
            dias_perdidos=5,
        )
        seguranca = self._pulso()["seguranca"]
        self.assertEqual(seguranca["dias_sem_afastamento"], 12)
        self.assertEqual(seguranca["sem_apuracao_porque"], "")

    def test_as_taxas_continuam_nulas_com_a_MESMA_frase_do_painel_de_ssma(self):
        """Dois textos para a mesma ausência viram duas explicações.

        A frase é constante compartilhada de propósito: o dia em que uma delas
        mudar sozinha, a pessoa passa a achar que são coisas diferentes.
        """
        seguranca = self._pulso()["seguranca"]
        self.assertIsNone(seguranca["taxa_frequencia"])
        self.assertIsNone(seguranca["taxa_gravidade"])
        painel = services.indicadores_de_ssma(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(
            seguranca["taxas_indisponiveis_porque"].split(",")[0],
            painel["taxas_indisponiveis_porque"].split(",")[0],
        )

    def test_o_primeiro_plano_publicado_nao_tem_desvio_e_diz_por_que(self):
        prazo = self._pulso()["prazo"]
        self.assertTrue(prazo["tem_plano"])
        self.assertIsNone(prazo["desvio_dias"])
        self.assertIn("primeiro plano", prazo["sem_apuracao_porque"])

    def test_o_bloco_sem_permissao_vem_nulo_e_declarado(self):
        pulso = self._pulso(pode=lambda p: p == "pdca.cronograma.view")
        self.assertIsNone(pulso["seguranca"])
        self.assertIsNone(pulso["ppc"])
        self.assertIsNotNone(pulso["prazo"])
        self.assertIn(
            "pdca.ocorrencia.view",
            {n["permissao"] for n in pulso["sem_permissao"]},
        )


class CarteiraTests(_BaseCockpit):
    """B1 — a leitura que cruza obras, que até aqui não existia."""

    def _carteira(self, **extra):
        return services.carteira(tenant_id=self.tenant.pk, **extra)

    def test_a_carteira_poe_as_obras_lado_a_lado(self):
        Obra.objects.create(
            tenant=self.tenant, nome_obra="Galpão Norte", endereco="Rua 12",
        )
        carteira = self._carteira()
        self.assertEqual(carteira["total"], 2)
        self.assertFalse(carteira["truncada"])
        self.assertEqual(
            {l["nome"] for l in carteira["obras"]},
            {"Residencial Fundação", "Galpão Norte"},
        )

    def test_as_pendencias_vem_discriminadas_e_a_pior_e_nomeada(self):
        """**Não soma o que não se soma.**

        Uma CAT vencendo e um defeito de pintura não viram "2 pendências": a
        linha diz qual é cada uma, e `pior_pendencia` aponta a de maior
        consequência para a carteira poder ser ordenada pelo que dói.
        """
        self._ocorrencia_com_cat()
        self._nc_sem_plano()

        linha = self._carteira()["obras"][0]
        codigos = {p["codigo"]: p["quantas"] for p in linha["pendencias"]}
        self.assertEqual(codigos["cat_por_comunicar"], 1)
        self.assertEqual(codigos["ncs_abertas"], 1)
        self.assertEqual(linha["pior_pendencia"]["codigo"], "cat_por_comunicar")
        self.assertEqual(linha["pior_pendencia"]["consequencia"], "prazo_legal")

    def test_a_obra_sem_pendencia_nao_inventa_uma_pior(self):
        linha = self._carteira()["obras"][0]
        self.assertEqual(linha["pendencias"], [])
        self.assertIsNone(linha["pior_pendencia"])

    def test_a_contagem_da_carteira_bate_com_a_lista_da_fila(self):
        """**Entrar na obra não pode mudar o número.**

        A carteira conta em SQL e a fila lista; se as duas divergissem, a
        diretoria decidiria por um número e a obra trabalharia por outro — que
        é o D138 em escala de carteira.
        """
        self._ocorrencia_com_cat()
        self._restricao_vencida()
        self._nc_sem_plano()
        self._nc_sem_plano(descricao="Junta fora de espessura")

        linha = self._carteira()["obras"][0]
        contagens = {p["codigo"]: p["quantas"] for p in linha["pendencias"]}
        fila = {f["codigo"]: f["total"] for f in self._fila()["faixas"]}
        self.assertEqual(contagens["cat_por_comunicar"], fila["cat_por_comunicar"])
        self.assertEqual(
            contagens["restricoes_vencidas"], fila["restricoes_vencidas"],
        )
        self.assertEqual(contagens["ncs_abertas"], fila["ncs_sem_plano"])

    def test_o_teto_corta_e_a_resposta_declara_quantas_ficaram_de_fora(self):
        """Carteira truncada em silêncio é a diretoria decidindo sobre 40
        obras achando que viu todas."""
        for i in range(PDCA_TETO_OBRAS_NA_CARTEIRA + 2):
            Obra.objects.create(
                tenant=self.tenant, nome_obra=f"Obra {i:03d}", endereco="Rua",
            )
        carteira = self._carteira()
        self.assertEqual(len(carteira["obras"]), PDCA_TETO_OBRAS_NA_CARTEIRA)
        self.assertTrue(carteira["truncada"])
        self.assertEqual(carteira["total"], PDCA_TETO_OBRAS_NA_CARTEIRA + 3)
        self.assertEqual(carteira["teto"], PDCA_TETO_OBRAS_NA_CARTEIRA)

    def test_a_obra_de_outra_empresa_nao_entra_na_carteira(self):
        outro = Tenant.objects.create(slug="pdca-cockpit-3", nome="Outra")
        Obra.objects.create(
            tenant=outro, nome_obra="Obra alheia", endereco="Rua X",
        )
        nomes = {l["nome"] for l in self._carteira()["obras"]}
        self.assertNotIn("Obra alheia", nomes)

    def test_o_recorte_por_obras_devolve_so_as_pedidas(self):
        outra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Galpão Norte", endereco="Rua 12",
        )
        carteira = self._carteira(obras=[outra.pk])
        self.assertEqual([l["obra"] for l in carteira["obras"]], [outra.pk])

    def test_sem_permissao_de_avanco_a_coluna_vem_nula_e_declarada(self):
        carteira = self._carteira(pode=lambda p: p != "pdca.avanco.view")
        self.assertIsNone(carteira["obras"][0]["avanco"])
        self.assertIsNotNone(carteira["obras"][0]["prazo"])
        self.assertIn(
            "pdca.avanco.view",
            {n["permissao"] for n in carteira["sem_permissao"]},
        )


class BuscaUnicaTests(_BaseCockpit):
    """B4 — a válvula que permite o menu ficar em seis postos."""

    def _busca(self, termo, **extra):
        return services.busca_unica(
            tenant_id=self.tenant.pk, termo=termo, **extra
        )

    def _especie(self, resposta, codigo):
        return next(
            (e for e in resposta["especies"] if e["codigo"] == codigo), None,
        )

    def test_o_termo_curto_nao_varre_e_explica(self):
        resposta = self._busca("a")
        self.assertTrue(resposta["curta"])
        self.assertEqual(resposta["especies"], [])
        self.assertIn("2 letras", resposta["aviso"])

    def test_acha_sem_acento_nas_duas_direcoes(self):
        """A régua de acessibilidade da casa: ninguém caça o `ç` de luva.

        As **duas** direções, e é o que o `unaccent` dos dois lados garante:
        quem escreve `fundacao` acha `Fundação`, e quem escreve `Fundação`
        acha o mesmo registro. Normalizar só um lado passaria num teste e
        falharia no outro.
        """
        LocalObra.objects.create(
            tenant=self.tenant, obra=self.obra, codigo="FND",
            nome="Bloco de Fundação", nivel=NivelLocal.BLOCO,
        )
        sem_acento = self._especie(self._busca("fundacao"), "local")
        com_acento = self._especie(self._busca("Fundação"), "local")
        self.assertEqual(len(sem_acento["resultados"]), 1)
        self.assertEqual(len(com_acento["resultados"]), 1)

    def test_varre_as_sete_especies_e_devolve_so_as_que_acharam(self):
        """Sete cabeçalhos vazios afogam o único resultado que veio.

        A busca varre as sete e devolve **duas** aqui — a atividade "Alvenaria
        do 4º" e o contrato cujo objeto é "Alvenaria e revestimento". É o caso
        que o teto por espécie protege: as duas aparecem, nenhuma esconde a
        outra, e as cinco que não acharam nada não ocupam linha.
        """
        resposta = self._busca("alvenaria")
        self.assertEqual(resposta["especies_varridas"], 7)
        self.assertEqual(
            [e["codigo"] for e in resposta["especies"]],
            ["atividade", "contrato"],
        )

    def test_o_teto_e_por_especie_para_uma_nao_esconder_a_outra(self):
        """Quarenta atividades "alvenaria" não podem esconder o contrato."""
        for i in range(PDCA_TETO_RESULTADOS_POR_ESPECIE + 3):
            Atividade.objects.create(
                tenant=self.tenant, cronograma=self.cronograma,
                codigo=f"2.{i}", nome=f"Alvenaria trecho {i}",
                duracao_dias=1, profundidade=2,
            )
        ContratoObra.objects.create(
            tenant=self.tenant, obra=self.obra, fornecedor=self.fornecedor,
            numero="CT-200", objeto="Alvenaria estrutural",
            data_inicio=date(2026, 6, 1),
        )
        resposta = self._busca("alvenaria")
        atividades = self._especie(resposta, "atividade")
        self.assertEqual(
            len(atividades["resultados"]), PDCA_TETO_RESULTADOS_POR_ESPECIE,
        )
        self.assertTrue(atividades["truncada"])
        self.assertIsNotNone(self._especie(resposta, "contrato"))

    def test_a_especie_sem_permissao_vira_frase_e_nao_403(self):
        resposta = self._busca("alvenaria", pode=lambda p: p == "pdca.nc.view")
        self.assertEqual(resposta["especies"], [])
        self.assertIn(
            "pdca.cronograma.view",
            {n["permissao"] for n in resposta["sem_permissao"]},
        )

    def test_o_recorte_por_obra_nao_traz_a_obra_vizinha(self):
        outra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Galpão Norte", endereco="Rua 12",
        )
        LocalObra.objects.create(
            tenant=self.tenant, obra=outra, codigo="GN-1",
            nome="Alvenaria do galpão", nivel=NivelLocal.BLOCO,
        )
        ampla = self._especie(self._busca("alvenaria"), "local")
        estreita = self._busca("alvenaria", obra_id=self.obra.pk)
        self.assertEqual(len(ampla["resultados"]), 1)
        self.assertIsNone(self._especie(estreita, "local"))

    def test_a_ocorrencia_nao_vaza_o_bloco_clinico_no_resultado(self):
        """A busca não pode ser a porta lateral do que o serializer fecha."""
        Ocorrencia.objects.create(
            tenant=self.tenant, obra=self.obra,
            tipo=TipoOcorrencia.ACIDENTE_TIPICO,
            ocorrido_em=timezone.now() - timedelta(days=1),
            descricao="Queda na alvenaria do 4º.",
            natureza_lesao="Fratura exposta de tíbia", cid10="S82.1",
            atestado_dias=30,
        )
        achado = self._especie(self._busca("alvenaria"), "ocorrencia")
        bruto = str(achado["resultados"])
        self.assertNotIn("S82.1", bruto)
        self.assertNotIn("Fratura", bruto)

    def test_a_empresa_vizinha_nao_aparece_na_busca(self):
        outro = Tenant.objects.create(slug="pdca-cockpit-4", nome="Outra")
        alheia = Obra.objects.create(
            tenant=outro, nome_obra="Obra alheia", endereco="Rua X",
        )
        LocalObra.objects.create(
            tenant=outro, obra=alheia, codigo="AL-1",
            nome="Alvenaria alheia", nivel=NivelLocal.BLOCO,
        )
        self.assertIsNone(self._especie(self._busca("alvenaria"), "local"))


class MudancasRecentesTests(_BaseCockpit):
    """O terceiro bloco do cockpit — fatos, não posts."""

    def test_o_defeito_aberto_vira_fato_com_quem_e_quando(self):
        NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, gravidade=GravidadeNC.MAIOR,
            descricao="Parede fora de prumo", aberta_por="tecnico",
        )
        recentes = services.mudancas_recentes(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(recentes["total"], 1)
        fato = recentes["fatos"][0]
        self.assertEqual(fato["verbo"], "defeito registrado")
        self.assertEqual(fato["quem"], "tecnico")

    def test_o_que_e_mais_velho_que_a_janela_fica_de_fora(self):
        antiga = NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, gravidade=GravidadeNC.MENOR,
            descricao="Defeito antigo",
        )
        NaoConformidade.objects.filter(pk=antiga.pk).update(
            aberta_em=timezone.now() - timedelta(days=60),
        )
        recentes = services.mudancas_recentes(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(recentes["total"], 0)
        largo = services.mudancas_recentes(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk, dias=90,
        )
        self.assertEqual(largo["total"], 1)


class ApiDoCockpitTests(APITestCase):
    """As três portas **pelo HTTP** — e a RLS que o achado S1 ensinou.

    As três são `APIView` pura, e é exatamente a família em que o S1 achou
    views de dashboard lendo dado de qualquer tenant. Aqui a carteira cruza
    obras *de propósito*, então o teste tem de cobrar o isolamento pela porta.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="cockpit-api", nome="Construtora Cockpit API",
        )
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial Fundação",
            endereco="Rua API",
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), status=Cronograma.Status.VIGENTE,
        )
        Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Alvenaria do 4º", duracao_dias=5, profundidade=1,
        )
        self.usuario = Usuario.objects.create(
            username="cockpit", tenant=self.tenant,
        )
        self._autenticar()

    def _autenticar(self, permissions=None, modules=("pdca",)):
        self.usuario.iam_modules = list(modules)
        self.usuario.iam_permissions = list(
            permissions if permissions is not None else [
                "pdca.cronograma.view", "pdca.avanco.view", "pdca.local.view",
                "pdca.nc.view", "pdca.verificacao.view", "pdca.medicao.view",
                "pdca.contrato.view", "pdca.programacao.view",
                "pdca.restricao.view", "pdca.ocorrencia.view",
            ]
        )
        self.client.force_authenticate(user=self.usuario)

    def test_a_carteira_responde_e_declara_o_teto(self):
        resposta = self.client.get("/api/pdca/carteira/")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        corpo = resposta.json()
        self.assertEqual(corpo["teto"], PDCA_TETO_OBRAS_NA_CARTEIRA)
        self.assertEqual(
            [l["nome"] for l in corpo["obras"]], ["Residencial Fundação"],
        )

    def test_hoje_traz_fila_pulso_e_mudancas_numa_leitura_so(self):
        resposta = self.client.get(f"/api/pdca/hoje/?obra={self.obra.pk}")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        corpo = resposta.json()
        self.assertEqual(corpo["obra"], self.obra.pk)
        for bloco in ("fila", "pulso", "mudancas"):
            self.assertIn(bloco, corpo)

    def test_hoje_aceita_desligar_as_mudancas(self):
        corpo = self.client.get(
            f"/api/pdca/hoje/?obra={self.obra.pk}&mudancas=0",
        ).json()
        self.assertNotIn("mudancas", corpo)

    def test_dias_que_nao_e_numero_responde_400_e_nao_500(self):
        """D187 na entrada: erro de quem digitou tem frase, não stack."""
        resposta = self.client.get(
            f"/api/pdca/hoje/?obra={self.obra.pk}&dias=ontem",
        )
        self.assertEqual(resposta.status_code, 400, resposta.data)

    def test_a_busca_responde_e_corta_o_termo_curto(self):
        curta = self.client.get("/api/pdca/busca/?q=a").json()
        self.assertTrue(curta["curta"])
        achou = self.client.get("/api/pdca/busca/?q=alvenaria").json()
        self.assertEqual(
            [e["codigo"] for e in achou["especies"]], ["atividade"],
        )

    def test_sem_o_modulo_contratado_as_tres_portas_fecham(self):
        self._autenticar(modules=())
        for rota in (
            "/api/pdca/carteira/",
            f"/api/pdca/hoje/?obra={self.obra.pk}",
            "/api/pdca/busca/?q=alvenaria",
        ):
            self.assertEqual(self.client.get(rota).status_code, 403, rota)

    def test_a_carteira_NAO_atravessa_o_tenant(self):
        outro = Tenant.objects.create(slug="cockpit-api-2", nome="Outra")
        Obra.objects.create(
            tenant=outro, nome_obra="Obra alheia", endereco="Rua X",
        )
        corpo = self.client.get("/api/pdca/carteira/").json()
        self.assertNotIn("Obra alheia", str(corpo))

    def test_hoje_de_obra_alheia_recusa_sem_vazar_o_nome(self):
        outro = Tenant.objects.create(slug="cockpit-api-3", nome="Outra")
        alheia = Obra.objects.create(
            tenant=outro, nome_obra="Obra alheia", endereco="Rua X",
        )
        resposta = self.client.get(f"/api/pdca/hoje/?obra={alheia.pk}")
        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertNotIn("Obra alheia", str(resposta.data))

    def test_o_status_anuncia_o_cockpit_e_os_tres_tetos(self):
        corpo = self.client.get("/api/pdca/status/").json()
        for capacidade in (
            "carteira", "fila_do_dia", "pulso_da_obra", "busca_unica",
        ):
            self.assertTrue(corpo["recursos"][capacidade], capacidade)
        self.assertEqual(
            corpo["tetos"]["obras_na_carteira"], PDCA_TETO_OBRAS_NA_CARTEIRA,
        )
        self.assertEqual(
            corpo["tetos"]["resultados_por_especie"],
            PDCA_TETO_RESULTADOS_POR_ESPECIE,
        )


# ===========================================================================
# B3 — o posto da medição: a carteira de contratos e a fila do dinheiro
# ===========================================================================
#
# O que estes testes protegem:
#
# - a fila é **documento parado**, nunca contagem: cada linha diz qual boletim,
#   de que contrato, de que período e por quanto;
# - o recorte de permissão é **por bloco** — quem só ateste continua vendo a
#   fila de atesto sem ver a carteira de contratos, e o que falta vem nomeado;
# - o total vem **ao lado** da lista cortada, porque a lista é cortada pelo teto
#   e uma tela que contasse `linhas` diria o número errado;
# - a carteira **não recalcula** o saldo: ela repete `saldo_do_contrato`, que é
#   a mesma resposta de `GET contratos/{id}/saldo/`;
# - e a ausência declarada: **não existe faixa de "contrato sem medir"**, porque
#   o sistema não conhece a periodicidade combinada com o empreiteiro.


class FilaDaMedicaoTests(_BaseCockpit):
    """B3 — o que espera alguém no caminho do dinheiro."""

    def _fila_da_medicao(self, **extra):
        return services.fila_da_medicao(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk, **extra
        )

    def test_obra_sem_documento_parado_devolve_fila_vazia(self):
        fila = self._fila_da_medicao()
        self.assertEqual(fila["total"], 0)
        for bloco in (
            "medicoes_em_rascunho", "medicoes_a_atestar",
            "retencoes_a_liberar", "aditivos_a_decidir",
        ):
            self.assertEqual(fila[bloco], [], bloco)
        self.assertEqual(fila["sem_permissao"], [])

    def test_o_rascunho_parado_entra_com_o_periodo_e_o_liquido(self):
        """Apurou e não mandou — é o documento que ninguém está esperando
        porque ninguém sabe que ele existe."""
        medicao = Medicao.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=1,
            periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 6, 30),
            status=Medicao.Status.RASCUNHO,
            apurada_por="Engenheiro da obra",
        )
        #: `apurada_em` é `auto_now_add`, então o passado se escreve por
        #: `update` — e é ele que tem de virar o "há quanto tempo espera".
        Medicao.objects.filter(pk=medicao.pk).update(
            apurada_em=timezone.now() - timedelta(days=9),
        )
        fila = self._fila_da_medicao()

        self.assertEqual(fila["totais"]["medicoes_em_rascunho"], 1)
        linha = fila["medicoes_em_rascunho"][0]
        self.assertEqual(linha["id"], medicao.pk)
        self.assertEqual(linha["chave"], f"medicao:{medicao.pk}")
        self.assertIn("CT-100", linha["titulo"])
        self.assertIn("30/06/2026", linha["detalhe"])
        self.assertEqual(linha["contrato"], self.contrato.pk)
        self.assertEqual(linha["apurada_por"], "Engenheiro da obra")
        self.assertEqual(linha["dias"], 9)
        #: O boletim sem uma linha sequer não é o mesmo problema do que está
        #: pronto e parado: um pede para ser preenchido, o outro conferido.
        self.assertEqual(linha["linhas"], 0)
        self.assertIn("liquido", linha)

    def test_a_medicao_em_atesto_entra_e_o_rascunho_nao_se_mistura(self):
        rascunho = Medicao.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=1,
            periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 6, 30),
            status=Medicao.Status.RASCUNHO,
        )
        em_atesto = Medicao.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=2,
            periodo_inicio=date(2026, 7, 1), periodo_fim=date(2026, 7, 31),
            status=Medicao.Status.EM_APROVACAO,
        )

        fila = self._fila_da_medicao()
        self.assertEqual(
            [l["id"] for l in fila["medicoes_em_rascunho"]], [rascunho.pk],
        )
        self.assertEqual(
            [l["id"] for l in fila["medicoes_a_atestar"]], [em_atesto.pk],
        )
        self.assertEqual(fila["total"], 2)

    def test_a_medicao_aprovada_ou_cancelada_NAO_espera_ninguem(self):
        """Fila é o que **está parado**, não o histórico do contrato."""
        for numero, status in (
            (1, Medicao.Status.APROVADA),
            (2, Medicao.Status.CANCELADA),
            (3, Medicao.Status.REPROVADA),
        ):
            Medicao.objects.create(
                tenant=self.tenant, contrato=self.contrato, numero=numero,
                periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 6, 30),
                status=status,
            )
        self.assertEqual(self._fila_da_medicao()["total"], 0)

    def test_o_aditivo_aberto_entra_porque_muda_o_que_se_mede(self):
        aditivo = AditivoContrato.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=1,
            justificativa="Acréscimo de revestimento na fachada oeste.",
            status=AditivoContrato.Status.EM_APROVACAO,
        )
        fila = self._fila_da_medicao()
        linha = fila["aditivos_a_decidir"][0]
        self.assertEqual(linha["id"], aditivo.pk)
        self.assertEqual(linha["tipo"], "aditivo")
        self.assertIn("fachada oeste", linha["detalhe"])
        self.assertEqual(linha["status"], AditivoContrato.Status.EM_APROVACAO)

    def test_o_aditivo_aprovado_sai_da_fila(self):
        AditivoContrato.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=1,
            justificativa="Já decidido.",
            status=AditivoContrato.Status.APROVADO,
        )
        self.assertEqual(self._fila_da_medicao()["aditivos_a_decidir"], [])

    def test_a_retencao_pedida_entra_com_o_valor_e_a_condicao(self):
        liberacao = LiberacaoRetencao.objects.create(
            tenant=self.tenant, contrato=self.contrato,
            valor=Decimal("4000.00"), data=date(2026, 8, 10),
            condicao_atendida="Garantia de 12 meses vencida sem chamado.",
            status=LiberacaoRetencao.Status.EM_APROVACAO,
        )
        linha = self._fila_da_medicao()["retencoes_a_liberar"][0]
        self.assertEqual(linha["id"], liberacao.pk)
        self.assertEqual(linha["tipo"], "liberacao")
        self.assertIn("Garantia de 12 meses", linha["detalhe"])
        self.assertEqual(linha["liquido"], Decimal("4000.00"))

    def test_a_fila_nao_enxerga_o_contrato_de_outra_obra(self):
        from fornecedores.models import Fornecedor

        outra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Outra obra", endereco="Rua 2",
        )
        fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Empreiteira vizinha",
            email="vizinha@example.com",
        )
        contrato = ContratoObra.objects.create(
            tenant=self.tenant, obra=outra, fornecedor=fornecedor,
            numero="CT-999", objeto="Outra coisa",
            data_inicio=date(2026, 6, 1), status=ContratoObra.Status.VIGENTE,
        )
        Medicao.objects.create(
            tenant=self.tenant, contrato=contrato, numero=1,
            periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 6, 30),
            status=Medicao.Status.RASCUNHO,
        )
        self.assertEqual(self._fila_da_medicao()["total"], 0)

    def test_sem_permissao_de_medicao_o_bloco_vem_vazio_e_NOMEADO(self):
        """Recusar a página inteira esconderia o trabalho que a pessoa pode
        fazer; omitir em silêncio faria a fila parecer vazia."""
        self._medicao_em_atesto()
        AditivoContrato.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=1,
            justificativa="Acréscimo.",
            status=AditivoContrato.Status.EM_APROVACAO,
        )
        fila = self._fila_da_medicao(
            pode=lambda p: p != "pdca.medicao.view",
        )
        self.assertEqual(fila["medicoes_a_atestar"], [])
        self.assertEqual(fila["totais"]["medicoes_a_atestar"], 0)
        #: e o que ela **pode** ver continua lá
        self.assertEqual(len(fila["aditivos_a_decidir"]), 1)
        self.assertEqual(
            [n["permissao"] for n in fila["sem_permissao"]],
            ["pdca.medicao.view"],
        )

    def test_sem_permissao_de_contrato_a_fila_de_atesto_continua(self):
        """Quem ateste medição pode não ler contrato — e o contrário."""
        self._medicao_em_atesto()
        LiberacaoRetencao.objects.create(
            tenant=self.tenant, contrato=self.contrato,
            valor=Decimal("1000.00"), data=date(2026, 8, 10),
            condicao_atendida="Condição.",
            status=LiberacaoRetencao.Status.EM_APROVACAO,
        )
        fila = self._fila_da_medicao(
            pode=lambda p: p != "pdca.contrato.view",
        )
        self.assertEqual(len(fila["medicoes_a_atestar"]), 1)
        self.assertEqual(fila["retencoes_a_liberar"], [])
        self.assertEqual(
            [n["permissao"] for n in fila["sem_permissao"]],
            ["pdca.contrato.view"],
        )

    def test_o_total_vem_AO_LADO_da_lista_cortada(self):
        """A lista é cortada pelo teto; contar `linhas` na tela daria o número
        errado, e número errado numa fila de dinheiro é pior que nenhum."""
        teto = services.PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA
        for numero in range(1, teto + 4):
            Medicao.objects.create(
                tenant=self.tenant, contrato=self.contrato, numero=numero,
                periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 6, 30),
                status=Medicao.Status.RASCUNHO,
            )
        fila = self._fila_da_medicao()
        self.assertEqual(len(fila["medicoes_em_rascunho"]), teto)
        self.assertEqual(fila["totais"]["medicoes_em_rascunho"], teto + 3)
        self.assertEqual(fila["total"], teto + 3)

    def test_NAO_existe_faixa_de_contrato_sem_medir(self):
        """A ausência é desenho, e ela é declarada.

        De quanto em quanto tempo se mede é cláusula combinada com cada
        empreiteiro — o contrato nem guarda o campo. Uma faixa dessas acenderia
        todo dia para todo contrato vigente, e aviso que aparece sempre ensina
        a ignorar a fila.
        """
        fila = self._fila_da_medicao()
        self.assertNotIn("contratos_a_medir", fila)
        self.assertNotIn("contratos_atrasados", fila)


class CarteiraDeContratosTests(_BaseCockpit):
    """A leitura de cima do posto: os contratos com o saldo resolvido."""

    def _carteira(self, **extra):
        return services.carteira_de_contratos(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk, **extra
        )

    def test_a_linha_traz_o_contrato_e_o_saldo_inteiro(self):
        carteira = self._carteira()
        self.assertEqual(carteira["total"], 1)
        self.assertFalse(carteira["truncada"])
        linha = carteira["linhas"][0]
        self.assertEqual(linha["contrato"], self.contrato.pk)
        self.assertEqual(linha["numero"], "CT-100")
        self.assertEqual(linha["fornecedor_nome"], "Empreiteira Cockpit")
        for chave in (
            "valor_contratado", "medido_aprovado", "saldo", "retencao",
            "periodo_sugerido",
        ):
            self.assertIn(chave, linha["saldo"], chave)

    def test_o_saldo_da_carteira_e_o_MESMO_do_endpoint_do_contrato(self):
        """§10.1 — nenhuma leitura que atravessa calcula nada de novo.

        Duas implementações da mesma soma é o D138 em escala de carteira: a
        tela do contrato diria um número e a do posto diria outro, e ninguém
        saberia em qual acreditar.
        """
        linha = self._carteira()["linhas"][0]
        direto = services.saldo_do_contrato(self.contrato)
        self.assertEqual(linha["saldo"]["valor_contratado"],
                         direto["valor_contratado"])
        self.assertEqual(linha["saldo"]["saldo"], direto["saldo"])

    def test_a_trava_da_planilha_viaja_com_a_linha(self):
        """Convenções §11 — a tela lê a resposta, não reimplementa a condição."""
        linha = self._carteira()["linhas"][0]
        aberta, motivo = services.planilha_editavel(self.contrato)
        self.assertEqual(linha["planilha_editavel"], aberta)
        self.assertEqual(linha["planilha_fechada_porque"], motivo)

    def test_o_contrato_encerrado_sai_da_leitura_que_abre_o_posto(self):
        self.contrato.status = ContratoObra.Status.ENCERRADO
        self.contrato.save(update_fields=["status"])
        carteira = self._carteira()
        self.assertEqual(carteira["linhas"], [])
        self.assertEqual(carteira["total"], 0)

    def test_sem_permissao_de_contrato_a_carteira_vem_NOMEADA(self):
        carteira = self._carteira(pode=lambda p: p != "pdca.contrato.view")
        self.assertEqual(carteira["linhas"], [])
        self.assertEqual(
            [n["permissao"] for n in carteira["sem_permissao"]],
            ["pdca.contrato.view"],
        )

    def test_a_carteira_declara_o_teto_para_a_tela_poder_dizer_o_corte(self):
        self.assertEqual(
            self._carteira()["teto"], services.PDCA_TETO_CONTRATOS_NO_POSTO,
        )


class ApiDoPostoDaMedicaoTests(APITestCase):
    """A porta do posto **pelo HTTP** — e a tenancy explícita da `APIView`."""

    def setUp(self):
        from fornecedores.models import Fornecedor

        self.tenant = Tenant.objects.create(
            slug="posto-medicao", nome="Construtora do Posto",
        )
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial Posto", endereco="Rua M",
        )
        self.fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Empreiteira do Posto",
            email="posto@example.com",
        )
        self.contrato = ContratoObra.objects.create(
            tenant=self.tenant, obra=self.obra, fornecedor=self.fornecedor,
            numero="CT-500", objeto="Estrutura",
            data_inicio=date(2026, 6, 1), status=ContratoObra.Status.VIGENTE,
        )
        self.medicao = Medicao.objects.create(
            tenant=self.tenant, contrato=self.contrato, numero=1,
            periodo_inicio=date(2026, 6, 1), periodo_fim=date(2026, 6, 30),
            status=Medicao.Status.EM_APROVACAO,
        )
        self.usuario = Usuario.objects.create(
            username="posto", tenant=self.tenant,
        )
        self._autenticar()

    def _autenticar(self, permissions=None, modules=("pdca",)):
        self.usuario.iam_modules = list(modules)
        self.usuario.iam_permissions = list(
            permissions if permissions is not None
            else ["pdca.medicao.view", "pdca.contrato.view"]
        )
        self.client.force_authenticate(user=self.usuario)

    def test_o_posto_traz_contratos_e_fila_numa_leitura_so(self):
        resposta = self.client.get(f"/api/pdca/medicao/?obra={self.obra.pk}")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        corpo = resposta.json()
        self.assertEqual(corpo["obra"], self.obra.pk)
        self.assertEqual(corpo["obra_nome"], "Residencial Posto")
        self.assertEqual(len(corpo["contratos"]["linhas"]), 1)
        self.assertEqual(len(corpo["fila"]["medicoes_a_atestar"]), 1)

    def test_o_dinheiro_viaja_como_STRING_e_nao_como_float(self):
        """`float` tem 53 bits de mantissa e não representa centavo — é a razão
        de o DRF serializar decimal como string, e vale para este dicionário
        montado à mão."""
        corpo = self.client.get(
            f"/api/pdca/medicao/?obra={self.obra.pk}",
        ).json()
        linha = corpo["contratos"]["linhas"][0]
        self.assertIsInstance(linha["saldo"]["valor_contratado"], str)
        self.assertIsInstance(
            corpo["fila"]["medicoes_a_atestar"][0]["liquido"], str,
        )

    def test_quem_so_ateste_nao_recebe_403_na_PAGINA(self):
        """§10.1 — o portão declara só `RequireModule`.

        Exigir `pdca.contrato.view` aqui recusaria o posto inteiro a quem
        ateste medição, que é justamente quem mais o usa.
        """
        self._autenticar(permissions=["pdca.medicao.view"])
        resposta = self.client.get(f"/api/pdca/medicao/?obra={self.obra.pk}")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        corpo = resposta.json()
        self.assertEqual(len(corpo["fila"]["medicoes_a_atestar"]), 1)
        self.assertEqual(corpo["contratos"]["linhas"], [])
        self.assertEqual(
            [n["permissao"] for n in corpo["contratos"]["sem_permissao"]],
            ["pdca.contrato.view"],
        )

    def test_sem_o_modulo_contratado_a_porta_fecha(self):
        self._autenticar(modules=())
        resposta = self.client.get(f"/api/pdca/medicao/?obra={self.obra.pk}")
        self.assertEqual(resposta.status_code, 403, resposta.data)

    def test_obra_que_nao_e_numero_responde_400_e_nao_500(self):
        """D187 na entrada: `?obra=abc` é erro de quem digitou.

        Sem a conversão em `_minha_obra`, o `filter(pk="abc")` estoura no
        driver e a resposta é 500 — em DEBUG, a página de depuração do Django
        dentro da tela. Vale para as cinco leituras que atravessam.
        """
        for rota in (
            "/api/pdca/medicao/?obra=abc",
            "/api/pdca/hoje/?obra=abc",
        ):
            resposta = self.client.get(rota)
            self.assertEqual(resposta.status_code, 400, f"{rota}: {resposta.data}")

    def test_obra_de_outro_tenant_recusa_sem_vazar_o_nome(self):
        outro = Tenant.objects.create(slug="posto-2", nome="Outra")
        alheia = Obra.objects.create(
            tenant=outro, nome_obra="Obra alheia", endereco="Rua X",
        )
        resposta = self.client.get(f"/api/pdca/medicao/?obra={alheia.pk}")
        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertNotIn("Obra alheia", str(resposta.data))

    def test_o_status_anuncia_o_posto_e_o_teto_de_contratos(self):
        corpo = self.client.get("/api/pdca/status/").json()
        self.assertTrue(corpo["recursos"]["posto_da_medicao"])
        self.assertTrue(corpo["recursos"]["posto_da_qualidade"])
        self.assertTrue(corpo["recursos"]["posto_da_seguranca"])
        self.assertFalse(
            corpo["recursos"]["cobranca_por_periodicidade_de_medicao"],
        )
        self.assertEqual(
            corpo["tetos"]["contratos_no_posto"],
            PDCA_TETO_CONTRATOS_NO_POSTO,
        )


# ===========================================================================
# B8 e B9 — os postos da qualidade e da segurança
# ===========================================================================


class PostosDaQualidadeEDaSegurancaTests(_BaseCockpit):
    """A fila do posto **é** a fila do dia recortada — e o teste cobra isso.

    Se as duas fossem montadas em lugares diferentes, o `HOJE` diria "defeito
    sem plano há 3 dias" e o posto diria outra coisa sobre o mesmo defeito.
    """

    def _qualidade(self, **extra):
        return services.posto_da_qualidade(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk, **extra
        )

    def _seguranca(self, **extra):
        return services.posto_da_seguranca(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk, **extra
        )

    def test_a_fila_da_qualidade_e_o_retrabalho_da_fila_do_dia(self):
        self._nc_sem_plano()
        self._ocorrencia_com_cat()
        self._medicao_em_atesto()

        posto = self._qualidade()["fila"]
        do_dia = [
            f for f in self._fila()["faixas"] if f["origem"] == "qualidade"
        ]
        self.assertEqual(posto["faixas"], do_dia)
        self.assertEqual([f["codigo"] for f in posto["faixas"]], ["ncs_sem_plano"])
        #: Quatro faixas varridas — as do laço —, e não as onze do dia.
        self.assertEqual(posto["faixas_varridas"], 4)

    def test_a_fila_da_seguranca_e_a_do_dia_com_a_CAT_no_topo(self):
        self._ocorrencia_com_cat()
        self._nc_sem_plano()

        posto = self._seguranca()["fila"]
        do_dia = [
            f for f in self._fila()["faixas"] if f["origem"] == "seguranca"
        ]
        self.assertEqual(posto["faixas"], do_dia)
        self.assertEqual(posto["faixas"][0]["codigo"], "cat_por_comunicar")
        self.assertEqual(posto["faixas_varridas"], 3)

    def test_o_painel_vem_do_painel_de_conformidade_e_nao_de_conta_nova(self):
        self._nc_sem_plano()
        esperado = services.painel_de_conformidade(
            obra_id=self.obra.pk, tenant_id=self.tenant.pk,
        )
        self.assertEqual(self._qualidade()["painel"], esperado)

    def test_quem_so_ve_ficha_recebe_a_fila_dela_e_o_painel_nulo_NOMEADO(self):
        """O painel conta NC; quem não vê NC recebe a razão, não um zero."""
        posto = self._qualidade(pode=lambda p: p == "pdca.verificacao.view")
        self.assertIsNone(posto["painel"])
        self.assertIn(
            "pdca.nc.view", [n["permissao"] for n in posto["sem_permissao"]],
        )

    def test_as_taxas_de_seguranca_voltam_nulas_e_com_a_frase(self):
        """Zero numa tela de segurança diria que a obra é segura."""
        self._ocorrencia_com_cat()
        indicadores = self._seguranca()["indicadores"]
        self.assertIsNone(indicadores["taxa_frequencia"])
        self.assertIsNone(indicadores["taxa_gravidade"])
        self.assertTrue(indicadores["taxas_indisponiveis_porque"])

    def test_quem_nao_ve_ocorrencia_nao_recebe_indicador_nem_frente(self):
        posto = self._seguranca(pode=lambda p: False)
        self.assertIsNone(posto["indicadores"])
        self.assertEqual(posto["frentes_interditadas"], [])
        self.assertEqual(
            [n["permissao"] for n in posto["sem_permissao"]],
            ["pdca.ocorrencia.view"],
        )

    def test_a_frente_interditada_aparece_a_parte_e_sai_quando_libera(self):
        """Não é faixa: liberar a frente é ato da semana. Aqui ela é o que o
        técnico precisa saber antes de encerrar a ocorrência que a abriu."""
        ocorrencia = self._ocorrencia_com_cat()
        ocorrencia.atividade = self.atividade
        ocorrencia.local = self.local
        ocorrencia.save(update_fields=["atividade", "local"])
        restricao = services.gerar_restricao_da_ocorrencia(ocorrencia=ocorrencia)

        interditadas = self._seguranca()["frentes_interditadas"]
        self.assertEqual(len(interditadas), 1)
        self.assertEqual(interditadas[0]["restricao"], restricao.pk)
        self.assertEqual(interditadas[0]["atividade_nome"], "Alvenaria do 4º")

        restricao.status = Restricao.Status.REMOVIDA
        restricao.save(update_fields=["status"])
        self.assertEqual(self._seguranca()["frentes_interditadas"], [])

    def test_a_fila_do_dia_continua_varrendo_as_onze(self):
        """A extração das faixas não pode ter mudado o que o `HOJE` lê."""
        self.assertEqual(self._fila()["faixas_varridas"], 11)


class ApiDosPostosDaQualidadeEDaSegurancaTests(APITestCase):
    """As duas portas **pelo HTTP**."""

    def setUp(self):
        self.tenant = Tenant.objects.create(slug="postos-qs", nome="Construtora QS")
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial QS", endereco="Rua Q",
        )
        NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, gravidade=GravidadeNC.MENOR,
            descricao="Rejunte falhado no banheiro 12",
        )
        Ocorrencia.objects.create(
            tenant=self.tenant, obra=self.obra,
            tipo=TipoOcorrencia.QUASE_ACIDENTE,
            ocorrido_em=timezone.now() - timedelta(hours=2),
            descricao="Martelo caiu do andaime sem atingir ninguém.",
        )
        self.usuario = Usuario.objects.create(username="qs", tenant=self.tenant)
        self._autenticar()

    def _autenticar(self, permissions=None, modules=("pdca",)):
        self.usuario.iam_modules = list(modules)
        self.usuario.iam_permissions = list(
            permissions if permissions is not None
            else ["pdca.nc.view", "pdca.verificacao.view", "pdca.ocorrencia.view"]
        )
        self.client.force_authenticate(user=self.usuario)

    def test_os_dois_postos_respondem_com_fila_e_leitura_ao_lado(self):
        qualidade = self.client.get(f"/api/pdca/qualidade/?obra={self.obra.pk}")
        self.assertEqual(qualidade.status_code, 200, qualidade.data)
        corpo = qualidade.json()
        self.assertEqual(corpo["obra_nome"], "Residencial QS")
        self.assertEqual(corpo["fila"]["total"], 1)
        self.assertEqual(corpo["painel"]["ncs_abertas"], 1)

        seguranca = self.client.get(f"/api/pdca/seguranca/?obra={self.obra.pk}")
        self.assertEqual(seguranca.status_code, 200, seguranca.data)
        corpo = seguranca.json()
        self.assertEqual(corpo["indicadores"]["quase_acidentes"], 1)
        codigos = [f["codigo"] for f in corpo["fila"]["faixas"]]
        self.assertIn("ocorrencias_sem_classificacao", codigos)

    def test_curinga_na_claim_nao_concede_nada(self):
        """D194: a claim é a lista exata. `pdca.*` é um código que não existe, e
        não um prefixo — tratá-lo como prefixo concederia todo código novo do
        catálogo e todo degrau de aprovação digitado errado."""
        self._autenticar(permissions=["pdca.*"])
        resposta = self.client.get(f"/api/pdca/seguranca/?obra={self.obra.pk}")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(
            [n["permissao"] for n in resposta.json()["sem_permissao"]],
            ["pdca.ocorrencia.view"],
        )

    def test_sem_permissao_nenhuma_a_pagina_abre_e_diz_o_que_falta(self):
        self._autenticar(permissions=[])
        resposta = self.client.get(f"/api/pdca/seguranca/?obra={self.obra.pk}")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(
            [n["permissao"] for n in resposta.json()["sem_permissao"]],
            ["pdca.ocorrencia.view"],
        )

    def test_recorte_de_data_invalido_responde_400_com_frase(self):
        resposta = self.client.get(
            f"/api/pdca/qualidade/?obra={self.obra.pk}&desde=ontem",
        )
        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertIn("desde", resposta.data)

    def test_obra_que_nao_e_numero_e_modulo_nao_contratado(self):
        for rota in ("/api/pdca/qualidade/?obra=abc", "/api/pdca/seguranca/?obra=abc"):
            self.assertEqual(self.client.get(rota).status_code, 400, rota)
        self._autenticar(modules=())
        self.assertEqual(
            self.client.get(f"/api/pdca/qualidade/?obra={self.obra.pk}").status_code,
            403,
        )

    def test_nenhuma_frase_do_posto_cita_numero_de_fatia(self):
        """Convenções §9: `PDCA.9` é vocabulário de quem escreveu o sistema."""
        import re

        for rota in ("qualidade", "seguranca"):
            corpo = self.client.get(f"/api/pdca/{rota}/?obra={self.obra.pk}").content
            self.assertIsNone(
                re.search(rb"PDCA\.\d", corpo), f"{rota}: {corpo[:300]!r}",
            )


# ===========================================================================
# B5 — a frente de quem está no canteiro
# ===========================================================================
#
# O que estes testes protegem:
#
# - "meu" casa por **nome sem acento**, porque o alvo é rótulo de texto em todo
#   o módulo — e quem entra com o nome do login pode pedir por outro;
# - a leitura **atravessa obras** por desenho, e não vaza a obra do vizinho;
# - o recorte de permissão é **por bloco**: sem `pdca.nc.view` a pessoa continua
#   vendo os compromissos, e o que falta vem nomeado;
# - bloco vazio vem **com razão escrita** — no celular, lista em branco é
#   indistinguível de lista que não carregou;
# - prometido e apontado viajam **separados**, e apontado nulo não é zero.


class MinhasFrentesTests(TestCase):
    """B5 — o que está atribuído a quem pede, na semana corrente."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            slug="pdca-frente", nome="Construtora Frente",
        )
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Frente", endereco="Rua 9",
        )
        cls.cronograma = Cronograma.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), status=Cronograma.Status.VIGENTE,
        )
        cls.atividade = Atividade.objects.create(
            tenant=cls.tenant, cronograma=cls.cronograma, codigo="1.1",
            nome="Alvenaria do 4º", duracao_dias=5, profundidade=1,
        )
        cls.local = LocalObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, codigo="T1-4",
            nome="Torre 1 · 4º pavimento", nivel=NivelLocal.PAVIMENTO,
        )

    def setUp(self):
        self.hoje = timezone.localdate()
        self.semana = services.abrir_programacao(
            obra=self.obra, semana_inicio=self.hoje,
            tenant_id=self.tenant.pk,
        )

    def _cartao(self, responsavel="Mestre Antônio", **extra):
        return ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=self.semana,
            atividade=self.atividade, responsavel=responsavel, **extra
        )

    def _frente(self, quem="Mestre Antônio", **extra):
        return services.minhas_frentes(
            tenant_id=self.tenant.pk, quem=quem, **extra
        )

    # -- o casamento por nome ------------------------------------------------

    def test_o_compromisso_da_semana_aparece_na_frente_de_quem_o_assumiu(self):
        self._cartao(local=self.local, percentual_previsto=Decimal("20"))
        frente = self._frente()
        bloco = frente["compromissos"]
        self.assertEqual(bloco["total"], 1)
        linha = bloco["linhas"][0]
        self.assertEqual(linha["nome"], "Alvenaria do 4º")
        self.assertEqual(linha["local_rotulo"], "Torre 1 · 4º pavimento")
        self.assertEqual(linha["previsto"], Decimal("20"))
        self.assertEqual(frente["semana_inicio"], services.segunda_da_semana(self.hoje))

    def test_o_nome_casa_sem_acento_e_sem_caixa(self):
        """A régua de acessibilidade da casa, aplicada ao nome de quem trabalha.

        Quem digita rápido digita sem acento, e no canteiro ninguém caça o `ô`.
        Exigir grafia exata faria a frente aparecer vazia — a forma de falha que
        não parece falha.
        """
        self._cartao(responsavel="Mestre Antônio")
        self.assertEqual(self._frente(quem="mestre antonio")["total"], 1)
        self.assertEqual(self._frente(quem="MESTRE ANTONIO")["total"], 1)

    def test_o_compromisso_de_outra_pessoa_nao_entra(self):
        self._cartao(responsavel="Encarregado Rita")
        self.assertEqual(self._frente()["compromissos"]["total"], 0)

    def test_sem_nome_a_leitura_devolve_vazio_dizendo_o_que_fazer(self):
        self._cartao()
        frente = self._frente(quem="   ")
        self.assertEqual(frente["total"], 0)
        self.assertIn("nome", frente["sem_nome_porque"])
        self.assertIsNone(frente["compromissos"])

    # -- prometido × apontado ------------------------------------------------

    def test_apontado_nulo_nao_e_zero(self):
        """Ninguém apontou é diferente de apontou e deu zero."""
        self._cartao(percentual_previsto=Decimal("20"))
        linha = self._frente()["compromissos"]["linhas"][0]
        self.assertIsNone(linha["apontado"])
        self.assertFalse(linha["apontou"])

    def test_o_apontado_da_semana_vem_ao_lado_do_prometido(self):
        item = self._cartao(percentual_previsto=Decimal("20"))
        ApontamentoAvanco.objects.create(
            tenant=self.tenant, atividade=self.atividade,
            data=self.semana.semana_inicio, percentual=Decimal("12"),
        )
        linha = self._frente()["compromissos"]["linhas"][0]
        self.assertEqual(linha["item"], item.pk)
        self.assertEqual(linha["previsto"], Decimal("20"))
        self.assertEqual(linha["apontado"], Decimal("12"))
        self.assertTrue(linha["apontou"])

    def test_a_trava_e_o_defeito_do_serviço_viajam_no_cartao(self):
        """Quem vai à frente precisa saber que ela está travada antes de ir."""
        self._cartao()
        Restricao.objects.create(
            tenant=self.tenant, atividade=self.atividade,
            tipo=TipoRestricao.MATERIAL, descricao="Bloco não entregue",
        )
        NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, atividade=self.atividade,
            gravidade=GravidadeNC.MAIOR, descricao="Parede fora de prumo",
        )
        linha = self._frente()["compromissos"]["linhas"][0]
        self.assertEqual(linha["restricoes_abertas"], 1)
        self.assertEqual(linha["ncs_abertas"], 1)

    # -- os outros três blocos ----------------------------------------------

    def test_a_trava_no_meu_nome_entra_com_prazo(self):
        Restricao.objects.create(
            tenant=self.tenant, atividade=self.atividade,
            tipo=TipoRestricao.PROJETO, descricao="Detalhe da laje não chegou",
            responsavel="Mestre Antônio",
            prazo=self.hoje - timedelta(days=2),
        )
        bloco = self._frente()["restricoes"]
        self.assertEqual(bloco["total"], 1)
        prazo = bloco["linhas"][0]["prazo"]
        self.assertTrue(prazo["vencido"])
        self.assertEqual(prazo["dias_restantes"], -2)

    def test_a_trava_removida_sai_da_frente(self):
        trava = Restricao.objects.create(
            tenant=self.tenant, atividade=self.atividade,
            tipo=TipoRestricao.MATERIAL, descricao="Bloco",
            responsavel="Mestre Antônio",
        )
        services.remover_restricao(
            restricao=trava, por="mestre", nota="Entregue hoje",
        )
        self.assertEqual(self._frente()["restricoes"]["total"], 0)

    def test_o_conserto_no_meu_nome_entra_e_o_concluido_sai(self):
        nc = NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, gravidade=GravidadeNC.MAIOR,
            descricao="Parede fora de prumo",
        )
        acao = PlanoAcao.objects.create(
            tenant=self.tenant, nao_conformidade=nc,
            o_que="Refazer o trecho", quem="Mestre Antônio",
            quando=self.hoje,
        )
        bloco = self._frente()["acoes"]
        self.assertEqual(bloco["total"], 1)
        self.assertEqual(bloco["linhas"][0]["acao"], acao.pk)
        self.assertEqual(bloco["linhas"][0]["prazo"]["dias_restantes"], 0)

        PlanoAcao.objects.filter(pk=acao.pk).update(
            status=PlanoAcao.Status.CONCLUIDA, concluida_em=timezone.now(),
        )
        self.assertEqual(self._frente()["acoes"]["total"], 0)

    def test_a_ficha_parada_no_meu_nome_diz_quantas_perguntas_faltam(self):
        modelo = ModeloVerificacao.objects.create(
            tenant=self.tenant, codigo="FVS-ALV", nome="FVS — Alvenaria",
            dominio=DominioVerificacao.QUALIDADE,
        )
        for ordem, texto in ((1, "Prumo"), (2, "Junta")):
            ItemModeloVerificacao.objects.create(
                tenant=self.tenant, modelo=modelo, ordem=ordem, texto=texto,
            )
        services.aplicar_verificacao(
            modelo=modelo, obra=self.obra, data=self.hoje,
            inspetor="Mestre Antônio", tenant_id=self.tenant.pk,
        )
        bloco = self._frente()["fichas"]
        self.assertEqual(bloco["total"], 1)
        self.assertEqual(bloco["linhas"][0]["por_responder"], 2)

    # -- vazio com razão, recorte e isolamento -------------------------------

    def test_bloco_vazio_traz_a_razao_escrita(self):
        frente = self._frente()
        self.assertEqual(frente["total"], 0)
        for codigo in ("compromissos", "restricoes", "acoes", "fichas"):
            self.assertTrue(
                frente[codigo]["vazio_porque"],
                f"{codigo} veio vazio sem dizer por quê",
            )

    def test_a_leitura_atravessa_obras_e_o_recorte_e_opcional(self):
        outra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Comercial Frente", endereco="Rua 10",
        )
        crono = Cronograma.objects.create(
            tenant=self.tenant, obra=outra, descricao="Plano 2",
            data_inicio=date(2026, 6, 1), status=Cronograma.Status.VIGENTE,
        )
        ativ = Atividade.objects.create(
            tenant=self.tenant, cronograma=crono, codigo="1",
            nome="Fundação", duracao_dias=4, profundidade=1,
        )
        segunda = services.abrir_programacao(
            obra=outra, semana_inicio=self.hoje, tenant_id=self.tenant.pk,
        )
        ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=segunda, atividade=ativ,
            responsavel="Mestre Antônio",
        )
        self._cartao()

        self.assertEqual(self._frente()["compromissos"]["total"], 2)
        so_uma = self._frente(obra_id=outra.pk)
        self.assertEqual(so_uma["compromissos"]["total"], 1)
        self.assertEqual(
            so_uma["compromissos"]["linhas"][0]["obra_nome"], "Comercial Frente",
        )

    def test_a_frente_NAO_atravessa_o_tenant(self):
        vizinho = Tenant.objects.create(slug="pdca-frente-2", nome="Vizinha")
        obra = Obra.objects.create(
            tenant=vizinho, nome_obra="Obra alheia", endereco="Rua X",
        )
        crono = Cronograma.objects.create(
            tenant=vizinho, obra=obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), status=Cronograma.Status.VIGENTE,
        )
        ativ = Atividade.objects.create(
            tenant=vizinho, cronograma=crono, codigo="1", nome="Alheia",
            duracao_dias=3, profundidade=1,
        )
        semana = services.abrir_programacao(
            obra=obra, semana_inicio=self.hoje, tenant_id=vizinho.pk,
        )
        ItemProgramacao.objects.create(
            tenant=vizinho, programacao=semana, atividade=ativ,
            responsavel="Mestre Antônio",
        )
        self.assertNotIn("Obra alheia", str(self._frente()))

    def test_a_permissao_recorta_por_bloco_e_nao_esvazia_a_pagina(self):
        self._cartao()
        nc = NaoConformidade.objects.create(
            tenant=self.tenant, obra=self.obra, gravidade=GravidadeNC.MENOR,
            descricao="Rejunte",
        )
        PlanoAcao.objects.create(
            tenant=self.tenant, nao_conformidade=nc, o_que="Refazer",
            quem="Mestre Antônio", quando=self.hoje,
        )
        frente = self._frente(pode=lambda p: p != "pdca.nc.view")
        self.assertEqual(frente["compromissos"]["total"], 1)
        self.assertIsNone(frente["acoes"])
        self.assertEqual(
            [n["permissao"] for n in frente["sem_permissao"]], ["pdca.nc.view"],
        )

    def test_o_bloco_corta_no_teto_e_declara_o_total(self):
        for indice in range(PDCA_TETO_LINHAS_POR_FRENTE + 3):
            ativ = Atividade.objects.create(
                tenant=self.tenant, cronograma=self.cronograma,
                codigo=f"2.{indice}", nome=f"Serviço {indice}",
                duracao_dias=2, profundidade=1,
            )
            ItemProgramacao.objects.create(
                tenant=self.tenant, programacao=self.semana, atividade=ativ,
                responsavel="Mestre Antônio", ordem=indice,
            )
        bloco = self._frente()["compromissos"]
        self.assertEqual(len(bloco["linhas"]), PDCA_TETO_LINHAS_POR_FRENTE)
        self.assertEqual(bloco["total"], PDCA_TETO_LINHAS_POR_FRENTE + 3)
        self.assertTrue(bloco["truncada"])


class ApiDasMinhasFrentesTests(APITestCase):
    """A quinta porta do cockpit — e a RLS que o achado S1 ensinou a armar."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="frente-api", nome="Construtora Frente API",
        )
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial Frente",
            endereco="Rua API",
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), status=Cronograma.Status.VIGENTE,
        )
        self.atividade = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Alvenaria do 4º", duracao_dias=5, profundidade=1,
        )
        self.semana = services.abrir_programacao(
            obra=self.obra, semana_inicio=timezone.localdate(),
            tenant_id=self.tenant.pk,
        )
        self.usuario = Usuario.objects.create(
            username="encarregado", tenant=self.tenant,
            first_name="Mestre", last_name="Antônio",
        )
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = [
            "pdca.programacao.view", "pdca.restricao.view",
            "pdca.nc.view", "pdca.verificacao.view",
        ]
        self.client.force_authenticate(user=self.usuario)

    def _cartao(self, responsavel):
        return ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=self.semana,
            atividade=self.atividade, responsavel=responsavel,
        )

    def test_a_porta_casa_pelo_nome_de_quem_pede(self):
        self._cartao("Mestre Antônio")
        resposta = self.client.get("/api/pdca/minhas-frentes/")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        corpo = resposta.json()
        self.assertEqual(corpo["quem"], "Mestre Antônio")
        self.assertEqual(corpo["compromissos"]["total"], 1)
        self.assertEqual(corpo["teto"], PDCA_TETO_LINHAS_POR_FRENTE)

    def test_como_troca_o_nome_procurado(self):
        """O rótulo do quadro nem sempre é o nome do login — ver a view."""
        self._cartao("Encarregado Rita")
        vazio = self.client.get("/api/pdca/minhas-frentes/").json()
        self.assertEqual(vazio["compromissos"]["total"], 0)
        achou = self.client.get(
            "/api/pdca/minhas-frentes/?como=encarregado rita",
        ).json()
        self.assertEqual(achou["compromissos"]["total"], 1)
        self.assertEqual(achou["quem"], "encarregado rita")

    def test_sem_o_modulo_contratado_a_porta_fecha(self):
        self.usuario.iam_modules = []
        self.client.force_authenticate(user=self.usuario)
        self.assertEqual(
            self.client.get("/api/pdca/minhas-frentes/").status_code, 403,
        )

    def test_a_obra_alheia_e_recusada_sem_vazar_o_nome(self):
        vizinho = Tenant.objects.create(slug="frente-api-2", nome="Vizinha")
        alheia = Obra.objects.create(
            tenant=vizinho, nome_obra="Obra alheia", endereco="Rua X",
        )
        resposta = self.client.get(
            f"/api/pdca/minhas-frentes/?obra={alheia.pk}",
        )
        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertNotIn("Obra alheia", str(resposta.data))

    def test_o_status_anuncia_a_frente_e_declara_que_nao_ha_offline(self):
        corpo = self.client.get("/api/pdca/status/").json()
        self.assertTrue(corpo["recursos"]["minhas_frentes"])
        self.assertFalse(corpo["recursos"]["campo_offline"])
        self.assertEqual(
            corpo["tetos"]["linhas_por_frente"], PDCA_TETO_LINHAS_POR_FRENTE,
        )


# ---------------------------------------------------------------------------
# A montagem do plano dentro do posto (09/10/2026) — fase, inserir, mover,
# colar/importar, orçamento e modelo anexado
# ---------------------------------------------------------------------------


class LigacaoDeFaseTests(BaseCronograma):
    """Decisão do dono, 09/10/2026: "dependências de fases" — a seta sai de uma
    etapa ou chega nela, e o CPM a expande nas folhas."""

    def test_fs_de_fase_segura_todas_as_folhas_da_etapa_seguinte(self):
        fund = self.atividade("1", duracao=None)
        self.atividade("1.1", duracao=3, pai=fund)
        self.atividade("1.2", duracao=5, pai=fund)
        estr = self.atividade("2", duracao=None)
        a = self.atividade("2.1", duracao=1, pai=estr)
        b = self.atividade("2.2", duracao=1, pai=estr)
        self.ligar(fund, estr)
        services.calcular_cpm(self.cronograma)
        a.refresh_from_db(); b.refresh_from_db()
        # A fundação termina na sexta 05/06 (a folha de 5 dias manda).
        self.assertEqual(a.inicio_cedo, date(2026, 6, 8))
        self.assertEqual(b.inicio_cedo, date(2026, 6, 8))

    def test_ss_de_fase_sai_das_folhas_que_abrem_a_etapa(self):
        fund = self.atividade("1", duracao=None)
        abre = self.atividade("1.1", duracao=2, pai=fund)
        fecha = self.atividade("1.2", duracao=3, pai=fund)
        self.ligar(abre, fecha)
        seguinte = self.atividade("2", duracao=1)
        self.ligar(fund, seguinte, tipo=Precedencia.Tipo.SS, atraso=1)
        services.calcular_cpm(self.cronograma)
        seguinte.refresh_from_db()
        self.assertEqual(seguinte.inicio_cedo, date(2026, 6, 2))

    def test_o_ciclo_que_passa_por_dentro_da_etapa_e_recusado(self):
        fund = self.atividade("1", duracao=None)
        dentro = self.atividade("1.1", duracao=2, pai=fund)
        depois = self.atividade("2", duracao=1)
        self.ligar(fund, depois)
        volta = services.LigacaoEntreFolhas(0, depois.pk, dentro.pk, "FS", 0)
        with self.assertRaises(ValidationError):
            services.verificar_rede(self.cronograma, nova=volta)


class MontagemDaArvoreTests(BaseCronograma):
    def _codigos(self):
        return dict(self.cronograma.atividades.values_list("nome", "codigo"))

    def test_inserir_logo_abaixo_empurra_as_seguintes_e_renumera(self):
        um = self.atividade("1")
        self.atividade("2")
        nova = services.inserir_atividade(
            self.cronograma, pai=None, depois_de=um, nome="Canteiro", duracao_dias=4,
        )
        self.assertEqual(nova.codigo, "2")
        self.assertEqual(self._codigos(), {
            "Serviço 1": "1", "Canteiro": "2", "Serviço 2": "3",
        })

    def test_mover_para_dentro_recua_e_renumera(self):
        um = self.atividade("1")
        dois = self.atividade("2")
        movida = services.mover_atividade(dois, pai=um)
        self.assertEqual(movida.codigo, "1.1")
        self.assertEqual(movida.profundidade, 2)

    def test_mover_para_dentro_de_si_e_recusado(self):
        um = self.atividade("1", duracao=None)
        filho = self.atividade("1.1", pai=um)
        with self.assertRaises(ValidationError):
            services.mover_atividade(um, pai=filho)

    def test_o_pai_que_fica_sem_filhos_volta_a_ter_duracao(self):
        um = self.atividade("1", duracao=None)
        filho = self.atividade("1.1", pai=um)
        services.mover_atividade(filho, pai=None)
        um.refresh_from_db()
        self.assertEqual(um.duracao_dias, 1)
        services.calcular_cpm(self.cronograma)

    def test_subir_entre_irmas_troca_a_ordem(self):
        self.atividade("1")
        dois = self.atividade("2")
        services.mover_atividade(dois, pai=None, posicao=0)
        self.assertEqual(self._codigos(), {"Serviço 2": "1", "Serviço 1": "2"})


class ImportarLinhasTests(BaseCronograma):
    def test_le_a_grafia_do_project_em_ingles_e_em_portugues(self):
        self.assertEqual(
            services.ler_predecessoras("1.2FS+3d; 1.4SS, 2TI-2 dias"),
            [("1.2", "FS", 3), ("1.4", "SS", 0), ("2", "FS", -2)],
        )

    def test_monta_a_arvore_a_rede_e_o_marco(self):
        resultado = services.importar_linhas(self.cronograma, [
            {"codigo": "1", "nome": "Fundação"},
            {"codigo": "1.1", "nome": "Estacas", "duracao_dias": "10"},
            {"codigo": "1.2", "nome": "Blocos", "duracao_dias": "8",
             "predecessoras": "1.1FS+2"},
            {"codigo": "2", "nome": "Entrega", "duracao_dias": "0"},
        ])
        self.assertEqual(resultado["criadas"], 4)
        self.assertEqual(resultado["ligacoes"], 1)
        blocos = self.cronograma.atividades.get(nome="Blocos")
        self.assertEqual(blocos.codigo, "1.2")
        lig = Precedencia.objects.get(destino=blocos)
        self.assertEqual((lig.origem.nome, lig.atraso_dias), ("Estacas", 2))
        self.assertTrue(self.cronograma.atividades.get(nome="Entrega").eh_marco)
        services.calcular_cpm(self.cronograma)

    def test_o_project_aponta_pelo_numero_da_linha(self):
        services.importar_linhas(self.cronograma, [
            {"nome": "Escavar", "nivel": 1, "duracao_dias": "2"},
            {"nome": "Concretar", "nivel": 1, "duracao_dias": "1", "predecessoras": "1"},
        ], referencia="linha")
        lig = Precedencia.objects.get(destino__nome="Concretar")
        self.assertEqual(lig.origem.nome, "Escavar")

    def test_entra_no_fim_do_que_ja_existe(self):
        self.atividade("1")
        services.importar_linhas(self.cronograma, [{"nome": "Colada", "duracao_dias": "3"}])
        self.assertEqual(self.cronograma.atividades.get(nome="Colada").codigo, "2")

    def test_ciclo_desfaz_o_bloco_inteiro(self):
        with self.assertRaises(ValidationError):
            services.importar_linhas(self.cronograma, [
                {"codigo": "1", "nome": "A", "duracao_dias": "1", "predecessoras": "2"},
                {"codigo": "2", "nome": "B", "duracao_dias": "1", "predecessoras": "1"},
            ])
        self.assertFalse(self.cronograma.atividades.exists())


class GerarDoOrcamentoTests(BaseCronograma):
    """Do orçamento vêm só etapas (decisão do dono, 10/10/2026): a etapa, quando
    começa, quanto dura em dias úteis do plano, quanto vale e o Hh orçado."""

    def setUp(self):
        super().setUp()
        from moduloorcamento import cronograma as cronograma_do_orcamento, planilha
        from moduloorcamento.models import ItemOrcado, Orcamento
        from obras.models import EtapaObra

        self.fundacao = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Fundação", ordem=1,
        )
        self.estrutura = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Estrutura", ordem=2,
        )
        self.orcamento = Orcamento.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Executivo",
            bdi_percentual=Decimal("0"), data_base=date(2026, 7, 1),
        )
        # A etapa do orçamento é o grupo de 1º nível da planilha; aqui ela está
        # ligada à etapa da obra (vínculo opcional, que o PDCA usa para casar).
        self.grupos = {}
        for ordem, (nome, etapa, valor) in enumerate((
            ("Fundação", self.fundacao, "40000"), ("Estrutura", self.estrutura, "60000"),
        )):
            grupo = ItemOrcado.objects.create(
                tenant=self.tenant, orcamento=self.orcamento, descricao=nome, ordem=ordem,
                tipo_linha=ItemOrcado.TipoLinha.SINTETICO,
            )
            ItemOrcado.objects.create(
                tenant=self.tenant, orcamento=self.orcamento, descricao=f"{nome} — serviço",
                tipo_linha=ItemOrcado.TipoLinha.ANALITICO, pai=grupo, ordem=1,
                quantidade=Decimal("1"), custo_unitario=Decimal(valor),
            )
            self.grupos[nome] = grupo
            cronograma_do_orcamento.vincular_etapa_da_obra(
                self.orcamento, grupo_id=grupo.pk, etapa_id=etapa.pk,
            )
        planilha.recalcular_orcamento(self.orcamento)
        # Fundação no tempo (3 a 14/08: 10 dias úteis); estrutura ainda não.
        cronograma_do_orcamento.planejar_etapa(
            self.orcamento, grupo_id=self.grupos["Fundação"].pk,
            inicio=date(2026, 8, 3), termino=date(2026, 8, 14),
        )
        self.orcamento.refresh_from_db()

    def test_vem_uma_atividade_por_etapa_com_inicio_duracao_e_valor(self):
        resultado = services.gerar_do_orcamento(self.cronograma, orcamento_id=self.orcamento.pk)
        self.assertEqual((resultado["criadas"], resultado["planejadas"], resultado["sem_plano"]), (2, 1, 1))

        fundacao = self.cronograma.atividades.get(etapa=self.fundacao)
        self.assertEqual(fundacao.nao_comecar_antes_de, date(2026, 8, 3))
        self.assertEqual(fundacao.duracao_dias, 10)
        self.assertEqual(fundacao.peso_informado, Decimal("40000"))
        self.assertTrue(fundacao.peso_do_orcamento)
        self.assertIsNone(fundacao.item_orcado_id)
        self.assertEqual(services.peso_de(fundacao), (Decimal("40000.0000"), "orcado"))

        estrutura = self.cronograma.atividades.get(etapa=self.estrutura)
        self.assertEqual(estrutura.duracao_dias, 5)  # duracao_padrao
        self.assertIsNone(estrutura.nao_comecar_antes_de)

        self.cronograma.refresh_from_db()
        self.assertEqual(self.cronograma.orcamento_origem_id, self.orcamento.pk)
        services.calcular_cpm(self.cronograma)

    def test_etapa_sem_vinculo_com_a_obra_tambem_vira_atividade(self):
        """O vínculo com a EtapaObra é opcional: sem ele a atividade nasce sem
        etapa da obra, e o planejador liga no plano."""
        from moduloorcamento import cronograma as cronograma_do_orcamento

        cronograma_do_orcamento.vincular_etapa_da_obra(
            self.orcamento, grupo_id=self.grupos["Estrutura"].pk, etapa_id=None,
        )
        services.gerar_do_orcamento(self.cronograma, orcamento_id=self.orcamento.pk)
        estrutura = self.cronograma.atividades.get(nome="Estrutura")
        self.assertIsNone(estrutura.etapa_id)
        self.assertEqual(estrutura.peso_informado, Decimal("60000"))
        # E a atualização casa pelo nome, sem duplicar.
        resultado = services.atualizar_do_orcamento(self.cronograma, orcamento_id=self.orcamento.pk)
        self.assertEqual(resultado["criadas"], 0)

    def test_simular_nao_escreve(self):
        resultado = services.gerar_do_orcamento(
            self.cronograma, orcamento_id=self.orcamento.pk, simular=True,
        )
        self.assertEqual(resultado["linhas"], 2)
        self.assertFalse(self.cronograma.atividades.exists())

    def test_as_etapas_nao_entram_duas_vezes(self):
        services.gerar_do_orcamento(self.cronograma, orcamento_id=self.orcamento.pk)
        with self.assertRaises(ValidationError):
            services.gerar_do_orcamento(self.cronograma, orcamento_id=self.orcamento.pk)
        self.assertTrue(services.orcamentos_da_obra(self.cronograma)[0]["ja_no_plano"])

    def test_editar_o_cronograma_do_orcamento_avisa_e_atualizar_traz(self):
        from moduloorcamento import cronograma as cronograma_do_orcamento

        services.gerar_do_orcamento(self.cronograma, orcamento_id=self.orcamento.pk)
        self.cronograma.refresh_from_db()
        self.assertFalse(services.situacao_do_orcamento(self.cronograma)["mudou"])

        cronograma_do_orcamento.planejar_etapa(
            self.orcamento, grupo_id=self.grupos["Fundação"].pk,
            inicio=date(2026, 8, 10), termino=date(2026, 8, 14),
        )
        situacao = services.situacao_do_orcamento(self.cronograma)
        self.assertEqual((situacao["mudou"], situacao["motivo"]), (True, "cronograma_editado"))
        self.assertTrue(situacao["pode_atualizar"])

        resultado = services.atualizar_do_orcamento(self.cronograma)
        self.assertEqual(resultado["atualizadas"], 2)
        fundacao = self.cronograma.atividades.get(etapa=self.fundacao)
        self.assertEqual((fundacao.nao_comecar_antes_de, fundacao.duracao_dias), (date(2026, 8, 10), 5))
        self.cronograma.refresh_from_db()
        self.assertFalse(services.situacao_do_orcamento(self.cronograma)["mudou"])

    def test_versao_nova_do_orcamento_avisa(self):
        from moduloorcamento import planilha

        services.gerar_do_orcamento(self.cronograma, orcamento_id=self.orcamento.pk)
        planilha.aprovar_orcamento(self.orcamento)
        nova = planilha.revisar_orcamento(self.orcamento, tipo="aditivo", motivo="Escopo")
        planilha.aprovar_orcamento(nova)
        self.cronograma.refresh_from_db()

        situacao = services.situacao_do_orcamento(self.cronograma)
        self.assertEqual(situacao["motivo"], "nova_versao")
        self.assertEqual(situacao["atualizar_de"], nova.pk)
        resultado = services.atualizar_do_orcamento(self.cronograma)
        self.assertEqual(resultado["versao"], nova.versao)
        self.cronograma.refresh_from_db()
        self.assertEqual(self.cronograma.orcamento_origem_id, nova.pk)

    def test_peso_digitado_deixa_de_ser_do_orcamento(self):
        from modulopdca.serializers import AtividadeSerializer

        services.gerar_do_orcamento(self.cronograma, orcamento_id=self.orcamento.pk)
        fundacao = self.cronograma.atividades.get(etapa=self.fundacao)
        s = AtividadeSerializer(fundacao, data={"peso_informado": "10"}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        fundacao.refresh_from_db()
        self.assertFalse(fundacao.peso_do_orcamento)


class AnexarModeloTests(BaseCronograma):
    def test_o_modelo_entra_no_fim_sem_apagar_nada(self):
        modelo = Cronograma.objects.create(
            tenant=self.tenant, descricao="Padrão", data_inicio=date(2026, 1, 1),
            eh_modelo=True, nome_modelo="Torre padrão",
        )
        base = Atividade.objects.create(
            tenant=self.tenant, cronograma=modelo, codigo="1", nome="Torre",
            profundidade=1,
        )
        Atividade.objects.create(
            tenant=self.tenant, cronograma=modelo, pai=base, codigo="1.1",
            nome="Pavimento", duracao_dias=4, profundidade=2,
        )
        self.atividade("1")
        resultado = services.anexar_modelo(modelo, self.cronograma)
        self.assertEqual(resultado["criadas"], 2)
        self.assertEqual(self.cronograma.atividades.get(nome="Pavimento").codigo, "2.1")


class ApiDaMontagemTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="pdca-montagem", nome="Construtora Monta")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra montada", endereco="Rua 1",
        )
        cls.calendario = CalendarioTrabalho.objects.create(
            tenant=cls.tenant, nome="Comercial", obra=cls.obra,
        )
        cls.usuario = Usuario.objects.create(username="monta", tenant=cls.tenant)

    def setUp(self):
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
        )
        self.um = Atividade.objects.create(
            tenant=self.tenant, cronograma=self.cronograma, codigo="1",
            nome="Fundação", duracao_dias=5, profundidade=1,
        )
        self.usuario.iam_modules = ["pdca"]
        self.usuario.iam_permissions = ["pdca.cronograma.view", "pdca.cronograma.edit"]
        self.client.force_authenticate(user=self.usuario)

    def test_inserir_e_mover_pela_api(self):
        url = f"/api/pdca/cronogramas/{self.cronograma.pk}/inserir-atividade/"
        resposta = self.client.post(url, {"pai": self.um.pk, "nome": "Estacas"}, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        self.assertEqual(resposta.json()["codigo"], "1.1")
        nova = resposta.json()["atividade_id"]
        resposta = self.client.post(
            f"/api/pdca/atividades/{nova}/mover/", {"pai": None, "posicao": 0}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["codigo"], "1")

    def test_so_ver_nao_insere(self):
        self.usuario.iam_permissions = ["pdca.cronograma.view"]
        self.client.force_authenticate(user=self.usuario)
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.cronograma.pk}/inserir-atividade/",
            {"nome": "X"}, format="json",
        )
        self.assertEqual(resposta.status_code, 403)

    def test_importar_e_listar_orcamentos(self):
        resposta = self.client.post(
            f"/api/pdca/cronogramas/{self.cronograma.pk}/importar-linhas/",
            {"linhas": [{"nome": "Colada", "duracao_dias": "2", "predecessoras": "1"}]},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertEqual(resposta.json()["ligacoes"], 1)
        resposta = self.client.get(f"/api/pdca/cronogramas/{self.cronograma.pk}/orcamentos/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), [])


class RestaurarLinhasTests(BaseCronograma):
    """O desfazer da exclusão (decisão do dono, 09/10/2026: o Ctrl+Z vale "até
    eu finalizar o plano")."""

    def _retrato(self, raiz):
        sub = [raiz, *Atividade.objects.filter(pai=raiz)]
        ids = {a.pk for a in sub}
        return {
            "atividades": [
                {"id": a.pk, "pai": a.pai_id, "nome": a.nome, "ordem": a.ordem,
                 "duracao_dias": a.duracao_dias, "eh_marco": a.eh_marco,
                 "local": None, "etapa": None, "item_orcado": None,
                 "calendario": None, "responsavel": None}
                for a in sub
            ],
            "ligacoes": [
                {"origem": p.origem_id, "destino": p.destino_id, "tipo": p.tipo,
                 "atraso_dias": p.atraso_dias}
                for p in Precedencia.objects.filter(Q(origem_id__in=ids) | Q(destino_id__in=ids))
            ],
        }

    def test_a_subarvore_volta_no_mesmo_lugar_com_as_ligacoes(self):
        um = self.atividade("1")
        dois = self.atividade("2", duracao=None)
        filha = self.atividade("2.1", duracao=4, pai=dois)
        tres = self.atividade("3")
        self.ligar(um, filha)
        self.ligar(filha, tres)
        retrato = self._retrato(dois)
        dois.delete()
        services.renumerar_eap(self.cronograma)

        resultado = services.restaurar_linhas(
            self.cronograma, pai_id=None, posicao=1, **retrato,
        )
        nova_filha = Atividade.objects.get(pk=resultado["mapa"][str(filha.pk)])
        self.assertEqual(nova_filha.codigo, "2.1")
        self.assertEqual(nova_filha.duracao_dias, 4)
        self.assertEqual(Atividade.objects.get(pk=tres.pk).codigo, "3")
        self.assertTrue(Precedencia.objects.filter(origem=um, destino=nova_filha).exists())
        self.assertTrue(Precedencia.objects.filter(origem=nova_filha, destino=tres).exists())
        services.calcular_cpm(self.cronograma)

    def test_vinculo_de_outra_obra_volta_vazio(self):
        outra = Obra.objects.create(tenant=self.tenant, nome_obra="Outra", endereco="Rua 2")
        local_alheio = LocalObra.objects.create(
            tenant=self.tenant, obra=outra, codigo="T", nome="Torre alheia",
            nivel=NivelLocal.BLOCO, profundidade=1,
        )
        a = self.atividade("1")
        retrato = self._retrato(a)
        retrato["atividades"][0]["local"] = local_alheio.pk
        antigo = a.pk
        a.delete()
        resultado = services.restaurar_linhas(self.cronograma, pai_id=None, posicao=0, **retrato)
        nova = Atividade.objects.get(pk=resultado["mapa"][str(antigo)])
        self.assertIsNone(nova.local_id)

    def test_pela_api(self):
        from rest_framework.test import APIClient

        usuario = Usuario.objects.create(username="restaura", tenant=self.tenant)
        usuario.iam_modules = ["pdca"]
        usuario.iam_permissions = ["pdca.cronograma.view", "pdca.cronograma.edit"]
        cliente = APIClient()
        cliente.force_authenticate(user=usuario)
        a = self.atividade("1", duracao=3)
        retrato = self._retrato(a)
        antigo = a.pk
        a.delete()
        resposta = cliente.post(
            f"/api/pdca/cronogramas/{self.cronograma.pk}/restaurar-linhas/",
            {"pai": None, "posicao": 0, **retrato}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.assertIn(str(antigo), resposta.json()["mapa"])
