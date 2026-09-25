"""Camada 2 — token bucket por fornecedor (docs/arquitetura/rate-limiting.md).

O que estes testes protegem, em ordem de importância:

1. **O limite conta CHAMADAS AO FORNECEDOR, não requisições à nossa API.** Era o
   defeito do desenho anterior: `emitir-lote` recebe uma lista, emite N notas numa
   requisição só e o contador de entrada marcava 1.
2. **Rajada passa, ritmo sustentado é respeitado** — lote de fechamento não pode
   virar fila, mas o fornecedor não pode ser inundado depois que o balde esvazia.
3. **Falta de token vira espera, não erro** — e, numa view síncrona, vira 429 com
   `Retry-After` em vez de 500.
4. **Redis fora não trava a emissão** (fail-open), mas grita no log.
"""
from unittest import mock

from django.test import SimpleTestCase, override_settings

from nucleo import rate_limit
from nucleo.rate_limit import LimiteFornecedorExcedido, consumir

# Balde pequeno e taxa lenta: torna o teste determinístico sem depender de tempo real.
_CONF = {"acme": {"taxa_por_segundo": 1, "burst": 3}}


class TokenBucketTests(SimpleTestCase):
    def setUp(self):
        # Cada teste começa com balde limpo — o estado vive no Redis e vazaria
        # entre testes (a mesma armadilha que o throttle de entrada causou).
        rate_limit._cliente = None
        rate_limit._script = None
        self._limpar()

    def _limpar(self):
        try:
            cliente, _ = rate_limit._redis()
            for chave in cliente.scan_iter("ratelimit:fornecedor:acme*"):
                cliente.delete(chave)
        except Exception:  # noqa: BLE001 — sem Redis, os testes que precisam dele pulam
            pass

    @override_settings(RATE_LIMIT_FORNECEDORES=_CONF)
    def test_rajada_ate_o_tamanho_do_balde_passa(self):
        """Lote legítimo não pode virar fila: o burst existe para isto."""
        for i in range(3):
            consumir("acme")  # não levanta

    @override_settings(RATE_LIMIT_FORNECEDORES=_CONF)
    def test_estourou_o_balde_vira_espera(self):
        for _ in range(3):
            consumir("acme")
        with self.assertRaises(LimiteFornecedorExcedido) as ctx:
            consumir("acme")
        self.assertEqual(ctx.exception.fornecedor, "acme")
        self.assertGreaterEqual(ctx.exception.espera_segundos, 1)

    @override_settings(RATE_LIMIT_FORNECEDORES=_CONF)
    def test_e_uma_excecao_do_drf_com_retry_after(self):
        """Views síncronas (gerar-cobranca, divergencias-asaas) capturam só
        AsaasAPIError — uma exceção comum viraria 500. Sendo Throttled, o DRF
        devolve 429 com Retry-After sozinho."""
        from rest_framework.exceptions import Throttled

        for _ in range(3):
            consumir("acme")
        with self.assertRaises(Throttled) as ctx:
            consumir("acme")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIsNotNone(ctx.exception.wait)

    @override_settings(RATE_LIMIT_FORNECEDORES=_CONF)
    def test_reposicao_devolve_token_com_o_tempo(self):
        """1 token/s: depois de ~1,1s de relógio simulado, passa de novo."""
        for _ in range(3):
            consumir("acme")
        with self.assertRaises(LimiteFornecedorExcedido):
            consumir("acme")
        agora = rate_limit.time.time()
        with mock.patch.object(rate_limit.time, "time", return_value=agora + 1.1):
            consumir("acme")  # não levanta

    @override_settings(RATE_LIMIT_FORNECEDORES=_CONF)
    def test_baldes_sao_independentes_por_fornecedor(self):
        """Esgotar a NFE.io não pode impedir o envio de e-mail."""
        for _ in range(3):
            consumir("acme")
        consumir("outro_fornecedor_sem_limite")  # não configurado → passa

    @override_settings(RATE_LIMIT_FORNECEDORES=_CONF)
    def test_chave_extra_separa_baldes(self):
        """Quando a credencial virar por tenant, cada empresa tem a própria cota
        no fornecedor — um balde único limitaria empresas sem relação entre si."""
        for _ in range(3):
            consumir("acme", chave_extra="tenant-a")
        consumir("acme", chave_extra="tenant-b")  # balde de outro tenant, intacto

    @override_settings(RATE_LIMIT_FORNECEDORES={})
    def test_fornecedor_sem_configuracao_passa(self):
        """Integração nova não pode ficar bloqueada por esquecimento de config."""
        for _ in range(50):
            consumir("servico_novo")

    @override_settings(RATE_LIMIT_FORNECEDORES=_CONF, RATE_LIMIT_DESLIGADO=True)
    def test_desligamento_explicito(self):
        for _ in range(50):
            consumir("acme")

    @override_settings(RATE_LIMIT_FORNECEDORES=_CONF)
    def test_redis_fora_nao_trava_a_emissao_mas_grita(self):
        """Fail-open é decisão: travar pararia nota e boleto do sistema inteiro.
        Mas silêncio foi o que causou o D21 — o log tem de ser de ERRO."""
        with mock.patch.object(rate_limit, "_redis", side_effect=OSError("redis fora")):
            with self.assertLogs("nucleo.rate_limit", level="ERROR") as logs:
                consumir("acme")
        self.assertTrue(
            any("RATE LIMIT INATIVO" in linha for linha in logs.output),
            f"esperava alerta de limitador inativo; veio: {logs.output}",
        )


class TaskReagendaTests(SimpleTestCase):
    """Sem token, a task tem de ESPERAR — não falhar e não bloquear o worker.

    Falhar mandaria para a DLQ uma nota que só precisava esperar a fila do
    fornecedor andar. Bloquear seria pior: worker parado esperando token deixa de
    atender toda a fila, inclusive tarefas de outros tenants.
    """

    #: **O banco é declarado ainda que o teste não o use** (D148). O
    #: `log_task_end` de `nucleo/signals.py` grava um `LogAtividadeUsuario` por
    #: task encerrada; num `SimpleTestCase` o Django recusa a escrita, o
    #: dispatcher do Celery engole a exceção e **loga o traceback como ERROR** —
    #: a cada `manage.py test`, com a suíte verde. O teste passava e a produção
    #: estava certa; o custo era de leitura, e um traceback com a palavra
    #: CRÍTICO impresso em toda execução treina o olho a ignorar exatamente a
    #: linha que um dia vai importar.
    databases = {"default"}

    def test_limite_de_fornecedor_vira_retry_e_nao_falha(self):
        from celery import shared_task
        from celery.exceptions import Retry

        from nucleo.tasks import DLQTask

        @shared_task(bind=True, base=DLQTask, max_retries=3)
        def _task_que_bate_no_limite(self):
            raise LimiteFornecedorExcedido("acme", 42)

        with mock.patch.object(DLQTask, "retry", side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                _task_que_bate_no_limite.apply(throw=True)

        self.assertTrue(retry.called, "limite de fornecedor não virou retry")
        kwargs = retry.call_args.kwargs
        self.assertEqual(kwargs.get("countdown"), 42, "não esperou o tempo informado pelo balde")
        # Orçamento próprio: esperar a janela do fornecedor não pode consumir as
        # tentativas reservadas a falhas de verdade (rede, 5xx).
        self.assertEqual(kwargs.get("max_retries"), DLQTask.RATE_LIMIT_MAX_RETRIES)
        self.assertGreater(DLQTask.RATE_LIMIT_MAX_RETRIES, 3)


class ContagemPorChamadaRealTests(SimpleTestCase):
    """O ponto central do desenho: o token é consumido no CLIENTE HTTP, então um
    lote de N notas consome N tokens — não 1, como contaria um limite de entrada."""

    def setUp(self):
        rate_limit._cliente = None
        rate_limit._script = None
        try:
            cliente, _ = rate_limit._redis()
            for chave in cliente.scan_iter("ratelimit:fornecedor:nfe_io*"):
                cliente.delete(chave)
        except Exception:  # noqa: BLE001
            pass

    @override_settings(
        RATE_LIMIT_FORNECEDORES={"nfe_io": {"taxa_por_segundo": 1, "burst": 5}},
        NFE_IO_API_KEY="k", NFE_IO_COMPANY_ID="c",
    )
    def test_lote_de_notas_consome_um_token_por_nota(self):
        from moduloerp.nfe_client import NFeClient

        cliente = NFeClient()
        with mock.patch("moduloerp.nfe_client.requests.request") as req:
            req.return_value = mock.Mock(
                status_code=200, ok=True, content=b"{}", json=lambda: {"id": "1"}
            )
            for _ in range(5):
                cliente._request("POST", "/x")
            self.assertEqual(req.call_count, 5)

            # 6ª nota do mesmo lote: balde vazio → espera, e a chamada NÃO sai.
            with self.assertRaises(LimiteFornecedorExcedido):
                cliente._request("POST", "/x")
            self.assertEqual(req.call_count, 5, "chamou o fornecedor mesmo sem token")
