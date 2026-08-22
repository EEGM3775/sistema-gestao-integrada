# backend/nucleo/test_frota.py
"""D98 — o porteiro da frota de trabalho pesado.

O que estes testes cobram é a diferença entre **freio** e **admissão**: o
`worker-conversao` sempre soube não estourar a máquina, e nunca soube dizer de
quem é a próxima vez. As três decisões do dono (16/08/2026) viram asserção aqui.
"""
from unittest import mock

from django.test import TestCase, override_settings

from .frota import (
    ha_espera,
    cancelar,
    classe_do_plano,
    concluir,
    enfileirar,
    liberar_orfas,
    posicao,
    priorizar,
    recolocar,
    situacao_da_fila,
)
from .models import TarefaNaFila, Tenant, Usuario


def _sem_broker():
    """Nenhum teste daqui publica de verdade: o assunto é a ORDEM, não o Celery."""
    return mock.patch("celery.current_app.send_task")


class FrotaTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.acme = Tenant.objects.create(slug="acme", nome="ACME")
        cls.beta = Tenant.objects.create(slug="beta", nome="Beta")
        cls.admin = Usuario.objects.create(username="admin_acme", tenant=cls.acme)

    def _por(self, tenant, chave, plano="profissional"):
        return enfileirar(
            tenant_id=tenant.pk, chave=chave, plano=plano,
            tarefa="t.converter", argumentos=[chave],
        )


@override_settings(FROTA_VAGAS={"conversao": 1})
class AdmissaoTests(FrotaTestBase):
    def test_a_fila_e_unica_e_a_posicao_conta_todo_mundo(self):
        """A pergunta é "quando chega a minha vez", e a resposta honesta conta
        quem vai passar antes — não só os do mesmo plano, que daria um número
        menor e errado."""
        with _sem_broker():
            primeira = self._por(self.acme, "a")
            segunda = self._por(self.beta, "b")
            terceira = self._por(self.acme, "c")

        primeira.refresh_from_db()
        self.assertEqual(primeira.situacao, "despachada")  # sentou na única vaga
        self.assertEqual(posicao(segunda), 1)
        self.assertEqual(posicao(terceira), 2)

    def test_a_cadeira_so_e_ocupada_por_um_com_uma_vaga(self):
        with _sem_broker():
            self._por(self.acme, "a")
            self._por(self.beta, "b")
        self.assertEqual(
            TarefaNaFila.objects.filter(situacao="despachada").count(), 1,
        )

    def test_concluir_libera_a_cadeira_e_chama_o_proximo(self):
        with _sem_broker():
            self._por(self.acme, "a")
            segunda = self._por(self.beta, "b")
            concluir("a")

        segunda.refresh_from_db()
        self.assertEqual(segunda.situacao, "despachada")

    def test_o_mesmo_trabalho_nao_ocupa_dois_lugares(self):
        with _sem_broker():
            uma = self._por(self.acme, "mesma")
            outra = self._por(self.acme, "mesma")
        self.assertEqual(uma.pk, outra.pk)
        self.assertEqual(TarefaNaFila.objects.count(), 1)

    def test_cancelar_tira_da_fila_e_anda_com_o_resto(self):
        with _sem_broker():
            self._por(self.acme, "a")
            segunda = self._por(self.beta, "b")
            cancelar("a")
        segunda.refresh_from_db()
        self.assertEqual(segunda.situacao, "despachada")


@override_settings(FROTA_VAGAS={"conversao": 1})
class PrioridadeEntrePlanosTests(FrotaTestBase):
    def test_premium_passa_na_frente_de_free_que_chegou_antes(self):
        """A reserva do premium não é decoração: com a frota cheia de free, a
        cadeira que vagar é dele."""
        with _sem_broker():
            self._por(self.acme, "ocupa", plano="free")   # senta na única vaga
            free = self._por(self.beta, "free-2", plano="free")
            premium = self._por(self.beta, "premium", plano="empresarial")

        self.assertEqual(posicao(premium), 1)
        self.assertEqual(posicao(free), 2)

    def test_plano_desconhecido_cai_em_comum_e_nunca_em_premium(self):
        """Na dúvida, o benefício não é presumido — a régua de sempre. Acontece
        de verdade no reprocessamento em massa, que não tem usuário."""
        self.assertEqual(classe_do_plano(""), "comum")
        self.assertEqual(classe_do_plano("plano-que-nao-existe"), "comum")
        self.assertEqual(classe_do_plano("EMPRESARIAL"), "premium")


@override_settings(FROTA_VAGAS={"conversao": 10})
class CadeiraMarcadaTests(FrotaTestBase):
    def test_free_tem_cadeira_garantida_com_a_fila_cheia_de_premium(self):
        """**A metade que prioridade pura não faz.** Com 10 vagas, 2 são do free
        (20%); ainda que 20 premium cheguem antes, o free senta — é o que impede
        "espera uma eternidade" de virar o comportamento normal."""
        with _sem_broker():
            for i in range(20):
                self._por(self.acme, f"p{i}", plano="empresarial")
            free = self._por(self.beta, "free", plano="free")

        free.refresh_from_db()
        self.assertEqual(free.situacao, "despachada")
        # E o premium não passou de onde podia: 5 reservadas + 3 livres.
        premium_em_voo = TarefaNaFila.objects.filter(
            situacao="despachada", plano="empresarial",
        ).count()
        self.assertEqual(premium_em_voo, 8)

    def test_premium_tem_cadeira_garantida_com_a_fila_cheia_de_free(self):
        with _sem_broker():
            for i in range(20):
                self._por(self.acme, f"f{i}", plano="free")
            premium = self._por(self.beta, "premium", plano="empresarial")

        premium.refresh_from_db()
        self.assertEqual(premium.situacao, "despachada")


@override_settings(FROTA_VAGAS={"conversao": 1})
class RecolocacaoTests(FrotaTestBase):
    def test_volta_para_o_fim_da_fila_e_cede_a_vez(self):
        """PRA.11 — quem esperou passa na frente do arquivo que já usou um turno."""
        with _sem_broker():
            pesado = self._por(self.acme, "pesado")
            esperando = self._por(self.beta, "leve")
            recolocar("pesado")

        pesado.refresh_from_db()
        esperando.refresh_from_db()
        self.assertEqual(esperando.situacao, "despachada")
        self.assertEqual(pesado.situacao, "aguardando")
        self.assertEqual(pesado.voltas, 1)

    def test_a_primeira_volta_fica_ATRAS_de_quem_nao_gastou_turno(self):
        """A metade "volta pro fim" da decisão, e ela quase não existiu.

        A primeira versão só tinha o degrau: a volta nº 1 já punha o arquivo à
        frente de todo mundo do mesmo plano, o que é literalmente o oposto do que
        foi pedido. É a penalidade que faz o fim da fila ser o fim da fila.
        """
        with _sem_broker():
            pesado = self._por(self.acme, "pesado")
            recem = self._por(self.beta, "recem")
            recolocar("pesado")

        pesado.refresh_from_db()
        recem.refresh_from_db()
        self.assertGreater(pesado.prioridade, recem.prioridade)

    def test_depois_de_muitas_voltas_ele_ultrapassa_e_termina(self):
        """A metade "crescente". Sem ela, um arquivo de 40 MB atrás de um fluxo
        contínuo de arquivos pequenos voltaria ao fim para sempre — o oposto de
        "continua assim até terminar"."""
        with _sem_broker():
            pesado = self._por(self.acme, "pesado")
            for _ in range(15):
                TarefaNaFila.objects.filter(chave="pesado").update(situacao="despachada")
                recolocar("pesado")
            recem = self._por(self.beta, "recem")

        pesado.refresh_from_db()
        self.assertEqual(pesado.voltas, 15)
        self.assertLess(pesado.prioridade, recem.prioridade)

    def test_o_envelhecimento_nao_compra_o_patamar_do_plano_de_cima(self):
        """A banda que mantém os patamares estanques. Sem ela, um free com
        voltas suficientes seria lido como `comum` e sentaria em cadeira que não
        é dele — a reserva vazando para quem mais espera."""
        with _sem_broker():
            free = self._por(self.acme, "free", plano="free")
            for _ in range(500):
                TarefaNaFila.objects.filter(chave="free").update(situacao="despachada")
                recolocar("free")
            comum = self._por(self.beta, "comum", plano="profissional")

        free.refresh_from_db()
        self.assertGreater(free.prioridade, comum.prioridade)


@override_settings(FROTA_VAGAS={"conversao": 1})
class PassarNaFrenteTests(FrotaTestBase):
    def test_o_admin_passa_na_frente_so_da_propria_empresa(self):
        """*(decisão do dono, 16/08/2026.)* Um botão que atrasasse o vizinho é um
        botão que todo mundo aperta sempre — zerando a prioridade e deixando só a
        fila imprevisível."""
        with _sem_broker():
            self._por(self.acme, "ocupa")        # senta na única vaga
            primeira_acme = self._por(self.acme, "acme-1")
            do_vizinho = self._por(self.beta, "beta-1")
            urgente = self._por(self.acme, "acme-2")

            antes_do_vizinho = posicao(do_vizinho)
            priorizar(urgente, user=self.admin)

        do_vizinho.refresh_from_db()
        urgente.refresh_from_db()
        primeira_acme.refresh_from_db()
        # Passou na frente da própria empresa...
        self.assertLess(posicao(urgente), posicao(primeira_acme))
        # ...e não atrasou ninguém de fora.
        self.assertEqual(posicao(do_vizinho), antes_do_vizinho)
        self.assertEqual(urgente.urgente_por_id, self.admin.pk)

    def test_o_aviso_diz_quantos_da_empresa_serao_atrasados(self):
        """O dono pediu o aviso junto com o botão. Sem o número, é um botão que
        todo mundo aperta sem saber o que faz."""
        with _sem_broker():
            self._por(self.acme, "ocupa")
            self._por(self.acme, "acme-1")
            self._por(self.beta, "beta-1")
            ultima = self._por(self.acme, "acme-2")

        aviso = situacao_da_fila(ultima)
        self.assertTrue(aviso["pode_priorizar"])
        self.assertEqual(aviso["na_frente_da_empresa"], 1)  # só a `acme-1`

    def test_sem_ninguem_da_empresa_na_frente_nao_ha_o_que_priorizar(self):
        with _sem_broker():
            self._por(self.beta, "ocupa")
            unica = self._por(self.acme, "acme-1")
        self.assertFalse(situacao_da_fila(unica)["pode_priorizar"])


@override_settings(FROTA_VAGAS={"conversao": 1})
class CadeiraPresaTests(FrotaTestBase):
    def test_worker_morto_nao_encolhe_a_frota_para_sempre(self):
        """A rede do desenho sem despachante próprio. Sem ela, cada OOM do cgroup
        levaria uma vaga embora em silêncio — e o sintoma seria uma fila cada vez
        mais lenta, sem nada nos logs."""
        from datetime import timedelta

        from django.utils import timezone

        with _sem_broker():
            self._por(self.acme, "morta")
            esperando = self._por(self.beta, "viva")

        TarefaNaFila.objects.filter(chave="morta").update(
            despachada_em=timezone.now() - timedelta(hours=2),
        )
        with _sem_broker():
            devolvidas = liberar_orfas()

        self.assertEqual(devolvidas, 1)
        esperando.refresh_from_db()
        self.assertEqual(esperando.situacao, "despachada")

    def test_broker_fora_devolve_a_linha_em_vez_de_perder_a_cadeira(self):
        """Marcar `despachada` uma mensagem que não saiu prometeria uma cadeira
        ocupada por trabalho que nunca vai rodar — a frota encolheria a cada
        tentativa."""
        with mock.patch("celery.current_app.send_task", side_effect=OSError("broker fora")):
            tarefa = self._por(self.acme, "a")

        tarefa.refresh_from_db()
        self.assertEqual(tarefa.situacao, "aguardando")


@override_settings(FROTA_VAGAS={"conversao": 1})
class CederSoComFilaTests(FrotaTestBase):
    """Ceder a vez para uma fila VAZIA é desperdício puro (decisão do dono, 16/08/2026).

    Antes desta regra o arquivo pesado se interrompia no fim do turno mesmo sem
    ninguém para receber a cadeira — e a passada seguinte repetia o custo fixo, que
    a medição de 16/08 pôs em 56% do relógio. `ha_espera` é a pergunta que o motor
    faz, entre uma folha e outra, para não pagar esse preço à toa.
    """

    def test_fila_vazia_nao_pede_a_vez(self):
        with _sem_broker():
            sozinha = self._por(self.acme, "sozinha")

        sozinha.refresh_from_db()
        self.assertEqual(sozinha.situacao, "despachada")
        self.assertFalse(
            ha_espera("sozinha"),
            "com a fila vazia o motor deve continuar trabalhando, não voltar ao fim",
        )

    def test_quem_chega_depois_pede_a_vez(self):
        with _sem_broker():
            self._por(self.acme, "pesada")
            self._por(self.beta, "leve")   # não cabe na única vaga: fica aguardando

        self.assertTrue(
            ha_espera("pesada"),
            "com alguém aguardando, o motor tem de ceder a vez na próxima folha",
        )

    def test_quem_ja_esta_rodando_nao_conta_como_espera(self):
        """Cadeira ocupada não está esperando por ESTA vaga.

        Contá-la faria o arquivo pesado ceder a vez para quem não a receberia —
        pagando o custo fixo e voltando a sentar na mesma cadeira.
        """
        # Frota folgada de propósito: com poucas vagas a RESERVA de plano seguraria
        # a segunda tarefa em `aguardando` e o teste mediria outra coisa.
        with override_settings(FROTA_VAGAS={"conversao": 10}), _sem_broker():
            uma = self._por(self.acme, "uma")
            outra = self._por(self.beta, "outra")

        uma.refresh_from_db()
        outra.refresh_from_db()
        self.assertEqual([uma.situacao, outra.situacao], ["despachada", "despachada"])
        self.assertFalse(ha_espera("uma"), "duas rodando, ninguém aguardando")

    def test_a_propria_tarefa_nao_pede_a_propria_vez(self):
        """Sem excluir a própria chave, a tarefa cederia a vez para si mesma.

        A janela em que isso importa é estreita e real: entre `recolocar` e o fim
        da passada que ainda está rodando, a linha já reaparece como `aguardando`.
        Se ela se contasse, a resposta seria "sim, há fila" para sempre — e o
        arquivo pesado cederia a vez a cada folha, sem nunca terminar.

        Uma vaga e duas tarefas: a primeira senta, a segunda fica aguardando. Do
        ponto de vista da SEGUNDA, a fila de espera está vazia — a única outra
        tarefa está rodando, não esperando —, e é essa a resposta que ela tem de
        obter sobre si mesma.
        """
        with _sem_broker():
            rodando = self._por(self.acme, "rodando")
            esperando = self._por(self.beta, "esperando")

        rodando.refresh_from_db()
        esperando.refresh_from_db()
        self.assertEqual(rodando.situacao, "despachada")
        self.assertEqual(esperando.situacao, "aguardando")
        self.assertFalse(
            ha_espera("esperando"),
            "a tarefa não pode se contar como a fila que a faz ceder a vez",
        )
