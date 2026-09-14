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
