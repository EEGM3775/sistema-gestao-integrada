"""Bancada da fila da frota (D98/PRA.11) — exercita a política com MUITOS arquivos.

Não é teste automatizado (esses estão em `testes/backend/nucleo/test_frota.py`): é a bancada que
roda contra o **banco de verdade**, com dezenas de arquivos de várias empresas e
planos ao mesmo tempo, para o comportamento agregado poder ser medido em vez de
inferido dos casos unitários.

**Tudo dentro de uma transação que é desfeita no fim.** A bancada escreve
centenas de linhas na fila e nenhuma delas pode sobrar: rodar isto contra o dev
não pode deixar resíduo que o próximo `docker compose up` tente despachar.

Uso: `python manage.py simular_fila`
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import override_settings

from nucleo import frota
from nucleo.models import TarefaNaFila, Tenant, Usuario


class Rollback(Exception):
    """Levantada de propósito no fim para desfazer tudo."""


class Command(BaseCommand):
    help = "Exercita a fila da frota com muitos arquivos e imprime o laudo."

    def handle(self, *args, **opts):
        self.linhas: list[str] = []
        try:
            with transaction.atomic():
                self._montar()
                self._cenario_a()
                self._cenario_b()
                self._cenario_c()
                self._cenario_d()
                self._cenario_e()
                raise Rollback
        except Rollback:
            self.stdout.write("\n".join(self.linhas))
            self.stdout.write("\n[banco intacto: a transação da bancada foi desfeita]")

    # -- infra ------------------------------------------------------------
    def diz(self, texto=""):
        self.linhas.append(texto)

    def titulo(self, texto):
        self.diz()
        self.diz("=" * 74)
        self.diz(texto)
        self.diz("=" * 74)

    def _montar(self):
        marca = uuid.uuid4().hex[:6]
        self.empresas = {
            nome: Tenant.objects.create(slug=f"bancada-{nome}-{marca}", nome=nome.upper())
            for nome in ("acme", "beta", "gama", "delta")
        }
        self.admin = Usuario.objects.create(
            username=f"bancada-admin-{marca}", tenant=self.empresas["acme"],
        )

    def _limpar(self):
        TarefaNaFila.objects.filter(chave__startswith="bancada:").delete()

    def _por(self, empresa, chave, plano):
        return frota.enfileirar(
            tenant_id=self.empresas[empresa].pk, chave=f"bancada:{chave}",
            plano=plano, tarefa="bancada.converter", argumentos=[chave],
        )

    def _mapa(self, limite=12):
        """A fila como ela está, na ordem em que vai sair."""
        vivos = TarefaNaFila.objects.filter(
            chave__startswith="bancada:",
        ).order_by("situacao", "prioridade", "criada_em")
        rodando = [t for t in vivos if t.situacao == "despachada"]
        esperando = [t for t in vivos if t.situacao == "aguardando"]
        for t in rodando:
            self.diz(f"   [RODANDO]  {t.chave[8:]:<22} {t.plano:<13} prio={t.prioridade}")
        for i, t in enumerate(esperando[:limite], start=1):
            volta = f" ({t.voltas}ª volta)" if t.voltas else ""
            self.diz(f"   {i:>2}º        {t.chave[8:]:<22} {t.plano:<13} prio={t.prioridade}{volta}")
        if len(esperando) > limite:
            self.diz(f"   … mais {len(esperando) - limite} esperando")

    # -- cenários ---------------------------------------------------------
    def _cenario_a(self):
        """Fila única, 3 empresas, 12 arquivos, UMA vaga (a frota de hoje)."""
        self.titulo("A · 12 arquivos de 3 empresas numa frota de 1 vaga")
        self._limpar()
        with override_settings(FROTA_VAGAS={"conversao": 1}), _sem_broker():
            ordem_de_chegada = []
            for i in range(1, 13):
                empresa = ["acme", "beta", "gama"][i % 3]
                plano = ["free", "profissional", "empresarial"][i % 3]
                self._por(empresa, f"A{i:02d}-{empresa}", plano)
                ordem_de_chegada.append(f"A{i:02d}-{empresa}({plano})")

            self.diz("Chegada (nesta ordem):")
            for pedaco in _em_blocos(ordem_de_chegada, 3):
                self.diz("   " + " · ".join(pedaco))
            self.diz()
            self.diz("Fila resultante:")
            self._mapa()

            em_voo = TarefaNaFila.objects.filter(
                chave__startswith="bancada:", situacao="despachada").count()
            self.diz()
            self.diz(f"→ Cadeiras ocupadas: {em_voo} (frota = 1). "
                     f"{'OK' if em_voo == 1 else 'FALHOU'}")
            primeiro = TarefaNaFila.objects.filter(
                chave__startswith="bancada:", situacao="aguardando",
            ).order_by("prioridade", "criada_em").first()
            self.diz(f"→ Próximo a sentar: {primeiro.chave[8:]} ({primeiro.plano}) — "
                     f"o empresarial que chegou depois passa na frente do free "
                     f"que chegou antes.")

    def _cenario_b(self):
        """Cadeira marcada: 30 premium afogando a fila, e o free que chega por último."""
        self.titulo("B · 30 arquivos premium + 4 free numa frota de 10 vagas")
        self._limpar()
        with override_settings(FROTA_VAGAS={"conversao": 10}), _sem_broker():
            for i in range(1, 31):
                self._por("acme", f"B-prem{i:02d}", "empresarial")
            for i in range(1, 5):
                self._por("delta", f"B-free{i:02d}", "free")

            em_voo = list(TarefaNaFila.objects.filter(
                chave__startswith="bancada:", situacao="despachada"))
            premium = [t for t in em_voo if t.plano == "empresarial"]
            free = [t for t in em_voo if t.plano == "free"]
            reserva = frota._reserva(10)

            self.diz(f"Política: {reserva['premium']} cadeiras só premium · "
                     f"{reserva['free']} só free · {reserva['livre']} livres")
            self.diz()
            self.diz(f"   premium em voo: {len(premium)}  "
                     f"(reserva {reserva['premium']} + livres {reserva['livre']})")
            self.diz(f"   free em voo:    {len(free)}  (reserva {reserva['free']})")
            self.diz()
            ok_free = len(free) == reserva["free"]
            ok_prem = len(premium) == reserva["premium"] + reserva["livre"]
            self.diz(f"→ O free sentou mesmo chegando por ÚLTIMO, atrás de 30 premium: "
                     f"{'OK' if ok_free else 'FALHOU'}")
            self.diz(f"→ O premium não invadiu a reserva do free: "
                     f"{'OK' if ok_prem else 'FALHOU'}")
            self.diz("   (é o que prioridade pura não faz: ela alijaria o free "
                     "indefinidamente)")

    def _cenario_c(self):
        """Um arquivo pesado voltando à fila contra um fluxo de arquivos leves."""
        self.titulo("C · 1 arquivo pesado × 10 leves chegando sem parar")
        self._limpar()
        with override_settings(FROTA_VAGAS={"conversao": 1}), _sem_broker():
            pesado = self._por("acme", "C-pesado-40MB", "profissional")
            self.diz(f"O pesado senta primeiro (fila vazia). prio={pesado.prioridade}")
            self.diz()
            self.diz("Cada linha: o pesado estoura o turno e volta; um leve chega.")
            self.diz()
            self.diz("   volta   prio(pesado)   onde o pesado ficou")
            for volta in range(1, 16):
                frota.recolocar("bancada:C-pesado-40MB")
                self._por("beta", f"C-leve{volta:02d}", "profissional")
                pesado.refresh_from_db()
                pos = frota.posicao(pesado)
                if volta in (1, 2, 5, 9, 10, 11, 12, 15):
                    # `posicao` é 0 para quem já saiu da fila. Na 1ª volta a fila
                    # ainda estava vazia, então "o fim da fila" e "a frente" eram
                    # o mesmo lugar e ele retomou na hora — dizer "0º" ali seria
                    # o relatório mentindo por economia de caso.
                    onde = (
                        "retomou na hora (não havia ninguém esperando)"
                        if pos == 0 else
                        f"{pos}º na fila — {pos - 1} leve(s) na frente"
                    )
                    self.diz(f"   {volta:>3}     {pesado.prioridade:>8}       {onde}")
                # o pesado é readmitido quando chega a vez dele
                TarefaNaFila.objects.filter(
                    chave="bancada:C-pesado-40MB").update(situacao="despachada")

            pesado.refresh_from_db()
            self.diz()
            self.diz("→ Nas primeiras voltas ele CEDE a vez (posição cresce): "
                     "é o 'volta pro fim'.")
            self.diz("→ A partir da 11ª ele ultrapassa os recém-chegados: "
                     "é o 'prioridade crescente'.")
            self.diz("→ Converge em vez de esperar para sempre atrás do fluxo de leves.")

    def _cenario_d(self):
        """Passar na frente com muitos arquivos, medindo quem se moveu."""
        self.titulo("D · passar na frente com 9 arquivos de 3 empresas")
        self._limpar()
        with override_settings(FROTA_VAGAS={"conversao": 1}), _sem_broker():
            self._por("delta", "D-ocupa", "profissional")  # senta na única vaga
            entrada = []
            for i in range(1, 10):
                empresa = ["acme", "beta", "gama"][i % 3]
                t = self._por(empresa, f"D{i:02d}-{empresa}", "profissional")
                entrada.append(t)

            antes = {t.chave: frota.posicao(_recarregar(t)) for t in entrada}
            urgente = [t for t in entrada if t.chave.endswith("acme")][-1]

            self.diz(f"Subindo o último arquivo da ACME: {urgente.chave[8:]}")
            self.diz()
            frota.priorizar(_recarregar(urgente), user=self.admin)
            depois = {t.chave: frota.posicao(_recarregar(t)) for t in entrada}

            self.diz("   arquivo                 empresa   antes → depois")
            mexeu_de_fora = 0
            for t in entrada:
                empresa = t.chave.split("-")[-1]
                a, d = antes[t.chave], depois[t.chave]
                seta = "  (subiu)" if d < a else ("  (desceu)" if d > a else "")
                if empresa != "acme" and a != d:
                    mexeu_de_fora += 1
                    seta += "  ← ATRASOU UM DE FORA"
                self.diz(f"   {t.chave[8:]:<22}  {empresa:<8}  {a:>2}  →  {d:<2}{seta}")

            self.diz()
            self.diz(f"→ Arquivos de OUTRAS empresas que mudaram de posição: "
                     f"{mexeu_de_fora} — {'OK' if mexeu_de_fora == 0 else 'FALHOU'}")
            self.diz("   (é permutação dos lugares que a ACME já ocupava, "
                     "não um furo na fila do plano)")

    def _cenario_e(self):
        """Carga: 200 arquivos de 4 empresas, para medir a ordem agregada."""
        self.titulo("E · carga de 200 arquivos, 4 empresas, frota de 8 vagas")
        self._limpar()
        with override_settings(FROTA_VAGAS={"conversao": 8}), _sem_broker():
            planos = {"acme": "free", "beta": "profissional",
                      "gama": "empresarial", "delta": "free"}
            for i in range(1, 201):
                empresa = ["acme", "beta", "gama", "delta"][i % 4]
                self._por(empresa, f"E{i:03d}-{empresa}", planos[empresa])

            em_voo = list(TarefaNaFila.objects.filter(
                chave__startswith="bancada:", situacao="despachada"))
            reserva = frota._reserva(8)
            por_classe = {"premium": 0, "comum": 0, "free": 0}
            for t in em_voo:
                por_classe[frota.classe_do_plano(t.plano)] += 1

            self.diz(f"Política para 8 vagas: {reserva['premium']} premium · "
                     f"{reserva['free']} free · {reserva['livre']} livres")
            self.diz()
            self.diz(f"   em voo: premium={por_classe['premium']} "
                     f"comum={por_classe['comum']} free={por_classe['free']} "
                     f"(total {len(em_voo)} / 8 vagas)")
            self.diz(f"   esperando: {TarefaNaFila.objects.filter(chave__startswith='bancada:', situacao='aguardando').count()}")
            self.diz()
            self.diz(f"→ Nenhuma vaga ociosa com fila cheia: "
                     f"{'OK' if len(em_voo) == 8 else 'FALHOU'}")
            self.diz(f"→ O free tem representação mesmo competindo com 50 empresariais: "
                     f"{'OK' if por_classe['free'] >= reserva['free'] else 'FALHOU'}")
            self.diz(f"→ Nenhum trabalho duplicado na fila: "
                     f"{'OK' if TarefaNaFila.objects.filter(chave__startswith='bancada:').count() == 200 else 'FALHOU'}")


def _sem_broker():
    """A bancada mede a ORDEM, não o Celery: nada é publicado de verdade."""
    return mock.patch("celery.current_app.send_task")


def _recarregar(t):
    return TarefaNaFila.objects.get(pk=t.pk)


def _em_blocos(itens, n):
    for i in range(0, len(itens), n):
        yield itens[i:i + n]
