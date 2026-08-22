"""D110 e D111 — o código para de tratar "mesmo número" como "mesmo insumo".

**D110.** Adoção e reclassificação casavam o `catalogo.Item` do tenant com a
publicação **só pelo código** e não conferiam mais nada. Enquanto for a SINAPI —
estável nos códigos — funciona; quando a fonte reaproveita o número entre
edições (tabela de prefeitura faz isso), o item do catálogo passa a se chamar
outra coisa **carregando o histórico do anterior**, e as composições e linhas
orçadas que o referenciam continuam apontando. A régua do dono: *divergiu, não
classifica e não sobrescreve — reporta*.

**D111.** A coluna `Classificação` só existe nas publicações a partir de
01/2025. Para quem carregou uma anterior não há o que reler, e todo insumo que
não é hora nem mês vira material. O comando não passa a adivinhar pela descrição
(seria o palpite que produziu o D109) — passa a **declarar** o buraco e a aceitar
a classificação que a empresa fizer à mão, em `--de-para`.
"""
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from catalogo.models import ComponenteComposicao, Item

from . import bancos, identidade, services
from .management.commands.reclassificar_itens_catalogo import Command
from .models import (
    BancoPreco,
    BaseReferencial,
    ComponenteBancoPreco,
    ComposicaoReferenciaItem,
    Fonte,
    InsumoReferencia,
    ItemBancoPreco,
)
from .tests import OrcamentoTestBase


class SemelhancaTests(SimpleTestCase):
    """A pergunta isolada do banco: estas duas linhas falam do mesmo insumo?"""

    def test_republicacao_com_outra_redacao_continua_sendo_o_mesmo_item(self):
        """O caso que a comparação por igualdade quebraria: a fonte reescreve a
        descrição entre edições sem trocar o insumo."""
        self.assertIsNone(identidade.conferir(
            descricao_catalogo="CIMENTO PORTLAND CP II-32",
            unidade_catalogo="KG",
            descricao_publicacao="CIMENTO PORTLAND COMPOSTO CP II-32",
            unidade_publicacao="kg",
        ))

    def test_codigo_reaproveitado_para_outro_insumo_e_divergencia(self):
        """O D110 em uma linha: o `1379` que era cimento virou betoneira."""
        divergencia = identidade.conferir(
            descricao_catalogo="CIMENTO PORTLAND CP II-32",
            unidade_catalogo="KG",
            descricao_publicacao="LOCACAO DE BETONEIRA 400L",
            unidade_publicacao="H",
        )
        self.assertIsNotNone(divergencia)
        self.assertEqual(divergencia.motivo, "descrição e unidade")
        self.assertEqual(divergencia.semelhanca, 0.0)

    def test_so_a_unidade_mudando_ja_e_divergencia(self):
        """Mesma descrição, unidade outra: o coeficiente da composição foi
        escrito contra a régua antiga, e trocá-la em silêncio muda o preço."""
        divergencia = identidade.conferir(
            descricao_catalogo="AREIA MEDIA - POSTO JAZIDA", unidade_catalogo="M3",
            descricao_publicacao="AREIA MEDIA - POSTO JAZIDA", unidade_publicacao="SC",
        )
        self.assertIsNotNone(divergencia)
        self.assertEqual(divergencia.motivo, "unidade")

    def test_grafia_alternativa_da_mesma_unidade_nao_acusa(self):
        """`m³`/`M3` e `UND`/`UN` são a mesma unidade escrita de dois jeitos —
        acusar aqui seria enxurrada de falso positivo, e guarda que grita errado
        para de ser lida."""
        for cat, pub in (("m³", "M3"), ("UND", "un"), ("Hora", "H"), ("m²", "M2")):
            with self.subTest(unidade=f"{cat}×{pub}"):
                self.assertIsNone(identidade.conferir(
                    descricao_catalogo="AREIA MEDIA", unidade_catalogo=cat,
                    descricao_publicacao="AREIA MEDIA", unidade_publicacao=pub,
                ))

    def test_lado_sem_informacao_nao_e_divergencia(self):
        """Item antigo sem descrição gravada não *discorda* de nada — ele calou."""
        self.assertIsNone(identidade.conferir(
            descricao_catalogo="", unidade_catalogo="",
            descricao_publicacao="CIMENTO PORTLAND CP II-32", unidade_publicacao="KG",
        ))

    def test_palavras_de_ligacao_nao_aproximam_descricoes_alheias(self):
        """Sem descartar "de"/"com", duas descrições longas e sem relação
        pareceriam parentes só por compartilharem preposição."""
        self.assertLess(
            identidade.semelhanca(
                "TUBO DE PVC COM JUNTA ELASTICA DE 100 MM",
                "PLACA DE SINALIZACAO DE OBRA COM PEDESTAL",
            ),
            identidade.LIMIAR_SEMELHANCA,
        )


class AdocaoConfereIdentidadeTests(OrcamentoTestBase):
    """A adoção deixa de sobrescrever o item que não é o item."""

    def setUp(self):
        self.edicao_antiga = self._base(mes=date(2024, 10, 1))
        self.cimento = self._ref(
            self.edicao_antiga, codigo="1379",
            descricao="CIMENTO PORTLAND CP II-32", unidade="KG",
        )

    def _edicao_nova_reaproveitando_o_codigo(self):
        """A edição seguinte da mesma fonte, em que o `1379` é outra coisa."""
        nova = self._base(mes=date(2026, 1, 1))
        return self._ref(
            nova, codigo="1379", descricao="LOCACAO DE BETONEIRA 400L",
            unidade="H", custo="12.50",
        )

    def test_readocao_de_codigo_reaproveitado_nao_sobrescreve(self):
        item = services.adotar_no_catalogo(self.cimento, self.tenant.id)
        betoneira = self._edicao_nova_reaproveitando_o_codigo()

        with self.assertRaises(services.IdentidadeDivergente) as capturado:
            services.adotar_no_catalogo(betoneira, self.tenant.id)

        item.refresh_from_db()
        self.assertEqual(item.descricao, "CIMENTO PORTLAND CP II-32")
        self.assertEqual(item.unidade, "KG")
        self.assertEqual(capturado.exception.item.pk, item.pk)
        self.assertEqual(capturado.exception.divergencia.motivo, "descrição e unidade")

    def test_o_que_ja_referenciava_o_item_continua_apontando_para_o_mesmo_insumo(self):
        """O dano do D110 não é a descrição errada — é a composição e a linha
        orçada seguirem apontando para um item que virou outro por baixo."""
        cimento_no_catalogo = services.adotar_no_catalogo(self.cimento, self.tenant.id)
        composicao = Item.objects.create(
            tenant=self.tenant, codigo_interno="PROPRIA-CONCRETO",
            descricao="CONCRETO USINADO", unidade="M3", tipo=Item.Tipo.COMPOSICAO,
        )
        ComponenteComposicao.objects.create(
            tenant=self.tenant, item_pai=composicao, item_filho=cimento_no_catalogo,
            coeficiente=Decimal("350"),
        )

        with self.assertRaises(services.IdentidadeDivergente):
            services.adotar_no_catalogo(
                self._edicao_nova_reaproveitando_o_codigo(), self.tenant.id
            )

        componente = ComponenteComposicao.objects.get(item_pai=composicao)
        self.assertEqual(componente.item_filho.descricao, "CIMENTO PORTLAND CP II-32")

    def test_forcar_e_a_decisao_de_quem_olhou_os_dois_lados(self):
        item = services.adotar_no_catalogo(self.cimento, self.tenant.id)
        betoneira = self._edicao_nova_reaproveitando_o_codigo()

        services.adotar_no_catalogo(betoneira, self.tenant.id, forcar=True)
        item.refresh_from_db()
        self.assertEqual(item.descricao, "LOCACAO DE BETONEIRA 400L")
        self.assertEqual(item.unidade, "H")

    def test_republicacao_legitima_continua_atualizando(self):
        """A guarda não pode custar a idempotência: mesma coisa, outra redação,
        atualiza como sempre atualizou."""
        item = services.adotar_no_catalogo(self.cimento, self.tenant.id)
        self.cimento.descricao = "CIMENTO PORTLAND COMPOSTO CP II-32"
        self.cimento.save(update_fields=["descricao"])

        services.adotar_no_catalogo(self.cimento, self.tenant.id)
        item.refresh_from_db()
        self.assertEqual(item.descricao, "CIMENTO PORTLAND COMPOSTO CP II-32")

    def test_item_adotado_guarda_a_edicao_de_onde_veio(self):
        item = services.adotar_no_catalogo(self.cimento, self.tenant.id)
        self.assertEqual(item.publicacao_referencia, "SINAPI SP 10/2024 desonerado")

    def test_a_procedencia_acompanha_a_edicao_na_readocao(self):
        """Os itens adotados antes do campo existir ficam com ele vazio, e por
        decisão não há backfill — inferir a edição seria inventar procedência.
        O que **precisa** valer é isto: a próxima adoção preenche, e uma
        republicação legítima move o rótulo para a edição nova."""
        item = services.adotar_no_catalogo(self.cimento, self.tenant.id)
        Item.objects.filter(pk=item.pk).update(publicacao_referencia="")

        nova = self._base(mes=date(2026, 1, 1))
        republicado = self._ref(
            nova, codigo="1379", descricao="CIMENTO PORTLAND CP II-32", unidade="KG",
        )
        services.adotar_no_catalogo(republicado, self.tenant.id)

        item.refresh_from_db()
        self.assertEqual(item.publicacao_referencia, "SINAPI SP 01/2026 desonerado")

    def test_lote_separa_o_que_entrou_do_que_ficou_de_fora(self):
        services.adotar_no_catalogo(self.cimento, self.tenant.id)
        betoneira = self._edicao_nova_reaproveitando_o_codigo()
        areia = self._ref(
            betoneira.base, codigo="00370", descricao="AREIA MEDIA - POSTO JAZIDA",
            unidade="M3", custo="90.00",
        )

        resultado = services.adotar_muitos([betoneira, areia], self.tenant.id)

        self.assertEqual(len(resultado.adotados), 1)
        self.assertEqual(resultado.adotados[0].codigo_interno, "SINAPI-00370")
        self.assertEqual(len(resultado.divergentes), 1)
        self.assertEqual(resultado.divergentes[0]["codigo"], "1379")
        self.assertEqual(resultado.divergentes[0]["motivo"], "descrição e unidade")

    def test_composicao_com_componente_divergente_nao_grava_nada(self):
        """Composição cujo insumo não é o que ela pensa que é não tem memória de
        cálculo válida — e adotá-la pela metade deixaria pai apontando filho
        errado, que é o D110 com outro nome."""
        services.adotar_no_catalogo(self.cimento, self.tenant.id)
        nova = self._base(mes=date(2026, 1, 1))
        composicao = self._ref(
            nova, codigo="92873", descricao="CONCRETAGEM DE PILARES FCK 25 MPA",
            unidade="M3", tipo=InsumoReferencia.Tipo.COMPOSICAO, custo="450.00",
        )
        betoneira = self._ref(
            nova, codigo="1379", descricao="LOCACAO DE BETONEIRA 400L", unidade="H",
        )
        ComposicaoReferenciaItem.objects.create(
            composicao=composicao, filho=betoneira, coeficiente=Decimal("1"))

        with self.assertRaises(services.IdentidadeDivergente):
            services.adotar_no_catalogo(composicao, self.tenant.id)

        self.assertFalse(
            Item.objects.filter(tenant=self.tenant, codigo_interno="SINAPI-92873").exists()
        )


class AdocaoDeBancoConfereIdentidadeTests(OrcamentoTestBase):
    """Mesma guarda no banco próprio — onde o risco é maior, e não menor: é ali
    que entram as tabelas de prefeitura, que são as que reaproveitam código."""

    def setUp(self):
        self.banco = BancoPreco.objects.create(
            tenant=self.tenant, nome="Prefeitura 2025", fonte=Fonte.PROPRIA,
        )
        self.cimento = ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="1379",
            descricao="CIMENTO PORTLAND CP II-32", unidade="KG",
            custo_unitario=Decimal("0.58"),
        )

    def test_item_do_banco_com_codigo_reaproveitado_nao_sobrescreve(self):
        adotado = bancos.adotar_no_catalogo(self.cimento, self.tenant.id)
        self.assertEqual(adotado.publicacao_referencia, "Prefeitura 2025")

        self.cimento.descricao = "LOCACAO DE BETONEIRA 400L"
        self.cimento.unidade = "H"
        self.cimento.save(update_fields=["descricao", "unidade"])

        with self.assertRaises(bancos.IdentidadeDivergente):
            bancos.adotar_no_catalogo(self.cimento, self.tenant.id)
        adotado.refresh_from_db()
        self.assertEqual(adotado.descricao, "CIMENTO PORTLAND CP II-32")

    def test_lote_do_banco_reporta_divergente_sem_derrubar_o_resto(self):
        bancos.adotar_no_catalogo(self.cimento, self.tenant.id)
        self.cimento.descricao = "LOCACAO DE BETONEIRA 400L"
        self.cimento.unidade = "H"
        self.cimento.save(update_fields=["descricao", "unidade"])
        areia = ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="00370",
            descricao="AREIA MEDIA", unidade="M3", custo_unitario=Decimal("90"),
        )

        resultado = bancos.adotar_muitos([self.cimento, areia], self.tenant.id)
        self.assertEqual(len(resultado.adotados), 1)
        self.assertEqual(len(resultado.divergentes), 1)

    def test_composicao_do_banco_com_componente_divergente_nao_grava(self):
        bancos.adotar_no_catalogo(self.cimento, self.tenant.id)
        self.cimento.descricao = "LOCACAO DE BETONEIRA 400L"
        self.cimento.unidade = "H"
        self.cimento.save(update_fields=["descricao", "unidade"])
        composicao = ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="92873",
            descricao="CONCRETAGEM DE PILARES", unidade="M3",
            tipo=InsumoReferencia.Tipo.COMPOSICAO, custo_unitario=Decimal("450"),
        )
        ComponenteBancoPreco.objects.create(
            tenant=self.tenant, composicao=composicao, filho=self.cimento,
            coeficiente=Decimal("350"),
        )

        with self.assertRaises(bancos.IdentidadeDivergente):
            bancos.adotar_no_catalogo(composicao, self.tenant.id)
        self.assertFalse(
            Item.objects.filter(tenant=self.tenant, codigo_referencia="92873").exists()
        )


class ApiAdocaoDivergenteTests(OrcamentoTestBase):
    """409 e não 400: nada está errado com o pedido — o conflito é de identidade,
    e a resposta traz os dois lados para quem está na tela decidir."""

    def setUp(self):
        self.autenticar()
        self.antiga = self._base(mes=date(2024, 10, 1))
        self.cimento = self._ref(
            self.antiga, codigo="1379", descricao="CIMENTO PORTLAND CP II-32", unidade="KG",
        )
        services.adotar_no_catalogo(self.cimento, self.tenant.id)
        self.nova = self._base(mes=date(2026, 1, 1))
        self.betoneira = self._ref(
            self.nova, codigo="1379", descricao="LOCACAO DE BETONEIRA 400L", unidade="H",
        )

    def test_adotar_devolve_409_com_os_dois_lados(self):
        resp = self.client.post(f"/api/orcamento/referencias/{self.betoneira.pk}/adotar/")
        self.assertEqual(resp.status_code, 409, resp.content)
        divergencia = resp.data["divergencia"]
        self.assertEqual(divergencia["descricao_catalogo"], "CIMENTO PORTLAND CP II-32")
        self.assertEqual(divergencia["descricao_publicacao"], "LOCACAO DE BETONEIRA 400L")
        self.assertEqual(divergencia["unidade_catalogo"], "KG")
        self.assertEqual(divergencia["unidade_publicacao"], "H")

    def test_forcar_pela_api_aplica(self):
        resp = self.client.post(
            f"/api/orcamento/referencias/{self.betoneira.pk}/adotar/",
            {"forcar": True}, format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["descricao"], "LOCACAO DE BETONEIRA 400L")

    def test_lote_devolve_os_divergentes_junto_com_os_adotados(self):
        areia = self._ref(
            self.nova, codigo="00370", descricao="AREIA MEDIA", unidade="M3", custo="90",
        )
        resp = self.client.post(
            "/api/orcamento/referencias/adotar-lote/",
            {"referencias": [self.betoneira.pk, areia.pk]}, format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["adotados"], 1)
        self.assertEqual(len(resp.data["divergentes"]), 1)
        self.assertEqual(resp.data["divergentes"][0]["codigo"], "1379")


class ReclassificacaoConfereIdentidadeTests(OrcamentoTestBase):
    """O comando deixa de casar por código e de deixar o último lido vencer."""

    def setUp(self):
        self.antiga = self._base(mes=date(2024, 10, 1))
        self.nova = self._base(mes=date(2026, 1, 1))

    def _rodar(self, **extra) -> str:
        saida = StringIO()
        call_command(
            "reclassificar_itens_catalogo", tenant=self.tenant.slug,
            sem_recalculo=True, stdout=saida, **extra,
        )
        return saida.getvalue()

    def _item(self, **campos):
        padroes = dict(
            tenant=self.tenant, codigo_interno="SINAPI-1379",
            descricao="CIMENTO PORTLAND CP II-32", unidade="KG",
            tipo=Item.Tipo.MATERIAL, codigo_referencia="1379", fonte_referencia="sinapi",
        )
        padroes.update(campos)
        return Item.objects.create(**padroes)

    def test_classificacao_vem_da_publicacao_que_confere_e_nao_da_ultima_lida(self):
        """As duas edições trazem o `1379`; só uma delas é este insumo. Antes, a
        última lida vencia e o cimento saía carimbado de equipamento."""
        item = self._item(tipo=Item.Tipo.SERVICO)
        cimento = self._ref(
            self.antiga, codigo="1379", descricao="CIMENTO PORTLAND CP II-32", unidade="KG",
        )
        cimento.grupo = "MATERIAL"
        cimento.save(update_fields=["grupo"])
        betoneira = self._ref(
            self.nova, codigo="1379", descricao="LOCACAO DE BETONEIRA 400L", unidade="H",
        )
        betoneira.grupo = "EQUIPAMENTO (LOCAÇÃO)"
        betoneira.save(update_fields=["grupo"])

        self._rodar()
        item.refresh_from_db()
        # A edição nova é a última lida e diria "equipamento"; quem confere com
        # o item é a antiga, e é ela que classifica.
        self.assertEqual(item.tipo, Item.Tipo.MATERIAL)

    def test_quando_nenhuma_publicacao_confere_nada_e_aplicado(self):
        item = self._item()
        betoneira = self._ref(
            self.nova, codigo="1379", descricao="LOCACAO DE BETONEIRA 400L", unidade="H",
        )
        betoneira.grupo = "EQUIPAMENTO (LOCAÇÃO)"
        betoneira.save(update_fields=["grupo"])

        saida = self._rodar()
        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.MATERIAL)
        self.assertIn("Não confere", saida)
        self.assertIn("1379", saida)

    def test_publicacoes_que_conferem_e_discordam_viram_ambiguidade(self):
        """Duas edições afirmando coisas diferentes sobre o **mesmo** item é
        pergunta para gente. Sortear uma seria o D110 de novo, com sorte."""
        item = self._item(tipo=Item.Tipo.SERVICO)
        for base, grupo in ((self.antiga, "MATERIAL"), (self.nova, "EQUIPAMENTO")):
            ref = self._ref(
                base, codigo="1379", descricao="CIMENTO PORTLAND CP II-32", unidade="KG",
            )
            ref.grupo = grupo
            ref.save(update_fields=["grupo"])

        saida = self._rodar()
        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.SERVICO)
        self.assertIn("Ambíguos", saida)

    def test_classificacao_que_confere_e_aplicada_normalmente(self):
        """A guarda não pode custar o que o ORC.9 entregou."""
        item = self._item(
            descricao="ESCAVADEIRA HIDRAULICA SOBRE ESTEIRAS", unidade="UN",
            codigo_interno="SINAPI-90777", codigo_referencia="90777",
        )
        ref = self._ref(
            self.nova, codigo="90777",
            descricao="ESCAVADEIRA HIDRAULICA SOBRE ESTEIRAS", unidade="UN",
        )
        ref.grupo = "EQUIPAMENTO (AQUISIÇÃO)"
        ref.save(update_fields=["grupo"])

        self._rodar()
        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.EQUIPAMENTO)


class PublicacaoSemClassificacaoTests(OrcamentoTestBase):
    """D111 — publicação anterior a 01/2025 não classifica insumo."""

    def setUp(self):
        self.base_2024 = self._base(mes=date(2024, 10, 1))

    def _rodar(self, **extra) -> str:
        saida = StringIO()
        call_command(
            "reclassificar_itens_catalogo", tenant=self.tenant.slug,
            sem_recalculo=True, stdout=saida, **extra,
        )
        return saida.getvalue()

    def _escavadeira(self):
        Item.objects.create(
            tenant=self.tenant, codigo_interno="SINAPI-90777",
            descricao="ESCAVADEIRA HIDRAULICA SOBRE ESTEIRAS", unidade="UN",
            tipo=Item.Tipo.MATERIAL, codigo_referencia="90777", fonte_referencia="sinapi",
        )
        self._ref(
            self.base_2024, codigo="90777",
            descricao="ESCAVADEIRA HIDRAULICA SOBRE ESTEIRAS", unidade="UN",
            custo="903480.94",
        )
        return Item.objects.get(codigo_interno="SINAPI-90777")

    def test_o_comando_declara_o_buraco_em_vez_de_adivinhar(self):
        """Nada de "contém ESCAVADEIRA → equipamento": é a classe de palpite que
        produziu o D109. O comando conta, diz e oferece as saídas."""
        item = self._escavadeira()
        saida = self._rodar()

        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.MATERIAL)
        self.assertIn("Sem classificação na fonte: 1", saida)
        self.assertIn("--de-para", saida)

    def test_de_para_aplica_a_classificacao_que_a_empresa_declarou(self):
        item = self._escavadeira()
        with TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "equipamentos.csv"
            arquivo.write_text(
                "codigo;natureza\n90777;EQUIPAMENTO\n", encoding="utf-8"
            )
            saida = self._rodar(de_para=str(arquivo))

        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.EQUIPAMENTO)
        # As flags de domínio acompanham a natureza declarada: equipamento tem
        # saldo em estoque mas não baixa contra a etapa como material consumido.
        self.assertFalse(item.consumivel)
        self.assertIn("declarada no --de-para", saida)

    def test_de_para_aceita_a_chave_interna_e_a_coluna_de_fonte(self):
        item = self._escavadeira()
        with TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "equipamentos.csv"
            arquivo.write_text("90777;equipamento;sinapi\n", encoding="utf-8")
            self._rodar(de_para=str(arquivo))

        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.EQUIPAMENTO)

    def test_linha_de_outra_fonte_nao_alcanca_o_item(self):
        item = self._escavadeira()
        with TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "equipamentos.csv"
            arquivo.write_text("90777;equipamento;orse\n", encoding="utf-8")
            self._rodar(de_para=str(arquivo))

        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.MATERIAL)

    def test_natureza_desconhecida_derruba_o_arquivo_inteiro(self):
        """Pular a linha ruim em silêncio é o pior desfecho: quem classificou
        trezentos itens iria embora achando que aplicou trezentos."""
        item = self._escavadeira()
        with TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "equipamentos.csv"
            arquivo.write_text(
                "90777;EQUIPAMENTO\n00370;MAQUINARIO PESADO\n", encoding="utf-8"
            )
            with self.assertRaises(CommandError) as capturado:
                self._rodar(de_para=str(arquivo))

        self.assertIn("MAQUINARIO PESADO", str(capturado.exception))
        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.MATERIAL)

    def test_de_para_contra_a_fonte_vence_mas_fica_registrado(self):
        item = self._escavadeira()
        InsumoReferencia.objects.filter(codigo="90777").update(grupo="MATERIAL")
        with TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "equipamentos.csv"
            arquivo.write_text("90777;EQUIPAMENTO\n", encoding="utf-8")
            saida = self._rodar(de_para=str(arquivo))

        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.EQUIPAMENTO)
        self.assertIn("valeu o --de-para", saida)

    def test_arquivo_inexistente_falha_antes_de_tocar_em_tenant(self):
        with self.assertRaises(CommandError):
            self._rodar(de_para="/nao/existe/de-para.csv")

    def test_de_para_com_preambulo_de_comentario_e_lido(self):
        """O de-para versionado se explica: comentário antes do cabeçalho, e
        vírgulas no texto corrido que não podem eleger o separador errado."""
        item = self._escavadeira()
        with TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "equipamentos.csv"
            arquivo.write_text(
                "# Classificação declarada pela empresa — escavadeira, caminhão e caçamba\n"
                "# são publicados em UN, então o plano B da unidade os chamou de material.\n"
                "\n"
                "codigo;natureza;fonte\n"
                "\n"
                "# --- equipamento ---\n"
                "90777;EQUIPAMENTO;sinapi\n",
                encoding="utf-8",
            )
            self._rodar(de_para=str(arquivo))

        item.refresh_from_db()
        self.assertEqual(item.tipo, Item.Tipo.EQUIPAMENTO)

    def test_arquivo_de_de_para_versionado_no_repo_e_valido(self):
        """O arquivo que acompanha o módulo tem de continuar carregável — ele é
        a resposta do D111 para a BA 10/2024, e um erro de digitação nele só
        apareceria no dia em que alguém precisasse rodar."""
        from django.conf import settings

        caminho = (
            Path(settings.BASE_DIR) / "moduloorcamento" / "dados"
            / "classificacao-sinapi-ba-2024-10.csv"
        )
        self.assertTrue(caminho.is_file(), f"sumiu: {caminho}")
        declarado = Command()._ler_de_para(str(caminho))
        self.assertEqual(len(declarado), 14)
        self.assertEqual(declarado[("sinapi", "14525")], Item.Tipo.EQUIPAMENTO)
        self.assertEqual(declarado[("sinapi", "37370")], Item.Tipo.ENCARGOS_COMPLEMENTARES)


class VocabularioDeClasseTests(SimpleTestCase):
    """Base cujas classes o sistema não conhece: nem alucina, nem para — **avisa**.

    Este é o buraco que a pergunta do dono (21/08/2026) abriu. `natureza_da_
    classificacao` casa por prefixo, e prefixo que não casa devolvia `None` —
    o mesmo `None` de "campo vazio". As duas causas iam para o plano B da
    unidade sem distinção e sem uma palavra, e como a coluna vinha preenchida o
    indicador de "publicação classifica insumo" ainda acendia **verde**.
    """

    def test_vocabulario_da_sinapi_continua_lido(self):
        casos = {
            "MATERIAL": Item.Tipo.MATERIAL,
            "MÃO DE OBRA": Item.Tipo.MAO_DE_OBRA,
            "EQUIPAMENTO (AQUISIÇÃO)": Item.Tipo.EQUIPAMENTO,
            "EQUIPAMENTO (LOCAÇÃO)": Item.Tipo.EQUIPAMENTO,
            "ENCARGOS COMPLEMENTARES": Item.Tipo.ENCARGOS_COMPLEMENTARES,
            "SERVIÇOS": Item.Tipo.SERVICO,
        }
        for texto, esperado in casos.items():
            with self.subTest(classe=texto):
                self.assertEqual(services.natureza_da_classificacao(texto), esperado)
                self.assertFalse(services.classificacao_desconhecida(texto))

    def test_plural_de_outras_bases_deixa_de_passar_batido(self):
        """"MATERIAIS" não começa por "material" (troca o `l` pelo `i`) — e é a
        classe mais comum de ORSE e SICRO inteiras."""
        self.assertEqual(services.natureza_da_classificacao("MATERIAIS"), Item.Tipo.MATERIAL)
        self.assertEqual(services.natureza_da_classificacao("EQUIPAMENTOS"), Item.Tipo.EQUIPAMENTO)

    def test_locacao_escrita_do_avesso_e_equipamento(self):
        """A prefeitura escreve "LOCAÇÃO DE EQUIPAMENTO"; a SINAPI, "EQUIPAMENTO
        (LOCAÇÃO)". Sem esta linha a de prefeitura caía no plano B — em `H`,
        virando mão de obra e levando encargo social (o D109 em outra fonte)."""
        self.assertEqual(
            services.natureza_da_classificacao("LOCAÇÃO DE EQUIPAMENTO"),
            Item.Tipo.EQUIPAMENTO,
        )

    def test_classe_que_declara_nao_ser_natureza_nao_vira_alarme(self):
        """"ESPECIAIS" e "TAXAS" foram reconhecidas — a resposta delas é "não
        classifico". Reportá-las seria ruído em toda importação da SINAPI."""
        for texto in ("ESPECIAIS", "TAXAS"):
            with self.subTest(classe=texto):
                self.assertIsNone(services.natureza_da_classificacao(texto))
                self.assertFalse(services.classificacao_desconhecida(texto))

    def test_vocabulario_desconhecido_e_reportavel(self):
        for texto in ("TRANSPORTES", "ATIVIDADES AUXILIARES", "VERBA", "ADMINISTRAÇÃO LOCAL"):
            with self.subTest(classe=texto):
                self.assertIsNone(services.natureza_da_classificacao(texto))
                self.assertTrue(services.classificacao_desconhecida(texto))

    def test_campo_vazio_nao_e_desconhecido(self):
        """Vazio é o D111 — a fonte não respondeu. Contado à parte, e com outra
        saída (publicação 2025+ ou `--de-para`)."""
        for texto in ("", None, "   "):
            with self.subTest(classe=repr(texto)):
                self.assertFalse(services.classificacao_desconhecida(texto))


class ImportacaoAvisaSobreClassificacaoTests(OrcamentoTestBase):
    """Coluna **ausente**: avisa e segue — não há pergunta a fazer a ninguém.

    É o contraponto do `ImportacaoExigeDecisaoDoSuperuserTests` logo abaixo, e a
    diferença entre os dois é de quem tem a resposta. Aqui a fonte simplesmente
    não classificou (D111): a publicação continua útil, como era antes da ORC.9,
    e parar não traria informação nova. Lá a fonte respondeu e nós é que não
    entendemos — e essa pergunta tem dono.
    """

    CSV_VOCABULARIO_CONHECIDO = (
        "CÓDIGO;DESCRIÇÃO DO INSUMO;UNIDADE;PREÇO;CLASSIFICAÇÃO\n"
        "101;BETONEIRA 400L;H;12,50;LOCACAO DE EQUIPAMENTO\n"
        "104;CIMENTO CP II;KG;0,58;MATERIAIS\n"
        "105;PEDREIRO;H;25,84;MÃO DE OBRA\n"
        "106;TAXA DE ART;UN;120,00;TAXAS\n"
    )

    CSV_SEM_CLASSE = (
        "CÓDIGO;DESCRIÇÃO DO INSUMO;UNIDADE;PREÇO\n"
        "201;ESCAVADEIRA HIDRAULICA;UN;903480,94\n"
        "202;OLEO DIESEL;L;5,97\n"
    )

    CSV_PARCIAL = (
        "CÓDIGO;DESCRIÇÃO DO INSUMO;UNIDADE;PREÇO;CLASSIFICAÇÃO\n"
        "301;CIMENTO CP II;KG;0,58;MATERIAL\n"
        "302;AREIA MEDIA;M3;89,50;\n"
    )

    def setUp(self):
        services.esquecer_classes_declaradas()

    def _importar(self, conteudo: str, **extra) -> str:
        saida = StringIO()
        with TemporaryDirectory() as tmp:
            arquivo = self._escrever(Path(tmp), "insumos.csv", conteudo)
            call_command(
                "importar_base_referencial", fonte="sinapi", mes="2026-09",
                insumos=str(arquivo), stdout=saida, **extra,
            )
        return saida.getvalue()

    def test_vocabulario_todo_conhecido_passa_sem_alarme(self):
        """Inclui as grafias que antes passavam batidas (`MATERIAIS`, `LOCACAO
        DE EQUIPAMENTO`) e a classe que declara não ser natureza (`TAXAS`)."""
        saida = self._importar(self.CSV_VOCABULARIO_CONHECIDO)

        self.assertNotIn("NÃO IMPORTADO", saida)
        base = BaseReferencial.objects.get(fonte="sinapi", mes_referencia=date(2026, 9, 1))
        self.assertEqual(InsumoReferencia.objects.filter(base=base).count(), 4)

    def test_publicacao_sem_a_coluna_avisa_e_importa(self):
        saida = self._importar(self.CSV_SEM_CLASSE)

        self.assertIn("nenhum insumo traz classificação", saida)
        self.assertIn("01/2025", saida)
        base = BaseReferencial.objects.get(fonte="sinapi", mes_referencia=date(2026, 9, 1))
        self.assertEqual(InsumoReferencia.objects.filter(base=base).count(), 2)

    def test_coluna_preenchida_pela_metade_conta_quantos_caem_na_unidade(self):
        saida = self._importar(self.CSV_PARCIAL)
        self.assertIn("1 insumo(s) sem classificação", saida)


class ImportacaoExigeDecisaoDoSuperuserTests(OrcamentoTestBase):
    """Classe sem tradução **para a importação** e devolve a pergunta.

    Decisão do dono (21/08/2026). A base-mãe é global e read-only: só o
    superuser importa, e o que ele importa todos os tenants enxergam. Traduzir
    uma classe errado é alavanca de preço para a plataforma inteira, e quem tem
    a resposta é justamente quem está rodando o comando — então o comando não
    escolhe sozinho, lista o que não soube fazer e para.
    """

    CSV = (
        "CÓDIGO;DESCRIÇÃO DO INSUMO;UNIDADE;PREÇO;CLASSIFICAÇÃO\n"
        "301;CAMINHAO BASCULANTE;H;98,00;TRANSPORTES\n"
        "302;ADMINISTRACAO DA OBRA;MES;9000,00;ATIVIDADES AUXILIARES\n"
        "303;CIMENTO CP II;KG;0,58;MATERIAL\n"
    )

    def setUp(self):
        services.esquecer_classes_declaradas()
        self.addCleanup(services.esquecer_classes_declaradas)

    def _importar(self, **extra) -> str:
        saida = StringIO()
        with TemporaryDirectory() as tmp:
            arquivo = self._escrever(Path(tmp), "insumos.csv", self.CSV)
            call_command(
                "importar_base_referencial", fonte="orse", mes="2026-09",
                insumos=str(arquivo), stdout=saida, **extra,
            )
        return saida.getvalue()

    def _publicacao(self):
        return BaseReferencial.objects.filter(
            fonte="orse", mes_referencia=date(2026, 9, 1)
        ).first()

    def test_para_e_lista_o_que_nao_foi_feito(self):
        with self.assertRaises(CommandError) as capturado:
            self._importar()

        recado = str(capturado.exception)
        self.assertIn("NÃO IMPORTADO", recado)
        self.assertIn("TRANSPORTES", recado)
        self.assertIn("ATIVIDADES AUXILIARES", recado)
        self.assertNotIn("MATERIAL;", recado)  # essa foi lida
        # As duas saídas ficam escritas, com o caminho do arquivo a editar.
        self.assertIn("orse.csv", recado)
        self.assertIn("--aceitar-sem-classe", recado)

    def test_nada_e_gravado_quando_para(self):
        """Para **antes** de escrever: publicação meio importada seria pior que
        nenhuma, porque parece completa."""
        with self.assertRaises(CommandError):
            self._importar()
        base = self._publicacao()
        self.assertEqual(InsumoReferencia.objects.filter(base=base).count(), 0)

    def test_aceitar_sem_classe_e_a_decisao_consciente_de_seguir(self):
        saida = self._importar(aceitar_sem_classe=True)
        self.assertIn("aceitas por --aceitar-sem-classe", saida)
        self.assertEqual(InsumoReferencia.objects.filter(base=self._publicacao()).count(), 3)

    def test_dicionario_da_fonte_resolve_e_nao_pergunta_de_novo(self):
        """A resposta dada uma vez vale para as publicações seguintes da fonte —
        senão a mesma pergunta voltaria todo mês."""
        with TemporaryDirectory() as tmp:
            services.PASTA_DE_CLASSES = Path(tmp)
            (Path(tmp) / "orse.csv").write_text(
                "# vocabulário da ORSE\n"
                "TRANSPORTES;material\n"
                "ATIVIDADES AUXILIARES;servico\n",
                encoding="utf-8",
            )
            services.esquecer_classes_declaradas()
            try:
                saida = self._importar()
            finally:
                services.PASTA_DE_CLASSES = (
                    Path(services.__file__).resolve().parent / "dados" / "classes"
                )
                services.esquecer_classes_declaradas()

        self.assertNotIn("NÃO IMPORTADO", saida)
        self.assertEqual(InsumoReferencia.objects.filter(base=self._publicacao()).count(), 3)

    def test_a_traducao_declarada_chega_na_adocao(self):
        """Não basta deixar importar: a classe declarada tem de virar a natureza
        do item quando ele for adotado."""
        with TemporaryDirectory() as tmp:
            services.PASTA_DE_CLASSES = Path(tmp)
            (Path(tmp) / "orse.csv").write_text("TRANSPORTES;equipamento\n", encoding="utf-8")
            services.esquecer_classes_declaradas()
            try:
                base = self._base(fonte=Fonte.ORSE, uf="SE", mes=date(2026, 9, 1))
                ref = self._ref(
                    base, codigo="301", descricao="CAMINHAO BASCULANTE", unidade="H",
                )
                ref.grupo = "TRANSPORTES"
                ref.save(update_fields=["grupo"])
                item = services.adotar_no_catalogo(ref, self.tenant.id)
            finally:
                services.PASTA_DE_CLASSES = (
                    Path(services.__file__).resolve().parent / "dados" / "classes"
                )
                services.esquecer_classes_declaradas()

        # Sem a declaração, `H` teria feito dele mão de obra — e mão de obra
        # leva encargo social sobre um custo que não é salário.
        self.assertEqual(item.tipo, Item.Tipo.EQUIPAMENTO)


class ResumoDeclaraSePublicacaoClassificaTests(OrcamentoTestBase):
    """A tela precisa poder **dizer** que a publicação não classifica insumo —
    senão o usuário descobre olhando a analítica e estranhando (foi como o D111
    apareceu)."""

    def setUp(self):
        self.autenticar()

    def test_publicacao_sem_a_coluna_classificacao_e_declarada(self):
        base = self._base(mes=date(2024, 10, 1))
        self._ref(base, codigo="1379", descricao="CIMENTO", unidade="KG")

        linha = self.client.get("/api/orcamento/bases-resumo/").data[0]
        self.assertFalse(linha["classifica_insumo"])
        self.assertEqual(linha["insumos_classificados"], 0)

    def test_publicacao_de_2025_em_diante_classifica(self):
        base = self._base(mes=date(2026, 1, 1))
        ref = self._ref(base, codigo="1379", descricao="CIMENTO", unidade="KG")
        ref.grupo = "MATERIAL"
        ref.save(update_fields=["grupo"])

        linha = self.client.get("/api/orcamento/bases-resumo/").data[0]
        self.assertTrue(linha["classifica_insumo"])
        self.assertEqual(linha["insumos_classificados"], 1)
        self.assertEqual(linha["classes_desconhecidas"], [])

    def test_coluna_preenchida_com_vocabulario_ilegivel_nao_acende_verde(self):
        """A regressão que a pergunta do dono expôs: `classifica_insumo` media
        "a coluna veio preenchida". Uma base de vocabulário próprio passava por
        classificada enquanto nenhuma classe dela chegava à natureza."""
        base = self._base(mes=date(2026, 1, 1))
        for codigo, grupo in (("1", "TRANSPORTES"), ("2", "ATIVIDADES AUXILIARES")):
            ref = self._ref(base, codigo=codigo, descricao=f"INSUMO {codigo}", unidade="H")
            ref.grupo = grupo
            ref.save(update_fields=["grupo"])

        linha = self.client.get("/api/orcamento/bases-resumo/").data[0]
        self.assertFalse(linha["classifica_insumo"])
        self.assertEqual(linha["insumos_classificados"], 2)  # a coluna VEIO preenchida…
        self.assertEqual(  # …e mesmo assim não classifica nada
            linha["classes_desconhecidas"], ["ATIVIDADES AUXILIARES", "TRANSPORTES"],
        )

    def test_publicacao_com_classe_conhecida_e_desconhecida_junto(self):
        """Meio-termo real: parte do vocabulário é lida, parte não. O indicador
        fecha (há item caindo no plano B) e a tela recebe quais classes são."""
        base = self._base(mes=date(2026, 1, 1))
        for codigo, grupo in (("1", "MATERIAIS"), ("2", "VERBA")):
            ref = self._ref(base, codigo=codigo, descricao=f"INSUMO {codigo}", unidade="UN")
            ref.grupo = grupo
            ref.save(update_fields=["grupo"])

        linha = self.client.get("/api/orcamento/bases-resumo/").data[0]
        self.assertFalse(linha["classifica_insumo"])
        self.assertEqual(linha["classes_desconhecidas"], ["VERBA"])

    def test_mesma_classe_com_espaco_a_mais_nao_aparece_duas_vezes(self):
        """Regressão pega no stack vivo: o `distinct()` do banco separa
        "Agregados" de "Agregados ", e a tela listava a mesma classe duas
        vezes."""
        base = self._base(mes=date(2026, 1, 1))
        for codigo, grupo in (("1", "Agregados"), ("2", "Agregados "), ("3", " Agregados")):
            ref = self._ref(base, codigo=codigo, descricao=f"INSUMO {codigo}", unidade="M3")
            ref.grupo = grupo
            ref.save(update_fields=["grupo"])

        linha = self.client.get("/api/orcamento/bases-resumo/").data[0]
        self.assertEqual(linha["classes_desconhecidas"], ["Agregados"])
