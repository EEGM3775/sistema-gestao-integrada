"""O medidor por cgroup — e a regra de que ele nunca pode custar a medição.

**O que estes testes cobram.** O caminho de cgroup é opcional em todo passo:
sem `SGI_CGROUP_MEDICAO`, com a raiz apagada, sem `memory.peak`, sem permissão
de gravar em `cgroup.procs` — o desfecho tem de ser sempre o mesmo, *amostragem*,
e nunca uma exceção subindo por dentro de uma conversão. Um medidor que derruba
a operação que ele mede é pior do que medidor nenhum.

**Por que a raiz é falsa e isto ainda vale.** O cgroupfs é um sistema de arquivos
de pseudo-arquivos: criar diretório, escrever um pid em `cgroup.procs`, ler um
inteiro de `memory.peak`. Um diretório temporário reproduz a *forma* inteira —
a sequência de passos, a ordem entre ler o pico e devolver o processo, e o que
acontece quando cada passo falha. O que ele **não** reproduz é a semântica do
kernel (a cobrança de páginas de fato ir para o cgroup novo), e essa metade só
se verifica em host com cgroup v2 — está declarada na planta §4.7 como tal.
"""
from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from nucleo import consumo


class RaizFalsa:
    """Um `cgroup2` de mentira em disco, com os pseudo-arquivos que o medidor lê."""

    def __init__(self, base: str, *, com_peak: bool = True, peak_bytes: int = 300 * 1048576):
        self.dir = pathlib.Path(base) / "sgi-medicao"
        self.dir.mkdir()
        (self.dir / "cgroup.subtree_control").write_text("")
        self.origem = pathlib.Path(base) / "origem"
        self.origem.mkdir()
        (self.origem / "cgroup.procs").write_text("")
        self.com_peak = com_peak
        self.peak_bytes = peak_bytes
        self._mkdir_real = os.mkdir
        self._rmdir_real = os.rmdir

    def mkdir_que_popula(self, caminho, *args, **kwargs):
        """`os.mkdir` que já cria os pseudo-arquivos — é o que o kernel faz."""
        self._mkdir_real(caminho, *args, **kwargs)
        destino = pathlib.Path(caminho)
        (destino / "cgroup.procs").write_text("")
        if self.com_peak:
            (destino / "memory.peak").write_text(f"{self.peak_bytes}\n")

    def rmdir_que_limpa(self, caminho, *args, **kwargs):
        """`os.rmdir` que ignora os pseudo-arquivos, como o cgroupfs faz.

        Um cgroup se remove com `rmdir` **mesmo tendo** `cgroup.procs` e
        `memory.peak` dentro — eles são do kernel, não entradas de diretório de
        verdade. Num `tmpfs` o mesmo `rmdir` daria `ENOTEMPTY`, e o medidor
        concluiria que não conseguiu limpar quando em produção consegue.
        """
        destino = pathlib.Path(caminho)
        if destino.is_dir():
            for pseudo in destino.iterdir():
                if pseudo.is_file():
                    pseudo.unlink()
        self._rmdir_real(caminho, *args, **kwargs)


class MedirComCgroup(unittest.TestCase):
    """A janela feliz e as seis formas de ela não acontecer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _com_raiz(self, raiz: RaizFalsa):
        """Aponta o medidor para a raiz falsa e finge o monte/cgroup do processo."""
        self.enterContext(mock.patch.dict(os.environ, {consumo.ENV_CGROUP: str(raiz.dir)}))
        self.enterContext(mock.patch.object(consumo, "_monte_cgroup2", return_value=str(raiz.origem.parent)))
        self.enterContext(mock.patch.object(consumo, "_cgroup_atual", return_value="/origem"))
        self.enterContext(mock.patch.object(os, "mkdir", raiz.mkdir_que_popula))
        self.enterContext(mock.patch.object(os, "rmdir", raiz.rmdir_que_limpa))

    def test_pico_sai_do_memory_peak_e_a_fonte_diz_qual_foi(self):
        raiz = RaizFalsa(self.tmp.name, peak_bytes=2_437 * 1048576)
        self._com_raiz(raiz)

        with consumo.medir(intervalo=10) as custo:
            pass

        self.assertEqual(custo["pico_cgroup_mb"], 2_437)
        self.assertEqual(custo["fonte"], "cgroup")

    def test_o_processo_volta_ao_cgroup_de_origem_e_o_da_janela_some(self):
        """A limpeza é a metade que, falhando, deixa o worker num cgroup órfão."""
        raiz = RaizFalsa(self.tmp.name)
        self._com_raiz(raiz)

        with consumo.medir(intervalo=10):
            durante = [p for p in raiz.dir.iterdir() if p.is_dir()]
            self.assertEqual(len(durante), 1, "a janela devia ter criado seu cgroup")

        self.assertEqual([p for p in raiz.dir.iterdir() if p.is_dir()], [])
        self.assertEqual(
            (raiz.origem / "cgroup.procs").read_text(), str(os.getpid()),
            "o processo tem de voltar para o cgroup de onde saiu",
        )

    def test_amostragem_continua_medindo_com_o_cgroup_ligado(self):
        """As colunas de atribuição não podem sumir quando o exato aparece.

        `pico_cgroup_mb` diz *quanto*; só a amostragem diz *onde*. Trocar uma
        pela outra perderia a separação subprocesso × em processo, que é o que
        decide qual metade otimizar.
        """
        raiz = RaizFalsa(self.tmp.name)
        self._com_raiz(raiz)

        with consumo.medir(intervalo=0.01) as custo:
            pass

        for campo in ("pico_va_mb", "pico_rss_mb", "filhos", "cpu_s", "segundos"):
            self.assertIn(campo, custo)

    def test_sem_a_variavel_de_ambiente_nao_toca_em_cgroup_nenhum(self):
        """Opt-in de deploy: o medidor não sai procurando cgroup por conta própria."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(consumo.ENV_CGROUP, None)
            with mock.patch.object(consumo, "_cgroup_atual") as espiao:
                with consumo.medir(intervalo=10) as custo:
                    pass
        espiao.assert_not_called()
        self.assertEqual(custo["fonte"], "amostragem")
        self.assertIsNone(custo["pico_cgroup_mb"])

    def test_raiz_apontada_mas_inexistente_cai_na_amostragem(self):
        with mock.patch.dict(os.environ, {consumo.ENV_CGROUP: f"{self.tmp.name}/nao-existe"}):
            with consumo.medir(intervalo=10) as custo:
                pass
        self.assertEqual(custo["fonte"], "amostragem")

    def test_kernel_sem_memory_peak_desiste_sem_mudar_o_processo_de_cgroup(self):
        """Mudar de cgroup para não poder ler nada é pior do que não mudar."""
        raiz = RaizFalsa(self.tmp.name, com_peak=False)
        self._com_raiz(raiz)

        with consumo.medir(intervalo=10) as custo:
            pass

        self.assertEqual(custo["fonte"], "amostragem")
        self.assertIsNone(custo["pico_cgroup_mb"])
        self.assertEqual(
            [p for p in raiz.dir.iterdir() if p.is_dir()], [],
            "o cgroup criado antes da desistência tem de ser removido",
        )

    def test_falha_ao_entrar_no_cgroup_nao_derruba_a_operacao_medida(self):
        """O caso que importa: a operação roda inteira, medida ou não."""
        raiz = RaizFalsa(self.tmp.name)
        self._com_raiz(raiz)
        original = consumo._escrever

        def recusa_procs(caminho, texto):
            if caminho.endswith("op-" + str(os.getpid()) + "-0/cgroup.procs"):
                return False
            if "/op-" in caminho and caminho.endswith("cgroup.procs"):
                return False
            return original(caminho, texto)

        with mock.patch.object(consumo, "_escrever", recusa_procs):
            rodou = False
            with consumo.medir(intervalo=10) as custo:
                rodou = True

        self.assertTrue(rodou)
        self.assertEqual(custo["fonte"], "amostragem")

    def test_origem_nao_gravavel_recusa_a_mudanca_inteira(self):
        """A trava que impede o worker de ficar fora do próprio cgroup.

        Medido em container real (13/08/2026): com o cgroup delegado montado
        **fora** do cgroup do container, a janela mede certo, não consegue voltar
        e deixa o processo do lado de fora — onde o `mem_limit` do container não
        o alcança mais. O medidor tem de recusar a ida quando a volta não é
        gravável, e o preço disso é medir por amostragem, que é o preço certo.
        """
        raiz = RaizFalsa(self.tmp.name)
        self._com_raiz(raiz)
        original = consumo._escrever
        origem_procs = str(raiz.origem / "cgroup.procs")

        # A recusa vem do **mount** somente-leitura (`EROFS`), e não da permissão
        # do arquivo: o worker roda como root no container, e root passa por cima
        # do modo do arquivo. Simular por `chmod` não reproduziria nada.
        def origem_somente_leitura(caminho, texto):
            return False if caminho == origem_procs else original(caminho, texto)

        with mock.patch.object(consumo, "_escrever", origem_somente_leitura):
            with consumo.medir(intervalo=10) as custo:
                pass

        self.assertEqual(custo["fonte"], "amostragem")
        self.assertEqual(
            [p for p in raiz.dir.iterdir() if p.is_dir()], [],
            "desistir tem de limpar o cgroup que chegou a ser criado",
        )

    def test_duas_janelas_aninhadas_nao_disputam_o_mesmo_processo(self):
        """A de fora é a dona; a de dentro amostra.

        Mover o processo para o cgroup da janela interna tiraria a externa de
        baixo do próprio medidor — o pico dela pararia de crescer no meio.
        """
        raiz = RaizFalsa(self.tmp.name)
        self._com_raiz(raiz)

        with consumo.medir(intervalo=10) as externo:
            with consumo.medir(intervalo=10) as interno:
                pass

        self.assertEqual(externo["fonte"], "cgroup")
        self.assertEqual(interno["fonte"], "amostragem")


class NaoMedido(unittest.TestCase):
    """A regra do D82 no formato de teste: ausência não é zero."""

    def test_filho_nao_amostrado_sai_none_e_nao_zero(self):
        with consumo.medir(intervalo=10) as custo:
            pass
        self.assertIsNone(custo["pico_filho_mb"])
        self.assertFalse(custo["filho_medido"])

    def test_cgroup_ausente_sai_none_e_nao_zero(self):
        """`0` aqui viraria "não custou nada" no relatório — a mentira do D82."""
        with consumo.medir(intervalo=10) as custo:
            pass
        self.assertIsNone(custo["pico_cgroup_mb"])
