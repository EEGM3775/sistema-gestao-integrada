"""Testes do Orçamento — ORC.0 (base referencial de plataforma + adoção).

Cobre: importação por comando (idempotente, formato brasileiro de número,
detecção de cabeçalho e mapeamento manual), adoção no catálogo do tenant
(idempotente, recursiva, isolada por tenant), a API read-only e o entitlement do
módulo.
"""
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command
from rest_framework.test import APITestCase

from catalogo.models import ComponenteComposicao, Item
from nucleo.models import Tenant, Usuario

from . import services
from .management.commands.importar_base_referencial import (
    detectar_colunas,
    detectar_delimitador,
    normalizar,
    para_decimal,
)
from .models import BaseReferencial, ComposicaoReferenciaItem, Fonte, InsumoReferencia

ORC_PERMS_FULL = [
    "orcamento.base.view", "orcamento.base.adotar",
    "orcamento.orcamento.view", "orcamento.orcamento.edit",
    "orcamento.orcamento.aprovar", "orcamento.orcamento.revisar",
    "orcamento.item.view", "orcamento.item.edit",
    "orcamento.relatorio.view",
]

CSV_INSUMOS = (
    "CÓDIGO;DESCRIÇÃO DO INSUMO;UNIDADE;PREÇO MEDIANO R$;GRUPO\n"
    "1379;CIMENTO PORTLAND COMPOSTO CP II-32;KG;0,58;MATERIAL\n"
    "88309;SERVENTE COM ENCARGOS COMPLEMENTARES;H;19,42;MAO DE OBRA\n"
    "00370;AREIA MEDIA - POSTO JAZIDA;M3;1.234,56;MATERIAL\n"
)

CSV_ANALITICA = (
    "CODIGO DA COMPOSICAO;DESCRICAO DA COMPOSICAO;UNIDADE DA COMPOSICAO;"
    "TIPO DE ITEM;CODIGO DO ITEM;DESCRICAO DO ITEM;UNIDADE DO ITEM;COEFICIENTE\n"
    "92873;CONCRETAGEM DE PILARES FCK 25 MPA;M3;INSUMO;1379;CIMENTO PORTLAND COMPOSTO CP II-32;KG;350,00000\n"
    "92873;CONCRETAGEM DE PILARES FCK 25 MPA;M3;INSUMO;88309;SERVENTE COM ENCARGOS COMPLEMENTARES;H;2,50000\n"
    "92873;CONCRETAGEM DE PILARES FCK 25 MPA;M3;INSUMO;00370;AREIA MEDIA - POSTO JAZIDA;M3;0,50000\n"
)


class OrcamentoTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="orc-a", nome="Construtora A")
        cls.tenant_b = Tenant.objects.create(slug="orc-b", nome="Construtora B")
        cls.user = Usuario.objects.create(username="orcamentista_a", tenant=cls.tenant)

    def autenticar(self, user=None, modules=("orcamento",), perms=ORC_PERMS_FULL):
        user = user or self.user
        user.iam_modules = list(modules)
        user.iam_permissions = list(perms)
        self.client.force_authenticate(user=user)
        return user

    def _base(self, fonte=Fonte.SINAPI, uf="SP", mes=date(2026, 7, 1)):
        return BaseReferencial.objects.create(
            fonte=fonte, uf=uf, mes_referencia=mes,
            regime_encargos=BaseReferencial.Regime.DESONERADO,
        )

    def _ref(self, base, codigo="1379", descricao="CIMENTO CP II-32", unidade="KG",
             tipo=InsumoReferencia.Tipo.INSUMO, custo="0.58"):
        return InsumoReferencia.objects.create(
            base=base, codigo=codigo, descricao=descricao, unidade=unidade,
            tipo=tipo, custo_unitario=Decimal(custo),
        )

    def _escrever(self, pasta: Path, nome: str, conteudo: str) -> Path:
        caminho = pasta / nome
        caminho.write_text(conteudo, encoding="utf-8")
        return caminho


class HelpersDoImportadorTests(OrcamentoTestBase):
    def test_normalizar_remove_acento_e_caixa(self):
        self.assertEqual(normalizar("PREÇO MEDIANO R$"), "preco mediano r$")
        self.assertEqual(normalizar("Descrição\ndo  Insumo"), "descricao do insumo")
        self.assertEqual(normalizar(None), "")

    def test_para_decimal_aceita_formato_brasileiro(self):
        self.assertEqual(para_decimal("1.234,56"), Decimal("1234.56"))
        self.assertEqual(para_decimal("0,58"), Decimal("0.58"))
        self.assertEqual(para_decimal("R$ 19,42"), Decimal("19.42"))
        self.assertEqual(para_decimal(0.58), Decimal("0.58"))
        self.assertEqual(para_decimal(""), Decimal("0"))
        self.assertEqual(para_decimal("não é número"), Decimal("0"))

    def test_delimitador_prefere_ponto_e_virgula_sobre_virgula_decimal(self):
        """Regressão: `csv.Sniffer` elegia a vírgula DECIMAL como delimitador em
        `1379;CIMENTO;KG;0,58` e partia a última coluna em duas, sem erro."""
        self.assertEqual(detectar_delimitador("1379;CIMENTO;KG;0,58\n"), ";")
        self.assertEqual(detectar_delimitador("codigo,descricao,unidade,preco\n"), ",")
        self.assertEqual(detectar_delimitador("1379\tCIMENTO\tKG\t0,58\n"), "\t")

    def test_detectar_colunas_encontra_cabecalho_fora_da_primeira_linha(self):
        linhas = [
            ["SINAPI - Sistema Nacional de Pesquisa de Custos e Índices"],
            [],
            ["CÓDIGO", "DESCRIÇÃO DO INSUMO", "UNIDADE", "PREÇO MEDIANO R$"],
            ["1379", "CIMENTO", "KG", "0,58"],
        ]
        mapa, indice, _ = detectar_colunas(linhas, ("codigo", "descricao", "unidade", "preco"))
        self.assertEqual(indice, 2)
        self.assertEqual(mapa["codigo"], 0)
        self.assertEqual(mapa["preco"], 3)

    def test_detectar_colunas_devolve_cabecalhos_vistos_quando_falha(self):
        linhas = [["COLUNA A", "COLUNA B"], ["1", "2"]]
        mapa, _, vistos = detectar_colunas(linhas, ("codigo", "descricao", "unidade", "preco"))
        self.assertIsNone(mapa)
        self.assertIn("coluna a", vistos[0])


class ImportacaoTests(OrcamentoTestBase):
    def _importar(self, pasta, **extra):
        saida = StringIO()
        opcoes = {
            "fonte": "sinapi", "uf": "SP", "mes": "2026-07", "regime": "desonerado",
            "stdout": saida,
        }
        opcoes.update(extra)
        call_command("importar_base_referencial", **opcoes)
        return saida.getvalue()

    def test_importa_insumos_criando_publicacao(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            arquivo = self._escrever(pasta, "insumos.csv", CSV_INSUMOS)
            self._importar(pasta, insumos=str(arquivo))

        base = BaseReferencial.objects.get(fonte="sinapi", uf="SP", mes_referencia=date(2026, 7, 1))
        self.assertEqual(base.total_insumos, 3)
        self.assertEqual(base.rotulo, "SINAPI SP 07/2026 desonerado")
        cimento = InsumoReferencia.objects.get(base=base, codigo="1379")
        self.assertEqual(cimento.custo_unitario, Decimal("0.5800"))
        self.assertEqual(cimento.unidade, "KG")
        areia = InsumoReferencia.objects.get(base=base, codigo="00370")
        self.assertEqual(areia.custo_unitario, Decimal("1234.5600"))

    def test_reimportar_atualiza_sem_duplicar(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            arquivo = self._escrever(pasta, "insumos.csv", CSV_INSUMOS)
            self._importar(pasta, insumos=str(arquivo))
            reajustado = CSV_INSUMOS.replace("0,58", "0,67")
            arquivo.write_text(reajustado, encoding="utf-8")
            saida = self._importar(pasta, insumos=str(arquivo))

        self.assertEqual(BaseReferencial.objects.count(), 1)
        self.assertEqual(InsumoReferencia.objects.count(), 3)
        self.assertEqual(
            InsumoReferencia.objects.get(codigo="1379").custo_unitario, Decimal("0.6700")
        )
        self.assertIn("0 novos, 3 atualizados", saida)

    def test_analitica_cria_composicao_e_componentes(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            insumos = self._escrever(pasta, "insumos.csv", CSV_INSUMOS)
            analitica = self._escrever(pasta, "analitica.csv", CSV_ANALITICA)
            self._importar(pasta, insumos=str(insumos), analitica=str(analitica))

        base = BaseReferencial.objects.get()
        self.assertEqual(base.total_composicoes, 1)
        composicao = InsumoReferencia.objects.get(tipo=InsumoReferencia.Tipo.COMPOSICAO)
        self.assertEqual(composicao.codigo, "92873")
        self.assertEqual(composicao.unidade, "M3")
        componentes = ComposicaoReferenciaItem.objects.filter(composicao=composicao)
        self.assertEqual(componentes.count(), 3)
        cimento = componentes.get(filho__codigo="1379")
        self.assertEqual(cimento.coeficiente, Decimal("350.00000"))

    def test_reimportar_analitica_substitui_componentes(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            insumos = self._escrever(pasta, "insumos.csv", CSV_INSUMOS)
            analitica = self._escrever(pasta, "analitica.csv", CSV_ANALITICA)
            self._importar(pasta, insumos=str(insumos), analitica=str(analitica))
            # A publicação nova tirou a areia da composição.
            reduzida = "\n".join(
                l for l in CSV_ANALITICA.strip().split("\n") if ";00370;" not in l
            ) + "\n"
            analitica.write_text(reduzida, encoding="utf-8")
            self._importar(pasta, insumos=str(insumos), analitica=str(analitica))

        composicao = InsumoReferencia.objects.get(tipo=InsumoReferencia.Tipo.COMPOSICAO)
        self.assertEqual(ComposicaoReferenciaItem.objects.filter(composicao=composicao).count(), 2)

    def test_dry_run_nao_grava_itens(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            arquivo = self._escrever(pasta, "insumos.csv", CSV_INSUMOS)
            saida = self._importar(pasta, insumos=str(arquivo), dry_run=True)

        self.assertEqual(InsumoReferencia.objects.count(), 0)
        self.assertIn("nada foi gravado", saida)

    def test_cabecalho_irreconhecivel_falha_dizendo_o_que_viu(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            arquivo = self._escrever(pasta, "estranho.csv", "A;B;C\n1;2;3\n")
            with self.assertRaises(CommandError) as ctx:
                self._importar(pasta, insumos=str(arquivo))
        self.assertIn("Não reconheci o cabeçalho", str(ctx.exception))
        self.assertIn("--colunas", str(ctx.exception))

    def test_colunas_manuais_vencem_a_deteccao(self):
        conteudo = "1379;CIMENTO CP II-32;KG;0,58\n"  # sem cabeçalho algum
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            arquivo = self._escrever(pasta, "sem_cabecalho.csv", conteudo)
            self._importar(
                pasta, insumos=str(arquivo),
                colunas="codigo=1,descricao=2,unidade=3,preco=4",
            )
        self.assertEqual(InsumoReferencia.objects.get().codigo, "1379")

    def test_exige_ao_menos_um_arquivo(self):
        with self.assertRaises(CommandError):
            call_command(
                "importar_base_referencial", fonte="sinapi", mes="2026-07", stdout=StringIO()
            )

    def test_mes_invalido_falha(self):
        with TemporaryDirectory() as tmp:
            arquivo = self._escrever(Path(tmp), "insumos.csv", CSV_INSUMOS)
            with self.assertRaises(CommandError):
                call_command(
                    "importar_base_referencial", fonte="sinapi", mes="julho de 2026",
                    insumos=str(arquivo), stdout=StringIO(),
                )


class AdocaoTests(OrcamentoTestBase):
    def test_adota_insumo_como_material_com_seam_preenchido(self):
        base = self._base()
        ref = self._ref(base)
        item = services.adotar_no_catalogo(ref, self.tenant.id)

        self.assertEqual(item.codigo_interno, "SINAPI-1379")
        self.assertEqual(item.tipo, Item.Tipo.MATERIAL)
        self.assertEqual(item.fonte_referencia, "sinapi")
        self.assertEqual(item.codigo_referencia, "1379")
        self.assertTrue(item.compravel)
        self.assertTrue(item.estocavel)
        self.assertEqual(item.tenant_id, self.tenant.id)

    def test_adota_mao_de_obra_como_servico_nao_estocavel(self):
        base = self._base()
        ref = self._ref(base, codigo="88309", descricao="SERVENTE", unidade="H")
        item = services.adotar_no_catalogo(ref, self.tenant.id)

        self.assertEqual(item.tipo, Item.Tipo.SERVICO)
        self.assertFalse(item.estocavel)
        self.assertFalse(item.compravel)

    def test_adocao_e_idempotente_e_atualiza_descricao(self):
        base = self._base()
        ref = self._ref(base)
        primeiro = services.adotar_no_catalogo(ref, self.tenant.id)
        ref.descricao = "CIMENTO PORTLAND CP II-32 (revisado)"
        ref.save()
        segundo = services.adotar_no_catalogo(ref, self.tenant.id)

        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(Item.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(segundo.descricao, "CIMENTO PORTLAND CP II-32 (revisado)")

    def test_readocao_nao_desfaz_decisao_da_empresa_nas_flags(self):
        base = self._base()
        ref = self._ref(base)
        item = services.adotar_no_catalogo(ref, self.tenant.id)
        item.estocavel = False  # a empresa decidiu que não controla estoque disso
        item.save()

        services.adotar_no_catalogo(ref, self.tenant.id)
        item.refresh_from_db()
        self.assertFalse(item.estocavel)

    def test_adota_composicao_com_componentes(self):
        base = self._base()
        composicao = self._ref(
            base, codigo="92873", descricao="CONCRETAGEM DE PILARES", unidade="M3",
            tipo=InsumoReferencia.Tipo.COMPOSICAO, custo="450.00",
        )
        cimento = self._ref(base)
        servente = self._ref(base, codigo="88309", descricao="SERVENTE", unidade="H", custo="19.42")
        ComposicaoReferenciaItem.objects.create(
            composicao=composicao, filho=cimento, coeficiente=Decimal("350"))
        ComposicaoReferenciaItem.objects.create(
            composicao=composicao, filho=servente, coeficiente=Decimal("2.5"))

        item = services.adotar_no_catalogo(composicao, self.tenant.id)

        self.assertEqual(item.tipo, Item.Tipo.COMPOSICAO)
        self.assertFalse(item.estocavel)
        componentes = ComponenteComposicao.objects.filter(item_pai=item)
        self.assertEqual(componentes.count(), 2)
        self.assertEqual(
            componentes.get(item_filho__codigo_interno="SINAPI-1379").coeficiente,
            Decimal("350.00000"),
        )
        # Os insumos da composição também entraram no catálogo da empresa.
        self.assertEqual(Item.objects.filter(tenant=self.tenant).count(), 3)

    def test_adocao_nao_recursiva_ignora_componentes(self):
        base = self._base()
        composicao = self._ref(
            base, codigo="92873", tipo=InsumoReferencia.Tipo.COMPOSICAO, unidade="M3")
        cimento = self._ref(base)
        ComposicaoReferenciaItem.objects.create(
            composicao=composicao, filho=cimento, coeficiente=Decimal("350"))

        item = services.adotar_no_catalogo(composicao, self.tenant.id, recursivo=False)
        self.assertEqual(ComponenteComposicao.objects.filter(item_pai=item).count(), 0)

    def test_adocao_e_por_tenant(self):
        base = self._base()
        ref = self._ref(base)
        services.adotar_no_catalogo(ref, self.tenant.id)
        services.adotar_no_catalogo(ref, self.tenant_b.id)

        self.assertEqual(Item.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(Item.objects.filter(tenant=self.tenant_b).count(), 1)
        self.assertEqual(
            Item.objects.filter(codigo_interno="SINAPI-1379").count(), 2  # um por empresa
        )

    def test_referencia_sem_unidade_e_recusada(self):
        base = self._base()
        ref = self._ref(base, unidade="")
        with self.assertRaises(services.AdocaoInvalida):
            services.adotar_no_catalogo(ref, self.tenant.id)


class EntitlementTests(OrcamentoTestBase):
    def test_sem_modulo_orcamento_recebe_403(self):
        self.autenticar(modules=[])
        self.assertEqual(self.client.get("/api/orcamento/bases/").status_code, 403)

    def test_com_modulo_sem_permissao_recebe_403(self):
        self.autenticar(modules=["orcamento"], perms=[])
        self.assertEqual(self.client.get("/api/orcamento/bases/").status_code, 403)

    def test_com_modulo_e_permissao_recebe_200(self):
        self.autenticar()
        self.assertEqual(self.client.get("/api/orcamento/bases/").status_code, 200)

    def test_adotar_exige_permissao_propria(self):
        base = self._base()
        ref = self._ref(base)
        self.autenticar(perms=["orcamento.base.view"])  # vê a base, não adota
        resp = self.client.post(f"/api/orcamento/referencias/{ref.pk}/adotar/")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Item.objects.count(), 0)


class ApiBaseReferencialTests(OrcamentoTestBase):
    def setUp(self):
        self.autenticar()
        self.base = self._base()
        self.cimento = self._ref(self.base)
        self.composicao = self._ref(
            self.base, codigo="92873", descricao="CONCRETAGEM DE PILARES FCK 25",
            unidade="M3", tipo=InsumoReferencia.Tipo.COMPOSICAO, custo="450.00",
        )
        ComposicaoReferenciaItem.objects.create(
            composicao=self.composicao, filho=self.cimento, coeficiente=Decimal("350"))

    def test_base_e_read_only(self):
        self.assertEqual(self.client.post("/api/orcamento/bases/", {}).status_code, 405)
        self.assertEqual(
            self.client.delete(f"/api/orcamento/bases/{self.base.pk}/").status_code, 405
        )
        self.assertEqual(
            self.client.patch(f"/api/orcamento/referencias/{self.cimento.pk}/", {}).status_code, 405
        )

    def test_busca_por_descricao(self):
        resp = self.client.get("/api/orcamento/referencias/?search=concretagem")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["codigo"], "92873")

    def test_lista_marca_o_que_ja_foi_adotado(self):
        resp = self.client.get("/api/orcamento/referencias/?search=cimento")
        self.assertIsNone(resp.data["results"][0]["adotado_item_id"])

        item = services.adotar_no_catalogo(self.cimento, self.tenant.id)
        resp = self.client.get("/api/orcamento/referencias/?search=cimento")
        self.assertEqual(resp.data["results"][0]["adotado_item_id"], item.item_id)

    def test_composicao_devolve_analitica_com_parcela_de_custo(self):
        resp = self.client.get(f"/api/orcamento/referencias/{self.composicao.pk}/composicao/")
        self.assertEqual(resp.status_code, 200)
        componente = resp.data["componentes"][0]
        self.assertEqual(componente["filho_codigo"], "1379")
        # 350 × 0,58 = 203,00 — a memória de cálculo do preço.
        self.assertEqual(Decimal(componente["custo_no_item"]), Decimal("203.0000"))

    def test_adotar_pela_api_cria_item_no_catalogo(self):
        resp = self.client.post(f"/api/orcamento/referencias/{self.composicao.pk}/adotar/")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["codigo_interno"], "SINAPI-92873")
        self.assertEqual(resp.data["componentes"], 1)
        self.assertTrue(Item.objects.filter(tenant=self.tenant, codigo_interno="SINAPI-92873").exists())

    def test_adotar_lote(self):
        resp = self.client.post(
            "/api/orcamento/referencias/adotar-lote/",
            {"referencias": [self.cimento.pk, self.composicao.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["adotados"], 2)

    def test_adotar_lote_sem_ids_e_400(self):
        resp = self.client.post("/api/orcamento/referencias/adotar-lote/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_resumo_conta_itens_e_adotados(self):
        services.adotar_no_catalogo(self.cimento, self.tenant.id)
        resp = self.client.get("/api/orcamento/bases-resumo/")
        self.assertEqual(resp.status_code, 200)
        linha = resp.data[0]
        self.assertEqual(linha["insumos"], 1)
        self.assertEqual(linha["composicoes"], 1)
        self.assertEqual(linha["adotados_no_catalogo"], 1)
        self.assertEqual(linha["rotulo"], "SINAPI SP 07/2026 desonerado")

    def test_status_do_modulo(self):
        resp = self.client.get("/api/orcamento/status/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["modulo"], "orcamento")
        self.assertEqual(resp.data["bases_referenciais"], 1)
