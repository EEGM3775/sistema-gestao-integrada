# backend/modulomaps/models.py
"""Maps — a dimensão espacial da plataforma.

**Duas metades**, e a divisão não é estética (docs/modulos/modulomaps.md §1):

- `Local` é **fundação sem entitlement**. Georreferenciar obra, empreendimento,
  fornecedor ou almoxarifado é atributo de cadastro, no mesmo nível de "quanto
  custa" — SAP põe geo no *Business Partner Address*, Oracle no `HZ_LOCATIONS`,
  ninguém vende isso à parte. Se ficasse atrás do módulo, quem não assina Maps
  teria SIL e SCM sem saber onde as coisas ficam.
- **Camadas** (`Camada`/`Feicao`, `Ortofoto`, `PlanoVoo`, `Rota`, `Geofence`)
  ficam atrás do entitlement `maps`: cada uma tem custo próprio (storage raster,
  motor de rota, geocodificação fina).

Armazenamento único em **SRID 4326** (WGS84) — é o que GPS, KML e GeoJSON falam.
Métrica (distância, área) sai de reprojeção sob demanda; guardar em UTM por zona
quebraria toda obra perto de divisa de fuso.
"""
from django.contrib.gis.db import models as gis
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel


class Precisao(models.TextChoices):
    """Quão perto do lugar real o ponto está. **Nunca é invisível** — é a mesma
    exigência de dado honesto que fez o Orçamento declarar `cobertura_pct`. Um
    pin de centroide de município e um pin arrastado à mão não podem parecer a
    mesma coisa na tela: o segundo é a porta, o primeiro é "algum lugar naquela
    cidade", e um mapa que os desenha igual mente."""

    EXATA = "exata", _("Exata (pin ou EXIF)")
    ENDERECO = "endereco", _("Endereço geocodificado")
    CEP = "cep", _("Centroide de CEP")
    MUNICIPIO = "municipio", _("Centroide de município")
    DESCONHECIDA = "desconhecida", _("Sem coordenada")


class FonteGeo(models.TextChoices):
    """De onde a coordenada veio. Procedência anda junto da precisão: as duas
    respondem "por que devo acreditar neste ponto?"."""

    MANUAL = "manual", _("Pin posicionado à mão")
    EXIF = "exif", _("EXIF de foto")
    GEOCODER = "geocoder", _("Geocodificador de endereço")
    CEP = "cep", _("Base de CEP")
    IBGE = "ibge", _("Malha municipal do IBGE")
    IMPORTACAO = "importacao", _("Importação conferida")
    NFE = "nfe", _("Endereço do XML da NF-e")


# ---------------------------------------------------------------------------
# 1. FUNDAÇÃO — sem entitlement
# ---------------------------------------------------------------------------
class Local(TenantScopedModel):
    """Onde uma entidade fica.

    O vínculo é **polimórfico por FKs nuláveis + discriminador `tipo`**, e não
    `GenericForeignKey`: preserva integridade referencial, permite
    `select_related` e é o padrão que a casa já usa em `moduloscm.CentroCusto` e
    `modulosil.LocalEstoque`.
    """

    class Tipo(models.TextChoices):
        OBRA = "obra", _("Obra")
        EMPREENDIMENTO = "empreendimento", _("Empreendimento")
        FORNECEDOR = "fornecedor", _("Fornecedor")
        LOCAL_ESTOQUE = "local_estoque", _("Local de estoque")
        UNIDADE = "unidade", _("Unidade imobiliária")
        AVULSO = "avulso", _("Ponto avulso")

    local_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=180, verbose_name=_("Nome"))
    tipo = models.CharField(max_length=16, choices=Tipo.choices, default=Tipo.AVULSO, verbose_name=_("Tipo de vínculo"))

    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.CASCADE, related_name="locais", verbose_name=_("Obra"))
    empreendimento = models.ForeignKey("empreendimentos.Empreendimento", null=True, blank=True, on_delete=models.CASCADE, related_name="locais", verbose_name=_("Empreendimento"))
    fornecedor = models.ForeignKey("fornecedores.Fornecedor", null=True, blank=True, on_delete=models.CASCADE, related_name="locais", verbose_name=_("Fornecedor"))
    local_estoque = models.ForeignKey("modulosil.LocalEstoque", null=True, blank=True, on_delete=models.CASCADE, related_name="locais", verbose_name=_("Local de estoque"))
    unidade = models.ForeignKey("empreendimentos.Unidade", null=True, blank=True, on_delete=models.CASCADE, related_name="locais", verbose_name=_("Unidade"))

    # `ponto` é nulável de propósito: o Local pode nascer do endereço em texto e
    # ficar sem coordenada até a cascata rodar. `precisao=desconhecida` é um
    # estado legítimo — e é o que alimenta a fila de decisão "obras sem
    # coordenada". Zerar em 0,0 (golfo da Guiné) seria fabricar dado.
    ponto = gis.PointField(srid=4326, null=True, blank=True, spatial_index=True, verbose_name=_("Ponto"))
    area = gis.PolygonField(srid=4326, null=True, blank=True, spatial_index=True, verbose_name=_("Perímetro (canteiro/terreno)"))

    cep = models.CharField(max_length=9, blank=True, verbose_name=_("CEP"))
    logradouro = models.CharField(max_length=255, blank=True, verbose_name=_("Logradouro"))
    numero = models.CharField(max_length=20, blank=True, verbose_name=_("Número"))
    complemento = models.CharField(max_length=120, blank=True, verbose_name=_("Complemento"))
    bairro = models.CharField(max_length=120, blank=True, verbose_name=_("Bairro"))
    cidade = models.CharField(max_length=120, blank=True, verbose_name=_("Cidade"))
    uf = models.CharField(max_length=2, blank=True, verbose_name=_("UF"))
    ibge = models.CharField(max_length=7, blank=True, verbose_name=_("Código IBGE do município"))

    precisao = models.CharField(max_length=14, choices=Precisao.choices, default=Precisao.DESCONHECIDA, verbose_name=_("Precisão"))
    fonte = models.CharField(max_length=12, choices=FonteGeo.choices, blank=True, verbose_name=_("Procedência"))
    geocodificado_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Geocodificado em"))

    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Local")
        verbose_name_plural = _("Locais")
        ordering = ["nome"]
        constraints = [
            # Um local por entidade vinculada: a obra tem UM endereço, não uma
            # coleção. Parciais porque a maioria das FKs é nula em cada linha.
            models.UniqueConstraint(fields=["tenant", "obra"], condition=Q(obra__isnull=False), name="maps_local_obra_unico"),
            models.UniqueConstraint(fields=["tenant", "empreendimento"], condition=Q(empreendimento__isnull=False), name="maps_local_empreend_unico"),
            models.UniqueConstraint(fields=["tenant", "fornecedor"], condition=Q(fornecedor__isnull=False), name="maps_local_fornecedor_unico"),
            models.UniqueConstraint(fields=["tenant", "local_estoque"], condition=Q(local_estoque__isnull=False), name="maps_local_estoque_unico"),
            models.UniqueConstraint(fields=["tenant", "unidade"], condition=Q(unidade__isnull=False), name="maps_local_unidade_unico"),
            # O discriminador tem de bater com a FK preenchida. Sem esta trava, um
            # `tipo="obra"` sem obra passaria e o mapa da empresa mostraria um pin
            # que não é de nada.
            models.CheckConstraint(
                name="maps_local_vinculo_coerente",
                condition=(
                    Q(tipo="obra", obra__isnull=False)
                    | Q(tipo="empreendimento", empreendimento__isnull=False)
                    | Q(tipo="fornecedor", fornecedor__isnull=False)
                    | Q(tipo="local_estoque", local_estoque__isnull=False)
                    | Q(tipo="unidade", unidade__isnull=False)
                    | Q(tipo="avulso")
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "tipo"], name="maps_local_tenant_tipo_idx"),
            # A fila de decisão "sem coordenada" é uma varredura por este campo.
            models.Index(fields=["tenant", "precisao"], name="maps_local_precisao_idx"),
        ]

    def __str__(self):
        return self.nome

    @property
    def latitude(self):
        return self.ponto.y if self.ponto else None

    @property
    def longitude(self):
        return self.ponto.x if self.ponto else None

    def endereco_formatado(self) -> str:
        """Uma linha para geocodificar ou exibir. Monta só o que existe."""
        partes = [
            " ".join(p for p in [self.logradouro, self.numero] if p).strip(),
            self.bairro,
            " - ".join(p for p in [self.cidade, self.uf] if p),
            self.cep,
        ]
        return ", ".join(p for p in partes if p)


# ---------------------------------------------------------------------------
# 2. CAMADAS — entitlement `maps`
# ---------------------------------------------------------------------------
class Camada(TenantScopedModel):
    """Agrupa feições por assunto (progresso da obra, sondagens, interferências,
    marcos topográficos) e controla visibilidade/cor/ordem."""

    camada_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=120, verbose_name=_("Nome"))
    descricao = models.CharField(max_length=255, blank=True, verbose_name=_("Descrição"))
    cor = models.CharField(max_length=9, default="#E79A22", verbose_name=_("Cor"))
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem de desenho"))
    visivel = models.BooleanField(default=True, verbose_name=_("Visível por padrão"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.CASCADE, related_name="camadas_mapa", verbose_name=_("Obra"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Camada")
        verbose_name_plural = _("Camadas")
        ordering = ["ordem", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nome"], name="maps_camada_nome_por_tenant"),
        ]

    def __str__(self):
        return self.nome


class Feicao(TenantScopedModel):
    """Desenho do usuário sobre o mapa: ponto, linha ou polígono.

    `data_referencia` é o que permite o **antes/depois** — a mesma feição
    (mesmo `grupo`) medida em voos de datas diferentes conta a evolução da obra.
    Sem ela, sobrepor dois levantamentos daria dois pins soltos.
    """

    class Tipo(models.TextChoices):
        MARCO = "marco", _("Marco topográfico")
        SONDAGEM = "sondagem", _("Sondagem")
        INTERFERENCIA = "interferencia", _("Interferência")
        PROGRESSO = "progresso", _("Progresso de obra")
        FOTO = "foto", _("Foto georreferenciada")
        ANOTACAO = "anotacao", _("Anotação")

    feicao_id = models.AutoField(primary_key=True)
    camada = models.ForeignKey(Camada, on_delete=models.CASCADE, related_name="feicoes", verbose_name=_("Camada"))
    nome = models.CharField(max_length=180, verbose_name=_("Nome"))
    tipo = models.CharField(max_length=14, choices=Tipo.choices, default=Tipo.ANOTACAO, verbose_name=_("Tipo"))
    geom = gis.GeometryField(srid=4326, spatial_index=True, verbose_name=_("Geometria"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.CASCADE, related_name="feicoes", verbose_name=_("Obra"))
    data_referencia = models.DateField(verbose_name=_("Data de referência"))
    # Amarra as versões da mesma feição ao longo do tempo (antes/depois).
    grupo = models.CharField(max_length=64, blank=True, verbose_name=_("Grupo temporal"))
    propriedades = models.JSONField(default=dict, blank=True, verbose_name=_("Propriedades"))
    # Seams de rede (inertes) — mesmo padrão do SCM.
    ref_externa = models.CharField(max_length=64, blank=True, verbose_name=_("Referência externa"))
    origem_tenant = models.CharField(max_length=64, blank=True, verbose_name=_("Tenant de origem"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Feição")
        verbose_name_plural = _("Feições")
        ordering = ["-data_referencia", "nome"]
        indexes = [
            models.Index(fields=["tenant", "data_referencia"], name="maps_feicao_data_idx"),
            models.Index(fields=["tenant", "grupo"], name="maps_feicao_grupo_idx"),
        ]

    def __str__(self):
        return f"{self.nome} ({self.data_referencia:%d/%m/%Y})"


class Ortofoto(TenantScopedModel):
    """Índice do acervo raster do drone — **não** uma cópia dele.

    O que passa a existir com isto: a ortofoto vira camada do mapa da empresa
    sem abrir o drone. O pixel continua onde sempre esteve (NodeODM/COG); aqui
    ficam `bbox` e data, que é o que permite perguntar "o que voamos nesta área,
    e quando?".
    """

    ortofoto_id = models.AutoField(primary_key=True)
    titulo = models.CharField(max_length=180, verbose_name=_("Título"))
    # `chunk_uuid` é o identificador do task no funcoesODM; guardado como texto
    # porque o drone é outro serviço, com outro banco — FK cruzando serviço seria
    # acoplamento que a arquitetura não tem.
    chunk_uuid = models.CharField(max_length=64, blank=True, verbose_name=_("Chunk (funcoesODM)"))
    projeto_drone_id = models.CharField(max_length=64, blank=True, verbose_name=_("Projeto no drone"))
    bbox = gis.PolygonField(srid=4326, spatial_index=True, verbose_name=_("Envelope (bbox)"))
    data_voo = models.DateField(verbose_name=_("Data do voo"))
    gsd_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_("GSD (cm/px)"))
    crs_origem = models.CharField(max_length=20, blank=True, verbose_name=_("CRS de origem"))
    url_cog = models.URLField(max_length=500, blank=True, verbose_name=_("URL do COG"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.SET_NULL, related_name="ortofotos", verbose_name=_("Obra"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Ortofoto")
        verbose_name_plural = _("Ortofotos")
        ordering = ["-data_voo", "titulo"]
        indexes = [
            models.Index(fields=["tenant", "data_voo"], name="maps_orto_data_idx"),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.data_voo:%d/%m/%Y})"


class PlanoVoo(TenantScopedModel):
    """Missão de voo: área + parâmetros → rota de aquisição exportável.

    A altura NÃO é digitada solta: ela sai do **GSD alvo** com a geometria da
    câmera (`altura = gsd × focal × largura_px / largura_sensor`). Digitar altura
    e GSD como campos independentes é o erro clássico — o voo sai com resolução
    diferente da prometida e ninguém percebe até o processamento.
    """

    class Tipo(models.TextChoices):
        GRID = "grid", _("Grid (linhas paralelas)")
        DUPLO_GRID = "duplo_grid", _("Duplo grid (cruzado)")
        PERIMETRO = "perimetro", _("Perímetro")
        ORBITAL = "orbital", _("Orbital / POI")
        CORREDOR = "corredor", _("Corredor")

    plano_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=180, verbose_name=_("Nome"))
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.GRID, verbose_name=_("Tipo"))
    area = gis.PolygonField(srid=4326, spatial_index=True, verbose_name=_("Área de voo"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.SET_NULL, related_name="planos_voo", verbose_name=_("Obra"))

    gsd_alvo_cm = models.DecimalField(max_digits=5, decimal_places=2, default=2, verbose_name=_("GSD alvo (cm/px)"))
    altura_m = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True, verbose_name=_("Altura calculada (m)"))
    sobreposicao_frontal_pct = models.PositiveIntegerField(
        default=75, validators=[MinValueValidator(20), MaxValueValidator(95)], verbose_name=_("Sobreposição frontal (%)")
    )
    sobreposicao_lateral_pct = models.PositiveIntegerField(
        default=65, validators=[MinValueValidator(20), MaxValueValidator(95)], verbose_name=_("Sobreposição lateral (%)")
    )
    velocidade_ms = models.DecimalField(max_digits=4, decimal_places=1, default=8, verbose_name=_("Velocidade (m/s)"))
    angulo_graus = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(179)], verbose_name=_("Ângulo das linhas (°)"))

    # Geometria da câmera — sem ela o GSD é chute. Defaults de uma câmera 1"
    # (classe Phantom 4 Pro / Mavic 3), a mais comum em obra no Brasil.
    camera_nome = models.CharField(max_length=80, default="Genérica 1\" (13.2 mm)", verbose_name=_("Câmera"))
    sensor_largura_mm = models.DecimalField(max_digits=6, decimal_places=2, default=13.2, verbose_name=_("Largura do sensor (mm)"))
    distancia_focal_mm = models.DecimalField(max_digits=6, decimal_places=2, default=8.8, verbose_name=_("Distância focal (mm)"))
    imagem_largura_px = models.PositiveIntegerField(default=5472, verbose_name=_("Largura da imagem (px)"))
    imagem_altura_px = models.PositiveIntegerField(default=3648, verbose_name=_("Altura da imagem (px)"))

    # Resultado do cálculo (MAP.4) — inerte até `calcular/` rodar.
    linha = gis.LineStringField(srid=4326, null=True, blank=True, verbose_name=_("Rota de voo"))
    waypoints = models.JSONField(default=list, blank=True, verbose_name=_("Waypoints"))
    distancia_m = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True, verbose_name=_("Distância (m)"))
    duracao_min = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True, verbose_name=_("Duração estimada (min)"))
    fotos_estimadas = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Fotos estimadas"))
    calculado_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Calculado em"))

    # Autorização de voo (SARPAS/DECEA) — campo de CONTROLE, não integração: o
    # órgão não expõe API, e prometer integração seria vender o que não existe.
    # O que o sistema faz é não deixar esquecer (fila de decisão da tela).
    autorizacao_protocolo = models.CharField(max_length=60, blank=True, verbose_name=_("Protocolo SARPAS/DECEA"))
    autorizacao_validade = models.DateField(null=True, blank=True, verbose_name=_("Validade da autorização"))

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Plano de voo")
        verbose_name_plural = _("Planos de voo")
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nome"], name="maps_plano_nome_por_tenant"),
        ]

    def __str__(self):
        return self.nome


class Rota(TenantScopedModel):
    """Roteirização de suprimento: da origem às paradas, na ordem que o motor
    devolveu. Hoje é **planejamento** (o que vai sair); execução com rastro do
    motorista exige app de campo — a decisão está registrada na planta §13."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        PLANEJADA = "planejada", _("Planejada")
        CONCLUIDA = "concluida", _("Concluída")
        CANCELADA = "cancelada", _("Cancelada")

    class Procedencia(models.TextChoices):
        """De onde saiu a linha. `estimada` é reta entre pontos — aparece na tela
        como estimativa, nunca como rota de rua."""

        OSRM = "osrm", _("Motor de rota (OSRM)")
        ESTIMADA = "estimada", _("Estimativa em linha reta")

    rota_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=180, verbose_name=_("Nome"))
    origem = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="rotas_origem", verbose_name=_("Origem"))
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.SET_NULL, related_name="rotas", verbose_name=_("Obra"))
    data_planejada = models.DateField(null=True, blank=True, verbose_name=_("Data planejada"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RASCUNHO, verbose_name=_("Status"))

    linha = gis.LineStringField(srid=4326, null=True, blank=True, verbose_name=_("Traçado"))
    distancia_m = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True, verbose_name=_("Distância (m)"))
    duracao_s = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Duração estimada (s)"))
    procedencia = models.CharField(max_length=10, choices=Procedencia.choices, blank=True, verbose_name=_("Procedência do traçado"))
    otimizada_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Otimizada em"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Rota")
        verbose_name_plural = _("Rotas")
        ordering = ["-criado_em"]

    def __str__(self):
        return self.nome


class ParadaRota(TenantScopedModel):
    """Parada de uma rota, na ordem de visita. `ordem` é reescrita pelo
    `otimizar/`; a janela de horário é restrição de entrega (canteiro que só
    recebe pela manhã), não decoração."""

    parada_id = models.AutoField(primary_key=True)
    rota = models.ForeignKey(Rota, on_delete=models.CASCADE, related_name="paradas", verbose_name=_("Rota"))
    local = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="paradas", verbose_name=_("Local"))
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))
    janela_inicio = models.TimeField(null=True, blank=True, verbose_name=_("Janela — início"))
    janela_fim = models.TimeField(null=True, blank=True, verbose_name=_("Janela — fim"))
    carga_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name=_("Carga (kg)"))
    chegada_estimada_s = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Chegada estimada (s da partida)"))
    observacao = models.CharField(max_length=255, blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Parada de rota")
        verbose_name_plural = _("Paradas de rota")
        ordering = ["rota", "ordem"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "rota", "local"], name="maps_parada_local_unico_na_rota"),
        ]

    def __str__(self):
        return f"{self.ordem}. {self.local_id}"


class Geofence(TenantScopedModel):
    """Cerca do canteiro. Nasce do `Local.area` (ou de um raio em torno do
    ponto) e é o gancho de ponto por geolocalização e de foto georreferenciada
    do diário — os dois consumidores são de OUTROS módulos, por isso a cerca
    mora aqui e não no RH."""

    class Tipo(models.TextChoices):
        CANTEIRO = "canteiro", _("Canteiro de obra")
        DEPOSITO = "deposito", _("Depósito / almoxarifado")
        RESTRITA = "restrita", _("Área restrita")

    geofence_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=180, verbose_name=_("Nome"))
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.CANTEIRO, verbose_name=_("Tipo"))
    local = models.ForeignKey(Local, on_delete=models.CASCADE, related_name="geofences", verbose_name=_("Local"))
    area = gis.PolygonField(srid=4326, spatial_index=True, verbose_name=_("Área"))
    # Guardado quando a cerca foi gerada por raio: é a explicação do desenho.
    raio_m = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Raio de origem (m)"))
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Geofence")
        verbose_name_plural = _("Geofences")
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nome"], name="maps_geofence_nome_por_tenant"),
        ]

    def __str__(self):
        return self.nome
