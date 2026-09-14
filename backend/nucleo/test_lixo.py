"""A lixeira da plataforma — o que fecha o D116.

O achado nasceu de uma frase simples: *uma obra que ganhou plano nunca mais sai
pela API*. `CalendarioTrabalho.obra` é `CASCADE`, `Cronograma.calendario` é
`PROTECT`, e o coletor do Django não isenta o que já está na fila de exclusão —
a combinação é impossível de satisfazer.

Este arquivo prova as duas metades da saída:

1. **excluir não apaga** — marca a lápide, e por isso o impasse acima nem é
   consultado. É o que faz a obra do D116 sair de vista hoje;
2. **a purga apaga**, e aí o impasse é desatado no lugar certo (o receptor do
   módulo dono), com o plano modelo sobrevivendo como o dono mandou.

O alvo dos cenários é a **`Obra`**, e não um modelo de mentira: é ela que abriu o
achado, é ela que carrega o nó `CASCADE`/`PROTECT`, e é sobre ela que a decisão
do dono foi escrita.
"""
from datetime import date, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient
from django.utils import timezone

from modulopdca.models import CalendarioTrabalho, Cronograma
from obras.models import EtapaObra, Obra
from payment.planos import LIXO_RETENCAO_PADRAO_DIAS

from .lixo import (
    antes_de_purgar, alvo_de, item_de, mover_para_lixo, purgar, purgar_vencidos,
    restaurar, retencao_dias,
)
from .models import Lixo, Tenant, Usuario


class BaseLixeira(TestCase):
    """Uma empresa, uma obra com plano — exatamente o cenário do D116."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="lixeira", nome="Construtora Lixeira")
        cls.outro_tenant = Tenant.objects.create(slug="vizinha", nome="Construtora Vizinha")
        cls.usuario = Usuario.objects.create(username="gestor", tenant=cls.tenant)
        cls.usuario.iam_quotas = {"lixo_retencao_dias": 15}

    def setUp(self):
        self.obra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial Aurora", endereco="Rua 1",
        )
        self.calendario = CalendarioTrabalho.objects.create(
            tenant=self.tenant, obra=self.obra, nome="Calendário da Aurora",
        )
        self.cronograma = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano v1",
            data_inicio=date(2026, 1, 5), calendario=self.calendario,
        )


class ExcluirMarcaALapideTests(BaseLixeira):
    def test_a_obra_do_d116_sai_de_vista_sem_esbarrar_no_protect(self):
        """O achado inteiro, em um teste.

        Antes: `obra.delete()` com um cronograma de pé levantava `ProtectedError`
        (que virava 409 depois do D117, e 500 mudo antes dele). Agora a exclusão
        não consulta o `PROTECT` — ela não apaga nada.
        """
        item = mover_para_lixo(self.obra, usuario=self.usuario, motivo="cancelada")

        self.assertIsNotNone(item.pk)
        self.obra.refresh_from_db()
        self.assertIsNotNone(self.obra.excluido_em)
        self.assertEqual(self.obra.excluido_por, self.usuario)
        self.assertEqual(self.obra.motivo_exclusao, "cancelada")
        # E o que estava de pé continua de pé — nada cascateou.
        self.assertTrue(Cronograma.objects.filter(pk=self.cronograma.pk).exists())
        self.assertTrue(CalendarioTrabalho.objects.filter(pk=self.calendario.pk).exists())

    def test_some_do_gerente_padrao_mas_nao_do_banco(self):
        mover_para_lixo(self.obra, usuario=self.usuario)

        self.assertFalse(Obra.objects.filter(pk=self.obra.pk).exists())
        self.assertTrue(Obra.todos.filter(pk=self.obra.pk).exists())
        self.assertEqual(Obra.todos.no_lixo().count(), 1)

    def test_a_travessia_de_fk_continua_enxergando_o_excluido(self):
        """`_base_manager` não filtra — e é disso que o ORM se serve.

        Se filtrasse, `cronograma.obra` levantaria `DoesNotExist` no meio de
        qualquer serializer que tocasse a obra na lixeira, e a própria tela do
        lixo não conseguiria dizer de quem era o quê.
        """
        mover_para_lixo(self.obra, usuario=self.usuario)

        cronograma = Cronograma.objects.get(pk=self.cronograma.pk)
        self.assertEqual(cronograma.obra_id, self.obra.pk)
        self.assertEqual(cronograma.obra.nome_obra, "Residencial Aurora")

    def test_a_relacao_reversa_herda_o_corte(self):
        etapa = EtapaObra.objects.create(
            tenant=self.tenant, obra=self.obra, nome_etapa="Fundação", ordem=1,
        )
        self.assertEqual(self.obra.etapas.count(), 1)

        mover_para_lixo(etapa, usuario=self.usuario)
        self.assertEqual(self.obra.etapas.count(), 0)

    def test_excluir_duas_vezes_e_recusado(self):
        mover_para_lixo(self.obra, usuario=self.usuario)
        self.obra.refresh_from_db()
        with self.assertRaises(ValidationError):
            mover_para_lixo(self.obra, usuario=self.usuario)

    def test_um_item_ativo_por_alvo(self):
        """A constraint parcial, e não a confiança no chamador."""
        mover_para_lixo(self.obra, usuario=self.usuario)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lixo.objects.create(
                tenant=self.tenant,
                alvo_tipo=ContentType.objects.get_for_model(Obra),
                alvo_id=self.obra.pk,
                rotulo="duplicata",
                excluido_em=timezone.now(),
                purgar_em=timezone.now() + timedelta(days=15),
            )

    def test_a_lixeira_libera_o_nome_para_recadastro(self):
        """Sem a condição na `UniqueConstraint`, o nome ficaria refém por 15 dias.

        É o defeito mais provável de uma lápide feita pela metade: o usuário
        exclui, tenta cadastrar de novo com o mesmo nome e leva "já existe" sobre
        um registro que ele não consegue ver em lugar nenhum.
        """
        mover_para_lixo(self.obra, usuario=self.usuario)
        gemea = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial Aurora", endereco="Rua 1",
        )
        self.assertNotEqual(gemea.pk, self.obra.pk)


class PrazoTests(BaseLixeira):
    def test_o_prazo_vem_do_plano_e_fica_congelado(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        esperado = item.excluido_em + timedelta(days=15)
        self.assertAlmostEqual(
            item.purgar_em, esperado, delta=timedelta(seconds=2),
        )

    def test_sem_claim_cai_no_padrao_em_vez_de_recusar(self):
        """Fail-open: token de serviço não pode impedir alguém de excluir."""
        sem_plano = Usuario.objects.create(username="servico", tenant=self.tenant)
        self.assertEqual(retencao_dias(sem_plano), LIXO_RETENCAO_PADRAO_DIAS)

        item = mover_para_lixo(self.obra, usuario=sem_plano)
        self.assertAlmostEqual(
            item.purgar_em,
            item.excluido_em + timedelta(days=LIXO_RETENCAO_PADRAO_DIAS),
            delta=timedelta(seconds=2),
        )

    def test_downgrade_de_plano_nao_encurta_a_janela_de_quem_ja_apagou(self):
        """O prazo é lido do campo gravado, nunca recalculado — `planos.py` §5.5g."""
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        gravado = item.purgar_em

        self.usuario.iam_quotas = {"lixo_retencao_dias": 3}  # downgrade
        item.refresh_from_db()
        self.assertEqual(item.purgar_em, gravado)


class RestaurarTests(BaseLixeira):
    def test_restaurar_e_o_inverso_exato(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario, motivo="engano")
        restaurar(item, usuario=self.usuario)

        self.obra.refresh_from_db()
        self.assertIsNone(self.obra.excluido_em)
        self.assertEqual(self.obra.motivo_exclusao, "")
        self.assertTrue(Obra.objects.filter(pk=self.obra.pk).exists())

        item.refresh_from_db()
        self.assertIsNotNone(item.restaurado_em)
        self.assertFalse(item.ativo)

    def test_restaurar_duas_vezes_e_recusado(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        restaurar(item, usuario=self.usuario)
        with self.assertRaises(ValidationError):
            restaurar(item, usuario=self.usuario)

    def test_depois_de_restaurar_da_para_excluir_de_novo(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        restaurar(item, usuario=self.usuario)
        self.obra.refresh_from_db()

        segundo = mover_para_lixo(self.obra, usuario=self.usuario)
        self.assertNotEqual(segundo.pk, item.pk)
        self.assertEqual(item_de(self.obra).pk, segundo.pk)


class PurgaTests(BaseLixeira):
    def test_a_purga_apaga_de_verdade_e_desata_o_no_do_calendario(self):
        """O `CASCADE`/`PROTECT` do D116, desatado no lugar certo.

        Sem o receptor do `modulopdca`, este `DELETE` seria recusado: o coletor
        veria `Cronograma.calendario` (`PROTECT`) apontando para um calendário
        que o `CASCADE` da obra também quer levar.
        """
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        item = purgar(item, usuario=self.usuario)

        self.assertEqual(item.falha_na_purga, "")
        self.assertIsNotNone(item.purgado_em)
        self.assertFalse(Obra.todos.filter(pk=self.obra.pk).exists())
        self.assertFalse(Cronograma.objects.filter(pk=self.cronograma.pk).exists())
        self.assertFalse(CalendarioTrabalho.objects.filter(pk=self.calendario.pk).exists())

    def test_o_plano_modelo_sobrevive_a_obra(self):
        """A decisão do dono de 23/08, cobrada aqui.

        *"Deixa o plano para poder ser usado como modelo em outra obra — e isso
        tem que ser possível para não ter que criar 300 planos em um
        empreendimento grande."*
        """
        modelo = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Torre padrão",
            versao=2, data_inicio=date(2026, 1, 5), calendario=self.calendario,
            eh_modelo=True, nome_modelo="Torre 20 pavimentos",
        )

        item = mover_para_lixo(self.obra, usuario=self.usuario)
        purgar(item, usuario=self.usuario)

        modelo.refresh_from_db()
        self.assertIsNone(modelo.obra_id)
        self.assertIsNone(modelo.calendario_id)
        self.assertTrue(modelo.eh_modelo)
        self.assertEqual(modelo.nome_modelo, "Torre 20 pavimentos")
        # E o plano COMUM morreu com a obra, que é o desenho.
        self.assertFalse(Cronograma.objects.filter(pk=self.cronograma.pk).exists())

    def test_a_lixeira_guarda_o_rotulo_depois_de_nao_haver_mais_o_que(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        purgar(item, usuario=self.usuario)

        item.refresh_from_db()
        self.assertEqual(item.rotulo, "Residencial Aurora")
        self.assertEqual(item.excluido_por_nome, "gestor")

    def test_purga_automatica_nao_inventa_um_ator(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        item = purgar(item, usuario=None)
        self.assertIsNotNone(item.purgado_em)
        self.assertIsNone(item.purgado_por)

    def test_a_purga_recusada_fica_escrita_e_o_item_continua_na_lixeira(self):
        """Regra 4 — o oposto do 500 mudo que abriu o D116."""

        def recusar(sender, alvo, item, **kwargs):
            raise ValidationError("a contabilidade ainda precisa desta obra")

        antes_de_purgar.connect(recusar, sender=Obra)
        try:
            item = mover_para_lixo(self.obra, usuario=self.usuario)
            item = purgar(item, usuario=self.usuario)
        finally:
            antes_de_purgar.disconnect(recusar, sender=Obra)

        self.assertIsNone(item.purgado_em)
        self.assertTrue(item.ativo)
        self.assertIn("contabilidade", item.falha_na_purga)
        # E nada foi apagado pela metade.
        self.assertTrue(Obra.todos.filter(pk=self.obra.pk).exists())

    def test_purgar_o_que_ja_saiu_e_erro_do_chamador(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        restaurar(item, usuario=self.usuario)
        with self.assertRaises(ValidationError):
            purgar(item, usuario=self.usuario)


class VarreduraTests(BaseLixeira):
    def test_so_leva_o_que_venceu(self):
        vencida = mover_para_lixo(self.obra, usuario=self.usuario)
        Lixo.objects.filter(pk=vencida.pk).update(
            purgar_em=timezone.now() - timedelta(days=1)
        )

        nova = Obra.objects.create(
            tenant=self.tenant, nome_obra="Edifício Novo", endereco="Rua 2",
        )
        no_prazo = mover_para_lixo(nova, usuario=self.usuario)

        resultado = purgar_vencidos()

        self.assertEqual(resultado["purgados"], 1)
        self.assertFalse(Obra.todos.filter(pk=self.obra.pk).exists())
        no_prazo.refresh_from_db()
        self.assertTrue(no_prazo.ativo)
        self.assertTrue(Obra.todos.filter(pk=nova.pk).exists())

    def test_nao_leva_o_que_foi_restaurado_no_prazo(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        Lixo.objects.filter(pk=item.pk).update(
            purgar_em=timezone.now() - timedelta(days=1)
        )
        item.refresh_from_db()
        restaurar(item, usuario=self.usuario)

        resultado = purgar_vencidos()

        self.assertEqual(resultado["purgados"], 0)
        self.assertTrue(Obra.objects.filter(pk=self.obra.pk).exists())

    def test_uma_recusa_nao_derruba_a_volta_inteira(self):
        """Transação por item — a obra teimosa não desfaz a purga das outras."""
        teimosa = Obra.objects.create(
            tenant=self.tenant, nome_obra="Obra Teimosa", endereco="Rua 3",
        )

        def recusar_so_a_teimosa(sender, alvo, item, **kwargs):
            if alvo.pk == teimosa.pk:
                raise ValidationError("esta não sai")

        antes_de_purgar.connect(recusar_so_a_teimosa, sender=Obra)
        try:
            for objeto in (self.obra, teimosa):
                item = mover_para_lixo(objeto, usuario=self.usuario)
                Lixo.objects.filter(pk=item.pk).update(
                    purgar_em=timezone.now() - timedelta(days=1)
                )
            resultado = purgar_vencidos()
        finally:
            antes_de_purgar.disconnect(recusar_so_a_teimosa, sender=Obra)

        self.assertEqual(resultado["purgados"], 1)
        self.assertEqual(resultado["recusados"], 1)
        self.assertFalse(Obra.todos.filter(pk=self.obra.pk).exists())
        self.assertTrue(Obra.todos.filter(pk=teimosa.pk).exists())

    def test_o_teto_da_volta_e_respeitado(self):
        for i in range(3):
            obra = Obra.objects.create(
                tenant=self.tenant, nome_obra=f"Obra {i}", endereco="Rua X",
            )
            item = mover_para_lixo(obra, usuario=self.usuario)
            Lixo.objects.filter(pk=item.pk).update(
                purgar_em=timezone.now() - timedelta(days=1)
            )

        resultado = purgar_vencidos(teto=2)
        self.assertEqual(resultado["encontrados"], 2)
        self.assertEqual(resultado["purgados"], 2)


class IsolamentoTests(BaseLixeira):
    def test_a_lixeira_de_uma_empresa_nao_enxerga_a_da_outra(self):
        vizinha = Obra.objects.create(
            tenant=self.outro_tenant, nome_obra="Obra da Vizinha", endereco="Rua 9",
        )
        outro_usuario = Usuario.objects.create(
            username="vizinho", tenant=self.outro_tenant,
        )

        mover_para_lixo(self.obra, usuario=self.usuario)
        mover_para_lixo(vizinha, usuario=outro_usuario)

        self.assertEqual(Lixo.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(
            Lixo.objects.filter(tenant=self.tenant).first().rotulo,
            "Residencial Aurora",
        )

    def test_alvo_de_resolve_o_que_esta_sob_a_lapide(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        recuperada = alvo_de(item)
        self.assertEqual(recuperada.pk, self.obra.pk)

    def test_alvo_de_devolve_none_depois_da_purga(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        purgar(item, usuario=self.usuario)
        item.refresh_from_db()
        self.assertIsNone(alvo_de(item))


class ApiDaLixeiraTests(BaseLixeira):
    """A tela lê a API — e foi aqui que ela se contradisse.

    O painel dizia *"1 na lixeira"* e a tabela logo abaixo dizia *"Nada na
    lixeira"*. Causa: este projeto não tem `DEFAULT_PAGINATION_CLASS` global, e
    ViewSet sem paginador devolve **array puro** em vez do envelope
    `{count, results}`. O `resumo/` é um objeto e funcionava; a lista não.

    A asserção que importa não é "responde 200" — é **a lista e o resumo
    concordarem**. Um teste que só conferisse o status passaria com o defeito de
    pé, porque o array puro também é 200.
    """

    def setUp(self):
        super().setUp()
        self.usuario.is_tenant_admin = True
        self.usuario.save(update_fields=["is_tenant_admin"])
        self.api = APIClient()
        self.api.force_authenticate(user=self.usuario)

    def test_a_lista_vem_paginada_e_traz_o_item(self):
        mover_para_lixo(self.obra, usuario=self.usuario)

        resp = self.api.get("/api/lixo/")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.data)   # o envelope, não o array puro
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["rotulo"], "Residencial Aurora")
        self.assertEqual(resp.data["results"][0]["modelo_rotulo"], "Obra")
        self.assertEqual(resp.data["results"][0]["estado"], "no_lixo")

    def test_o_resumo_e_a_lista_nunca_se_contradizem(self):
        mover_para_lixo(self.obra, usuario=self.usuario)

        resumo = self.api.get("/api/lixo/resumo/")
        lista = self.api.get("/api/lixo/")

        self.assertEqual(resumo.data["total"], lista.data["count"])
        self.assertEqual(resumo.data["total"], len(lista.data["results"]))

    def test_o_restaurado_sai_da_lista_e_da_contagem(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        self.api.post(f"/api/lixo/{item.pk}/restaurar/")

        resumo = self.api.get("/api/lixo/resumo/")
        lista = self.api.get("/api/lixo/")

        self.assertEqual(resumo.data["total"], 0)
        self.assertEqual(lista.data["count"], 0)

    def test_o_historico_completo_ainda_mostra_o_restaurado(self):
        item = mover_para_lixo(self.obra, usuario=self.usuario)
        self.api.post(f"/api/lixo/{item.pk}/restaurar/")

        lista = self.api.get("/api/lixo/?estado=todos")

        self.assertEqual(lista.data["count"], 1)
        self.assertEqual(lista.data["results"][0]["estado"], "restaurado")
        # Relógio parado: não há purga marcada para o que já saiu da lixeira.
        self.assertIsNone(lista.data["results"][0]["dias_para_purga"])

    def test_sem_a_permissao_a_lixeira_nao_abre(self):
        comum = Usuario.objects.create(username="comum", tenant=self.tenant)
        comum.iam_permissions = []
        api = APIClient()
        api.force_authenticate(user=comum)

        self.assertEqual(api.get("/api/lixo/").status_code, 403)
