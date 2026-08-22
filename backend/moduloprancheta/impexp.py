# backend/moduloprancheta/impexp.py
"""PRA.5 — a Prancheta declara o que entra e o que sai. É o `IE.n` do módulo.

**Por que a Prancheta é a primeira porta a migrar.** Ela é a única com achado de
segurança aberto — o [D75](../../docs/historico-correcoes.md): a porta de upload decidia o
formato pelo **nome do arquivo** e entregava o binário ao LibreDWG, que é parser
em C rodando no worker. O [D65](../../docs/historico-correcoes.md) já tinha
registrado que sufixo é dado do atacante, e o remédio existia do lado do motor
desde a IE.3 — só não tinha sido aplicado aqui.

**A régua ficou maior do que a R17 escrita** (decisão do dono, 08/08/2026): o
`funcoesimpexp` é o único meio de importação e exportação do projeto, e isso
inclui **download**. Então este arquivo declara as duas metades:

- **entrada** — o acervo histórico entra em lote, com conferência (R1) e desfazer
  (R6), e o upload avulso vira lote de 1. A allowlist passa a ser a da
  plataforma, decidida por **assinatura de bytes**;
- **saída** — as três portas de leitura do módulo (a revisão como o projetista a
  entregou, a derivada que o nosso motor gerou, o snapshot da marcação) passam a
  sair pelo `entregar_arquivo`, com `nosniff`, `attachment`, tipo declarado por
  nós e cache — numa implementação só, a do motor.

**O que este módulo continua sendo dono, e não delega:** qual MIME cada um dos
seus formatos tem (o motor não conhece DWG), o que é paywall comercial (§6 da
planta) e a taxonomia da pasta do projetista.
"""
from __future__ import annotations

from funcoesimpexp.entrega import CACHE_IMUTAVEL, buscar_do_tenant
from funcoesimpexp.registro import (
    CAMPO_ARQUIVO,
    NATUREZA_ARQUIVO,
    RASTRO_AUDITADO,
    RASTRO_INTERNO,
    ArquivoEntregue,
    Coluna,
    ContextoInvalido,
    EntregaInvalida,
    Recurso,
    registrar,
)

from payment.planos import PRANCHETA_TETO_SNAPSHOT_MB

from .entrega import nome_da_derivada, tipo_da_derivada, tipo_do_formato
from .formatos import (
    FORMATO_POR_CODIGO,
    FORMATOS,
    registrar_formatos_na_plataforma,
)
from .models import (
    DerivadaProjeto,
    Disciplina,
    DocumentoProjeto,
    PontoDeVista,
    RevisaoDocumento,
)
from .pipeline import TIERS_PADRAO, agendar
from .planos import formatos_do_plano, teto_de_snap, tiers_do_plano
from .taxonomia import (
    codigo_e_revisao,
    disciplina_do_caminho,
    disciplinas_do_nome,
    proximo_rotulo,
    revisao_declarada,
)

#: O teto do snapshot, que é a unidade em que o motor fala e a mesma em que o
#: dono o edita ([payment/planos.py](../../payment/planos.py) §5.3). O alias
#: existe porque o nome curto é o que o gancho e o teste usam; o número é de lá,
#: e vale para os DOIS caminhos da mesma imagem — a que chega solta pelo
#: `ponto-de-vista/` e a que vem dentro de um `.bcfzip`.
MAX_SNAPSHOT_MB = PRANCHETA_TETO_SNAPSHOT_MB

#: A allowlist da plataforma aprende os formatos deste módulo **no import**, que
#: é quando o `autodiscover_modules("impexp")` do motor traz este arquivo. Antes
#: do registro, `detectar_formato` não sabe o que é um DWG — e é essa ignorância
#: que a porta antiga preenchia olhando o nome do arquivo (o D75).
FORMATOS_REGISTRADOS = registrar_formatos_na_plataforma()

#: As espécies de arquivo que o acervo entrega. Ficam nomeadas aqui, e não soltas
#: em `if`s, porque são o contrato da URL: `revisao` é o que o cliente mandou e
#: `derivada` é o que nós produzimos. As duas saem pela mesma porta e com rastros
#: diferentes — ver `entregar_arquivo`.
ESPECIE_REVISAO = "revisao"
ESPECIE_DERIVADA = "derivada"
#: O índice de snap da mesma derivada (PRA.10). Espécie separada e não um `?tipo=`
#: na derivada porque são dois binários com MIME e nome diferentes na mesma
#: linha — e porque `entregar_arquivo` resolve `(espécie, chave)` num campo só.
ESPECIE_SNAP = "snap"
#: A do outro recurso. O snapshot da marcação **não** é do acervo, e o motivo é
#: o gate: `PontoDeVistaViewSet` sempre exigiu `prancheta.marcacao`, não
#: `prancheta.documento` (a segregação da PRA.3). Um recurso tem um conjunto de
#: permissões; pendurar o snapshot no acervo trocaria o gate dele em silêncio, e
#: para MAIS gente — quem tem `documento.view` e não tem `marcacao.view` passaria
#: a ver apontamento de canteiro. Dois gates, dois recursos.
ESPECIE_SNAPSHOT = "snapshot"


def _palpite_de_disciplina(arquivo, *, escolha: str | None) -> str:
    """O que a pasta e o nome dizem, na ordem de precedência da PRA.9c.

    Devolve **texto separado por vírgula** porque é assim que a coluna `multipla`
    viaja: o JSON da linha guarda o que a conferência mostra, e o motor não
    conhece o significado da vírgula — quem a lê de volta é o
    `_disciplinas_da_linha`, do outro lado.
    """
    da_pasta = disciplina_do_caminho(arquivo.caminho)
    if da_pasta != Disciplina.OUTRA:
        return da_pasta
    do_nome = disciplinas_do_nome(arquivo.nome)
    if do_nome:
        return ",".join(do_nome)
    return (escolha or "").strip() or Disciplina.OUTRA


def _disciplinas_da_linha(valor) -> list[str]:
    """A célula da conferência lida de volta como lista, na ordem escrita.

    A primeira é a principal — é o contrato do `definir_disciplinas`, e é o que
    a coluna denormalizada `disciplina` do documento vai guardar. Existe como
    função porque tanto o palpite (`ARQ-ELE-…` → duas) quanto a correção do
    operador (que marca dois chips) chegam aqui pelo mesmo campo de texto, e
    partir a vírgula em dois lugares foi como a primeira versão pôs
    `"arquitetura,eletrica"` — que não é `choices` de ninguém — dentro do campo.
    """
    return [d.strip() for d in str(valor or "").split(",") if d.strip()]


@registrar("prancheta.acervo")
class AcervoDeProjeto(Recurso):
    """O acervo de projeto: as pranchas que o campo abre e o escritório publica."""

    rotulo = "Acervo de projeto"
    modulo = "prancheta"
    natureza = NATUREZA_ARQUIVO

    # §3 — acesso total para operar o acervo em lote: ver o documento e poder
    # gravá-lo. O acervo não tem coluna de PII, então não há permissão de máscara
    # a somar.
    permissoes_exigidas = ("prancheta.documento.view", "prancheta.documento.edit")

    # **O gate da SAÍDA é só de leitura, e isto não é afrouxamento.** A PRA.3 deu
    # ao `campo` `documento.view` sem `edit` de propósito — quem aponta problema no
    # canteiro não governa o acervo. Se abrir a prancha exigisse o conjunto acima,
    # o visualizador que existe desde a PRA.2 fecharia para o usuário para quem o
    # módulo foi feito, e fecharia por causa de uma regra escrita para a
    # exportação tabular. Ver `Recurso.permissoes_entrega`.
    permissoes_entrega = ("prancheta.documento.view",)

    chave = "hash"
    colunas = (
        Coluna("hash", "Hash", obrigatoria=True),
        Coluna("nome", "Arquivo"),
        Coluna("caminho", "Caminho na pasta"),
        Coluna("formato", "Formato"),
        Coluna("tamanho", "Tamanho (bytes)", tipo=int),
        Coluna("obra", "Obra"),
        # **Editável e múltipla** (R19/PRA.9c). É a única coluna que o operador
        # corrige na conferência, e o motivo é o custo do erro: a pasta da obra
        # inteira traz elétrica, hidráulica e arquitetura juntas, o palpite acerta
        # as subpastas organizadas e erra o arquivo solto no meio — e sem corrigir
        # ali a única saída era recusar a linha e reenviar aquele arquivo à parte.
        # As outras continuam de leitura: código e revisão saem do nome e são o
        # que a conferência existe para o operador **conferir**, não reescrever.
        Coluna("disciplina", "Disciplina", editavel=True, multipla=True),
        # PRA.5b — as duas colunas que a conferência existe para mostrar, porque
        # são as que a plataforma **adivinhou** do nome do arquivo (R18). Sem
        # elas a tela listaria hash e tamanho, que ninguém sabe conferir.
        Coluna("codigo", "Código do documento", obrigatoria=True),
        Coluna("revisao", "Revisão"),
    )

    #: A obra é escolhida antes de o lote começar, e não adivinhada da pasta. O
    #: porquê está em [taxonomia.py](taxonomia.py): disciplina errada custa um
    #: filtro, obra errada põe a planta de um prédio no canteiro de outro.
    contexto_requerido = ("obra",)

    #: O que o acervo recebe. Subconjunto da allowlist da plataforma: o registry
    #: diz o que ela sabe **reconhecer**, isto diz o que ESTE destino aceita.
    #: `bcf` fica de fora de propósito — marcação não é desenho, e a porta dela é
    #: o `prancheta.marcacao`.
    formatos_arquivo = tuple(
        c for c in FORMATOS_REGISTRADOS if not FORMATO_POR_CODIGO[c].interop
    )

    # ------------------------------------------------------------------
    # O que este módulo VENDE — o motor pergunta, o `payment/` responde
    # ------------------------------------------------------------------

    def formatos_contratados(self, user):
        """A parede comercial da visualização, aplicada agora na porta única.

        Era `uploads.validar_arquivo` quem a aplicava, no meio da checagem de
        segurança. Separar as duas é o ponto: **reconhecer** um DWG é da
        plataforma e vale para todo mundo; **abrir** DWG é o que este cliente
        comprou. A primeira é 400, a segunda é 402.
        """
        return tuple(formatos_do_plano(user))

    def teto_mb_do_formato(self, codigo: str) -> int:
        """O teto medido de cada formato (§6 da planta) — 100 MB de PDF, 300 de IFC.

        Sai daqui e não do registry da plataforma porque o mesmo PDF é planilha
        de preço no Orçamento e prancha aqui. O teto de infra fica por cima.
        """
        formato = FORMATO_POR_CODIGO.get(codigo)
        return formato.max_mb if formato else 0

    # ------------------------------------------------------------------
    # Entrada em lote (PRA.5b) — o acervo histórico do escritório
    # ------------------------------------------------------------------
    #
    # **Por que o lote existe e o avulso não bastava.** O upload avulso pede que
    # alguém escolha o documento, digite a revisão e aponte o arquivo — uma vez
    # por prancha. Um acervo histórico tem anos de projeto, e a implantação
    # começa por ele: sem esta fatia o cliente entra no produto digitando
    # trezentos formulários, ou não entra.
    #
    # **O que muda em relação ao avulso é só quem adivinha** (R18): aqui a
    # plataforma lê disciplina, código e revisão do caminho da pasta, e por isso
    # o lote **para na conferência** — nada entra no acervo antes do sim, e a R6
    # desfaz. No avulso não há palpite nosso, e ele grava direto.

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        """Resolve a obra de destino **antes** de ler um único byte.

        Guarda também os **tiers de motor do plano de quem abriu o lote**, e essa
        é a parte que não é óbvia: `pipeline.agendar` os exige, eles saem da
        claim do token (`tiers_do_plano`), e `aplicar_linha` roda numa requisição
        **posterior** — a da confirmação —, onde o motor não passa o usuário. Sem
        isto o lote inteiro cairia no `TIERS_PADRAO` (só o livre), e um cliente
        premium veria trezentas pranchas convertidas pelo motor de entrada para
        depois pedir reprocessamento em massa.

        Guardar em vez de reler é o mesmo raciocínio do serializer da revisão: o
        plano vem no token, não no banco, e o worker não tem token.
        """
        from obras.models import Obra

        obra = Obra.objects.filter(pk=contexto.get("obra") or 0, tenant_id=tenant_id).first()
        if obra is None:
            # Mesma mensagem para "não existe" e "é de outro tenant": distinguir
            # confirmaria a existência da obra alheia.
            raise ContextoInvalido("Escolha uma obra da sua empresa para receber o acervo.")

        # `teto_snap` viaja no contexto pela mesma razão que `tiers`: o lote roda
        # em task, onde não há usuário para consultar plano nem add-on.
        resolvido = {
            "obra": obra.pk,
            "tiers": list(tiers_do_plano(user)),
            "teto_snap": teto_de_snap(user),
            # A classe de cadeira na frota (D98), congelada pela mesma razão que
            # os `tiers`: quem aplica o lote é uma requisição posterior.
            "plano": getattr(user, "iam_plano", "") or "",
        }

        # Disciplina é **opcional** aqui, ao contrário da obra, e o critério é o
        # mesmo custo de erro da [taxonomia](taxonomia.py): disciplina errada
        # custa um filtro, obra errada põe a planta de um prédio no canteiro de
        # outro. Validada contra o vocabulário do tenant para não gravar
        # trezentas pranchas com um slug que a tela não sabe pintar.
        escolhida = (contexto.get("disciplina") or "").strip()
        if escolhida:
            from .disciplinas import indice

            def escopo(qs):
                return qs.filter(tenant_id=tenant_id)

            if escolhida not in indice(escopo):
                raise ContextoInvalido(f"A disciplina '{escolhida}' não existe neste acervo.")
            resolvido["disciplina"] = escolhida

        return resolvido

    def rotulo_do_contexto(self) -> str:
        obra = self._obra()
        return f"Obra: {obra.nome_obra}" if obra else ""

    def _obra(self):
        """A obra do lote, lida uma vez por operação.

        O cache é seguro porque `com_contexto()` devolve uma **cópia** do recurso
        por operação — a instância do registry nunca é tocada. Sem ele,
        `dados_do_arquivo` faria uma consulta por arquivo do lote só para repetir
        o mesmo nome trezentas vezes.
        """
        from obras.models import Obra

        if not hasattr(self, "_obra_cache"):
            self._obra_cache = Obra.objects.filter(pk=self.contexto.get("obra") or 0).first()
        return self._obra_cache

    def opcoes_da_coluna(self, campo: str) -> list[dict] | None:
        """O vocabulário do tenant, para a conferência oferecer em vez de digitar.

        `cor` viaja junto porque é por ela que a pessoa reconhece a disciplina
        antes de ler o nome — a mesma gramática do resto do módulo, agora dentro
        de um componente compartilhado que não sabe o que é disciplina.
        """
        if campo != "disciplina":
            return None
        from .disciplinas import catalogo

        tenant_id = (self.contexto or {}).get("tenant_id")

        def escopo(qs):
            # Sem tenant não se devolve vocabulário de ninguém: `none()` faz a
            # tela cair nas 13 embutidas (que o `catalogo` sempre soma) em vez de
            # vazar as disciplinas criadas por outro cliente.
            return qs.filter(tenant_id=tenant_id) if tenant_id else qs.none()

        return [
            {"valor": d["codigo"], "rotulo": d["nome"], "cor": d["cor"]}
            for d in catalogo(escopo)
        ]

    def dados_do_arquivo(self, arquivo) -> dict:
        """O palpite da R18: o que a pasta e o nome do arquivo dizem.

        `obra` sai do contexto e não do caminho — é a assimetria explicada em
        [taxonomia.py](taxonomia.py) —, mas continua na tabela da conferência
        porque é a primeira coisa que o operador precisa ver antes de confirmar
        trezentas pranchas: *para qual obra isto está indo*.

        **A revisão é a `revisao_declarada` e não a do `codigo_e_revisao`**, e a
        troca é da PRA.9d. Aquela devolve `R00` em dois casos diferentes — o
        arquivo que **diz** `_R00` e o que **não diz nada** —, e a fusão era
        inofensiva enquanto este era o caminho do acervo *histórico*: acervo que
        chega inteiro entra num documento vazio, e qualquer rótulo serve. Com o
        upload avulso fora (era ele que resolvia "a entrega de hoje de uma prancha
        viva"), a mesma porta passou a receber os dois casos, e a fusão inverte o
        segundo: o documento tem `R04` em campo, chega `HID-001.pdf` sem marca, o
        `R00` está livre — e a entrega de hoje entraria **atrás** da que o canteiro
        está executando. Célula vazia é a resposta honesta de *"o nome não disse"*,
        e quem a resolve é o `aplicar_linha`, que é onde se sabe o que o documento
        já tem.
        """
        codigo, _ = codigo_e_revisao(arquivo.nome)
        revisao = revisao_declarada(arquivo.nome)
        obra = self._obra()
        return {
            "hash": arquivo.hash,
            "nome": arquivo.nome,
            "caminho": arquivo.caminho,
            "formato": arquivo.formato,
            "tamanho": arquivo.tamanho,
            "obra": obra.nome_obra if obra else "",
            # **O palpite de cada arquivo vence; a escolha da tela é a reserva**
            # (PRA.9c — invertido de propósito em relação à PRA.9b).
            #
            # A PRA.9b fez a escolha sobrescrever tudo, e o dono achou o defeito
            # no uso: manda-se a pasta **da obra inteira**, com elétrica,
            # hidráulica e arquitetura dentro, e uma escolha só carimbava as três
            # com a mesma disciplina — pior do que o palpite, porque o palpite ao
            # menos acertava as subpastas organizadas.
            #
            # Agora: pasta que declara (`.../ELE/x.dwg`) manda; **nome** que
            # declara (`ARQ-PLB-001.dwg`) manda em seguida; e a escolha da tela
            # cobre só o que sobrou — que é justamente o arquivo solto no meio.
            # A R1 continua valendo: o que a plataforma vai gravar é o que a
            # conferência mostra, palpite ou escolha.
            #
            # **O nome devolve TODAS as disciplinas que declara, e não a
            # primeira.** A coluna é `multipla` desde a PRA.9c, mas este palpite
            # continuava cortando em `[0]`: `ARQ-ELE-PLB-001.dwg` chegava à
            # conferência só como Arquitetura, e a Elétrica tinha de ser marcada
            # à mão em cada linha. O upload avulso — que era o outro caminho da
            # tela, e saiu na PRA.9d — pré-marcava as duas desde sempre; manter o
            # corte aqui teria transformado o caminho único numa regressão para o
            # arquivo que declara mais de uma. A **pasta** continua declarando
            # uma só, porque é uma só que ela declara.
            "disciplina": _palpite_de_disciplina(
                arquivo, escolha=self.contexto.get("disciplina"),
            ),
            "codigo": codigo,
            "revisao": revisao,
        }

    def localizar(self, dados: dict, tenant_id):
        """O mesmo arquivo já está no acervo **desta obra**?

        Por `hash`, que é a chave: o mesmo desenho reenviado com outro nome é o
        mesmo desenho. **Escopado à obra do lote**, e não ao tenant inteiro, de
        propósito — o detalhe-padrão que o escritório repete em todas as obras é
        legitimamente um documento em cada uma delas, e um teste por tenant o
        deixaria de fora da segunda em diante sem explicar por quê.
        """
        return (
            RevisaoDocumento.objects.filter(
                tenant_id=tenant_id,
                hash_sha256=dados.get("hash") or "",
                documento__obra_id=self.contexto.get("obra") or 0,
            )
            .select_related("documento")
            .first()
        )

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict | None:
        """Cria (ou reaproveita) o documento e grava a revisão. É aqui que entra.

        **Nasce `rascunho`, sempre.** Publicar é verbo separado
        (`prancheta.revisao.publicar`) porque muda o que o campo vai executar, e o
        lote pede só `documento.edit` — um lote que publicasse daria a quem sobe
        arquivo o poder que a PRA.0 separou de propósito (a lição do D28). O
        acervo carregado em lote nasce sem vigente, e isso é a fila de decisão do
        cockpit funcionando, não uma lacuna.
        """
        if existente is not None:
            # Já está aqui, byte a byte. Não há o que atualizar: o arquivo de uma
            # revisão é write-once (planta §9), e reescrevê-lo deixaria hash,
            # formato e tamanho descrevendo outro conteúdo. Sem estado anterior
            # porque nada mudou — e `desfazer` não deve apagar o que já existia.
            return None

        # A coluna é `multipla`: o valor chega como `"arquitetura,eletrica"` — do
        # palpite do nome ou dos dois chips que o operador marcou na conferência
        # —, e é partido **antes** do `get_or_create`. Fazê-lo só depois foi o
        # defeito da primeira versão desta fatia: a lista inteira ia para o
        # `defaults`, e `"arquitetura,eletrica"` não é `choices` de ninguém — o
        # `create()` não valida, então o valor entrava no banco para explodir na
        # primeira tela que traduzisse o rótulo.
        escolhidas = _disciplinas_da_linha(dados.get("disciplina"))
        documento, documento_novo = DocumentoProjeto.objects.get_or_create(
            tenant_id=tenant_id,
            obra_id=self.contexto["obra"],
            codigo=dados["codigo"],
            defaults={
                # O título sai do mesmo código porque é a única coisa legível que
                # um acervo histórico traz. Fica editável na tela do documento —
                # inventar um título "bonito" a partir do nome do arquivo seria
                # dado fabricado, que a régua do módulo não admite.
                "titulo": dados["codigo"][:180],
                # `OUTRA` e não `""`: o campo tem `choices`, e um valor fora
                # delas passaria pelo `create()` (que não valida) para explodir na
                # primeira tela que traduzisse o rótulo. A **primeira** da lista é
                # a principal — o mesmo contrato do `definir_disciplinas`.
                "disciplina": next(iter(escolhidas), Disciplina.OUTRA),
            },
        )
        # PRA.9c — o vínculo, e não só a coluna. Um documento nascido pelo lote
        # sem ele responderia certo (o `codigos_de_disciplina` cai no campo), mas
        # a primeira reclassificação pela tela apagaria a classificação de origem
        # sem que ninguém tivesse pedido. Só na criação: o lote não reclassifica
        # prancha que já existe — regra que era do `enviar/` avulso e ficou de pé
        # quando ele saiu (PRA.9d), porque é do acervo e não daquela porta.
        if documento_novo and escolhidas:
            documento.definir_disciplinas(escolhidas)
        revisao = RevisaoDocumento(
            tenant_id=tenant_id,
            documento=documento,
            revisao=proximo_rotulo(documento, dados.get("revisao") or ""),
            nome_original=dados.get("nome") or "",
            # O `dados["caminho"]` já era lido pela taxonomia da R18 e morria
            # aqui. Guardá-lo custa um campo e responde "de qual pasta do
            # escritório veio esta prancha?", que sem ele não tem resposta.
            caminho_origem=(dados.get("caminho") or "")[:1024],
            formato=dados.get("formato") or "",
            tamanho_bytes=dados.get("tamanho") or 0,
            hash_sha256=dados.get("hash") or "",
            situacao=RevisaoDocumento.Situacao.RASCUNHO,
        )
        # **`arquivo.save()` e não `arquivo = ...`**, e a diferença não é de
        # estilo: atribuir o `FieldFile` da conferência copiaria só o *nome* do
        # caminho, e as duas linhas passariam a apontar para o mesmo binário. O
        # `aplicar` do motor agenda a limpeza da área de conferência logo depois
        # — ela apagaria o arquivo do acervo, e o acervo ficaria com trezentas
        # revisões cujo download é 404. O motor conta com esta cópia: "o módulo
        # dono já tem a sua própria cópia (o `FileField.save()` dele copiou os
        # bytes)".
        #
        # `open("rb")` porque o binário pode ter sido lido antes (o hash, a
        # detecção) e um ponteiro no fim gravaria um arquivo vazio — a mesma
        # armadilha que o `admitir` resolve restaurando a posição.
        binario = dados[CAMPO_ARQUIVO]
        binario.open("rb")
        # O caminho de destino usa `documento.obra_id` e `tenant_id`
        # (`caminho_revisao`), então os dois já estão na instância acima.
        revisao.arquivo.save(dados.get("nome") or "prancha", binario, save=False)
        revisao.save()
        # `plano` do contexto, pelo mesmo motivo que `tiers` (D98): a aplicação
        # do lote roda numa requisição posterior — a da confirmação — e numa task,
        # onde não há o usuário que abriu a remessa. Congelá-lo em
        # `validar_contexto` é o que faz um lote de trezentas pranchas entrar na
        # fila com a classe de cadeira de quem o mandou, e não como `comum`.
        agendar(revisao, tiers=tuple(self.contexto.get("tiers") or TIERS_PADRAO),
                teto_snap=self.contexto.get("teto_snap") or 0,
                plano=self.contexto.get("plano") or "")
        return {
            "acao": "criou",
            "revisao": revisao.pk,
            # Só quando ESTE lote criou o documento. Desfazer não pode apagar um
            # documento que já existia e que agora está sem revisões por acaso.
            "documento": documento.pk if documento_novo else None,
        }

    # **`_rotulo_livre` saiu na PRA.9d, e quem ficou é o `proximo_rotulo`** da
    # [taxonomia](taxonomia.py). Os dois resolviam a colisão que a transação
    # exige — `PLANTA.dwg` e `PLANTA (cópia).dwg` do mesmo acervo histórico
    # palpitam o mesmo rótulo, e a `UniqueConstraint` levantando no meio do lote
    # derrubaria as outras 299 pranchas com um 500 —, e nesse caso dão a MESMA
    # resposta. Divergiam só no rótulo não declarado: o daqui tapava o primeiro
    # buraco (`R00` livre num documento que tem `R04` em campo), o de lá continua
    # do maior. Enquanto o avulso existia, cada um servia a sua porta; agora a
    # porta é uma e recebe os dois casos, e tapar buraco poria a entrega de hoje
    # atrás da que o canteiro está executando.

    def desfazer_linha(self, estado_anterior: dict, tenant_id) -> None:
        """R6 — a revisão sai do acervo, e os bytes saem do disco com ela.

        **Apagar o `FileField` explicitamente** porque o Django não o faz: um
        `delete()` de linha deixa o binário no storage desde a 1.3, e num lote de
        acervo isso seriam centenas de MB cobrados de um cliente que desfez
        justamente para não os ter. As derivadas caem por cascata da FK; as
        conversões que já estiverem na fila para elas morrem sozinhas ao não
        achar a linha, que é o caminho que o pipeline já trata.
        """
        revisao = RevisaoDocumento.objects.filter(
            pk=estado_anterior.get("revisao") or 0, tenant_id=tenant_id,
        ).first()
        if revisao is not None:
            arquivo = revisao.arquivo
            revisao.delete()
            if arquivo:
                arquivo.delete(save=False)

        documento_id = estado_anterior.get("documento")
        if documento_id:
            # Só se continuar vazio: entre aplicar e desfazer cabe um upload
            # avulso no mesmo documento, e apagá-lo levaria junto uma revisão que
            # este lote nunca tocou.
            DocumentoProjeto.objects.filter(
                pk=documento_id, tenant_id=tenant_id, revisoes__isnull=True,
            ).delete()

    # ------------------------------------------------------------------
    # Saída — as três portas de leitura, agora pela porta única
    # ------------------------------------------------------------------

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        """Resolve `(espécie, chave)` no binário que pode sair.

        **Os três rastros são diferentes de propósito**, e a linha que os separa é
        a mesma que a R17 já usa na entrada — *item que o sistema cria não é
        importação, é registro*:

        - a **revisão** é o arquivo do cliente. Baixá-la é o dado saindo do
          perímetro, que é O evento de LGPD da R12 — vai para a trilha. O custo
          é uma linha por pessoa por revisão (a URL é `immutable` e a revisão é
          write-once), e o que se compra com ela é saber quem levou o projeto;
        - a **derivada** é o SVG/glTF que o **nosso motor** gerou, servido ao
          **nosso** visualizador. Auditá-la encheria a trilha do
          [D67](../../docs/historico-correcoes.md) de "abriu uma prancha" e
          afogaria "levou a base de clientes";
        - o **snapshot** é o mesmo caso da derivada: é o recorte da tela que o
          próprio módulo renderiza ao lado do comentário.

        **O cache imutável vale nas três, mas por motivos distintos** — e é o
        [D51](../../docs/historico-correcoes.md) que obriga a distinção: a revisão
        é write-once (planta §9), então o id basta; a derivada é **reescrita** a
        cada reconversão, e só é imutável porque `url_da_derivada` carrega o `?v=`
        da identidade do conteúdo. Trocar uma pela outra é como o conserto do D46
        ficou invisível na tela por um ano.
        """
        if especie == ESPECIE_REVISAO:
            revisao = _buscar(RevisaoDocumento, "revisao_id", chave, tenant_id)
            return ArquivoEntregue(
                campo=revisao.arquivo,
                nome=revisao.nome_original,
                tipo=tipo_do_formato(revisao.formato),
                objeto=revisao,
                rastro=RASTRO_AUDITADO,
                cache=CACHE_IMUTAVEL,
            )

        if especie == ESPECIE_DERIVADA:
            derivada = _buscar(DerivadaProjeto, "derivada_id", chave, tenant_id)
            nome = derivada.arquivo.name if derivada.arquivo else ""
            return ArquivoEntregue(
                campo=derivada.arquivo,
                nome=nome_da_derivada(derivada),
                tipo=tipo_da_derivada(nome),
                objeto=derivada,
                rastro=RASTRO_INTERNO,
                cache=CACHE_IMUTAVEL,
            )

        if especie == ESPECIE_SNAP:
            # **Mesmo gate, mesmo cache e mesmo rastro da derivada**, porque é a
            # mesma coisa: geometria que o nosso motor gerou, servida ao nosso
            # visualizador. Um recurso próprio daria a impressão de que se pode
            # liberar o snap de uma prancha sem liberar a prancha.
            derivada = _buscar(DerivadaProjeto, "derivada_id", chave, tenant_id)
            if not derivada.snap:
                # Sem sidecar não se entrega vazio: bytes de zero comprimento
                # chegariam à tela como um índice legítimo de nenhum ponto, e a
                # mira simplesmente não grudaria em lugar nenhum, sem dizer por
                # quê. 404 a tela sabe ler — é "esta folha não tem snap".
                raise EntregaInvalida("Esta folha não tem índice de snap.")
            return ArquivoEntregue(
                campo=derivada.snap,
                nome=f"snap-{derivada.pk}.snap",
                tipo="application/octet-stream",
                objeto=derivada,
                rastro=RASTRO_INTERNO,
                cache=CACHE_IMUTAVEL,
            )

        raise EntregaInvalida(f"Espécie '{especie}' não existe no acervo de projeto.")


@registrar("prancheta.marcacao")
class MarcacoesDoProjeto(Recurso):
    """O que a marcação carrega em arquivo — hoje, o snapshot do ponto de vista.

    **Recurso separado do acervo por causa do gate, não por gosto de simetria.**
    A PRA.3 segregou de propósito: ver documento é `prancheta.documento.view`, ver
    apontamento é `prancheta.marcacao.view`, e há persona com um e não com o
    outro. Um `Recurso` tem **um** conjunto de permissões — pendurar o snapshot no
    `prancheta.acervo` trocaria o gate dele em silêncio, e para mais gente.

    É também onde o **BCF** vai entrar e sair quando a ida e volta com o
    escritório passar pela porta única: o `.bcfzip` é arquivo, o gate é este, e o
    `importar-bcf` de hoje é a última porta de upload do módulo fora do motor.
    """

    rotulo = "Marcações de projeto"
    modulo = "prancheta"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("prancheta.marcacao.view", "prancheta.marcacao.edit")
    permissoes_entrega = ("prancheta.marcacao.view",)

    chave = "guid"
    colunas = (
        Coluna("guid", "GUID (BCF)", obrigatoria=True),
        Coluna("nome", "Arquivo"),
        Coluna("formato", "Formato"),
        Coluna("tamanho", "Tamanho (bytes)", tipo=int),
    )

    #: PRA.5b — os dois arquivos que ENTRAM por aqui, e são de naturezas opostas:
    #: o `.bcfzip` que o escritório respondeu (arquivo do cliente, lido pelo nosso
    #: parser de zip) e a `imagem` do ponto de vista (recorte que o navegador
    #: produziu no ato de marcar). Nenhum é desenho — o desenho é o
    #: `prancheta.acervo`, e quem tentar por aqui recebe o endereço certo em vez
    #: da lista de formatos ([porta.py](porta.py)).
    formatos_arquivo = ("bcf", "imagem")

    def formatos_contratados(self, user):
        """A mesma parede comercial do acervo, e ela morde só o BCF.

        `imagem` está em **todos** os planos (`formatos_prancheta` do
        [payment/planos.py](../../payment/planos.py), do `free` para cima), então
        na prática esta linha decide uma coisa só: levar a marcação para o
        software do projetista e trazê-la de volta é o que o plano vende — marcar
        dentro do sistema vem com o módulo (planta §6).

        Ler do mesmo `formatos_do_plano` que o acervo lê é o ponto: o formato é
        vendido **uma vez**, e é honrado em qualquer porta que o receba.
        """
        return tuple(formatos_do_plano(user))

    def teto_mb_do_formato(self, codigo: str) -> int:
        """O teto DESTE destino, que não é o do mesmo formato no acervo.

        É o caso que o gancho existe para atender, e aqui ele aparece dentro do
        próprio módulo: `imagem` no acervo é uma prancha escaneada; `imagem`
        **aqui** é o recorte de tela de um ponto de vista, e são dois tamanhos
        diferentes da mesma coisa. Os dois números vêm de
        [payment/planos.py](../../payment/planos.py) §5.3 — `PRANCHETA_MB_POR_FORMATO`
        e `PRANCHETA_TETO_SNAPSHOT_MB` —, e o segundo vale também para o snapshot
        que chega **dentro** de um `.bcfzip`. Um número só faria os dois caminhos
        do mesmo dado divergirem, que é o que o
        [D75.1](../../docs/historico-correcoes.md) pegou acontecendo com a
        extensão composta.
        """
        if codigo == "imagem":
            return MAX_SNAPSHOT_MB
        formato = FORMATO_POR_CODIGO.get(codigo)
        return formato.max_mb if formato else 0

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        """O snapshot — o recorte da tela que alguém tirou ao apontar o problema.

        `RASTRO_INTERNO` pelo mesmo motivo da derivada: é imagem que o **nosso**
        visualizador escreveu, renderizada ao lado do comentário na **nossa**
        tela. É a plataforma lendo o que ela mesma produziu, e não dado saindo do
        perímetro.
        """
        if especie != ESPECIE_SNAPSHOT:
            raise EntregaInvalida(f"Espécie '{especie}' não existe nas marcações.")
        ponto = _buscar(PontoDeVista, "ponto_de_vista_id", chave, tenant_id)
        return ArquivoEntregue(
            campo=ponto.snapshot,
            nome=f"marcacao-{ponto.guid}.png",
            # O snapshot é escrito pelo NOSSO leitor de BCF e pelo nosso
            # visualizador — o tipo é conhecido, não adivinhado do upload.
            tipo="image/png",
            objeto=ponto,
            rastro=RASTRO_INTERNO,
            cache=CACHE_IMUTAVEL,
        )


def _buscar(modelo, campo_pk: str, chave: str, tenant_id):
    """Busca escopada por tenant — o mecanismo subiu para o motor no **D70**.

    Ele estava aqui e passou a ser preciso em mais nove recursos. Escopo de
    tenant é guarda-corpo, e guarda-corpo copiado é guarda-corpo que diverge:
    `buscar_do_tenant` é a mesma função, uma vez só, com a mesma promessa —
    filtra por tenant de todo jeito e devolve 404 tanto para o que não existe
    quanto para o que é de outro cliente.
    """
    return buscar_do_tenant(modelo, chave, tenant_id, campo_pk=campo_pk)
