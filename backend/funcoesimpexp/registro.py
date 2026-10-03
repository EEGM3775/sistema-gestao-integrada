# backend/funcoesimpexp/registro.py
"""IE.0 — o contrato: como um módulo declara o que sai e o que entra.

Este arquivo é o vocabulário inteiro do funcoesimpexp. **O motor não conhece
modelo nenhum**; ele só sabe percorrer `Coluna` e chamar os ganchos de um
`Recurso`. Quem sabe o que é um item orçado, um cliente ou uma conta a pagar é o
módulo dono, e ele conta isso aqui.

A escolha por declaração (e não por reflexão sobre o ORM, como fazia o v01) é o
que mantém a régua da planta §2 aplicável: `Model.objects.values()` devolve
`empreendimento_id = 47` e `cpf_cnpj` em claro — nomes de coluna de banco, sem
rótulo, sem tipo e sem gate de PII. Uma declaração custa ~15 linhas por recurso e
paga com as três saídas da §5 saindo de uma fonte só (R2).

`Recurso` é classe comum, não `dataclass`, de propósito: os ganchos são
**métodos** que a subclasse sobrescreve, e o `__init__` gerado por `@dataclass`
atribuiria os defaults por cima deles na instanciação — apagando em silêncio o
`queryset` que o módulo acabou de escrever.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal


class RecursoInvalido(Exception):
    """Declaração que não obedece à régua — erro de programação, não de uso."""


class RecursoDesconhecido(KeyError):
    """Pediram um recurso que ninguém registrou."""


class ContextoInvalido(Exception):
    """Destino ausente, de outro tenant ou fechado para escrita.

    Erro **de uso**, não de programação: quem chama traduz para 400/404/409
    conforme o caso. Existe separado de `RecursoInvalido` justamente por isso —
    declaração torta derruba o boot, destino errado devolve mensagem ao usuário.
    """


class EntregaInvalida(Exception):
    """Pediram um arquivo que não existe, não é deste tenant ou não tem binário.

    **As três causas viram 404, e é deliberado que a de outro tenant também.**
    Responder 403 a um id que existe noutro tenant confirma que ele existe — o
    mesmo raciocínio que faz `_Base.importacao` buscar sempre pelo queryset
    escopado. Quem não pode ver não deve conseguir distinguir "não existe" de
    "não é seu".
    """


TIPOS_SUPORTADOS = (str, int, Decimal, bool)

#: As duas naturezas de recurso (IE.3). Ver a nota em `Recurso.natureza`.
NATUREZA_LINHA = "linha"
NATUREZA_ARQUIVO = "arquivo"

#: Chave reservada em `dados` por onde o binário chega a `aplicar_linha` num
#: recurso de natureza `arquivo`.
#:
#: Reservada e não parâmetro novo de propósito: mudar a assinatura de
#: `aplicar_linha` obrigaria os seis recursos de linha que já existem a
#: reescreverem um gancho por causa de uma natureza que não é a deles. O prefixo
#: `_` a mantém fora das `colunas` (que nunca começam com sublinhado) e fora do
#: arquivo de recusadas da R5.
CAMPO_ARQUIVO = "_arquivo"

#: As duas políticas de rastro de uma **entrega** (IE.3b). Ver `ArquivoEntregue`.
RASTRO_AUDITADO = "auditado"
RASTRO_INTERNO = "interno"


@dataclass(frozen=True)
class ArquivoRecebido:
    """Um arquivo na área de conferência — o que o motor sabe sem abri-lo.

    **Sem abri-lo** é a parte que importa: o motor reconhece o formato pelos
    bytes iniciais (a allowlist de `limites.py`) e não interpreta o conteúdo.
    Quem eventualmente o abre é o módulo dono, depois da decisão — e o antivírus,
    quando entrar ([D74](../../docs/modulos/funcoesimpexp.md)), entra exatamente
    aqui, entre receber e conferir, porque é o ponto por onde todo arquivo passa.
    """

    nome: str
    #: Caminho relativo dentro da pasta enviada (`ObraA/ARQ/planta.dwg`), ou o
    #: nome puro num envio avulso. É o que carrega a taxonomia de um acervo.
    caminho: str
    tamanho: int
    #: SHA-256 do conteúdo. É a chave natural de idempotência de um lote de
    #: arquivos: o mesmo desenho reenviado é `duplicada`, mesmo com outro nome.
    hash: str
    formato: str


@dataclass(frozen=True)
class ArquivoEntregue:
    """Um arquivo que o recurso autoriza a **sair** — o espelho de `ArquivoRecebido`.

    **Por que a saída de binário também é do motor** (decisão do dono,
    08/08/2026): o `funcoesimpexp` é o único meio de importação e exportação do
    projeto, e isso inclui *download*, não só upload. A R17 tratava só da
    entrada, e o preço de a saída ter ficado de fora estava à vista — a
    `moduloprancheta/entrega.py` reimplementava sozinha o `nosniff`, o
    `attachment`, o tipo decidido por nós e o saneamento do nome. Quatro
    guarda-corpos, segunda cópia, exatamente a forma do [D75](../../docs/historico-correcoes.md)
    do lado da entrada.

    **Entrega não é exportação, e as duas convivem de propósito.** Exportar é
    gerar um arquivo tabular a partir do `queryset` — tem recorte (R7), cabeçalho
    de procedência (R9), caminho de job (R10) e linha em `Exportacao`. Entregar é
    deixar sair **um binário que o recurso já guarda**, como o cliente o mandou ou
    como o nosso motor o produziu. Não há o que recortar nem o que gerar; o que
    há é quem pode, que tipo declaramos, e se o ato entra na trilha.

    `objeto` é a instância do ORM de onde o arquivo veio. Serve a duas coisas que
    o motor não teria como saber sozinho: o `tenant` da linha de auditoria e o
    `modelo`/`objeto_id` que a trilha guarda.
    """

    #: O `FileField` em si — o motor só o abre, nunca o interpreta.
    campo: object
    #: Nome sugerido. Passa por saneamento antes de virar header: ele costuma ter
    #: origem no cliente, e nome de arquivo é texto de terceiro.
    nome: str
    #: MIME que **nós** declaramos. Nunca adivinhado do nome que veio de fora —
    #: é a decisão (1) da porta de leitura da Prancheta, agora valendo para todos.
    tipo: str
    objeto: object = None
    #: `RASTRO_AUDITADO` grava `AuditLog`; `RASTRO_INTERNO` não.
    #:
    #: A distinção é a mesma que a R17 já faz na entrada — *"item que o sistema
    #: cria não é importação, é registro"*. O arquivo que o cliente mandou saindo
    #: do perímetro é evento de LGPD e vai para a trilha; a derivada que o nosso
    #: motor gerou, servida ao nosso próprio visualizador, é a plataforma lendo o
    #: que ela mesma produziu. Auditar as duas com a mesma ação encheria a trilha
    #: do D67 de "abriu uma prancha" e afogaria "levou a base de clientes".
    #:
    #: O padrão é auditar: quem quiser ficar de fora declara, e a declaração fica
    #: no código do módulo, revisável.
    rastro: str = RASTRO_AUDITADO
    #: `Cache-Control`. Vazio = o motor não promete nada (`private, no-store`),
    #: que é o certo para quem não puder garantir que a URL identifica o conteúdo.
    cache: str = ""


@dataclass(frozen=True)
class Guardado:
    """DMS — onde um recurso **guarda** arquivos, para o registro único.

    O `funcoesimpexp` já era a porta única de todo arquivo que entra e sai (R17).
    Faltava a terceira pergunta de quem coordena documentos — *o que está aqui
    dentro, de quem é, desde quando* —, e ela se responde com a mesma declaração:
    o recurso diz em que model e em que `FileField` os arquivos dele moram, e o
    registro (`funcoesimpexp/arquivos.py`) os lista com o mesmo gate e o mesmo
    link da entrega. Nenhum arquivo é copiado; nenhum segundo registro existe.

    `especie` é a mesma do `entregar_arquivo` — é ela que fecha o laço entre
    "listar" e "baixar". Os lookups são do ORM a partir do model.
    """

    especie: str
    modelo: object
    campo: str
    #: Campo de data para ordenar e mostrar ("desde quando").
    quando: str = ""
    #: O texto que identifica o arquivo para quem procura (nome do documento).
    titulo: str = ""
    #: O contexto: de qual obra, cliente, funcionário (lookup do ORM).
    onde: str = ""
    #: Recorte do model quando ele guarda mais de uma espécie (`{"especie": ...}`).
    filtro: dict = None


@dataclass(frozen=True)
class Coluna:
    """Uma coluna do arquivo — e, por R2, também do modelo e do validador.

    `campo` é o nome interno (o que os ganchos recebem e devolvem); `rotulo` é o
    que aparece no cabeçalho do arquivo. Os dois são distintos de propósito:
    renomear o rótulo para o usuário não pode quebrar a gravação, e mudar o campo
    interno não pode mudar o arquivo que o cliente já usa como modelo.
    """

    campo: str
    rotulo: str
    tipo: type = str
    obrigatoria: bool = False
    exemplo: str = ""
    # Sinônimos aceitos no cabeçalho de um arquivo importado, além do rótulo.
    # Alimentam o de-para automático (R4); o que não casar vai para o operador
    # mapear à mão, nunca para adivinhação.
    aliases: tuple[str, ...] = ()
    # --- R19: correção linha a linha na conferência -----------------------
    #
    # Até aqui a conferência só aceitava **aceitar ou recusar** a linha inteira,
    # e a planta registrava isso como o limite que impedia a obra de ser palpite
    # como as outras. O caso que o forçou veio do acervo: manda-se a pasta da
    # obra, o palpite acerta as subpastas organizadas e erra o arquivo solto no
    # meio — e a única saída era recusar a linha e reenviar o arquivo à parte.
    #
    # `editavel` abre a célula na tela; `multipla` diz que ela aceita mais de um
    # valor (guardados separados por vírgula no `valores`, que é JSON de texto).
    # Quem oferece a lista é o recurso, em `opcoes_da_coluna` — o motor não
    # conhece disciplina, obra nem centro de custo, e não deve conhecer.
    editavel: bool = False
    multipla: bool = False

    def __post_init__(self) -> None:
        if not self.campo or not self.rotulo:
            raise RecursoInvalido("Coluna precisa de `campo` e `rotulo`.")
        if self.tipo not in TIPOS_SUPORTADOS:
            raise RecursoInvalido(
                f"Coluna '{self.campo}': tipo {self.tipo!r} não suportado. "
                "Use str, int, Decimal ou bool."
            )

    @property
    def numerica(self) -> bool:
        return self.tipo in (Decimal, int)


class Recurso:
    """O que um módulo declara. Subclasse, preencha e decore com `@registrar(id)`.

    Um recurso pode ser só de exportação (curva ABC, DRE), só de importação
    (contagem de inventário) ou os dois — o motor descobre pelo que foi
    sobrescrito: `queryset` habilita a saída, `aplicar_linha` habilita a entrada.

    **Contexto.** O registry guarda uma instância por processo, sem estado. Quando
    a operação tem um *destino* dentro do módulo — qual banco de preço recebe as
    linhas, qual orçamento é a planilha —, o motor não passa esse dado gancho a
    gancho: ele chama `com_contexto()`, que devolve uma **cópia rasa** com
    `self.contexto` preenchido, e é nela que os ganchos rodam. A instância do
    registry nunca é tocada, então duas importações simultâneas de bancos
    diferentes não se cruzam — que é o defeito que guardar o destino no singleton
    produziria, e produziria só sob concorrência, em produção.
    """

    # --- identidade -------------------------------------------------------
    id: str = ""
    rotulo: str = ""
    modulo: str = ""
    # Destino da operação (`{"banco": 12}`). Vazio na instância do registry;
    # preenchido nas cópias que `com_contexto` devolve.
    contexto: dict = {}

    # --- acesso (planta §3 / R11) ----------------------------------------
    # Conjunto INTEIRO exigido: meia permissão bloqueia. Inclui a permissão de
    # máscara de toda coluna sensível declarada — se a exportação traz CPF, o
    # `cadastro.cliente_doc.view` entra aqui. É a única obrigação que a regra
    # simplificada transfere para quem declara.
    permissoes_exigidas: tuple[str, ...] = ()

    # Conjunto exigido para **entregar um arquivo** (IE.3b). Vazio = vale o de
    # cima, que é o certo para quase todo recurso.
    #
    # **Existe porque entrega não é exportação, e o §3 fala de exportação.** A
    # regra de "acesso total ou nada" nasceu de um risco concreto: a planilha com
    # a coluna capada sai parecendo completa e é somada fora do sistema por quem
    # não estava na tela. Abrir UMA prancha que a pessoa já pode ver no módulo não
    # tem essa forma — não há coluna, não há agregado, e o gate certo é o de
    # leitura do próprio acervo.
    #
    # Sem esta separação a conta não fecharia na Prancheta: o recurso precisa de
    # `documento.edit` para importar o lote histórico, e exigir o mesmo na saída
    # tiraria do `campo` — que a PRA.3 deixou de propósito só com `view` — a
    # capacidade de abrir o desenho no canteiro. O gate da saída teria fechado uma
    # tela que hoje funciona, e fechado por causa de uma regra escrita para outro
    # ato.
    permissoes_entrega: tuple[str, ...] = ()

    @property
    def entitlement(self) -> str | None:
        """Módulo que precisa estar contratado para **importar** neste recurso.

        Só a escrita depende dele — exportar é portabilidade e segue aberta ao
        admin, auditada (ver `acesso.exigir_entitlement_de_escrita`).

        O padrão é o próprio `modulo`, que é o certo para a maioria. Recurso de
        **fundação** — dado que a plataforma georreferencia ou cadastra sem
        vender, como o `maps.local` — sobrescreve com `entitlement = None`, e é
        por isso que isto não é simplesmente `modulo`: o `maps.local` declara
        `modulo = "maps"` e mesmo assim abre para todo tenant, porque `Local` é a
        metade sem entitlement do módulo (planta do Maps, MAP.0).
        """
        return self.modulo or None

    # --- forma ------------------------------------------------------------
    #
    # **Natureza (IE.3) — o que é uma unidade de decisão neste recurso.**
    #
    #   "linha"   — a unidade é uma linha de planilha. O motor abre o arquivo,
    #               lê linhas, e cada linha vira um `LinhaImportacao` com
    #               `valores`. É tudo que o IE.0 fazia.
    #   "arquivo" — a unidade é **o arquivo inteiro**. O motor não o abre: ele
    #               reconhece o formato pelos bytes, guarda o binário na área de
    #               conferência e deixa a decisão para uma pessoa. É a prancha do
    #               projetista, a foto do diário, o ASO do funcionário.
    #
    # A máquina é a mesma nas duas — `preparar → conferir → aplicar → desfazer`,
    # R1 e R6 valendo igual —, e é por isso que a natureza é um atributo e não um
    # segundo motor. O que muda é de onde vêm as unidades: de `ler_bytes` numa,
    # dos arquivos enviados na outra.
    natureza: str = "linha"
    colunas: tuple[Coluna, ...] = ()
    # Campo que decide criar × atualizar (R3). Sem ele não há importação
    # idempotente — e sem idempotência, reimportar duplica tudo.
    chave: str = ""
    formatos_saida: tuple[str, ...] = ("xlsx", "csv", "pdf")
    formatos_entrada: tuple[str, ...] = ("xlsx", "csv")
    # Códigos de formato que ESTE recurso de arquivo aceita — subconjunto do que
    # o módulo registrou na allowlist (`limites.registrar_formato`). Vazio em
    # recurso de linha.
    #
    # São duas listas e não uma porque respondem a perguntas diferentes: o
    # registry diz o que a **plataforma** sabe reconhecer, e isto diz o que
    # **este recurso** aceita receber. O acervo da Prancheta quer DWG e IFC; o
    # ASO do RH quer PDF e imagem, e receber um DWG ali seria um acidente que
    # nenhuma das duas listas sozinha impediria.
    formatos_arquivo: tuple[str, ...] = ()
    # Chaves de contexto que a tela precisa perguntar antes do upload. Publicado
    # em `descrever()` para o wizard montar o passo de destino sem saber de
    # domínio — sem isso o frontend teria um `if recurso == "orcamento.banco"`
    # escrito à mão, que é exatamente o acoplamento que o registry evita.
    contexto_requerido: tuple[str, ...] = ()
    # DMS — onde moram os arquivos que este recurso guarda (`Guardado`). Vazio
    # em recurso que não guarda arquivo (planilha, relatório).
    guardados: tuple = ()

    # ------------------------------------------------------------------
    # Ganchos — sobrescreva o que o recurso oferece
    # ------------------------------------------------------------------

    def queryset(self, request, recorte: dict):
        """Linhas a exportar, já escopadas por tenant e com o recorte da tela (R7).

        Devolve iterável de dicionários `campo -> valor` (ou de objetos, se
        `serializar_objeto` for sobrescrito).
        """
        raise NotImplementedError

    def serializar_objeto(self, obj) -> dict:
        """Objeto do ORM → `campo -> valor`. Só quando `queryset` devolve objetos."""
        return {c.campo: getattr(obj, c.campo, None) for c in self.colunas}

    def contar(self, request, recorte: dict) -> int | None:
        """Quantas linhas o recorte tem, sem materializá-las (R10).

        Num `QuerySet` sai um `COUNT` no banco; numa lista, o `len`. Gerador não
        tem como ser contado sem ser consumido, e aí a resposta honesta é `None`
        = "não sei" — o motor então trata como pequeno. Recurso que espera volume
        e devolve gerador deve sobrescrever isto, senão troca o job por um
        timeout.
        """
        try:
            alvo = self.queryset(request, recorte)
        except NotImplementedError:
            return None
        contador = getattr(alvo, "count", None)
        if callable(contador):
            try:
                return int(contador())
            except TypeError:  # list.count exige argumento — não é o do ORM
                pass
        try:
            return len(alvo)
        except TypeError:
            return None

    def dados_do_arquivo(self, arquivo: "ArquivoRecebido") -> dict:
        """IE.3 — a identidade de um arquivo recebido, no vocabulário do módulo.

        Só para `natureza = "arquivo"`. Recebe o que o motor sabe sem abrir o
        binário (nome, caminho relativo dentro da pasta enviada, tamanho, hash,
        formato reconhecido) e devolve o `campo -> valor` que as `colunas`
        declaram — exatamente como `extrair` faz com uma linha de planilha. Daí
        para a frente o motor não distingue as duas naturezas.

        **É aqui que a pasta vira metadado.** O projetista organiza o acervo em
        `OBRA/DISCIPLINA/prancha.dwg`, e essa estrutura é a única fonte de
        obra/disciplina que existe num lote histórico. Derivar isso é do módulo,
        não do motor: só o dono do domínio sabe que o segundo nível é disciplina
        — e quando errar, o operador corrige no de-para, que é o mesmo mecanismo
        da planilha com cabeçalho torto (R4).

        O padrão preenche o que é universal e deixa o resto vazio, de modo que um
        recurso de arquivo mínimo (um anexo sem taxonomia) funcione sem
        sobrescrever nada.
        """
        return {
            "nome": arquivo.nome,
            "caminho": arquivo.caminho,
            "tamanho": arquivo.tamanho,
            "hash": arquivo.hash,
            "formato": arquivo.formato,
        }

    def teto_mb_do_formato(self, codigo: str) -> int:
        """PRA.5a — teto deste recurso para este formato, em MB. 0 = o do plano.

        **Existe porque o teto não é propriedade do formato.** O mesmo PDF é
        planilha de preço de prefeitura no Orçamento (dezenas de MB, teto de
        planilha) e prancha executiva na Prancheta (100 MB). Um número só no
        registry serviria mal aos dois, e o que se perderia é justamente o caso
        de uso do módulo que declarou o formato.

        O teto de infraestrutura fica por cima deste, sempre — contrato negociado
        não compra o direito de derrubar o worker compartilhado.
        """
        return 0

    def formatos_contratados(self, user) -> tuple[str, ...] | None:
        """Quais dos `formatos_arquivo` o plano DESTE usuário inclui.

        `None` = não sei / não vendo por formato, e aí vale a lista inteira.

        **O gancho existe porque a venda é do módulo, e o motor não a conhece.**
        A Prancheta vende formato pelo `formatos_prancheta` de
        [payment/planos.py](../../payment/planos.py), que é onde o dono o edita —
        e a régua do projeto é clara: todo limite é knob de plano, e knob de plano
        mora em `payment/`. O que muda na PRA.5a é **quem aplica**: era o módulo,
        na porta dele; passa a ser o motor, na porta única, com um 402 só para
        todos os módulos.
        """
        return None

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> "ArquivoEntregue":
        """IE.3b — resolve um pedido de download num arquivo que pode sair.

        Só para `natureza = "arquivo"`. `especie` e `chave` são **opacos ao
        motor**: ele os tira da URL e os repassa inteiros. Quem sabe que
        `("derivada", "412")` é a conversão nº 412 e que ela pertence a esta obra
        é o módulo dono — o motor não conhece modelo nenhum, e é o que o mantém
        servindo seis módulos sem um `if` por módulo.

        **A checagem de tenant é do gancho, e não é formalidade.** A RLS já está
        armada pela view, mas ela protege a consulta, não a escolha de o que
        consultar: filtre por `tenant_id` de todo jeito, e levante
        `EntregaInvalida` no que não achar. É a mesma disciplina de `localizar`.

        Levante `EntregaInvalida` também quando a linha existe e o binário não —
        derivada ainda convertendo, derivada em erro, volume trocado. É o 404
        honesto que a porta da Prancheta já dava, e ele não pode virar 500.
        """
        raise NotImplementedError

    def validar_linha(self, dados: dict) -> str:
        """Regra de negócio do módulo. Devolve o motivo da recusa, ou "" se passa.

        Roda na conferência, antes de qualquer gravação — é aqui que "quantidade
        negativa" ou "obra de outro tenant" viram linha inválida em vez de erro
        no meio do lote.
        """
        return ""

    def localizar(self, dados: dict, tenant_id):
        """Objeto existente com esta chave, ou `None`. É o que decide criar × atualizar."""
        raise NotImplementedError

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict | None:
        """Grava a linha. Devolve o que `desfazer_linha` precisa para reverter (R6).

        Convenção: `{"acao": "criou", "pk": ...}` ou
        `{"acao": "atualizou", "pk": ..., "antes": {...}}`. `None` = sem reversão.
        """
        raise NotImplementedError

    def desfazer_linha(self, estado_anterior: dict, tenant_id) -> None:
        """Reverte uma linha aplicada. Sem isto, o lote não é desfazível."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Contexto — o destino da operação dentro do módulo
    # ------------------------------------------------------------------

    def com_contexto(self, contexto: dict | None):
        """Cópia deste recurso amarrada a um destino. Ver a nota da classe."""
        instancia = copy.copy(self)
        instancia.contexto = dict(contexto or {})
        return instancia

    def validar_contexto(self, contexto: dict, user, tenant_id) -> dict:
        """Resolve e valida o destino **antes** de ler o arquivo.

        Devolve o contexto normalizado (o que será persistido no lote) ou levanta
        `ContextoInvalido`. Rodar antes da leitura é deliberado: descobrir que o
        banco está travado depois de classificar 40 mil linhas é fazer o usuário
        esperar para receber um "não".

        O padrão não exige nada — recurso sem destino (a carteira de clientes
        inteira, a curva ABC) não precisa declarar isto.
        """
        return dict(contexto or {})

    def checar_quota_objeto(self, novas: int, limites: dict | None, tenant_id) -> None:
        """Teto de **acervo** do módulo, se houver (planta §9).

        O motor cuida sozinho de `importacao_linhas`, que é quota de *operação* e
        vale para todo recurso. Teto de acervo é outra coisa e é sempre do
        módulo: `banco_preco_linhas` conta linhas de tabela de preço e não faria
        sentido aplicado a uma importação de clientes. Quem tem acervo declara o
        seu aqui e levanta `LimiteDoPlano`.
        """
        return None

    def rotulo_do_contexto(self) -> str:
        """Como o destino aparece no cabeçalho de procedência (R9). Ex.: "Banco: Prefeitura"."""
        return ""

    # ------------------------------------------------------------------
    # Introspecção usada pelo motor
    # ------------------------------------------------------------------

    @classmethod
    def _sobrescreveu(cls, nome: str) -> bool:
        return getattr(cls, nome, None) is not getattr(Recurso, nome, None)

    @property
    def exporta(self) -> bool:
        return type(self)._sobrescreveu("queryset")

    @property
    def importa(self) -> bool:
        return type(self)._sobrescreveu("aplicar_linha")

    @property
    def desfazivel(self) -> bool:
        return type(self)._sobrescreveu("desfazer_linha")

    @property
    def de_arquivo(self) -> bool:
        """A unidade de decisão deste recurso é um arquivo, não uma linha (IE.3)."""
        return self.natureza == NATUREZA_ARQUIVO

    @property
    def entrega(self) -> bool:
        """Este recurso deixa sair o binário que guarda (IE.3b)."""
        return type(self)._sobrescreveu("entregar_arquivo")

    @property
    def permissoes_da_entrega(self) -> tuple[str, ...]:
        """Gate da saída de arquivo — o próprio, ou o do recurso se não declarou."""
        return self.permissoes_entrega or self.permissoes_exigidas

    @property
    def coluna_chave(self) -> Coluna | None:
        return self.coluna_por_campo(self.chave)

    def coluna_por_campo(self, campo: str) -> Coluna | None:
        return next((c for c in self.colunas if c.campo == campo), None)

    def obrigatorias(self) -> tuple[Coluna, ...]:
        return tuple(c for c in self.colunas if c.obrigatoria)

    # ------------------------------------------------------------------
    # A régua, verificada no registro
    # ------------------------------------------------------------------

    def validar(self) -> None:
        """Falha no import do módulo, não no clique do usuário.

        Declaração torta é erro de programação: descobrir no boot custa um
        traceback; descobrir no request custa um arquivo errado na mão de um
        cliente.
        """
        if not self.id or "." not in self.id:
            raise RecursoInvalido(f"id do recurso deve ser 'modulo.recurso' (veio {self.id!r}).")
        if not self.rotulo:
            raise RecursoInvalido(f"{self.id}: falta `rotulo`.")
        if not self.modulo:
            raise RecursoInvalido(f"{self.id}: falta `modulo`.")
        if self.natureza not in (NATUREZA_LINHA, NATUREZA_ARQUIVO):
            raise RecursoInvalido(
                f"{self.id}: natureza {self.natureza!r} desconhecida "
                f"(use {NATUREZA_LINHA!r} ou {NATUREZA_ARQUIVO!r})."
            )
        if self.de_arquivo:
            # **Esta régua foi INVERTIDA em 08/08/2026, e vale registrar o que ela
            # dizia**: que um recurso de arquivo sem `aplicar_linha` era erro,
            # porque "exportar arquivo do acervo é a porta de LEITURA do módulo
            # dono, não uma exportação tabular". A premissa (entrega ≠ exportação)
            # continua certa e virou o `ArquivoEntregue`; a conclusão — que por
            # isso a saída ficava fora do motor — foi revogada pelo dono: a porta
            # única é de entrada **e** de saída. Um recurso de arquivo pode agora
            # só receber, só entregar, ou os dois.
            if not (self.importa or self.entrega):
                raise RecursoInvalido(
                    f"{self.id}: recurso de natureza {NATUREZA_ARQUIVO!r} sem "
                    "`aplicar_linha` nem `entregar_arquivo` — não recebe e não "
                    "entrega arquivo, então não faz nada."
                )
            if self.importa and not self.formatos_arquivo:
                raise RecursoInvalido(
                    f"{self.id}: recurso de arquivo precisa declarar `formatos_arquivo`. "
                    "Sem isso a allowlist ficaria aberta, e allowlist aberta é denylist "
                    "(a régua do gov.br que a planta §2 adota)."
                )
        elif self.entrega:
            raise RecursoInvalido(
                f"{self.id}: `entregar_arquivo` num recurso de natureza "
                f"{NATUREZA_LINHA!r}. Recurso de linha não guarda binário — o que ele "
                "tem a oferecer é a exportação tabular do `queryset`."
            )
        if not self.permissoes_exigidas:
            raise RecursoInvalido(
                f"{self.id}: `permissoes_exigidas` vazio. A planta §3 não admite recurso "
                "sem gate — conjunto vazio liberaria import/export para qualquer um."
            )
        if not self.colunas:
            raise RecursoInvalido(f"{self.id}: falta declarar `colunas`.")
        campos = [c.campo for c in self.colunas]
        repetidos = sorted({c for c in campos if campos.count(c) > 1})
        if repetidos:
            raise RecursoInvalido(f"{self.id}: colunas repetidas: {repetidos}.")
        if not (self.exporta or self.importa or self.entrega):
            raise RecursoInvalido(
                f"{self.id}: nem `queryset`, nem `aplicar_linha`, nem "
                "`entregar_arquivo` — recurso não faz nada."
            )
        # R3 vale só para quem importa: exportação não precisa de chave.
        if self.importa:
            if not self.chave:
                raise RecursoInvalido(
                    f"{self.id}: importação sem `chave`. Sem chave de identidade, reimportar "
                    "o mesmo arquivo duplica tudo (R3)."
                )
            if self.coluna_chave is None:
                raise RecursoInvalido(
                    f"{self.id}: `chave` aponta para '{self.chave}', que não está em `colunas`."
                )
            if not type(self)._sobrescreveu("localizar"):
                raise RecursoInvalido(
                    f"{self.id}: importação exige `localizar` — é como o motor decide se a "
                    "linha cria ou atualiza."
                )

    def descrever(self) -> dict:
        """O que a API publica para o frontend montar botão e wizard."""
        return {
            "id": self.id,
            "rotulo": self.rotulo,
            "modulo": self.modulo,
            "exporta": self.exporta,
            "importa": self.importa,
            # A saída de binário é declarada à parte da tabular porque a tela faz
            # coisas diferentes com as duas: `exporta` vira o `<BotaoExportar>`
            # (escolher formato, esperar job), `entrega` vira link direto para um
            # arquivo que já existe. Um campo só faria o botão de exportar
            # aparecer sobre um acervo que não tem planilha para dar.
            "entrega": self.entrega,
            "desfazivel": self.desfazivel,
            "chave": self.chave,
            # A tela precisa disto para escolher o gesto: recurso de linha abre o
            # seletor de planilha e o wizard de de-para; recurso de arquivo abre
            # o seletor de PASTA e mostra uma lista de arquivos. Sem publicar a
            # natureza, o frontend voltaria ao `if recurso === "prancheta.acervo"`
            # escrito à mão — o acoplamento que o registry existe para evitar.
            "natureza": self.natureza,
            "formatos_saida": list(self.formatos_saida),
            "formatos_entrada": list(self.formatos_entrada),
            "formatos_arquivo": list(self.formatos_arquivo),
            "contexto_requerido": list(self.contexto_requerido),
            "colunas": [
                {
                    "campo": c.campo,
                    "rotulo": c.rotulo,
                    "tipo": c.tipo.__name__,
                    "obrigatoria": c.obrigatoria,
                    "exemplo": c.exemplo,
                    # R19 — a tela abre a célula só onde o recurso permitiu, e
                    # com as opções que ele deu. Sem publicar as duas coisas o
                    # wizard voltaria a `if recurso === "prancheta.acervo"`, que é
                    # o acoplamento que o registry existe para não ter.
                    "editavel": c.editavel,
                    "multipla": c.multipla,
                    "opcoes": self.opcoes_da_coluna(c.campo) if c.editavel else None,
                }
                for c in self.colunas
            ],
        }

    # --- R19: correção linha a linha --------------------------------------

    def opcoes_da_coluna(self, campo: str) -> list[dict] | None:  # noqa: ARG002
        """As opções de uma coluna `editavel` — `[{valor, rotulo, cor?}]`.

        `None` (o padrão) = texto livre. O motor não conhece disciplina, obra nem
        centro de custo, então quem responde é o módulo; `cor` é opcional e a
        tela a usa como bolinha quando vem.

        Roda no `descrever`, que é uma leitura por abertura de wizard — pode
        consultar o banco, mas não deve pesar: é o catálogo do tenant, não o
        acervo dele.
        """
        return None

    def validar_correcao(self, campo: str, valor: str) -> str:
        """Normaliza (ou recusa) o valor que a conferência gravou à mão.

        Chamado antes de escrever em `LinhaImportacao.valores`. O padrão confia
        na allowlist de `opcoes_da_coluna` — que o motor já aplica —, e existe
        para o módulo que precisa de mais do que "está na lista": normalizar
        caixa, resolver sinônimo, recusar combinação impossível.
        """
        return valor


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRO: dict[str, Recurso] = {}


def registrar(recurso_id: str):
    """Decorador de classe: `@registrar("orcamento.planilha")`.

    Registra uma **instância** — recurso não tem estado por request, então uma
    só serve o processo inteiro.
    """

    def decorador(cls):
        if not isinstance(cls, type) or not issubclass(cls, Recurso):
            raise RecursoInvalido("@registrar decora subclasse de Recurso.")
        cls.id = recurso_id
        instancia = cls()
        instancia.validar()
        anterior = _REGISTRO.get(recurso_id)
        if anterior is not None and type(anterior) is not cls:
            raise RecursoInvalido(
                f"Recurso '{recurso_id}' registrado duas vezes — o id é a chave do endpoint "
                "e colisão faria um módulo servir o dado do outro."
            )
        _REGISTRO[recurso_id] = instancia
        return cls

    return decorador


def obter(recurso_id: str) -> Recurso:
    try:
        return _REGISTRO[recurso_id]
    except KeyError:
        raise RecursoDesconhecido(recurso_id) from None


def listar() -> tuple[Recurso, ...]:
    return tuple(_REGISTRO[k] for k in sorted(_REGISTRO))
