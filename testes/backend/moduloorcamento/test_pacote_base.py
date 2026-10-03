"""DMS.1 — o pacote da base referencial (`moduloorcamento/pacote.py`).

O que estes testes protegem: que o pacote leve a base de um banco a outro
**com as FKs remapeadas** (o id do destino é outro), que importar de novo não
duplique nada, e que um arquivo alterado seja recusado antes de tocar no banco.
"""
import os
import tarfile
import tempfile
from datetime import date
from decimal import Decimal

from moduloorcamento import pacote
from moduloorcamento.models import (
    AnaliticaNacional,
    BaseReferencial,
    ComposicaoReferenciaItem,
    Fonte,
    IndiceEconomico,
    InsumoReferencia,
    ValorIndice,
)

from .tests import OrcamentoTestBase


class PacoteDaBaseTests(OrcamentoTestBase):
    def setUp(self):
        super().setUp()
        self.pasta = tempfile.mkdtemp()
        self.arquivo = os.path.join(self.pasta, "base.tar")
        sp = self._base(uf="SP")
        self._base(uf="BA")
        cimento = self._ref(sp, codigo="1379", custo="0.58")
        self.composicao = self._ref(sp, codigo="87292", descricao="ARGAMASSA", unidade="M3",
                                    tipo=InsumoReferencia.Tipo.COMPOSICAO, custo="420.00")
        ComposicaoReferenciaItem.objects.create(composicao=self.composicao, filho=cimento,
                                                coeficiente=Decimal("350"))
        AnaliticaNacional.objects.create(fonte=Fonte.SINAPI, competencia=date(2026, 7, 1),
                                         codigo_composicao="87292", codigo_item="1379",
                                         coeficiente=Decimal("350"))
        incc = IndiceEconomico.objects.create(codigo="INCC-TESTE", nome="INCC teste")
        ValorIndice.objects.create(indice=incc, competencia=date(2026, 7, 1),
                                   numero_indice=Decimal("1000.5"))

    def _apagar_a_base(self):
        ComposicaoReferenciaItem.objects.all().delete()
        InsumoReferencia.objects.all().delete()
        BaseReferencial.objects.all().delete()
        AnaliticaNacional.objects.all().delete()
        ValorIndice.objects.all().delete()
        IndiceEconomico.objects.filter(codigo="INCC-TESTE").delete()

    def test_leva_a_base_e_remapeia_as_fks(self):
        manifesto = pacote.exportar(self.arquivo, avisar=lambda *_: None)
        self.assertEqual(manifesto["tabelas"]["bases"]["linhas"], 2)
        self.assertEqual(manifesto["tabelas"]["componentes"]["linhas"], 1)
        id_antigo = self.composicao.pk
        self._apagar_a_base()

        resumo = pacote.importar(self.arquivo, avisar=lambda *_: None)

        self.assertEqual((resumo["bases"], resumo["insumos"], resumo["componentes"]), (2, 2, 1))
        nova = InsumoReferencia.objects.get(codigo="87292")
        self.assertNotEqual(nova.pk, id_antigo)
        componente = ComposicaoReferenciaItem.objects.get(composicao=nova)
        self.assertEqual(componente.filho.codigo, "1379")
        self.assertEqual(componente.filho.base_id, nova.base_id)
        self.assertEqual(AnaliticaNacional.objects.count(), 1)
        self.assertEqual(ValorIndice.objects.get(indice__codigo="INCC-TESTE").numero_indice, Decimal("1000.5"))

    def test_importar_de_novo_nao_duplica(self):
        pacote.exportar(self.arquivo, avisar=lambda *_: None)
        resumo = pacote.importar(self.arquivo, avisar=lambda *_: None)
        self.assertEqual((resumo["bases"], resumo["bases_ja_existentes"], resumo["insumos"]), (0, 2, 0))
        self.assertEqual(InsumoReferencia.objects.count(), 2)

    def test_retoma_so_a_publicacao_que_falta(self):
        """Commit por publicação: se a importação cair no meio, rodar de novo
        refaz só a que não entrou — e as composições dela, pela chave natural."""
        pacote.exportar(self.arquivo, avisar=lambda *_: None)
        InsumoReferencia.objects.filter(base__uf="SP").delete()
        BaseReferencial.objects.filter(uf="SP").delete()
        resumo = pacote.importar(self.arquivo, avisar=lambda *_: None)
        self.assertEqual((resumo["bases"], resumo["bases_ja_existentes"]), (1, 1))
        self.assertEqual((resumo["insumos"], resumo["componentes"]), (2, 1))
        self.assertEqual(ComposicaoReferenciaItem.objects.get().filho.base.uf, "SP")

    def test_pacote_da_versao_antiga_e_recusado(self):
        manifesto = pacote.exportar(self.arquivo, avisar=lambda *_: None)
        antigo = os.path.join(self.pasta, "v1.tar")
        with tarfile.open(self.arquivo) as origem, tarfile.open(antigo, "w") as destino:
            for membro in origem.getmembers():
                dados = origem.extractfile(membro).read()
                if membro.name == pacote.MANIFESTO:
                    import json
                    dados = json.dumps({**manifesto, "versao": 1}).encode()
                    membro.size = len(dados)
                import io
                destino.addfile(membro, io.BytesIO(dados))
        with self.assertRaisesRegex(pacote.PacoteInvalido, "versão 1"):
            pacote.importar(antigo, avisar=lambda *_: None)

    def test_recorte_por_fonte_e_competencia(self):
        orse = self._base(fonte=Fonte.ORSE, uf="SE", mes=date(2025, 1, 1))
        self._ref(orse, codigo="X1")
        manifesto = pacote.exportar(self.arquivo, fontes=["orse"], avisar=lambda *_: None)
        self.assertEqual((manifesto["tabelas"]["bases"]["linhas"], manifesto["tabelas"]["insumos"]["linhas"]), (1, 1))
        manifesto = pacote.exportar(self.arquivo, desde=date(2026, 1, 1), avisar=lambda *_: None)
        self.assertEqual(manifesto["tabelas"]["bases"]["linhas"], 2)

    def test_arquivo_alterado_e_recusado_antes_de_gravar(self):
        pacote.exportar(self.arquivo, avisar=lambda *_: None)
        adulterado = os.path.join(self.pasta, "adulterado.tar")
        with tarfile.open(self.arquivo) as origem, tarfile.open(adulterado, "w") as destino:
            for membro in origem.getmembers():
                dados = origem.extractfile(membro).read()
                if membro.name == "insumos.csv.gz":
                    import gzip
                    dados = gzip.compress(gzip.decompress(dados).replace(b"0.58", b"9.99"))
                    membro.size = len(dados)
                import io
                destino.addfile(membro, io.BytesIO(dados))
        self._apagar_a_base()
        with self.assertRaises(pacote.PacoteInvalido):
            pacote.importar(adulterado, avisar=lambda *_: None)
        self.assertEqual(BaseReferencial.objects.count(), 0)
