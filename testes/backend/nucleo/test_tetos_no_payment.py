"""Todo teto ou limite vive em `payment/` — e este arquivo é quem cobra.

**Decisão do dono, 08/08/2026.** Não é preferência de organização: teto escrito
em código de engenharia é botão comercial que o dono não vê, e o preço disso
apareceu num caso pequeno e exato. O teto do recorte de tela da Prancheta era uma
constante em `bcf.py`; a recusa por tamanho é **sempre 402**; e o corpo do 402 diz
*"faça upgrade do plano"*. Enquanto o número não fosse do dono, o sistema oferecia
um upgrade que nenhum plano vendia — mentira sincera, escrita por quem não sabia
que estava prometendo.

**A varredura que este teste substitui.** Ao aplicar a régua, os limites estavam
espalhados por doze arquivos: `bcf.py`, `formatos.py`, `config/settings.py` (que é
arquivo de *deploy* — quem opera a máquina lê, o dono não), dois motores, o
comando de bancada, `nucleo/upload_validation.py`, os dois cortes síncrono×job do
`funcoesimpexp`, o calendário e seis paginadores. Nenhum deles é lido por quem
decide o produto. Fazer a varredura de novo a cada revisão é o que este arquivo
existe para evitar.

**O que ele NÃO faz, e é deliberado:** não varre o repositório atrás de números.
Uma heurística sobre literais acusaria constante física (`RAIO_TERRA_M`), largura
de campo (`max_length`) e parâmetro de parsing — e um teste que grita errado é
desligado na terceira vez. Em vez disso ele prende **os pontos conhecidos**: cada
constante de teto tem de continuar apontando para `payment/planos.py`. Reescrever
um número no módulo quebra aqui, que é onde a regressão importa.

A fronteira do que não é limite está escrita na §5.6 do `planos.py`.
"""
import inspect

from django.test import SimpleTestCase

from payment import planos


class TetosDaPranchetaTests(SimpleTestCase):
    """O módulo onde a régua nasceu — e o que tinha mais número solto."""

    def test_tamanho_de_arquivo_vem_do_payment(self):
        from moduloprancheta import bcf, impexp
        from moduloprancheta.formatos import FORMATO_POR_CODIGO, TETO_UPLOAD_DIRETO_MB

        MB = 1024 * 1024
        self.assertEqual(TETO_UPLOAD_DIRETO_MB, planos.IMPEXP_TETO_INFRA_ARQUIVO_MB)
        self.assertEqual(impexp.MAX_SNAPSHOT_MB, planos.PRANCHETA_TETO_SNAPSHOT_MB)
        self.assertEqual(bcf.MAX_SNAPSHOT_BYTES, planos.PRANCHETA_TETO_SNAPSHOT_MB * MB)
        self.assertEqual(
            bcf.MAX_DESCOMPRIMIDO_BYTES, planos.PRANCHETA_TETO_BCF_DESCOMPRIMIDO_MB * MB,
        )
        self.assertEqual(bcf.MAX_XML_BYTES, planos.PRANCHETA_TETO_BCF_XML_MB * MB)
        self.assertEqual(bcf.MAX_TOPICOS, planos.PRANCHETA_TETO_BCF_TOPICOS)
        # O teto por formato deixou de ser campo do dataclass.
        for codigo, mb in planos.PRANCHETA_MB_POR_FORMATO.items():
            self.assertEqual(
                FORMATO_POR_CODIGO[codigo].max_mb, mb,
                f"o teto de '{codigo}' divergiu do que o dono declarou",
            )

    def test_orcamento_de_conversao_vem_do_payment(self):
        """O padrão é do dono; a variável de ambiente é de quem opera a máquina.

        Por isso a comparação é com o **default**: um `PRANCHETA_CONVERSAO_*` no
        ambiente do runner é legítimo e não pode reprovar a régua.

        **Esta tolerância tem um preço, e é `test_deploy_nao_redeclara_teto_do_dono`
        quem o paga.** Pular a asserção na presença da env é o que faz sentido para
        o runner, e é exatamente o que a desarmava dentro do contêiner: o
        `deploy/compose/base.yml` declarava `PRANCHETA_CONVERSAO_MEMORIA_MB: 1536`,
        então a env existia *sempre* e este teste nunca assertava onde mais
        importava. As duas metades só funcionam juntas.
        """
        import os

        from django.conf import settings

        if not os.getenv("PRANCHETA_CONVERSAO_MEMORIA_MB"):
            self.assertEqual(
                settings.PRANCHETA_CONVERSAO_MEMORIA_MB, planos.PRANCHETA_CONVERSAO_MEMORIA_MB,
            )
        if not os.getenv("PRANCHETA_CONVERSAO_SEGUNDOS"):
            self.assertEqual(
                settings.PRANCHETA_CONVERSAO_SEGUNDOS, planos.PRANCHETA_CONVERSAO_SEGUNDOS,
            )

    def test_tetos_dos_motores_vem_do_payment(self):
        from moduloprancheta.motores import documento, dwg, dxf, ifc

        self.assertEqual(dxf.MAX_DESENHOS, planos.PRANCHETA_TETO_FOLHAS_POR_ARQUIVO)
        self.assertEqual(ifc.TETO_ELEMENTOS, planos.PRANCHETA_TETO_ELEMENTOS_IFC)
        self.assertEqual(dwg.TIMEOUT_SEGUNDOS, planos.PRANCHETA_TIMEOUT_DWG_SEGUNDOS)
        self.assertEqual(
            dwg.TIMEOUT_PREVIEW_SEGUNDOS, planos.PRANCHETA_TIMEOUT_PREVIEW_SEGUNDOS,
        )
        self.assertEqual(documento.LADO_MINIATURA, planos.PRANCHETA_LADO_MINIATURA_PX)

    def test_o_teto_da_bancada_tambem(self):
        """Não limita cliente nenhum — limita a máquina de quem dispara a medição.

        Está aqui porque a régua não abre exceção para "é só ferramenta": foi
        justamente um comando de bancada sem teto que ocupou a estação em
        06/08/2026, e o número tem de estar onde alguém o veja.
        """
        from moduloprancheta.management.commands import medir_cobertura_dwg as medicao

        self.assertEqual(medicao.TETO_POR_ARQUIVO, planos.PRANCHETA_MEDICAO_TETO_SEGUNDOS)
        self.assertEqual(
            medicao.TIMEOUT_RESGATE, planos.PRANCHETA_MEDICAO_TIMEOUT_RESGATE_SEGUNDOS,
        )


class TetosDaPlataformaTests(SimpleTestCase):
    """Os que estavam fora da Prancheta, achados na mesma varredura."""

    def test_corte_entre_sincrono_e_job_vem_do_payment(self):
        """R10 do motor: é ele que decide o que trava a requisição."""
        from funcoesimpexp import exportacao, importacao

        self.assertEqual(
            exportacao.LIMITE_SINCRONO, planos.IMPEXP_LIMITE_SINCRONO_EXPORTACAO,
        )
        self.assertEqual(
            importacao.LIMITE_SINCRONO, planos.IMPEXP_LIMITE_SINCRONO_IMPORTACAO,
        )

    def test_teto_de_upload_do_nucleo_vem_do_payment(self):
        from nucleo import upload_validation

        self.assertEqual(upload_validation.DEFAULT_MAX_MB, planos.UPLOAD_PADRAO_MAX_MB)

    def test_tetos_de_modulo_vem_do_payment(self):
        from modulocalendar import serializers as calendario
        from moduloorcamento import precificacao
        from nucleo import notificacoes_views

        self.assertEqual(
            calendario.MAX_REMINDER_OFFSET, planos.CALENDAR_MAX_OFFSET_LEMBRETE_MIN,
        )
        self.assertEqual(
            notificacoes_views.LIMITE_LISTA, planos.NOTIFICACOES_LIMITE_LISTA,
        )
        self.assertEqual(
            precificacao.PROFUNDIDADE_MAXIMA,
            planos.ORCAMENTO_PROFUNDIDADE_MAXIMA_COMPOSICAO,
        )

    def test_tetos_da_memoria_do_quantitativo_vem_do_payment(self):
        """ORC.7 — quantas parciais uma linha aceita, e quão aninhada é a fórmula.

        O primeiro é teto de uso e é claramente do dono. O segundo entra pela
        mesma porta que o `ORCAMENTO_PROFUNDIDADE_MAXIMA_COMPOSICAO`: não protege
        contra execução (a avaliação é AST restrita, sem nome nem chamada) — é o
        freio contra expressão aninhada de propósito para consumir pilha.
        """
        from moduloorcamento import quantitativos

        self.assertEqual(
            quantitativos.ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM,
            planos.ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM,
        )
        self.assertEqual(
            quantitativos.ORCAMENTO_PROFUNDIDADE_MAXIMA_FORMULA,
            planos.ORCAMENTO_PROFUNDIDADE_MAXIMA_FORMULA,
        )

    def test_tetos_da_carga_da_base_oficial_vem_do_payment(self):
        """ORC.8 — o que sai da nossa máquina para o site da Caixa.

        Aqui a régua é prendida de um jeito diferente das outras: `carga.py` e
        `oficial.py` **não copiam** os números para constantes locais, leem
        `planos.*` na hora de usar. Então o que este teste cobra é que continue
        assim — uma constante local reaparecendo nesses módulos é exatamente a
        regressão que ele existe para pegar, e ela passaria despercebida porque
        nada quebra: o download só passa a obedecer a um número que o dono não vê.
        """
        from moduloorcamento import carga, oficial

        for nome in (
            "ORCAMENTO_CARGA_TETO_MB", "ORCAMENTO_CARGA_SEGUNDOS",
            "ORCAMENTO_CARGA_MEMORIA_MB", "ORCAMENTO_CARGA_TENTATIVAS",
            "ORCAMENTO_CARGA_ESPERA_INICIAL_S", "ORCAMENTO_CARGA_ESPERA_MAXIMA_S",
            "ORCAMENTO_CARGA_PAUSA_ENTRE_ARQUIVOS_S", "ORCAMENTO_CARGA_TETO_PUBLICACOES",
        ):
            self.assertTrue(
                hasattr(planos, nome), f"{nome} sumiu do payment/planos.py §5.5b"
            )
            for modulo in (carga, oficial):
                self.assertFalse(
                    hasattr(modulo, nome),
                    f"{modulo.__name__} redeclarou {nome} — o valor é do dono, "
                    "não do módulo (payment/planos.py §5.5b).",
                )


class PaginacaoTests(SimpleTestCase):
    """Página é limite dos dois lados — o que vem sem pedir e o teto do que se pede.

    Sem `max_page_size`, `?page_size=100000` transforma qualquer listagem numa
    exportação sem gate: mesma leitura, sem a auditoria da R12 e sem o "acesso
    total ou nada" da R11.
    """

    #: Módulo → `caminho.do.arquivo:ClassePaginador`. Explícito e **não descoberto
    #: por varredura**, por duas razões: paginador novo tem de entrar aqui (é o
    #: que faz o teste cobrar o teto de um módulo que ainda não existe), e nem
    #: todo paginador mora num `pagination.py` — o de Unidade é uma classe solta
    #: no `views.py` do `empreendimentos`, e foi exatamente ela que uma varredura
    #: por nome de arquivo deixou passar.
    PAGINADORES = {
        "catalogo": "catalogo.pagination:CatalogoPageNumberPagination",
        "clientes": "clientes.pagination:ClientePageNumberPagination",
        # O registro de arquivos do DMS (funcoesimpexp/arquivos.py).
        "dms": "funcoesimpexp.pagination:DmsPageNumberPagination",
        "empreendimentos": "empreendimentos.views:UnidadePagination",
        "erp": "moduloerp.pagination:ErpPageNumberPagination",
        # A lixeira (D116) não é módulo vendido e não tem `module_code` — ela é
        # de plataforma e mora no `nucleo`. Entra aqui pelo mesmo motivo que as
        # outras: é uma listagem paginada, e listagem paginada sem teto no
        # payment é `?page_size=100000` esperando para acontecer.
        "lixo": "nucleo.lixo_pagination:LixoPageNumberPagination",
        "maps": "modulomaps.pagination:MapsPageNumberPagination",
        "orcamento": "moduloorcamento.pagination:OrcamentoPageNumberPagination",
        "pdca": "modulopdca.pagination:PdcaPageNumberPagination",
        "prancheta": "moduloprancheta.pagination:PranchetaPageNumberPagination",
        "scm": "moduloscm.pagination:ScmPageNumberPagination",
        "sil": "modulosil.pagination:SilPageNumberPagination",
    }

    def _paginador(self, referencia):
        import importlib

        caminho, _, nome = referencia.partition(":")
        return getattr(importlib.import_module(caminho), nome)

    def test_todo_paginador_le_o_tamanho_do_payment(self):
        for modulo, caminho in self.PAGINADORES.items():
            paginador = self._paginador(caminho)
            self.assertEqual(
                paginador.page_size, planos.PAGINA_PADRAO[modulo],
                f"o tamanho de página de '{modulo}' divergiu do payment",
            )
            self.assertEqual(
                paginador.max_page_size, planos.PAGINA_MAXIMA[modulo],
                f"o teto de página de '{modulo}' divergiu do payment",
            )

    def test_o_payment_nao_declara_pagina_de_modulo_que_nao_existe(self):
        """O descasamento do outro lado: número órfão no arquivo do dono."""
        orfaos = sorted(set(planos.PAGINA_PADRAO) - set(self.PAGINADORES))
        self.assertEqual(orfaos, [], f"PAGINA_PADRAO declara módulo sem paginador: {orfaos}")
        self.assertEqual(sorted(planos.PAGINA_PADRAO), sorted(planos.PAGINA_MAXIMA))

    def test_o_padrao_nunca_passa_do_teto(self):
        for modulo in planos.PAGINA_PADRAO:
            self.assertLessEqual(
                planos.PAGINA_PADRAO[modulo], planos.PAGINA_MAXIMA[modulo],
                f"'{modulo}': a página padrão é maior que o teto dela",
            )


class DeployNaoRedeclaraTetoTests(SimpleTestCase):
    """A outra metade da régua: o arquivo de deploy não pode reescrever o número.

    **A regressão que motivou esta classe, 08/08/2026.** O
    `deploy/compose/base.yml` declarava, no `worker-conversao`::

        PRANCHETA_CONVERSAO_MEMORIA_MB: ${PRANCHETA_CONVERSAO_MEMORIA_MB:-1536}
        PRANCHETA_CONVERSAO_SEGUNDOS: ${PRANCHETA_CONVERSAO_SEGUNDOS:-300}

    Dois defeitos numa linha. O número do dono voltava a existir em arquivo de
    deploy — exatamente o que a decisão de 08/08 proíbe, e pelo mesmo motivo que
    tirou os tetos do `config/settings.py`: quem opera a máquina lê esse arquivo,
    o dono não. E, pior, o `settings.py` **já** resolvia o default a partir do
    `payment/planos.py`, então as duas linhas eram redundantes *e* venenosas:
    `test_orcamento_de_conversao_vem_do_payment` pula a asserção quando a env
    existe, e o compose fazia com que ela existisse sempre. Dentro do contêiner o
    guarda-corpo era no-op. Mudar o valor em `payment/` deixaria o contêiner no
    valor antigo, sem nenhum teste reclamando.

    Este teste é **geral de propósito**: em vez de prender os dois nomes que
    falharam, ele cobra que *nenhuma* constante escalar do `payment/planos.py`
    apareça como chave de ambiente num arquivo de deploy. É a única varredura por
    nome que a §"o que ele NÃO faz" deste módulo admite, porque não adivinha o que
    é teto — pergunta ao próprio arquivo do dono.

    **O que continua permitido:** exportar a env no ambiente para experimentar um
    teto diferente. O que não se pode é *versionar* o número num arquivo de deploy.
    """

    def _compose(self):
        """Os arquivos de compose, se este processo os enxerga.

        Sobe a partir do `payment/` procurando `deploy/compose/`. Acha num clone
        do repositório — que é onde o CI roda e onde a regressão é escrita — e
        **não** acha dentro da imagem de runtime, onde `payment` mora em
        `/app/payment` e `deploy/` não é embarcado (nem deve ser: arquivo de
        deploy não vai para dentro do contêiner que ele orquestra).

        Nesse caso o teste **pula com o motivo escrito**, em vez de falhar. A
        distinção importa: pular porque não há alvo é diferente de passar porque
        não se olhou — e foi justamente um `if` silencioso que desarmou o
        `test_orcamento_de_conversao_vem_do_payment` dentro do contêiner.
        """
        from pathlib import Path

        import payment

        atual = Path(payment.__file__).resolve().parent
        for raiz in [atual, *atual.parents]:
            alvo = raiz / "deploy" / "compose"
            if alvo.is_dir():
                arquivos = sorted(alvo.glob("*.yml"))
                self.assertTrue(
                    arquivos, f"{alvo} existe mas não tem *.yml — o teste perdeu o alvo",
                )
                return arquivos
        self.skipTest(
            "deploy/compose/ não é visível deste processo (imagem de runtime não "
            "embarca arquivo de deploy). A regressão é cobrada no clone do repositório."
        )

    def _constantes_escalares(self):
        """Os nomes que o dono declarou como número — não dicts nem listas."""
        return {
            nome
            for nome, valor in vars(planos).items()
            if nome.isupper() and not nome.startswith("_") and isinstance(valor, (int, float))
            and not isinstance(valor, bool)
        }

    def test_deploy_nao_redeclara_teto_do_dono(self):
        import re

        constantes = self._constantes_escalares()
        self.assertTrue(constantes, "payment/planos.py não expôs nenhuma constante escalar")

        reincidentes = []
        for arquivo in self._compose():
            for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
                achado = re.match(r"\s+([A-Z][A-Z0-9_]*):", linha)
                if achado and achado.group(1) in constantes:
                    reincidentes.append(f"{arquivo.name}:{numero} — {achado.group(1)}")

        self.assertEqual(
            reincidentes, [],
            "arquivo de deploy redeclarando teto que é do dono (o valor vive em "
            "payment/planos.py e o settings.py já o lê): " + "; ".join(reincidentes),
        )


class EscadaDeMemoriaPorPlanoTests(SimpleTestCase):
    """O degrau de RAM por plano não pode prometer o que a máquina não entrega (D101).

    **A invariante, e por que ela é de teste e não de comentário.** Quem sabe
    EXPLICAR tem de estourar antes de quem só mata. Se o teto de um plano passar do
    `CELERY_WORKER_MAX_MEMORY_PER_CHILD` ou do `mem_limit` do contêiner, o cliente
    para de receber `recurso_excedido` — que é frase legível no cockpit — e passa a
    receber um worker morto sem rastro, com a derivada presa em `convertendo`. É o
    D71/D76 ao contrário, e é o tipo de erro que só aparece em produção e sob carga.

    O 64,9 MB do acervo é a prova de que o degrau importa: ele converte de verdade
    (o `dwg2dxf` sai `0` e produz 531,8 MB de DXF) e morre só no nosso orçamento.
    Servi-lo exige subir a máquina PRIMEIRO — e é isso que este teste cobra.
    """

    def test_todo_plano_tem_degrau_declarado(self):
        for mapa, nome in (
            (planos.PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO, "conversão"),
            (planos.PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO, "subprocesso"),
        ):
            faltando = sorted(set(planos.PLANOS) - set(mapa))
            self.assertEqual(
                faltando, [],
                f"plano sem degrau de memória de {nome}: {faltando}. Plano ausente "
                "cai no padrão do módulo em silêncio, que é o valor de OUTRO plano.",
            )

    def test_degrau_nao_passa_do_que_a_maquina_entrega(self):
        from django.conf import settings

        celery_mb = int(getattr(settings, "CELERY_WORKER_MAX_MEMORY_PER_CHILD", 0) or 0) // 1024
        self.assertTrue(celery_mb, "CELERY_WORKER_MAX_MEMORY_PER_CHILD não está definido")

        for plano, teto in planos.PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO.items():
            self.assertLess(
                teto, celery_mb,
                f"o plano '{plano}' promete {teto} MB de conversão, mas o Celery "
                f"recicla o filho em {celery_mb} MB — o cliente receberia um worker "
                "morto sem rastro em vez de 'recurso_excedido'. Suba a máquina antes "
                "de subir este número.",
            )

    def test_subprocesso_nao_passa_do_que_o_conteiner_deixa(self):
        """O teto do subprocesso é o que SOBRA no contêiner, não o contêiner inteiro.

        Medido em 16/08/2026 no DWG de 64,9 MB do acervo: com 2.048 MB ele devolve
        `RecursoExcedido` em 8,9 s — erro legível; com 2.800 MB o processo morre com
        **exit 137 (SIGKILL)**, sem exceção e sem rastro. O `mem_limit` de 3.072 MB
        é do contêiner inteiro e o Python pai já reserva ~1.150 MB de VA.

        `PRANCHETA_SUBPROCESSO_MEMORIA_MB` é o valor provado nessa máquina, e por
        isso é o teto dos degraus até a máquina crescer ([D103](../../docs/pendencias.md)).
        """
        for plano, teto in planos.PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO.items():
            self.assertLessEqual(
                teto, planos.PRANCHETA_SUBPROCESSO_MEMORIA_MB,
                f"o plano '{plano}' promete {teto} MB ao subprocesso, acima do "
                f"{planos.PRANCHETA_SUBPROCESSO_MEMORIA_MB} MB que esta máquina "
                "comporta ao lado do processo pai — o cliente receberia exit 137 "
                "sem mensagem em vez de 'recurso_excedido'. Cresça o mem_limit antes.",
            )

    def test_escada_sobe_com_o_plano(self):
        """Plano mais caro nunca recebe menos memória que um mais barato."""
        ordem = [p for p in ("free", "essencial", "profissional", "empresarial") if p in planos.PLANOS]
        for mapa, nome in (
            (planos.PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO, "conversão"),
            (planos.PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO, "subprocesso"),
        ):
            degraus = [mapa[p] for p in ordem]
            self.assertEqual(
                degraus, sorted(degraus),
                f"a escada de {nome} desce em algum ponto ({dict(zip(ordem, degraus))}) "
                "— plano mais caro entregando menos máquina é upsell ao contrário",
            )


class TetosDoPdcaTests(SimpleTestCase):
    """PDCA.0 — a árvore que o cliente desenha e a escada que aprova dinheiro.

    Família nova de teto: as anteriores protegiam o que entra (bytes) ou o que a
    operação custa (memória, relógio). Estas protegem uma **estrutura que o
    cliente descreve numa frase curta** — "torre A, 20 pavimentos, 4 unidades por
    andar" são 1.600 linhas, e um dedo a mais são 16.000.
    """

    def test_a_arvore_de_locais_le_os_tetos_do_payment(self):
        from modulopdca import services

        self.assertIs(
            services.PDCA_PROFUNDIDADE_MAXIMA_LOCAL, planos.PDCA_PROFUNDIDADE_MAXIMA_LOCAL,
        )
        self.assertIs(
            services.PDCA_TETO_LOCAIS_POR_GERACAO, planos.PDCA_TETO_LOCAIS_POR_GERACAO,
        )
        self.assertIs(
            services.PDCA_TETO_LOCAIS_POR_OBRA, planos.PDCA_TETO_LOCAIS_POR_OBRA,
        )

    def test_a_escada_de_atesto_le_o_teto_de_niveis_do_payment(self):
        from nucleo import aprovacao

        self.assertIs(
            aprovacao.PDCA_TETO_NIVEIS_APROVACAO, planos.PDCA_TETO_NIVEIS_APROVACAO,
        )

    def test_o_corte_sincrono_cabe_dentro_do_teto_da_obra(self):
        """Uma geração não pode, sozinha, passar do que a obra inteira comporta —
        senão o teto maior nunca seria alcançável e o menor mentiria sobre o
        motivo da recusa."""
        self.assertLessEqual(
            planos.PDCA_TETO_LOCAIS_POR_GERACAO, planos.PDCA_TETO_LOCAIS_POR_OBRA,
        )

    def test_o_cronograma_le_os_tetos_do_payment(self):
        """PDCA.1 — os cinco números do plano de tempo saem do arquivo do dono.

        Vale mais aqui do que na fatia anterior porque estes estão marcados como
        **provisórios** até o estudo de viabilidade: a promessa escrita no
        `planos.py` é que editá-los é editar aquele bloco e mais nada, e é este
        teste que cobra a promessa.
        """
        from modulopdca import services

        self.assertIs(
            services.PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
            planos.PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
        )
        self.assertIs(
            services.PDCA_PROFUNDIDADE_MAXIMA_WBS, planos.PDCA_PROFUNDIDADE_MAXIMA_WBS,
        )
        self.assertIs(services.PDCA_TETO_CPM_SINCRONO, planos.PDCA_TETO_CPM_SINCRONO)
        self.assertIs(services.PDCA_CPM_SEGUNDOS, planos.PDCA_CPM_SEGUNDOS)
        self.assertIs(
            services.PDCA_TETO_VERSOES_POR_CRONOGRAMA,
            planos.PDCA_TETO_VERSOES_POR_CRONOGRAMA,
        )

    def test_o_cpm_sincrono_cabe_dentro_do_teto_de_atividades(self):
        """Se o corte síncrono fosse menor que o teto do cronograma sem existir
        um job, haveria cronograma legítimo que nasce impossível de calcular — e
        a recusa citaria um caminho assíncrono que ainda não existe."""
        self.assertLessEqual(
            planos.PDCA_TETO_CPM_SINCRONO, planos.PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
        )

    def test_a_escrita_em_lote_le_o_teto_do_payment(self):
        from modulopdca import services

        self.assertIs(
            services.PDCA_TETO_LINHAS_POR_LOTE, planos.PDCA_TETO_LINHAS_POR_LOTE,
        )

    def test_o_lote_cabe_dentro_do_cronograma(self):
        """Um lote maior que o cronograma inteiro seria teto que nunca morde — e
        teto que não morde é número que o dono acha que protege alguma coisa."""
        self.assertLessEqual(
            planos.PDCA_TETO_LINHAS_POR_LOTE, planos.PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
        )

    def test_o_avanco_le_os_tetos_do_payment(self):
        """PDCA.2 — os dois números do avanço saem do arquivo do dono."""
        from modulopdca import services

        self.assertIs(
            services.PDCA_TETO_APONTAMENTOS_POR_LOTE,
            planos.PDCA_TETO_APONTAMENTOS_POR_LOTE,
        )
        self.assertIs(
            services.PDCA_TETO_PONTOS_CURVA_S, planos.PDCA_TETO_PONTOS_CURVA_S,
        )

    def test_o_lote_de_apontamentos_cabe_dentro_do_cronograma(self):
        """Um lote maior que o cronograma inteiro seria teto que nunca morde —
        não existe semana com mais frentes do que o plano tem atividades."""
        self.assertLessEqual(
            planos.PDCA_TETO_APONTAMENTOS_POR_LOTE,
            planos.PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
        )

    def test_a_curva_cabe_num_grafico(self):
        """O teto de pontos existe para o eixo continuar legível. Acima de uns
        poucos milhares ele deixaria de proteger o que foi criado para proteger —
        e a engrossada de granularidade nunca aconteceria na prática."""
        self.assertLessEqual(planos.PDCA_TETO_PONTOS_CURVA_S, 2_000)

    def test_o_contrato_e_a_medicao_leem_os_tetos_do_payment(self):
        """PDCA.3 — os dois números da fatia do dinheiro saem do arquivo do dono."""
        from modulopdca import services

        self.assertIs(
            services.PDCA_TETO_ITENS_POR_CONTRATO,
            planos.PDCA_TETO_ITENS_POR_CONTRATO,
        )
        self.assertIs(
            services.PDCA_TETO_LINHAS_POR_MEDICAO,
            planos.PDCA_TETO_LINHAS_POR_MEDICAO,
        )

    def test_o_aditivo_e_as_deducoes_leem_os_tetos_do_payment(self):
        """PDCA.4 — os três números da fatia que muda o contrato."""
        from modulopdca import services

        self.assertIs(
            services.PDCA_TETO_ITENS_POR_ADITIVO, planos.PDCA_TETO_ITENS_POR_ADITIVO,
        )
        self.assertIs(
            services.PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO,
            planos.PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO,
        )
        self.assertIs(
            services.PDCA_TETO_DEDUCOES_POR_MEDICAO,
            planos.PDCA_TETO_DEDUCOES_POR_MEDICAO,
        )

    def test_o_aditivo_nao_reescreve_o_contrato_inteiro(self):
        """**Metade do contrato, e a metade é o ponto.** Aditivo que muda mais da
        metade da planilha não é aditivo — é contrato novo, e é assim que o
        mercado trata. Um teto igual ao do contrato deixaria de dizer isso."""
        self.assertLessEqual(
            planos.PDCA_TETO_ITENS_POR_ADITIVO,
            planos.PDCA_TETO_ITENS_POR_CONTRATO // 2,
        )

    def test_poucos_aditivos_abertos_por_vez(self):
        """Dois aditivos abertos sobre as mesmas linhas se conferem, cada um,
        contra o mesmo saldo — e passam os dois. O teto é pequeno de propósito:
        ele existe para o fluxo ser "fecha um, abre o próximo"."""
        self.assertLessEqual(planos.PDCA_TETO_ADITIVOS_ABERTOS_POR_CONTRATO, 10)

    def test_as_deducoes_nao_viram_planilha(self):
        """A medição brasileira típica tem de três a seis deduções. O teto deixa
        folga para o contrato que detalha por frente, e fecha a porta para colar
        uma planilha inteira de descontos linha a linha."""
        self.assertLessEqual(planos.PDCA_TETO_DEDUCOES_POR_MEDICAO, 100)

    def test_o_limite_legal_de_acrescimo_NAO_esta_no_payment(self):
        """A fronteira da §5.6, exercida.

        25% é o caso comum da Lei 14.133, 50% o da reforma de edifício, e existe
        contrato que não segue nenhum dos dois. O número é **do contrato**
        (`limite_acrescimo_percentual`, digitado pelo usuário), não do plano —
        escolhê-lo pelo cliente seria errar exatamente na exceção.
        """
        suspeitos = [
            nome for nome in dir(planos)
            if "ACRESCIMO" in nome or "ADITIVO_PERCENTUAL" in nome
        ]
        self.assertEqual(suspeitos, [])

        from modulopdca.models import ContratoObra

        self.assertTrue(
            ContratoObra._meta.get_field("limite_acrescimo_percentual").null,
            "o limite legal continua sendo um campo do contrato, e opcional",
        )

    def test_a_medicao_alcanca_o_contrato_inteiro(self):
        """**O teto de linhas por medição NÃO pode ser menor que o de itens.**

        A primeira medição de uma empreitada por preço unitário toca
        legitimamente todos os itens do contrato. Um teto menor aqui criaria o
        contrato que não pode ser medido de uma vez — trava sem benefício, já que
        o custo da apuração é linear e o teto do contrato já o cobre.
        """
        self.assertGreaterEqual(
            planos.PDCA_TETO_LINHAS_POR_MEDICAO,
            planos.PDCA_TETO_ITENS_POR_CONTRATO,
        )

    def test_o_contrato_cabe_dentro_do_cronograma(self):
        """O contrato é um **recorte** do plano, nunca o plano inteiro: contrato
        maior que o cronograma é sinal de planilha colada no lugar errado."""
        self.assertLessEqual(
            planos.PDCA_TETO_ITENS_POR_CONTRATO,
            planos.PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
        )

    def test_a_retencao_nao_virou_teto_de_plano(self):
        """**A fronteira da §5.6, cobrada.** Percentual de retenção, prazo de
        pagamento e limite legal de acréscimo são **cláusula do contrato** que o
        cliente negocia com o fornecedor dele — não teto comercial nosso. Um
        número desses aparecendo no `planos.py` seria o dono decidindo uma
        cláusula que não é dele, e o cliente descobrindo isso no meio de uma
        negociação.
        """
        proibidos = [
            nome for nome in dir(planos)
            if nome.startswith("PDCA_")
            and any(p in nome for p in ("RETENCAO", "PRAZO_PAGAMENTO", "ACRESCIMO"))
        ]
        self.assertEqual(proibidos, [], f"cláusula virou teto de plano: {proibidos}")

    def test_a_quota_de_plano_modelo_existe_em_todo_degrau(self):
        """Quota ausente num degrau é `KeyError` no meio de um POST; quota **0**
        é a resposta honesta "seu plano não vende isto"."""
        for slug, plano in planos.PLANOS.items():
            self.assertIn("planos_modelo", plano, f"o degrau '{slug}' não declara a quota")

    def test_a_quota_de_plano_modelo_e_aplicada_e_contada(self):
        """Quota que viaja no token sem contador do outro lado é promessa que
        ninguém cumpre — é a regra escrita em `quotas_efetivas`."""
        from nucleo import quotas

        self.assertIn("planos_modelo", planos.QUOTAS_DE_OBJETO)
        self.assertIn("planos_modelo", quotas.RECURSOS_CONTADOS)
        self.assertIn("planos_modelo", quotas.ROTULOS)
        self.assertEqual(quotas.FILTRO_DO_RECURSO["planos_modelo"], {"eh_modelo": True})

    def test_so_o_degrau_que_vende_o_modulo_tem_plano_modelo(self):
        """A régua comercial da §5.5c: o `pdca` é vendido do `empresarial` para
        cima. Um degrau abaixo com quota > 0 ofereceria biblioteca de padrões a
        quem não tem onde usá-la."""
        for slug in ("free", "essencial", "profissional"):
            self.assertEqual(
                planos.PLANOS[slug]["planos_modelo"], 0,
                f"o degrau '{slug}' não contrata o `pdca` e não pode ter modelo",
            )
        self.assertGreater(planos.PLANOS["empresarial"]["planos_modelo"], 0)


class TetosDoLastPlannerTests(SimpleTestCase):
    """PDCA.5 — os quatro números da fatia que fecha o Check e o Act.

    A mesma regra das anteriores: constante sem consumidor não é régua, é
    intenção — e o teste é o que prende uma à outra.
    """

    def test_o_last_planner_le_os_tetos_do_payment(self):
        from modulopdca import services

        self.assertIs(
            services.PDCA_TETO_ITENS_POR_PROGRAMACAO,
            planos.PDCA_TETO_ITENS_POR_PROGRAMACAO,
        )
        self.assertIs(
            services.PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA,
            planos.PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA,
        )
        self.assertIs(
            services.PDCA_TETO_CAUSAS_POR_TENANT,
            planos.PDCA_TETO_CAUSAS_POR_TENANT,
        )
        self.assertIs(
            services.PDCA_TETO_SEMANAS_PPC, planos.PDCA_TETO_SEMANAS_PPC,
        )

    def test_o_quadro_cabe_numa_parede(self):
        """O quadro de programação é uma parede de reunião: existe para o time
        olhar junto e decidir. Um teto grande demais deixaria de proteger o que
        foi criado para proteger."""
        self.assertLessEqual(planos.PDCA_TETO_ITENS_POR_PROGRAMACAO, 1_000)

    def test_a_semana_nao_comporta_o_cronograma_inteiro(self):
        """**O compromisso é um recorte, não uma cópia do plano.** Se coubesse
        tanto quanto o cronograma, o quadro viraria a WBS de novo — e o Last
        Planner existe justamente porque a lista da semana é curta o bastante
        para alguém assumi-la em voz alta."""
        self.assertLess(
            planos.PDCA_TETO_ITENS_POR_PROGRAMACAO,
            planos.PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
        )

    def test_o_catalogo_de_causas_continua_escolhivel(self):
        """A causa só serve se for escolhida da mesma lista toda semana. Com
        centenas de causas ninguém escolhe a mesma duas vezes e o ranking deixa
        de ranquear."""
        self.assertLessEqual(planos.PDCA_TETO_CAUSAS_POR_TENANT, 200)
        self.assertGreater(
            planos.PDCA_TETO_CAUSAS_POR_TENANT,
            len(__import__("modulopdca.services", fromlist=["x"]).CAUSAS_DE_FABRICA),
            "o teto tem de deixar espaço sobre o catálogo de fábrica",
        )

    def test_a_serie_de_ppc_cabe_num_eixo(self):
        """Irmão do teto de pontos da curva S, e pela mesma razão."""
        self.assertLessEqual(planos.PDCA_TETO_SEMANAS_PPC, 520)

    def test_o_PPC_nao_tem_meta_no_payment(self):
        """A fronteira da §5.6, exercida — e esta é a tentação óbvia da fatia.

        A literatura registra ~54% em obra convencional e 80–85% com LPS maduro,
        e seria fácil cravar 85 aqui como "meta do plano". O número é **resultado
        medido**, não limite de uso; e meta de desempenho é acordo entre o
        cliente e a equipe dele, da mesma classe do percentual de retenção que a
        §5.5h recusou.
        """
        suspeitos = [
            nome for nome in dir(planos)
            if "PPC" in nome and "SEMANAS" not in nome
        ]
        self.assertEqual(suspeitos, [])


class TetosDaLinhaDeBalancoTests(SimpleTestCase):
    """PDCA.6 — os quatro números da §5.5k.

    A mesma regra das anteriores: constante sem consumidor não é régua, é
    intenção — e o teste é o que prende uma à outra.
    """

    def test_a_linha_de_balanco_le_os_tetos_do_payment(self):
        from modulopdca import services

        self.assertIs(
            services.PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO,
            planos.PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO,
        )
        self.assertIs(
            services.PDCA_TETO_LINHAS_DE_BALANCO,
            planos.PDCA_TETO_LINHAS_DE_BALANCO,
        )
        self.assertIs(
            services.PDCA_TETO_LOCAIS_POR_RITMO,
            planos.PDCA_TETO_LOCAIS_POR_RITMO,
        )
        self.assertIs(
            services.PDCA_TETO_CONFLITOS_REPORTADOS,
            planos.PDCA_TETO_CONFLITOS_REPORTADOS,
        )

    def test_o_eixo_cabe_numa_tela(self):
        """A única razão de a LOB existir é que **o cruzamento de duas retas se
        vê**. Com mil linhas no eixo Y o rótulo não cabe e o gráfico vira uma
        mancha — que é o contrário do instrumento."""
        self.assertLessEqual(planos.PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO, 500)
        #: E ele tem de comportar a torre inteira, que é o caso que justifica o
        #: instrumento: 20 pavimentos × 4 unidades já são 80.
        self.assertGreaterEqual(planos.PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO, 100)

    def test_o_grafico_nao_vira_espaguete(self):
        """Com trinta retas sobrepostas ninguém enxerga qual cruza qual."""
        self.assertLessEqual(planos.PDCA_TETO_LINHAS_DE_BALANCO, 60)

    def test_um_traco_nao_gera_um_cronograma_inteiro(self):
        """**É tamanho de gesto e de desfazer.** Gerar milhares de atividades
        num clique cria um plano que ninguém revisa antes de publicar."""
        self.assertLess(
            planos.PDCA_TETO_LOCAIS_POR_RITMO,
            planos.PDCA_TETO_ATIVIDADES_POR_CRONOGRAMA,
        )

    def test_o_traco_cabe_no_eixo_que_a_tela_desenha(self):
        """Gerar mais locais do que o gráfico mostra produziria um plano que a
        própria ferramenta que o desenhou não consegue ler."""
        self.assertLessEqual(
            planos.PDCA_TETO_LOCAIS_POR_RITMO,
            planos.PDCA_TETO_LOCAIS_NA_LINHA_DE_BALANCO,
        )

    def test_o_RITMO_nao_tem_meta_no_payment(self):
        """A fronteira da §5.6, exercida — e é a tentação óbvia desta fatia.

        Quantos pavimentos por semana uma equipe faz é **resultado medido** da
        obra, não limite de uso do software; e "ritmo ideal" é acordo entre a
        empresa e a equipe dela. É a mesma recusa que a §5.5j fez com a meta de
        PPC e a §5.5h com o percentual de retenção.
        """
        suspeitos = [
            nome for nome in dir(planos)
            if ("RITMO" in nome or "GARGALO" in nome)
            and "LOCAIS_POR_RITMO" not in nome
        ]
        self.assertEqual(
            suspeitos, [],
            f"o ritmo é resultado da obra, não teto de plano: {suspeitos}",
        )


class TetosDaVerificacaoTests(SimpleTestCase):
    """PDCA.7 — os quatro números da máquina de verificação.

    A mesma regra das anteriores: constante sem consumidor não é régua, é
    intenção — e o teste é o que prende uma à outra.
    """

    def test_a_verificacao_le_os_tetos_do_payment(self):
        from modulopdca import services

        self.assertIs(
            services.PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO,
            planos.PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO,
        )
        self.assertIs(
            services.PDCA_TETO_MODELOS_POR_TENANT,
            planos.PDCA_TETO_MODELOS_POR_TENANT,
        )
        self.assertIs(
            services.PDCA_TETO_NCS_ABERTAS_POR_OBRA,
            planos.PDCA_TETO_NCS_ABERTAS_POR_OBRA,
        )
        self.assertIs(
            services.PDCA_TETO_ACOES_POR_NC, planos.PDCA_TETO_ACOES_POR_NC,
        )

    def test_a_ficha_termina_numa_visita(self):
        """**O instrumento do campo é uma pergunta por vez** (planta §5.2).

        Quem responde está de pé, com luva e sol na tela; ficha que não termina
        numa visita volta pela metade, e ficha pela metade não se distingue de
        serviço reprovado. O teto tem de caber no caso mais longo que o mercado
        usa de verdade — a vistoria de entrega de uma unidade, que passa de 100
        itens — sem virar documento de duzentas perguntas.
        """
        self.assertGreaterEqual(planos.PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO, 100)
        self.assertLessEqual(planos.PDCA_TETO_ITENS_POR_MODELO_VERIFICACAO, 300)

    def test_a_biblioteca_continua_escolhivel(self):
        """Irmão do catálogo de causas, e pela mesma razão: o modelo só serve se
        for **o mesmo** aplicado em toda obra. Com mil cadastrados, cada
        engenheiro escolhe o seu e a comparação entre obras acaba."""
        self.assertGreaterEqual(
            planos.PDCA_TETO_MODELOS_POR_TENANT,
            planos.PDCA_TETO_CAUSAS_POR_TENANT,
        )
        self.assertLessEqual(planos.PDCA_TETO_MODELOS_POR_TENANT, 500)

    def test_o_log_de_nc_e_gemeo_do_log_de_restricao(self):
        """Os dois existem para **zerar**, não para acumular — e um log de
        defeito maior que o de travas diria que a obra tolera mais defeito
        aberto do que impedimento aberto, que não é a mensagem."""
        self.assertEqual(
            planos.PDCA_TETO_NCS_ABERTAS_POR_OBRA,
            planos.PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA,
        )

    def test_uma_nc_que_pede_vinte_acoes_nao_e_uma_nc(self):
        """O teto não é limite de rigor: é o aviso de que o problema precisa ser
        quebrado em vários — e quebrado, cada um encerra o seu."""
        self.assertLessEqual(planos.PDCA_TETO_ACOES_POR_NC, 20)

    def test_a_CONFORMIDADE_nao_tem_meta_no_payment(self):
        """**A fronteira da §5.6, pela terceira vez no módulo** — e aqui é a
        mais tentadora das três.

        O PBQP-H e a ISO 9001 falam em índice de conformidade, e seria fácil
        cravar 95 como "meta do plano". Continua errado pelas duas razões de
        sempre: o número é **resultado medido**, não limite de uso, e meta de
        qualidade é acordo entre a empresa, o cliente e o organismo certificador
        dela. Mesma recusa que a §5.5j fez com o PPC e a §5.5k com o ritmo.

        **O prazo de verificação de eficácia entra na mesma varredura**: "30 dias
        depois de executada a ação" é cláusula do sistema de qualidade do
        cliente, da família da retenção da §5.5h — e é o `quando` do 5W2H,
        digitado por quem monta o plano.
        """
        suspeitos = [
            nome for nome in dir(planos)
            if nome.startswith("PDCA_")
            and any(p in nome for p in (
                "CONFORMIDADE", "META", "EFICACIA", "PRAZO_TRATAMENTO",
            ))
        ]
        self.assertEqual(
            suspeitos, [],
            f"resultado de qualidade virou teto de plano: {suspeitos}",
        )

    def test_a_ficha_cabe_dentro_do_gesto_que_a_aplica(self):
        """**Não há corte síncrono × job nesta fatia, e é uma decisão.**

        Aplicar um modelo escreve no máximo um item por pergunta, numa
        transação — o número que protege o gesto já é o teto de itens do modelo.
        Declarar um segundo criaria dois limites para a mesma pergunta, que é o
        que a §5.5f recusou para bytes por apontamento.
        """
        suspeitos = [
            nome for nome in dir(planos)
            if nome.startswith("PDCA_")
            and "VERIFICACAO" in nome
            and "SINCRONO" in nome
        ]
        self.assertEqual(suspeitos, [], f"teto duplicado para o mesmo gesto: {suspeitos}")


class TetosDaSsmaTests(SimpleTestCase):
    """PDCA.8 — os três da SSMA, **e o que a ausência de um quarto protege**."""

    #: **`assertIs` não serve para estes números, e vale escrever por quê.**
    #:
    #: A régua da casa prende constante a consumidor com
    #: `assertIs(services.X, planos.X)`, e ela funciona porque um `from ...
    #: import` faz os dois nomes apontarem para o mesmo objeto. Só que o CPython
    #: interna todo inteiro de −5 a 256: para um teto de 60, `assertIs` passa
    #: **mesmo que o `services` tenha redeclarado o literal** em vez de importar
    #: — que é exatamente a regressão que a regra existe para impedir. Conferido
    #: no interpretador: dois módulos com `X = 150` dão `is` verdadeiro; com
    #: `X = 500`, falso.
    #:
    #: Os três números desta fatia são todos ≤ 256, então o teste aqui olha a
    #: **procedência**: o nome tem de chegar ao `services` por `ImportFrom` de
    #: `payment.planos`, e não pode existir como atribuição no módulo. É a mesma
    #: pergunta que o `assertIs` queria fazer, feita de um jeito que os valores
    #: pequenos não escondem.
    TETOS = (
        "PDCA_TETO_PARTICIPANTES_POR_DDS",
        "PDCA_TETO_ANEXOS_POR_OCORRENCIA",
        "PDCA_TETO_OCORRENCIAS_NA_FILA",
    )

    def test_a_ssma_le_os_tetos_do_payment(self):
        from modulopdca import services

        for nome in self.TETOS:
            self.assertEqual(
                getattr(services, nome), getattr(planos, nome), nome,
            )

    def test_os_tetos_da_ssma_vem_por_IMPORT_e_nao_por_literal_repetido(self):
        """A prova de procedência que o `assertIs` não dá nesta faixa."""
        import ast
        import inspect

        from modulopdca import services

        arvore = ast.parse(inspect.getsource(services))

        importados, atribuidos = set(), set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module == "payment.planos":
                importados.update(a.asname or a.name for a in no.names)
            if isinstance(no, ast.Assign):
                for alvo in no.targets:
                    if isinstance(alvo, ast.Name):
                        atribuidos.add(alvo.id)

        for nome in self.TETOS:
            self.assertIn(
                nome, importados,
                f"{nome} não é importado de payment.planos — o número do dono "
                f"precisa chegar ao módulo por importação, não por cópia.",
            )
            self.assertNotIn(
                nome, atribuidos,
                f"{nome} foi reatribuído dentro do services: o valor do dono "
                f"deixou de valer e nenhum `assertIs` pegaria isso, porque o "
                f"CPython interna inteiros até 256.",
            )

    def test_a_roda_do_DDS_tem_tamanho_de_roda(self):
        """O DDS é a frente parada em círculo antes do turno.

        Acima de umas dezenas ninguém ouve e ninguém pergunta, e a lista vira o
        que ela não pode ser: assinatura colhida por fora do diálogo, que é a
        fraude que uma fiscalização procura. O número tem de caber na frente
        grande de uma obra vertical no pico e ainda descrever uma roda.
        """
        self.assertGreaterEqual(planos.PDCA_TETO_PARTICIPANTES_POR_DDS, 30)
        self.assertLessEqual(planos.PDCA_TETO_PARTICIPANTES_POR_DDS, 120)

    def test_NAO_existe_teto_de_ocorrencias_abertas_por_obra(self):
        """**A ausência é a decisão mais importante da §5.5m.**

        Seria o gêmeo óbvio do `PDCA_TETO_NCS_ABERTAS_POR_OBRA` e do
        `PDCA_TETO_RESTRICOES_ABERTAS_POR_OBRA`, e copiá-lo produziria um
        sistema que **recusa o registro de um acidente** porque a obra já tem
        registros demais. Log de NC e de restrição se zeram porque a empresa
        decide tratá-los; acidente não se decide.
        """
        suspeitos = [
            nome for nome in dir(planos)
            if nome.startswith("PDCA_TETO_")
            and ("OCORRENCIAS_ABERTAS" in nome or "ACIDENTES" in nome)
        ]
        self.assertEqual(
            suspeitos, [],
            f"teto de escrita sobre ocorrência é subnotificação: {suspeitos}",
        )

    def test_nenhum_indicador_de_seguranca_virou_teto(self):
        """Taxa, dias e meta são **resultado medido** — a fronteira da §5.6.

        A quarta vez que o módulo traça esta linha, depois do PPC, do ritmo e da
        conformidade. E a mais perigosa: meta de zero acidentes não só é acordo
        do cliente como **corrompe o dado que a fatia coleta** — quem persegue o
        número para de registrar o quase-acidente.
        """
        proibidos = [
            nome for nome in dir(planos)
            if nome.startswith(("PDCA_", "SSMA_"))
            and any(
                marca in nome for marca in (
                    "FREQUENCIA", "GRAVIDADE_SSMA", "DIAS_PERDIDOS",
                    "DIAS_DEBITADOS", "META_", "ZERO_ACIDENTE",
                )
            )
        ]
        self.assertEqual(
            proibidos, [], f"resultado medido não é teto de plano: {proibidos}",
        )

    def test_prazo_legal_e_periodicidade_nao_moram_no_payment(self):
        """O prazo da CAT é lei; a periodicidade do DDS é do cliente.

        Nenhum dos dois é teto comercial nosso — mesma família do limite legal
        de acréscimo que a §5.5h recusou e da janela de reentrega da Meta.
        """
        proibidos = [
            nome for nome in dir(planos)
            if any(m in nome for m in ("CAT_", "_CAT", "DDS_PERIODICIDADE",
                                       "PERIODICIDADE_DDS", "VALIDADE_ASO"))
        ]
        self.assertEqual(
            proibidos, [], f"cláusula legal ou de terceiro no payment: {proibidos}",
        )


class TetosDoCockpitDoPdcaTests(SimpleTestCase):
    """§5.5n — os cinco das leituras que atravessam obras e assuntos.

    Família nova de novo: as anteriores protegiam **uma** obra de cada vez.
    Estas protegem leituras que cruzam — e por isso o caro delas não é o que o
    cliente escreve, é o que o servidor tem de somar para responder.
    """

    #: A mesma ressalva da `TetosDaSsmaTests`: os cinco são ≤ 256, e o CPython
    #: interna esses inteiros — `assertIs` passaria mesmo com o `services`
    #: redeclarando o literal. O teste de procedência abaixo é quem pega.
    #:
    #: **Os dois últimos entraram atrasados**, e o atraso é o próprio argumento
    #: do D190: `PDCA_TETO_LINHAS_POR_FRENTE` nasceu com a frente do canteiro e
    #: ficou fora desta tupla, isto é, um teto do dono viveu uma fatia inteira
    #: sem ninguém cobrando que ele chegasse ao módulo por importação.
    TETOS = (
        "PDCA_TETO_OBRAS_NA_CARTEIRA",
        "PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA",
        "PDCA_TETO_RESULTADOS_POR_ESPECIE",
        "PDCA_TETO_LINHAS_POR_FRENTE",
        "PDCA_TETO_CONTRATOS_NO_POSTO",
    )

    def test_o_cockpit_le_os_tetos_do_payment(self):
        from modulopdca import services

        for nome in self.TETOS:
            self.assertEqual(
                getattr(services, nome), getattr(planos, nome), nome,
            )

    def test_os_tetos_do_cockpit_vem_por_IMPORT_e_nao_por_literal(self):
        import ast
        import inspect

        from modulopdca import services

        arvore = ast.parse(inspect.getsource(services))
        importados, atribuidos = set(), set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module == "payment.planos":
                importados.update(a.asname or a.name for a in no.names)
            if isinstance(no, ast.Assign):
                for alvo in no.targets:
                    if isinstance(alvo, ast.Name):
                        atribuidos.add(alvo.id)

        for nome in self.TETOS:
            self.assertIn(
                nome, importados,
                f"{nome} não é importado de payment.planos — o número do dono "
                f"precisa chegar ao módulo por importação, não por cópia.",
            )
            self.assertNotIn(nome, atribuidos, nome)

    def test_a_tela_recebe_os_tres_para_poder_declarar_o_corte(self):
        """Lista cortada em silêncio é pior que lista curta.

        A carteira truncada sem aviso é a diretoria decidindo sobre quarenta
        obras achando que viu todas — por isso todos viajam no `status/`.
        """
        from modulopdca import views

        fonte = inspect.getsource(views.PdcaStatusView)
        for nome in self.TETOS:
            self.assertIn(nome, fonte, nome)

    def test_a_carteira_cabe_numa_leitura_sincrona(self):
        """O teto existe porque **cada linha custa um rollup de cronograma**.

        Não há caminho assíncrono para a carteira, e um número grande aqui
        produziria uma página que demora sem ninguém saber por quê. Acima de
        umas poucas dezenas a leitura tem de mudar de desenho, não de número.
        """
        self.assertLessEqual(planos.PDCA_TETO_OBRAS_NA_CARTEIRA, 100)
        self.assertGreaterEqual(planos.PDCA_TETO_OBRAS_NA_CARTEIRA, 20)

    def test_a_busca_cabe_numa_paleta_sem_rolagem(self):
        """Sete espécies × o teto tem de caber numa lista que se lê de relance.

        O teto é **por espécie** justamente para nenhuma esconder outra; se ele
        crescesse, a paleta voltaria a ser uma tela de resultados — e aí a
        pessoa navega por menu de novo, que é o que a busca existe para evitar.
        """
        ESPECIES = 7
        self.assertLessEqual(
            planos.PDCA_TETO_RESULTADOS_POR_ESPECIE * ESPECIES, 100,
        )

    def test_a_faixa_da_fila_cabe_dentro_do_log_que_a_alimenta(self):
        """Teto de leitura maior que o de escrita nunca morderia.

        A faixa de NC sem plano não pode declarar que mostra mais linhas do que
        o log de NC em aberto (§5.5l) comporta — seria número que o dono acha
        que protege alguma coisa.
        """
        self.assertLessEqual(
            planos.PDCA_TETO_LINHAS_POR_FAIXA_DA_FILA,
            planos.PDCA_TETO_NCS_ABERTAS_POR_OBRA,
        )

    def test_o_posto_da_medicao_cabe_numa_leitura_sincrona(self):
        """Cada linha custa um `saldo_do_contrato`, e ele percorre as medições.

        É a irmã do teto da carteira, e o número é pequeno pela mesma razão: a
        alternativa que a tela usaria sem esta leitura — uma chamada de saldo
        por contrato — é pior, mas trocar N chamadas por uma só vale enquanto a
        única couber no tempo de uma página abrindo.
        """
        self.assertLessEqual(planos.PDCA_TETO_CONTRATOS_NO_POSTO, 60)
        self.assertGreaterEqual(planos.PDCA_TETO_CONTRATOS_NO_POSTO, 10)

    def test_a_periodicidade_da_medicao_NAO_virou_teto(self):
        """**A sexta vez que o módulo traça esta linha** (§5.6).

        A fila do posto da medição não tem faixa de "contrato sem medir há N
        dias", e a ausência é decisão de desenho: de quanto em quanto tempo se
        mede é **cláusula comercial** combinada com cada empreiteiro, e o
        contrato nem guarda esse campo. Um `PDCA_DIAS_SEM_MEDIR` aqui venderia
        como limite de plano um acordo entre o cliente e o fornecedor dele — e
        produziria uma faixa que acende todo dia para todo contrato vigente,
        que é o aviso que ensina a ignorar a fila.
        """
        proibidos = [
            nome for nome in dir(planos)
            if nome.startswith("PDCA_")
            and any(marca in nome for marca in (
                "DIAS_SEM_MEDIR", "PERIODICIDADE", "MEDICAO_MINIMA",
                "INTERVALO_DE_MEDICAO", "PRAZO_DE_ATESTO",
            ))
        ]
        self.assertEqual(
            proibidos, [],
            f"cláusula comercial virou teto de plano: {proibidos}",
        )

    def test_nenhum_indicador_da_carteira_virou_teto(self):
        """**A quinta vez que o módulo traça esta linha.**

        Depois do PPC (§5.5j), do ritmo (§5.5k), da conformidade (§5.5l) e das
        taxas de SSMA (§5.5m). A carteira **ordena** por avanço, PPC,
        conformidade e dias sem afastamento; ela não escolhe qual é bom, e um
        `PDCA_MINIMO_DE_AVANCO` aqui venderia como limite de plano uma meta que
        é acordo entre o cliente e a equipe dele.
        """
        proibidos = [
            nome for nome in dir(planos)
            if nome.startswith("PDCA_")
            and any(marca in nome for marca in (
                "AVANCO_MINIMO", "MINIMO_DE_AVANCO", "SPI", "CPI",
                "DESVIO_ACEITAVEL", "CARTEIRA_META",
            ))
        ]
        self.assertEqual(
            proibidos, [], f"resultado medido virou teto de plano: {proibidos}",
        )

    def test_o_piso_de_letras_da_busca_NAO_mora_no_payment(self):
        """E a ausência é declarada na §5.6, junto com o `JANELA` do CEP.

        Duas letras não dizem *até onde o cliente vai* — dizem a partir de
        quando a procura acerta. Quem limita o alcance é o
        `PDCA_TETO_RESULTADOS_POR_ESPECIE`, e esse está na §5.5n.
        """
        from modulopdca import services

        self.assertFalse(
            [n for n in dir(planos) if "MINIMO_DE_LETRAS" in n],
            "piso de acerto não é teto de plano",
        )
        self.assertGreaterEqual(services.MINIMO_DE_LETRAS, 2)


class TetosDaAutorizacaoTests(SimpleTestCase):
    """Remodelagem, fases 2 e 3 — o relógio do PDP e a fila da sombra (§5.5p).

    Pela lição do D190, identidade de objeto não prova nada para inteiro pequeno
    (o `14` do critério é internado pelo CPython): o que se cobra aqui é que o
    nome chega ao módulo **importado de `payment.planos`**, e que nenhum módulo
    da autorização o reescreve como literal.
    """

    def _importa_do_payment(self, modulo, nome):
        import ast

        arvore = ast.parse(inspect.getsource(modulo))
        importado = any(
            isinstance(no, ast.ImportFrom) and no.module == "payment.planos"
            and any(a.name == nome for a in no.names)
            for no in ast.walk(arvore)
        )
        reescrito = any(
            isinstance(no, ast.Assign)
            and any(getattr(t, "id", None) == nome for t in no.targets)
            for no in ast.walk(arvore)
        )
        self.assertTrue(importado, f"{modulo.__name__} não importa {nome} de payment.planos")
        self.assertFalse(reescrito, f"{modulo.__name__} redeclara {nome}")

    def test_o_pdp_e_a_sombra_leem_os_tetos_do_payment(self):
        from nucleo import autorizacao_pdp, autorizacao_sombra
        from nucleo.management.commands import modo_autorizacao, relatorio_pdp

        self._importa_do_payment(autorizacao_pdp, "AUTORIZACAO_PDP_TIMEOUT_MS")
        self._importa_do_payment(autorizacao_sombra, "AUTORIZACAO_SOMBRA_FILA")
        self._importa_do_payment(autorizacao_sombra, "AUTORIZACAO_DIVERGENCIA_JANELA_S")
        self._importa_do_payment(modo_autorizacao, "AUTORIZACAO_SOMBRA_DIAS_SEM_DIVERGENCIA")
        self._importa_do_payment(relatorio_pdp, "AUTORIZACAO_SOMBRA_DIAS_SEM_DIVERGENCIA")

    def test_o_relogio_do_pdp_chega_ao_cliente(self):
        from django.test import override_settings

        from nucleo import autorizacao_pdp

        with override_settings(SPICEDB_URL="http://pdp", SPICEDB_CHAVE="k"):
            autorizacao_pdp._cliente = None
            try:
                self.assertEqual(
                    autorizacao_pdp.cliente().timeout_s, planos.AUTORIZACAO_PDP_TIMEOUT_MS / 1000,
                )
            finally:
                autorizacao_pdp._cliente = None

    def test_o_relogio_e_curto_o_bastante_para_uma_requisicao(self):
        # Um PDP lento vira uma plataforma lenta: o teto tem de caber com folga
        # dentro do que uma requisição aguenta, e não pode ser zero.
        self.assertGreater(planos.AUTORIZACAO_PDP_TIMEOUT_MS, 0)
        self.assertLessEqual(planos.AUTORIZACAO_PDP_TIMEOUT_MS, 1000)


class TetosDoErpFinanceiroTests(SimpleTestCase):
    """§5.5s — a grade de títulos, o lote de boletos, a segunda via e o CNAB (itens 51–58)."""

    def _importa(self, modulo, nome):
        import ast

        arvore = ast.parse(inspect.getsource(modulo))
        importado = any(
            isinstance(no, ast.ImportFrom) and no.module == "payment.planos"
            and any(a.name == nome for a in no.names)
            for no in ast.walk(arvore)
        )
        self.assertTrue(importado, f"{modulo.__name__} deixou de ler {nome} do payment/planos.py")

    def test_os_limites_do_erp_vem_do_payment(self):
        from funcoescobrancas import documento, segunda_via
        from moduloerp import limites_lote, views, views_cnab

        self._importa(views, "ERP_TETO_NIVEIS_AGRUPAMENTO")
        self._importa(limites_lote, "ERP_TETO_COBRANCAS_POR_LOTE")
        self._importa(segunda_via, "ERP_SEGUNDA_VIA_PRAZO_DIAS")
        self._importa(segunda_via, "ERP_ENCARGOS_MULTA_PADRAO_PERCENTUAL")
        self._importa(documento, "ERP_BOLETO_PDF_TETO_MB")
        self._importa(documento, "ERP_BOLETO_PDF_SEGUNDOS")
        self._importa(views_cnab, "ERP_CNAB_RETORNO_TETO_MB")

    def test_o_padrao_de_encargos_cabe_no_teto(self):
        from decimal import Decimal

        self.assertLessEqual(
            Decimal(planos.ERP_ENCARGOS_MULTA_PADRAO_PERCENTUAL), Decimal(planos.ERP_ENCARGOS_MULTA_TETO_PERCENTUAL),
        )
        self.assertLessEqual(
            Decimal(planos.ERP_ENCARGOS_JUROS_MES_PADRAO_PERCENTUAL),
            Decimal(planos.ERP_ENCARGOS_JUROS_MES_TETO_PERCENTUAL),
        )

    def test_feriados_e_notas_em_lote_vem_do_payment(self):
        """§5.5t (01/10/2026) — a faixa do calendário e o acompanhamento da NFS-e."""
        from modulocalendar.management.commands import sincronizar_feriados
        from moduloerp import limites_lote, tasks

        self._importa(sincronizar_feriados, "CALENDARIO_ANO_INICIAL")
        self._importa(sincronizar_feriados, "CALENDARIO_ANO_FINAL")
        self._importa(tasks, "ERP_NFSE_CONSULTA_INTERVALO_S")
        self._importa(tasks, "ERP_NFSE_CONSULTA_TENTATIVAS")
        self._importa(limites_lote, "ERP_TETO_NOTAS_POR_LOTE")
        # A faixa é a mesma de todo campo de data da plataforma (`maxCalendarioISO`).
        self.assertEqual((planos.CALENDARIO_ANO_INICIAL, planos.CALENDARIO_ANO_FINAL), (1900, 2100))

    def test_o_lote_do_plano_nao_passa_da_infraestrutura(self):
        """§5.5u — o teto por lote de cada plano cabe no teto de infraestrutura,
        e as duas quotas viajam no token (família por operação)."""
        for slug, plano in planos.PLANOS.items():
            for chave, infra in (("boletos_por_lote", planos.ERP_TETO_COBRANCAS_POR_LOTE),
                                 ("notas_por_lote", planos.ERP_TETO_NOTAS_POR_LOTE)):
                valor = plano[chave]
                self.assertTrue(valor is None or 0 < valor <= infra, f"{slug}.{chave}={valor}")
        self.assertIn("boletos_por_lote", planos.QUOTAS_APLICADAS)
        self.assertIn("notas_por_lote", planos.QUOTAS_APLICADAS)
