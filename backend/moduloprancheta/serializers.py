# backend/moduloprancheta/serializers.py
"""Serializers da Prancheta.

Duas coisas atravessam todos eles:

1. **A revisão vigente viaja junto do documento.** O acervo existe para
   responder *"esta é a última?"*; um serializer que devolvesse só o documento
   obrigaria a tela a uma segunda chamada por prancha — e a lista da obra tem
   dezenas delas.
2. **Nada sobre o arquivo é digitado pelo cliente.** Formato, tamanho, hash e
   nome original saem do arquivo enviado, não do payload. Campo desses editável
   seria a porta para um acervo que mente sobre o próprio conteúdo — e o hash é
   o que o pipeline do PRA.1 usa para decidir se reconverte.
3. **Nenhuma resposta carrega URL de mídia.** O caminho de leitura é sempre o
   endpoint gateado (`.../arquivo/`) — `arquivo` entra como campo **write-only**
   e sai como `arquivo_url`. Devolver `/media/...` seria publicar um caminho que
   fora de `DEBUG` não existe e dentro dele não passa por gate nenhum
   ([entrega.py](entrega.py)).
"""
import math
import re

from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers

from nucleo.tenancy import scope_queryset_by_tenant
from nucleo.tenant_validators import TenantScopedModelSerializer

from . import disciplinas, entrega, pipeline, porta
from .formatos import FAMILIA_DOCUMENTO, FORMATO_POR_CODIGO
from .models import (
    ComentarioMarcacao,
    DerivadaProjeto,
    DesenhoProjeto,
    DisciplinaProjeto,
    DocumentoProjeto,
    Marcacao,
    Medicao,
    PontoDeVista,
    RevisaoDocumento,
)

from .entrega import RECURSO_ACERVO
from .planos import aviso_do_upload, teto_de_snap, tiers_do_plano


def escopar_ao_tenant(fields: dict, nome: str, request) -> None:
    """Restringe o queryset de um campo-FK ao tenant de quem pede.

    No Postgres a RLS fail-closed já esconderia a linha de outro tenant (a
    validação da FK faz um SELECT sob o contexto do requisitante), mas deixar
    isso implícito é apostar que ninguém rode este código fora daquele contexto.
    Aqui o 400 sai **nomeando o campo**, em vez de depender do banco.
    """
    tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
    campo = fields.get(nome)
    if tenant_id is not None and campo is not None and hasattr(campo, "queryset"):
        campo.queryset = campo.queryset.filter(tenant_id=tenant_id)


def _fila_da_conversao(derivada) -> dict | None:
    """O que dizer a quem está esperando — posição, andamento e o botão (D98).

    **Existe porque "convertendo" sozinho é indistinguível de "travado".** Era a
    queixa que abriu a fila: um DWG de 40 MB ficava meia hora com a mesma
    palavra na tela, e quem olhava concluía que o sistema tinha morrido. Aqui a
    espera passa a ter forma — *"3º da fila"*, *"12 de 40 folhas, 2ª passada"* —,
    que é a diferença entre esperar e não saber.

    Devolve `None` quando não há linha na fila: conversão que roda síncrona no
    teste, job anterior à PRA.11, ou a corrida normal entre o worker terminar e a
    tela perguntar. Ausente é resposta — a tela cai no "convertendo" de sempre em
    vez de mostrar uma posição inventada.
    """
    from nucleo import frota
    from nucleo.models import TarefaNaFila

    from .pipeline import chave_na_fila

    linha = TarefaNaFila.objects.filter(
        frota=frota.FROTA_CONVERSAO, chave=chave_na_fila(derivada.pk),
        situacao__in=[TarefaNaFila.Situacao.AGUARDANDO, TarefaNaFila.Situacao.DESPACHADA],
    ).first()
    if linha is None:
        return None
    dados = frota.situacao_da_fila(linha)
    dados["tarefa_id"] = linha.tarefa_id
    # O andamento em FOLHAS, que é a unidade que a pessoa entende — "12 de 40" diz
    # muito mais que "48%", e é honesto porque as folhas são contáveis de verdade.
    dados["folhas_prontas"] = derivada.retomada_desenhos
    dados["folhas_restantes"] = derivada.retomada_restam
    return dados


def aviso_da_revisao(desenhos, memoria: dict | None) -> dict | None:
    """O arquivo abriu — e ainda assim há o que dizer sobre ele.

    **Mudou de natureza nesta fatia.** No D46 o aviso era um pedido de desculpas
    com atalhos: a folha saía com 8,5 km, todo desenho aparecia minúsculo, e a
    tela oferecia rotas para dentro de uma página que não devia ter existido.
    Agora cada desenho tem a **própria folha**, então não há mais o que desculpar
    — o que sobra é informar, e são duas coisas distintas:

    - **quantas folhas o arquivo trouxe**, para ninguém abrir a primeira e
      concluir que o resto se perdeu. É a frase que o dono do acervo pediu que
      continuasse existindo no topo, mesmo com a lista lateral;
    - **que o desenho está georreferenciado**, que é a explicação de por que a
      régua não bate com o que um template errado mostraria — e o gancho do seam
      com o Maps (PRA.7).

    `None` é a resposta normal: um arquivo com uma folha só e sem coordenada de
    mundo não tem nada a declarar, e um aviso permanente treina o usuário a
    ignorar o aviso que importa.

    **O aglomerado descartado não entra aqui, e a regra é do dono:** o que tem
    desenho é para ser mostrado, o que não tem pode ser ignorado. Contá-lo na
    tela alarmava sem informar — foi medido no `MaxPlast`, onde os "513 registros
    sem traço" são **51 arcos de raio zero do bloco `onibus`, repetidos nas 10
    inserções dele**: as 39 linhas de cada ônibus estão desenhadas, no lugar
    certo, dentro do Desenho 1. Não havia geometria perdida para declarar, e a
    linha só fazia o leitor procurar um desenho que não existe. O censo continua
    gravado na `memoria` da derivada (`desenhos_sem_traco`, `registros_sem_traco`),
    que é onde se audita conversão — a tela do canteiro não é.
    """
    memoria = memoria or {}
    hachura = _frase_da_hachura(memoria)
    if len(desenhos) < 2 and not memoria.get("unidade_corrigida") and not hachura:
        return None

    partes = []
    if len(desenhos) >= 2:
        partes.append(
            "Cada um abre como uma prancha própria — use a lista para trocar."
        )
    if memoria.get("unidade_corrigida"):
        partes.append(memoria["unidade_corrigida"])
    if hachura:
        partes.append(hachura)

    if len(desenhos) >= 2:
        codigo, titulo = "varios_desenhos", f"Este arquivo traz {len(desenhos)} desenhos"
    elif memoria.get("unidade_corrigida"):
        codigo, titulo = "georreferenciado", "Desenho georreferenciado"
    else:
        codigo, titulo = "hachura_simplificada", "Hachura simplificada"
    return {
        "codigo": codigo,
        "titulo": titulo,
        "mensagem": " ".join(partes),
        "georreferenciado": bool(memoria.get("georreferenciado")),
    }


def _frase_da_hachura(memoria: dict) -> str:
    """O que dizer a quem abre uma prancha cuja hachura não saiu inteira (D57).

    **O tom é decisão de produto, não de engenharia.** Quem abre a prancha no
    canteiro não sabe o que é orçamento de conversão nem quer saber; o que ele
    precisa é de uma frase que responda "por que está diferente?" sem sugerir que
    o sistema falhou ou que o arquivo dele está errado — nenhuma das duas é
    verdade. Por isso as duas frases dizem primeiro **o que está na tela** e só
    depois o motivo, e a do contorno afirma explicitamente que nada sumiu: é a
    dúvida real de quem vê uma área hachurada ficar vazia.

    `completa` — o caso normal — não gera frase nenhuma. Avisar que está tudo
    certo é o jeito mais rápido de treinar o canteiro a fechar o aviso sem ler,
    e aí o aviso que importa morre junto (a mesma regra do `aviso_da_revisao`).
    """
    estado = memoria.get("hachura")
    if estado == "contorno":
        return (
            "As áreas hachuradas estão com o contorno desenhado e o interior "
            "vazio: o padrão de preenchimento era pesado demais para esta "
            "prancha. Nenhum traço do desenho foi omitido."
        )
    if estado == "parcial":
        quantas = memoria.get("hachuras_truncadas") or 0
        alvo = "1 área hachurada" if quantas == 1 else f"{quantas} áreas hachuradas"
        return (
            f"O preenchimento de {alvo} desta prancha era denso demais e foi "
            "desenhado só em parte. O contorno e o resto do desenho estão inteiros."
        )
    return ""


class DesenhoProjetoSerializer(serializers.ModelSerializer):
    """Uma folha da revisão: o que abrir, com que régua, e como se chama.

    `nome` é o **único** campo escrevível, e por um verbo próprio (`renomear/`).
    Tudo o mais é produto da conversão: deixar a tela mandar `caixa` ou `tracos`
    permitiria descrever uma folha que não é a que está no arquivo.
    """

    rotulo = serializers.CharField(read_only=True)
    visualizador = serializers.SerializerMethodField()
    snap = serializers.SerializerMethodField()
    tem_escala = serializers.BooleanField(read_only=True)

    class Meta:
        model = DesenhoProjeto
        fields = [
            "desenho_id", "revisao", "ordem", "nome", "rotulo", "tracos", "caixa",
            # A ponte de volta à coordenada do CAD. Viaja junto pelo mesmo motivo
            # que a régua: o leitor de coordenadas mostra a posição a cada
            # movimento do ponteiro, e buscá-la numa segunda chamada faria a
            # barra abrir mostrando o número errado antes do certo.
            "mundo",
            "visualizador", "snap", "tem_escala",
            # A régua desta folha. Viaja junto porque o visualizador troca de
            # desenho sem recarregar o acervo — buscar a escala numa segunda
            # chamada faria a primeira medida sair sem unidade, ou pior, com o
            # número certo aparecendo depois de piscar o errado.
            "escala_valor", "escala_unidade", "escala_origem", "escala_referencia",
            "escala_calibrada_em",
        ]
        read_only_fields = [f for f in fields if f != "nome"]

    def _derivada_pronta(self, obj):
        return next(
            (d for d in obj.derivadas.all()
             if d.estado == DerivadaProjeto.Estado.PRONTO and d.arquivo),
            None,
        )

    def get_visualizador(self, obj) -> str | None:
        """A URL da folha desta prancha, já versionada.

        `None` enquanto a conversão não terminou — é o estado normal de quem
        acabou de subir o arquivo, e devolver a URL assim mesmo faria a tela
        tentar abrir um 404 em vez de mostrar o estado que ela já recebeu.
        """
        derivada = self._derivada_pronta(obj)
        if derivada is None:
            return None
        return entrega.url_da_derivada(derivada.pk, entrega.versao_da_derivada(derivada))

    def get_snap(self, obj) -> dict | None:
        """O índice de snap desta folha, ao lado da folha.

        **Viaja aqui e não só na derivada** porque é daqui que a vista abre: o
        visualizador recebe o desenho, não a linha de conversão, e obrigá-lo a
        uma segunda chamada só para descobrir se há mira atrasaria o primeiro
        clique de medição em uma ida ao servidor — na tela que o canteiro usa
        com uma mão, segurando o celular com a outra.

        `None` quando não há índice. Quando há, `truncado` diz que o teto do
        plano cortou, e é o que autoriza a tela a dizer "snap parcial" em vez de
        deixar a pessoa concluir que a mira está quebrada.
        """
        derivada = self._derivada_pronta(obj)
        if derivada is None or not derivada.snap:
            return None
        return {
            "url": entrega.url_do_snap(derivada.pk, entrega.versao_da_derivada(derivada)),
            "pontos": derivada.snap_pontos,
            "truncado": derivada.snap_truncado,
        }


class DerivadaProjetoSerializer(serializers.ModelSerializer):
    """Read-only por completo: quem escreve aqui é o pipeline (PRA.1), nunca o
    cliente. O estado da conversão — **inclusive o erro** — é dado que a tela
    precisa mostrar, e é por isso que `erro_motivo`/`erro_detalhe` e a memória de
    conversão viajam junto: a régua de dados honestos vale para a falha também."""

    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    estado_rotulo = serializers.CharField(source="get_estado_display", read_only=True)
    erro_motivo_rotulo = serializers.CharField(source="get_erro_motivo_display", read_only=True)
    exige_upgrade = serializers.SerializerMethodField()
    problema_no_arquivo = serializers.SerializerMethodField()
    aviso = serializers.SerializerMethodField()
    arquivo_url = serializers.SerializerMethodField()
    snap_url = serializers.SerializerMethodField()

    class Meta:
        model = DerivadaProjeto
        fields = [
            "derivada_id", "revisao", "tipo", "tipo_rotulo", "motor", "motor_versao",
            "estado", "estado_rotulo", "arquivo_url", "tamanho_bytes",
            "erro_motivo", "erro_motivo_rotulo", "erro_detalhe", "exige_upgrade",
            "problema_no_arquivo", "aviso", "hash_origem", "memoria", "criado_em", "concluido_em",
            # Snap (PRA.10). Os três juntos, porque a tela decide com os três: sem
            # `snap_url` não há mira; com `snap_truncado` ela diz "parcial" e
            # oferece o pacote; `snap_pontos` é o que dá a medida do que falta.
            "snap_url", "snap_pontos", "snap_truncado",
        ]
        read_only_fields = fields

    def get_aviso(self, obj) -> dict | None:
        if obj.estado != DerivadaProjeto.Estado.PRONTO:
            # Derivada em erro já fala por `erro_motivo`; um segundo canal para o
            # mesmo fato faria a tela mostrar dois alertas do mesmo problema.
            return None
        return aviso_da_revisao(list(obj.revisao.desenhos.all()), obj.memoria)

    def get_arquivo_url(self, obj) -> str | None:
        """`None` enquanto não há bytes — que é o estado normal de uma derivada
        pendente, convertendo ou em erro. Devolver a URL assim mesmo faria a tela
        tentar abrir um 404 em vez de mostrar o estado que ela já recebeu."""
        if not obj.arquivo:
            return None
        return entrega.url_da_derivada(obj.pk, entrega.versao_da_derivada(obj))

    def get_snap_url(self, obj) -> str | None:
        """`None` quando esta folha não tem índice — e são três casos distintos:
        o plano não paga o recurso, o formato não rende geometria (PDF, imagem)
        ou a extração falhou. A tela não precisa distinguir os três para decidir
        o que fazer (não há mira), e quem precisa lê a memória de conversão."""
        if not obj.snap:
            return None
        return entrega.url_do_snap(obj.pk, entrega.versao_da_derivada(obj))

    def get_exige_upgrade(self, obj) -> bool:
        """A única falha que a tela deve transformar em botão de compra.

        Existe como campo próprio — e não como um `if` no frontend sobre a string
        do motivo — porque a distinção entre `motor_insuficiente` (limite de
        plano) e `motor_indisponivel` (motor fora da imagem) é justamente a que
        não pode ser refeita em cada tela que mostrar uma derivada.
        """
        return obj.erro_motivo == DerivadaProjeto.MotivoErro.MOTOR_INSUFICIENTE

    def get_problema_no_arquivo(self, obj) -> bool:
        """Falha que **ninguém** resolve: o arquivo é que não tem o que mostrar.

        Irmão do `exige_upgrade` e pela mesma razão: a tela não pode refazer a
        classificação sobre a string do motivo. Sem este campo, "o desenho está
        vazio" cairia na lista do que consertamos, e a fila do canteiro passaria
        a listar trabalho que não existe (D45).
        """
        return obj.erro_motivo in DerivadaProjeto.MOTIVOS_DO_ARQUIVO


class RevisaoDocumentoSerializer(TenantScopedModelSerializer):
    documento_codigo = serializers.CharField(source="documento.codigo", read_only=True)
    situacao_rotulo = serializers.CharField(source="get_situacao_display", read_only=True)
    formato_rotulo = serializers.SerializerMethodField()
    derivadas = DerivadaProjetoSerializer(many=True, read_only=True)
    enviado_por_nome = serializers.CharField(source="enviado_por.username", read_only=True)
    # Quem **publicou** é pergunta diferente de quem enviou, e as duas juntas são
    # o histórico de alterações do PRA.2: subir a revisão é entrega do
    # projetista, publicá-la é a decisão de alçada que muda o que o campo
    # executa. Sem este nome, a tela do responsável mostraria a data da decisão
    # sem o autor dela.
    publicado_por_nome = serializers.CharField(source="publicado_por.username", read_only=True)
    # Entra pelo upload, sai pelo endpoint gateado — nunca como caminho de mídia.
    # `write_only` e não `read_only`: é por este campo que a revisão nasce.
    arquivo = serializers.FileField(write_only=True)
    arquivo_url = serializers.SerializerMethodField()
    # O que o cliente precisa saber **agora** e que o estado da conversão só
    # diria daqui a alguns minutos — hoje, só o teto de peso do DWG (D47). `None`
    # é o caso normal, e a tela não mostra nada.
    aviso = serializers.SerializerMethodField()

    class Meta:
        model = RevisaoDocumento
        fields = "__all__"
        read_only_fields = [
            # `caminho_origem` entra aqui pela mesma razão do `nome_original`: é
            # texto de quem enviou, escrito **pelo lote** a partir do que a pasta
            # dizia. Editável por PATCH, viraria um campo de rastreabilidade que
            # o próprio cliente reescreve — que é o oposto de rastro.
            "tenant", "nome_original", "caminho_origem", "formato", "tamanho_bytes",
            "hash_sha256",
            # `situacao` NÃO é editável por PATCH: publicar é ato com permissão
            # própria (`prancheta.revisao.publicar`). Se fosse campo comum, quem
            # tivesse `.edit` mudaria para `vigente` num PATCH e a segregação de
            # alçada viraria decoração — é a mesma armadilha do D28.
            "situacao", "enviado_por", "enviado_em", "publicado_por", "publicado_em",
            # Calibrar é ato, como publicar: mexe no que TODA medida daquela
            # prancha vale. Editável por PATCH, quem tem `documento.edit`
            # reescreveria a régua sem passar pelo verbo que exige os dois
            # pontos e a distância — e sem deixar rastro de quem e quando.
            "escala_valor", "escala_unidade", "escala_referencia",
            "escala_calibrada_por", "escala_calibrada_em",
            # Procedência é conclusão de quem escreveu a escala (o verbo ou o
            # pipeline), nunca declaração de quem edita a revisão: editável, um
            # PATCH carimbaria "calibrada" numa régua que ninguém conferiu — e
            # essa palavra é justamente a que blinda o valor contra reconversão.
            "escala_origem",
        ]

    def get_formato_rotulo(self, obj) -> str:
        formato = FORMATO_POR_CODIGO.get(obj.formato)
        return formato.nome if formato else obj.formato

    def get_arquivo_url(self, obj) -> str | None:
        return entrega.url_da_revisao(obj.pk) if obj.arquivo else None

    def get_aviso(self, obj) -> str | None:
        request = self.context.get("request")
        return aviso_do_upload(
            obj.formato, obj.tamanho_bytes, getattr(request, "user", None),
        )

    def get_fields(self):
        fields = super().get_fields()
        escopar_ao_tenant(fields, "documento", self.context.get("request"))
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        arquivo = attrs.get("arquivo")

        # **O arquivo é write-once.** Trocá-lo numa revisão existente contradiz o
        # desenho central do módulo — "revisão nova é linha nova, nunca UPDATE"
        # (planta §9) — e deixaria hash, formato e tamanho descrevendo o arquivo
        # anterior, que é o que o pipeline do PRA.1 lê para decidir se reconverte.
        # O canteiro que já abriu a R01 continuaria vendo "R01" com outro desenho
        # dentro. Recusar aqui é mais barato que recalcular metadado e mais
        # honesto que aceitar em silêncio.
        if self.instance is not None and arquivo is not None:
            raise serializers.ValidationError({
                "arquivo": (
                    "O arquivo de uma revisão não pode ser trocado. Registre uma revisão nova."
                )
            })

        # PATCH sem re-upload não revalida nada: o arquivo é o que já está lá.
        if arquivo is None:
            return attrs
        request = self.context.get("request")
        usuario = getattr(request, "user", None)
        # **A porta é do `funcoesimpexp`, e é a única** (PRA.5a). O que existia
        # aqui era `uploads.validar_arquivo`, que decidia o formato pela extensão
        # do nome — o [D75](../../docs/historico-correcoes.md). Agora quem decide são os
        # bytes, e a mesma função admite o arquivo do diário, do RH e do lote
        # histórico: uma allowlist, uma detecção, um lugar por onde o antivírus
        # entra quando entrar.
        #
        # Grava direto, sem conferência, e é a régua do §7.3 da planta do motor:
        # confere-se o que a PLATAFORMA adivinhou. No lote adivinhamos obra e
        # disciplina do caminho da pasta; aqui a pessoa escolheu o documento e
        # digitou a revisão, e não há palpite nosso a confirmar.
        # **A porta levanta exceção comum, e quem chama traduz** — é o contrato
        # escrito no `admitir`, e ele existe porque a mesma porta roda fora de
        # HTTP (o lote, no worker), onde `APIException` não significa nada.
        #
        # Sem esta tradução as três recusas saíam como **500**: o gate de plano
        # virava erro do servidor em vez da parede comercial com o CTA, e foi o
        # que a suíte pegou ao rodar pela primeira vez depois da PRA.5a. A
        # tradução mudou de lugar na PRA.5b — virou [porta.py](porta.py), porque
        # passaram a existir três chamadores e três cópias dela seriam a mesma
        # forma do D75 do lado de dentro.
        self._admitido = porta.admitir(
            arquivo, recurso_id=RECURSO_ACERVO, user=usuario, campo="arquivo",
        )
        return attrs

    def create(self, validated_data):
        arquivo = validated_data["arquivo"]
        request = self.context.get("request")
        usuario = getattr(request, "user", None)
        validated_data.update({
            "nome_original": self._admitido.nome,
            "formato": self._admitido.formato,
            "tamanho_bytes": self._admitido.tamanho,
            "hash_sha256": self._admitido.hash,
            "enviado_por": usuario,
        })
        revisao = super().create(validated_data)

        # O pipeline entra AQUI e não num signal `post_save` de propósito: os
        # tiers de motor saem do plano do **usuário do request**, e um signal não
        # tem request. Passá-los por variável de contexto para o signal ler seria
        # reconstruir o request por baixo do pano — e a alternativa de o worker
        # reler o plano do banco não existe, porque o plano vem na claim do token.
        # `user` viaja junto para o porteiro da frota (D98) congelar plano e
        # add-ons de quem subiu: o despachante roda sem usuário e o worker sem
        # token, e resolvê-los depois exigiria uma consulta ao IAM por job.
        pipeline.agendar(revisao, tiers=tiers_do_plano(usuario),
                         teto_snap=teto_de_snap(usuario), user=usuario)
        return revisao


class RevisaoResumoSerializer(serializers.ModelSerializer):
    """O mínimo para a linha do acervo dizer qual desenho vale.

    Existe separado do serializer completo porque o acervo carrega a obra inteira
    de uma vez, e trazer observação, hash e derivadas de cada revisão só para
    escrever "R02, publicada em 12/07" seria pagar caro pela pergunta mais barata
    do módulo.
    """

    formato_rotulo = serializers.SerializerMethodField()
    conversao = serializers.SerializerMethodField()
    arquivo_url = serializers.SerializerMethodField()
    # As folhas desta revisão, na ordem em que se abrem. Vazio para PDF, imagem e
    # modelo 3D, que não têm folha separável — a tela lê `conversao.visualizador`
    # nesses casos, como sempre leu.
    desenhos = DesenhoProjetoSerializer(many=True, read_only=True)
    escala_valor = serializers.SerializerMethodField()
    escala_unidade = serializers.SerializerMethodField()
    escala_origem = serializers.SerializerMethodField()

    class Meta:
        model = RevisaoDocumento
        fields = [
            "revisao_id", "revisao", "formato", "formato_rotulo", "situacao",
            "tamanho_bytes", "data_emissao", "publicado_em", "arquivo_url", "conversao",
            "desenhos",
            # A escala viaja no resumo (PRA.3) porque o visualizador abre A PARTIR
            # do acervo: sem ela aqui, a régua da prancha só chegaria numa segunda
            # chamada — e a primeira medida do canteiro sairia sem unidade, ou
            # pior, o traço apareceria com o número certo só depois de piscar.
            # A procedência vem junto (PRA.3b) porque a tela precisa dizer se o
            # metro saiu do desenho ou do dedo de alguém — e é ela que decide se
            # o botão oferece "calibrar" ou "recalibrar".
            #
            # **Desde a PRA.1c estes três são a régua do PRIMEIRO desenho**, não
            # da revisão: a régua mora na folha, porque é ela que tem largura. Os
            # campos continuam aqui porque o caso de uma folha só é a esmagadora
            # maioria do acervo e responder a pergunta certa nele custa zero
            # chamada; quem abre a segunda folha lê a régua dela em `desenhos`.
            "escala_valor", "escala_unidade", "escala_origem",
        ]

    def _primeiro(self, obj):
        return next(iter(obj.desenhos.all()), None)

    def get_escala_valor(self, obj) -> float | None:
        desenho = self._primeiro(obj)
        return desenho.escala_valor if desenho else None

    def get_escala_unidade(self, obj) -> str:
        desenho = self._primeiro(obj)
        return desenho.escala_unidade if desenho else "m"

    def get_escala_origem(self, obj) -> str:
        desenho = self._primeiro(obj)
        return desenho.escala_origem if desenho else ""

    def get_formato_rotulo(self, obj) -> str:
        formato = FORMATO_POR_CODIGO.get(obj.formato)
        return formato.nome if formato else obj.formato

    def get_arquivo_url(self, obj) -> str | None:
        return entrega.url_da_revisao(obj.pk) if obj.arquivo else None

    def get_conversao(self, obj) -> dict:
        """O resumo que o card do acervo precisa, em uma chamada.

        Sem isto a tela do canteiro teria de buscar as derivadas de cada revisão
        para saber se dá para abrir — N chamadas no celular, exatamente onde a
        conexão é pior. Os cinco estados são o vocabulário da tela:

        - `pronta` — abre, e `visualizador` diz por onde;
        - `convertendo` — está acontecendo, mostre progresso;
        - `erro` — falhou, e `exige_upgrade` diz se vira botão de compra;
        - `nativa` — não há o que converter porque o browser já abre o arquivo
          (PDF/imagem antes de a miniatura ficar pronta) ou porque o dono do dado
          é outro módulo (KMZ vai para o Maps, LAS para o drone — planta §3);
        - `nao_agendada` — o motor existe e cabe no plano, mas a conversão nunca
          foi enfileirada (D81). Quem age é a plataforma, e a saída é reprocessar;
        - `sem_motor` — o formato tem motor previsto que ainda não existe aqui.

        `nativa` e `sem_motor` são estados diferentes de propósito: o primeiro é
        o produto funcionando, o segundo é uma lacuna. Fundi-los deixaria a tela
        dizendo "tudo certo" para um RVT que ninguém consegue abrir.

        **`pronta` não implica silêncio** (D46): a prancha que abre pode ainda
        assim estar ilegível, e nesse caso `aviso` carrega o quê e o porquê. Um
        sexto estado seria pior — quem abre a prancha continua abrindo, e a
        ressalva é sobre o que ele vai ver, não sobre poder ver.

        **`nativo` viaja em todos os estados** (PRA.2), e não só no `nativa`: é o
        que diz ao visualizador se os bytes são para o `<iframe>` do PDF ou para
        o desenho vetorial. Sem o campo, a tela teria de refazer a tabela de
        famílias do `formatos.py` em TypeScript — a mesma duplicação que
        `exige_upgrade` existe para evitar.
        """
        formato = FORMATO_POR_CODIGO.get(obj.formato)
        nativo = formato is not None and formato.familia == FAMILIA_DOCUMENTO
        original = entrega.url_da_revisao(obj.pk) if obj.arquivo else None

        derivadas = list(obj.derivadas.all())
        prontas = [d for d in derivadas if d.estado == DerivadaProjeto.Estado.PRONTO]
        if prontas:
            # Preferência de leitura: o 3D é o mais informativo, o vetor vem
            # depois, e a miniatura é o último recurso — ela identifica a prancha,
            # não substitui abri-la. Por isso PDF, cuja única derivada É a
            # miniatura, continua sendo aberto pelo arquivo original.
            ordem = {"modelo_3d": 0, "vetor_2d": 1, "miniatura": 2}
            melhor = sorted(prontas, key=lambda d: ordem.get(d.tipo, 9))[0]
            alvo = original if nativo else (
                entrega.url_da_derivada(melhor.pk, entrega.versao_da_derivada(melhor))
                if melhor.arquivo else None
            )
            return {
                "estado": "pronta", "tipo": melhor.tipo, "visualizador": alvo,
                "miniatura": next(
                    (entrega.url_da_derivada(d.pk, entrega.versao_da_derivada(d))
                     for d in prontas if d.tipo == "miniatura" and d.arquivo),
                    None,
                ),
                # `pronta` com ressalva: a prancha abre, e mesmo assim a tela tem
                # o que dizer — quantas folhas o arquivo trouxe, e se ele está em
                # coordenada de mundo. Viaja no resumo do acervo porque o
                # visualizador entra por aqui.
                "aviso": aviso_da_revisao(list(obj.desenhos.all()), melhor.memoria),
                "nativo": nativo, "exige_upgrade": False, "problema_no_arquivo": False,
            }

        emandamento = [
            d for d in derivadas
            if d.estado in (DerivadaProjeto.Estado.PENDENTE, DerivadaProjeto.Estado.LENDO,
                            DerivadaProjeto.Estado.CONVERTENDO,
                            DerivadaProjeto.Estado.RETOMANDO)
        ]
        if emandamento:
            # PDF em conversão ainda abre: o que está sendo gerado é a miniatura,
            # não o meio de leitura. Esconder o arquivo aqui tiraria do canteiro,
            # por alguns segundos, justamente o formato que nunca dependeu de nós.
            return {"estado": "convertendo", "tipo": emandamento[0].tipo,
                    "visualizador": original if nativo else None,
                    "nativo": nativo, "exige_upgrade": False, "problema_no_arquivo": False,
                    # **O que a espera é** (D98/PRA.11). "Convertendo" por meia
                    # hora sem mais nada é indistinguível de travado — e era
                    # exatamente essa a queixa que abriu a fila. Aqui vai a
                    # posição, o andamento em folhas e se o administrador pode
                    # subir este arquivo na fila da própria empresa.
                    "fila": _fila_da_conversao(emandamento[0])}

        comerro = [d for d in derivadas if d.estado == DerivadaProjeto.Estado.ERRO]
        if comerro:
            # **Qual falha a revisão reporta, quando há mais de uma.** Desde a
            # PRA.1b um DWG rende duas linhas — a prancha e a miniatura embutida
            # —, e elas falham por motivos independentes. Pegar a primeira era
            # pegar a de menor `tipo` em ordem alfabética, ou seja `miniatura`:
            # um arquivo que exige o motor premium passaria a anunciar "não traz
            # miniatura embutida", e o botão de compra sumiria da tela.
            #
            # A ordem é por **quanto a falha diz**: a comercial primeiro, depois a
            # acionável por quem enviou, depois as nossas, e por último as que não
            # pedem ação de ninguém.
            def peso(d):
                if d.erro_motivo == DerivadaProjeto.MotivoErro.MOTOR_INSUFICIENTE:
                    return 0
                if d.erro_motivo == DerivadaProjeto.MotivoErro.REFERENCIA_AUSENTE:
                    return 1
                return 3 if d.erro_motivo in DerivadaProjeto.MOTIVOS_DO_ARQUIVO else 2

            falha = sorted(comerro, key=peso)[0]
            return {
                "estado": "erro", "tipo": falha.tipo,
                "visualizador": original if nativo else None,
                "motivo": falha.erro_motivo, "detalhe": falha.erro_detalhe,
                "nativo": nativo,
                "exige_upgrade": (
                    falha.erro_motivo == DerivadaProjeto.MotivoErro.MOTOR_INSUFICIENTE
                ),
                # Nem compra nem conserto: o arquivo é que não tem o que mostrar.
                # Campo próprio pela mesma razão de `exige_upgrade` — a tela não
                # pode refazer esta classificação sobre a string do motivo.
                "problema_no_arquivo": falha.erro_motivo in DerivadaProjeto.MOTIVOS_DO_ARQUIVO,
            }

        # Sem derivada nenhuma: `planejar()` não achou motor com adaptador para
        # este plano. Duas causas bem diferentes, e fundi-las faria a tela dizer
        # "tudo certo" para um RVT que ninguém abre.
        if nativo:
            return {"estado": "nativa", "visualizador": original,
                    "nativo": True, "exige_upgrade": False, "problema_no_arquivo": False}
        if formato is not None and formato.dono != "prancheta":
            return {"estado": "outro_modulo", "dono": formato.dono,
                    "visualizador": None, "nativo": False, "exige_upgrade": False,
                    "problema_no_arquivo": False}

        # **`sem_motor` não se deduz da ausência de linha** (D81). O `agendar()`
        # cria a `DerivadaProjeto` de forma síncrona, antes de enfileirar: se
        # `planejar()` tivesse achado motor, a linha existiria — nem que fosse
        # `pendente`. Zero linhas com motor planejado significa, então, o oposto
        # do que esta resposta dizia: o motor existe e **ninguém agendou** —
        # revisão gravada direto no banco, carga que não passou pelo pipeline, ou
        # o `on_commit` que se perdeu. Dizer "não há motor" ali é a tela mentindo
        # sobre a causa, e mandando o dono comprar plano por um job que não rodou.
        if pipeline.planejar(obj.formato, self._tiers()):
            return {"estado": "nao_agendada", "visualizador": None,
                    "nativo": False, "exige_upgrade": False, "problema_no_arquivo": False}

        return {"estado": "sem_motor", "visualizador": None,
                "nativo": False, "exige_upgrade": False, "problema_no_arquivo": False}

    def _tiers(self):
        """Os tiers de motor do plano de quem está lendo.

        Sem `request` no contexto sobra o `TIERS_PADRAO` (só o livre), que é o
        conservador certo aqui: ele erra no sentido de **não** prometer motor.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return tiers_do_plano(user) if user else list(pipeline.TIERS_PADRAO)


class DisciplinaProjetoSerializer(TenantScopedModelSerializer):
    """A disciplina que o cliente cria. `codigo` nasce do nome quando não vem.

    Deixar o código ser digitado seria pedir que a pessoa entenda a diferença
    entre o rótulo e o slug — e o slug importa porque é ele que o documento
    guarda. Sai do nome por `slugify`, e a unicidade por tenant é do banco.
    """

    class Meta:
        model = DisciplinaProjeto
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em"]

    def to_internal_value(self, data):
        """Deriva o `codigo` do nome **antes** da validação de campo.

        Tem de ser aqui e não no `validate`: a `UniqueConstraint(tenant, codigo)`
        faz o DRF montar um `UniqueTogetherValidator`, e ele torna `codigo`
        obrigatório passando por cima de qualquer `extra_kwargs` — a requisição
        morria com "este campo é obrigatório" antes de o `validate` rodar. O
        `to_internal_value` roda antes de tudo isso, que é onde um valor
        *derivado* pertence.
        """
        if not data.get("codigo") and data.get("nome"):
            # `QueryDict` do multipart é imutável; copiar é mais barato que
            # descobrir isso em produção.
            data = data.copy()
            data["codigo"] = slugify(data["nome"])[:40]
        return super().to_internal_value(data)

    def validate_codigo(self, valor):
        if not valor:
            raise serializers.ValidationError(
                "Dê um nome à disciplina."
            )
        return valor

    def validate_cor(self, valor):
        # Só hex, e a razão é a de sempre: o valor vai para dentro de um `style`
        # no cliente. Aceitar texto livre aqui poria conteúdo do usuário num
        # atributo CSS — pequeno, mas é injeção do mesmo jeito.
        if valor and not re.fullmatch(r"#[0-9A-Fa-f]{6}", valor):
            raise serializers.ValidationError("Use hex no formato #RRGGBB.")
        return valor


class DocumentoProjetoSerializer(TenantScopedModelSerializer):
    disciplina_rotulo = serializers.SerializerMethodField()
    disciplina_cor = serializers.SerializerMethodField()
    # A lista inteira, resolvida (código + nome + cor), a **principal primeiro**.
    # A tela desenha os pontos coloridos do cartão a partir daqui sem precisar
    # cruzar com o catálogo — o que a faria errar a cor de uma disciplina que
    # alguém apagou no meio da sessão.
    disciplinas = serializers.SerializerMethodField()
    # A entrada: uma lista de códigos, principal primeiro. `write_only` porque a
    # saída é a resolvida acima — devolver o mesmo dado em dois formatos com o
    # mesmo nome é como as duas versões divergem.
    codigos_disciplina = serializers.ListField(
        child=serializers.CharField(max_length=40), write_only=True, required=False,
    )
    obra_nome = serializers.CharField(source="obra.nome_obra", read_only=True)
    etapa_nome = serializers.CharField(source="etapa.nome_etapa", read_only=True)
    vigente = serializers.SerializerMethodField()
    pendente = serializers.SerializerMethodField()
    total_revisoes = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoProjeto
        fields = "__all__"
        read_only_fields = ["tenant", "criado_em", "atualizado_em"]

    @property
    def _disciplinas(self) -> dict:
        """O índice do catálogo, **montado uma vez por resposta**.

        Vem do `context` quando quem chama o pôs lá (o acervo e o ViewSet põem),
        e só cai numa consulta própria quando alguém serializa um documento
        solto. Sem este cache o acervo de 141 pranchas faria 141 leituras da
        mesma tabela — o N+1 pela porta do rótulo.
        """
        cacheado = self.context.get("indice_disciplinas")
        if cacheado is not None:
            return cacheado
        request = self.context.get("request")
        user = getattr(request, "user", None)
        indice = disciplinas.indice(
            lambda qs: scope_queryset_by_tenant(qs, user)
        ) if user else {}
        self.context["indice_disciplinas"] = indice
        return indice

    def get_disciplina_rotulo(self, obj) -> str:
        return disciplinas.rotulo(obj.disciplina, self._disciplinas)

    def get_disciplina_cor(self, obj) -> str:
        return disciplinas.cor(obj.disciplina, self._disciplinas)

    def get_disciplinas(self, obj) -> list[dict]:
        mapa = self._disciplinas
        return [
            {
                "codigo": codigo,
                "nome": disciplinas.rotulo(codigo, mapa),
                "cor": disciplinas.cor(codigo, mapa),
            }
            for codigo in obj.codigos_de_disciplina
        ]

    def create(self, validated_data):
        codigos = validated_data.pop("codigos_disciplina", None)
        documento = super().create(validated_data)
        if codigos:
            documento.definir_disciplinas(codigos)
        return documento

    def update(self, instance, validated_data):
        # `pop` antes do super: `codigos_disciplina` não é campo do modelo, e o
        # `ModelSerializer` levantaria ao tentar atribuí-lo.
        codigos = validated_data.pop("codigos_disciplina", None)
        documento = super().update(instance, validated_data)
        if codigos is not None:
            documento.definir_disciplinas(codigos)
        return documento

    def get_vigente(self, obj):
        """`None` quando o documento ainda não tem revisão publicada.

        É estado legítimo, não erro: acervo carregado em lote nasce em rascunho,
        e é exatamente essa lista que alimenta a fila de decisão do cockpit
        (planta §11). Devolver um objeto vazio aqui esconderia a pendência.
        """
        vigente = obj.revisao_vigente
        # O `context` viaja: sem ele o resumo não alcança o `request`, e o
        # `get_conversao` perde o plano de quem lê — que é o que separa "não
        # existe motor" de "existe, mas ninguém enfileirou" (D81).
        return (
            RevisaoResumoSerializer(vigente, context=self.context).data
            if vigente else None
        )

    def get_pendente(self, obj):
        """O rascunho mais recente, quando o documento **não** tem vigente.

        É o que torna o cartão do canteiro capaz de resolver o próprio problema:
        sem este id, "sem revisão vigente" era um diagnóstico que só se
        respondia em outra aba, uma prancha por vez. `None` quando há vigente —
        trocar o desenho que o campo executa não é ação de cartão, é decisão com
        motivo (a mesma fronteira que o `publicar-pendentes` respeita).

        Sai do prefetch do acervo (`revisoes__derivadas`) e não de uma consulta
        própria: uma query por cartão traria de volta o N+1 que o
        `revisao_vigente` fechou.
        """
        if obj.revisao_vigente is not None:
            return None
        rascunhos = [
            r for r in obj.revisoes.all()
            if r.situacao == RevisaoDocumento.Situacao.RASCUNHO
        ]
        if not rascunhos:
            return None
        # Mesmo critério do verbo em lote — "mais recente" é o rótulo do carimbo,
        # com a data como desempate. Divergir daqui faria o cartão publicar uma
        # revisão diferente da que o botão da fila publicaria.
        recente = max(rascunhos, key=lambda r: (r.revisao, r.enviado_em))
        return RevisaoResumoSerializer(recente, context=self.context).data

    def get_total_revisoes(self, obj) -> int:
        # `len(...all())` e não `.count()`: aproveita o prefetch do acervo pela
        # mesma razão do `revisao_vigente`.
        return len(obj.revisoes.all())


# ===========================================================================
# PRA.3 — marcar e medir
# ===========================================================================
class PontoDeVistaSerializer(serializers.ModelSerializer):
    """O ponto de vista e sua imagem — a imagem por URL gateada, como todo o resto.

    O snapshot é foto de um trecho da prancha do cliente. Servi-lo por `/media/`
    o deixaria fora de auth, entitlement e RLS, que é o **S10** que este módulo
    já recusou repetir na PRA.2 quando tirou o arquivo da revisão de lá.
    """

    snapshot_url = serializers.SerializerMethodField()

    class Meta:
        model = PontoDeVista
        fields = ["ponto_de_vista_id", "guid", "camera", "snapshot_url", "criado_em"]
        read_only_fields = fields

    def get_snapshot_url(self, obj) -> str | None:
        return entrega.url_do_snapshot(obj.pk) if obj.snapshot else None


class ComentarioMarcacaoSerializer(TenantScopedModelSerializer):
    """Resposta na conversa do tópico.

    `autor_nome` sai preenchido em qualquer caso — com o `username` de quem tem
    login e com o nome que veio do BCF para quem não tem. Uma tela que mostrasse
    o autor em branco para o comentário do projetista externo faria a conversa
    parecer anônima justamente do lado de fora, que é o lado que a fatia existe
    para alcançar.
    """

    autor_nome = serializers.SerializerMethodField()

    class Meta:
        model = ComentarioMarcacao
        fields = [
            "comentario_id", "guid", "marcacao", "texto",
            "autor", "autor_nome", "ponto_de_vista", "criado_em",
        ]
        read_only_fields = [
            "tenant", "guid", "autor", "autor_nome", "criado_em", "ponto_de_vista",
        ]

    def get_autor_nome(self, obj) -> str:
        return obj.autor.username if obj.autor_id else (obj.autor_nome or "—")


# Tolerância do polígono/linha: coordenadas são normalizadas pela LARGURA, então
# x fica em [0,1] e y em [0, altura/largura]. O teto de 10 é folga generosa para
# uma folha muito alta e ainda barra o valor absurdo que viraria área infinita.
_LIMITE_COORDENADA = 10.0


def _validar_pontos(pontos, *, minimo: int) -> list[dict]:
    """Vértices vindos do cliente: quantidade, tipo e faixa.

    A validação existe porque `pontos` é `JSONField` — sem ela, um payload com
    string no lugar de número explodiria no cálculo como 500, e um com 50 mil
    vértices viraria uma linha de banco que nenhuma tela consegue desenhar.
    """
    if not isinstance(pontos, list) or len(pontos) < minimo:
        raise serializers.ValidationError({
            "pontos": f"Informe ao menos {minimo} vértice(s)."
        })
    if len(pontos) > 500:
        raise serializers.ValidationError({"pontos": "Máximo de 500 vértices por medição."})

    limpos = []
    for ponto in pontos:
        if not isinstance(ponto, dict):
            raise serializers.ValidationError({"pontos": "Cada vértice é um objeto {x, y}."})
        try:
            x, y = float(ponto["x"]), float(ponto["y"])
        except (KeyError, TypeError, ValueError) as erro:
            raise serializers.ValidationError({
                "pontos": "Cada vértice precisa de `x` e `y` numéricos."
            }) from erro
        if not (math.isfinite(x) and math.isfinite(y)):
            raise serializers.ValidationError({"pontos": "Coordenada inválida (infinita ou NaN)."})
        if abs(x) > _LIMITE_COORDENADA or abs(y) > _LIMITE_COORDENADA:
            raise serializers.ValidationError({
                "pontos": "Coordenada fora da folha."
            })
        limpos.append({"x": x, "y": y})
    return limpos


def medir(pontos: list[dict], *, tipo: str, escala: float | None) -> tuple[float, str]:
    """Converte os vértices em valor + unidade.

    **O cálculo é do servidor, não da tela.** A tela desenha e mostra um valor
    enquanto o dedo se move, mas quem grava é este código — senão o medido e o
    gravado divergiriam, que é exatamente o defeito que o **F19** encontrou no
    plano de pagamento (a regra vivia na tela e o motor calculava outra coisa).

    Sem escala, devolve o valor **normalizado** e unidade vazia: a medida existe,
    e o que não existe é o metro. É a régua de dados honestos aplicada ao caso em
    que a resposta certa é "não sei em quanto isso dá".
    """
    if tipo == Medicao.Tipo.AREA:
        # Shoelace. Fecha o polígono implicitamente (último → primeiro).
        soma = 0.0
        for i, atual in enumerate(pontos):
            seguinte = pontos[(i + 1) % len(pontos)]
            soma += atual["x"] * seguinte["y"] - seguinte["x"] * atual["y"]
        bruto = abs(soma) / 2
        # Área escala com o QUADRADO do fator linear — o erro clássico aqui é
        # multiplicar por `escala` e entregar um cômodo de 3 m².
        return (bruto * escala**2, "m²") if escala else (bruto, "")

    bruto = sum(
        math.dist((a["x"], a["y"]), (b["x"], b["y"]))
        for a, b in zip(pontos, pontos[1:])
    )
    return (bruto * escala, "m") if escala else (bruto, "")


def recalcular_medidas(desenho) -> int:
    """Reconverte as medidas desta folha para a régua nova. Devolve quantas.

    **Por que recalcular, se a decisão anterior era não mexer.** Até 15/08/2026
    recalibrar deixava a medida antiga intacta e a marcava `desatualizada`, para
    não reescrever um número que alguém pudesse ter anotado. O uso mostrou o
    inverso: ninguém recalibra por esporte — recalibra porque a régua estava
    errada, e a medida na tela junto com ela. Deixá-la ali entrega um número
    errado com aparência de conferido, que é o defeito mais caro deste módulo.

    **Os vértices é que são a verdade, e é isso que torna a conversão exata.**
    `pontos` é normalizado pela largura da folha, então não depende de régua
    nenhuma: a medida é sempre derivável, e o `valor` é cache. Recalcular não
    inventa dado — só refaz a conta que o `medir()` já fazia, com o número certo.

    O valor anterior vai para `valor_anterior`, com a régua que o produziu. É a
    diferença entre converter e apagar: quem tiver a caderneta do canteiro na mão
    consegue reencontrar de onde veio o número velho.
    """
    escala = desenho.escala_valor if desenho.escala_valor else None
    unidade_da_folha = desenho.escala_unidade or "m"
    alteradas = []

    for medicao in desenho.medicoes.all():
        if not medicao.pontos:
            continue
        valor, unidade = medir(medicao.pontos, tipo=medicao.tipo, escala=escala)
        if unidade and unidade_da_folha != "m":
            # `medir()` responde na unidade canônica; a folha pode estar em
            # outra. Sem esta linha, calibrar em centímetros gravaria "m".
            unidade = f"{unidade_da_folha}²" if medicao.tipo == Medicao.Tipo.AREA else unidade_da_folha
        if (abs((medicao.valor or 0) - valor) < 1e-12
                and medicao.unidade == unidade
                and medicao.escala_aplicada == escala):
            continue  # nada mudou para esta: não suja o histórico à toa
        medicao.valor_anterior = [
            *(medicao.valor_anterior or []),
            {
                "valor": medicao.valor,
                "unidade": medicao.unidade,
                "escala_aplicada": medicao.escala_aplicada,
                "em": timezone.now().isoformat(),
            },
        ][-10:]  # dez recalibrações bastam para reconstruir a história
        medicao.valor = valor
        medicao.unidade = unidade
        medicao.escala_aplicada = escala
        alteradas.append(medicao)

    if alteradas:
        Medicao.objects.bulk_update(
            alteradas, ["valor", "unidade", "escala_aplicada", "valor_anterior"])
    return len(alteradas)


class MedicaoSerializer(TenantScopedModelSerializer):
    """Uma medida. O cliente manda os vértices; o valor sai daqui."""

    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    criado_por_nome = serializers.CharField(source="criado_por.username", read_only=True)
    desatualizada = serializers.BooleanField(read_only=True)

    class Meta:
        model = Medicao
        fields = [
            "medicao_id", "revisao", "desenho", "marcacao", "tipo", "tipo_rotulo", "pontos",
            "valor", "unidade", "escala_aplicada", "desatualizada", "rotulo",
            "criado_por", "criado_por_nome", "criado_em",
        ]
        read_only_fields = [
            "tenant", "valor", "unidade", "escala_aplicada", "desatualizada",
            "criado_por", "criado_por_nome", "criado_em",
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        escopar_ao_tenant(fields, "revisao", request)
        escopar_ao_tenant(fields, "desenho", request)
        escopar_ao_tenant(fields, "marcacao", request)
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        tipo = attrs.get("tipo") or Medicao.Tipo.DISTANCIA
        attrs["pontos"] = _validar_pontos(
            attrs.get("pontos"), minimo=3 if tipo == Medicao.Tipo.AREA else 2
        )

        marcacao = attrs.get("marcacao")
        revisao = attrs.get("revisao")
        # Medida amarrada a marcação de OUTRA prancha descreveria um problema que
        # não está onde diz estar. O 400 nomeia o campo em vez de deixar a
        # inconsistência entrar no banco e aparecer como bug de tela depois.
        if marcacao and revisao and marcacao.revisao_id != revisao.pk:
            raise serializers.ValidationError({
                "marcacao": "A marcação pertence a outra revisão."
            })
        # Mesma classe de erro, um nível abaixo e mais caro: os vértices são
        # normalizados pela largura da FOLHA, então medir com o desenho errado
        # aplica a régua errada e devolve um número plausível. Plausível e errado
        # é o pior desfecho num campo cujo produto vira parede.
        desenho = attrs.get("desenho")
        if desenho and revisao and desenho.revisao_id != revisao.pk:
            raise serializers.ValidationError({
                "desenho": "O desenho pertence a outra revisão."
            })
        return attrs

    def create(self, validated_data):
        revisao = validated_data["revisao"]
        # A régua é a da FOLHA. Sem desenho informado cai no primeiro, que é o
        # que a revisão de uma folha só sempre foi — e é o caminho que mantém o
        # cliente antigo (que não conhece `desenho`) medindo certo.
        desenho = validated_data.get("desenho") or next(iter(revisao.desenhos.all()), None)
        escala = desenho.escala_valor if (desenho and desenho.tem_escala) else None
        valor, unidade = medir(
            validated_data["pontos"], tipo=validated_data.get("tipo", Medicao.Tipo.DISTANCIA),
            escala=escala,
        )
        if unidade and desenho and desenho.escala_unidade and desenho.escala_unidade != "m":
            # A unidade da calibração manda: quem calibrou em cm quer ler cm.
            unidade = desenho.escala_unidade + ("²" if unidade.endswith("²") else "")
        validated_data.update({
            "valor": valor,
            "unidade": unidade,
            # **Em que folha a medida foi tirada.** Resolvido aqui e não deixado
            # nulo porque é ele que sustenta `desatualizada`: sem o vínculo, uma
            # recalibração posterior não teria com que se comparar e a medida
            # velha passaria por atual — silenciosamente, que é o único jeito de
            # esse erro chegar ao canteiro.
            "desenho": desenho,
            # Carimbo, como o snapshot da linha do orçamento: recalibrar depois
            # não reescreve o que alguém já anotou e levou para o canteiro.
            "escala_aplicada": escala,
            "criado_por": getattr(self.context.get("request"), "user", None),
        })
        return super().create(validated_data)


class MarcacaoSerializer(TenantScopedModelSerializer):
    """O tópico BCF.

    `situacao` é **read-only** aqui, e isso não é descuido: mudar a situação é o
    verbo `situacao/`, com permissão própria (`prancheta.marcacao.resolver`).
    Fosse campo comum, quem pode criar marcação fecharia a própria — e a
    segregação viraria decoração, que é literalmente a armadilha do **D28** e a
    mesma razão de `RevisaoDocumento.situacao` também não ser editável.
    """

    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    situacao_rotulo = serializers.CharField(source="get_situacao_display", read_only=True)
    prioridade_rotulo = serializers.CharField(source="get_prioridade_display", read_only=True)
    aberta = serializers.BooleanField(read_only=True)

    documento = serializers.IntegerField(source="revisao.documento_id", read_only=True)
    documento_codigo = serializers.CharField(source="revisao.documento.codigo", read_only=True)
    documento_titulo = serializers.CharField(source="revisao.documento.titulo", read_only=True)
    obra = serializers.IntegerField(source="revisao.documento.obra_id", read_only=True)
    revisao_rotulo = serializers.CharField(source="revisao.revisao", read_only=True)
    # Marcação aberta sobre desenho que já não é o vigente é item da fila de
    # decisão, não lixo: alguém precisa dizer se o apontamento sobreviveu à
    # revisão nova. Vem calculado para a tela não refazer a regra.
    revisao_superada = serializers.SerializerMethodField()

    responsavel_nome = serializers.SerializerMethodField()
    criado_por_nome = serializers.SerializerMethodField()
    resolvido_por_nome = serializers.CharField(source="resolvido_por.username", read_only=True)

    comentarios = ComentarioMarcacaoSerializer(many=True, read_only=True)
    pontos_de_vista = PontoDeVistaSerializer(many=True, read_only=True)
    medicoes = MedicaoSerializer(many=True, read_only=True)

    class Meta:
        model = Marcacao
        fields = [
            "marcacao_id", "guid", "revisao", "desenho", "revisao_rotulo", "revisao_superada",
            "documento", "documento_codigo", "documento_titulo", "obra",
            "titulo", "descricao", "tipo", "tipo_rotulo",
            "situacao", "situacao_rotulo", "aberta",
            "prioridade", "prioridade_rotulo", "rotulos", "prazo",
            "responsavel", "responsavel_nome", "responsavel_email",
            "criado_por", "criado_por_nome", "autor_nome", "criado_em", "atualizado_em",
            "resolvido_por", "resolvido_por_nome", "resolvido_em",
            "origem", "ancora", "comentarios", "pontos_de_vista", "medicoes",
        ]
        read_only_fields = [
            "tenant", "guid", "situacao", "aberta", "criado_por", "criado_por_nome",
            "autor_nome", "criado_em", "atualizado_em",
            "resolvido_por", "resolvido_por_nome", "resolvido_em", "origem",
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        escopar_ao_tenant(fields, "revisao", request)
        escopar_ao_tenant(fields, "desenho", request)
        escopar_ao_tenant(fields, "responsavel", request)
        return fields

    def get_revisao_superada(self, obj) -> bool:
        return obj.revisao.situacao == RevisaoDocumento.Situacao.SUPERADA

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Pino fincado na folha errada aponta para um lugar que existe e não é o
        # lugar. Numa ferramenta cujo produto é dizer **onde**, é o defeito mais
        # caro que ela pode ter.
        desenho, revisao = attrs.get("desenho"), attrs.get("revisao")
        if desenho and revisao and desenho.revisao_id != revisao.pk:
            raise serializers.ValidationError({
                "desenho": "O desenho pertence a outra revisão."
            })
        return attrs

    def get_responsavel_nome(self, obj) -> str:
        return obj.responsavel.username if obj.responsavel_id else (obj.responsavel_email or "")

    def get_criado_por_nome(self, obj) -> str:
        return obj.criado_por.username if obj.criado_por_id else (obj.autor_nome or "—")

    def validate_ancora(self, valor):
        """Âncora vazia é legítima (marcação de modelo 3D não tem ponto na folha);
        âncora presente tem de ser um ponto de verdade."""
        if not valor:
            return {}
        return _validar_pontos([valor], minimo=1)[0]

    def create(self, validated_data):
        validated_data["criado_por"] = getattr(self.context.get("request"), "user", None)
        # Marcação sem folha declarada cai na primeira, que é o que a revisão de
        # um desenho só sempre foi — e é o que mantém o cliente que ainda não
        # conhece `desenho` fincando o pino num lugar que existe.
        if not validated_data.get("desenho") and validated_data.get("revisao"):
            validated_data["desenho"] = next(
                iter(validated_data["revisao"].desenhos.all()), None)
        return super().create(validated_data)


class CalibracaoSerializer(serializers.Serializer):
    """Entrada do verbo `calibrar/`: dois pontos na folha e quanto eles medem.

    Não é `ModelSerializer` porque o que entra (dois pontos + distância real) não
    é o que fica gravado (unidades na largura). A conversão é do servidor pela
    mesma razão da medição — a tela não pode ser a dona da régua.
    """

    a = serializers.DictField(child=serializers.FloatField())
    b = serializers.DictField(child=serializers.FloatField())
    distancia_real = serializers.FloatField(min_value=1e-6)
    unidade = serializers.CharField(max_length=4, default="m")

    def validate(self, attrs):
        pontos = _validar_pontos([attrs["a"], attrs["b"]], minimo=2)
        separacao = math.dist(
            (pontos[0]["x"], pontos[0]["y"]), (pontos[1]["x"], pontos[1]["y"])
        )
        # Dois pontos quase no mesmo lugar dariam uma escala gigantesca a partir
        # de um tremor de dedo — e toda medida da prancha herdaria o erro. 1% da
        # largura é o mínimo em que a referência ainda é uma cota, não um toque.
        if separacao < 0.01:
            raise serializers.ValidationError({
                "b": (
                    "Os dois pontos estão muito próximos. Trace sobre uma cota conhecida, de ponta "
                    "a ponta."
                )
            })
        attrs["pontos"] = pontos
        attrs["escala_valor"] = attrs["distancia_real"] / separacao
        return attrs
