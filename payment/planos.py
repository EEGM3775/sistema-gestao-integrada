"""Planos, quotas e parâmetros de limite — os VALORES comerciais do produto.

Mexer aqui é decisão de negócio, não de engenharia: ver `payment/README.md`.
As regras que consomem estes números estão em `payment/regras.py`.

Racional de preço e posicionamento: docs/arquitetura/monetizacao.md §5.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Plano de entrada
# ---------------------------------------------------------------------------
# Todo tenant sem assinatura cai aqui — inclusive os de dev/staging. É o degrau
# de aquisição: o cliente usa de graça, esbarra nas quotas e aí quer pagar. Por
# isso `free` é restritivo em OBJETO (1 obra, 1 usuário) e generoso em
# EXPERIÊNCIA (os módulos base funcionam de verdade): quota apertada demais na
# experiência não converte, converte desinstalação.
#
# É também o default seguro: tenant provisionado com erro fica no plano MENOR,
# nunca sem limite.
PLANO_PADRAO = "free"

# ---------------------------------------------------------------------------
# 2. Parâmetros do teto de requisições por hora (D23 — camada 1)
# ---------------------------------------------------------------------------
# teto = min(RATE_BASE_HORA + seats * RATE_POR_SEAT_HORA, RATE_TETO_INFRA_HORA)
#
# RATE_POR_SEAT_HORA é o consumo de UMA pessoa em uma hora de trabalho pesado.
# Piso conhecido: ~75 req/h só com o app aberto e ninguém mexendo (o sino de
# notificações faz polling a cada 60s + o refresh silencioso do token). O resto
# é trabalho real — uma tela do ERP dispara ~10 chamadas ao abrir, então 900/h
# comporta ~80 aberturas de tela por hora, por pessoa.
RATE_POR_SEAT_HORA = 900

# Piso por empresa, independente de tamanho: mesmo o plano de 1 usuário precisa
# de folga para jobs, webhooks e a segunda aba que a pessoa deixou aberta.
RATE_BASE_HORA = 6_000

# Teto DURO, acima de qualquer plano. Não é número comercial e sim de
# capacidade: é o que a infraestrutura atual serve (~17 req/s sustentados para
# um tenant). Contrato "Sob Medida" que precise de mais exige projeto de
# capacidade — réplicas de backend e de leitura — antes de subir este número.
# Todo grande (GitHub para em 12.500/h, Stripe tem teto global) mantém um limite
# absoluto por cima da fórmula, justamente para a fórmula não virar cheque em
# branco.
RATE_TETO_INFRA_HORA = 60_000

# ---------------------------------------------------------------------------
# 3. Planos
# ---------------------------------------------------------------------------
# `seats` alimenta o teto de requisições (único enforcement ligado hoje).
# As demais quotas estão DECLARADAS E INERTES até o D24 — ver README.
#
# `None` = ilimitado / negociado por contrato.
# `preco_mensal` em reais; anual = 10× o mensal (2 meses grátis).
PLANOS: dict[str, dict] = {
    "free": {
        "nome": "Free",
        "preco_mensal": 0,
        "publico": "1 engenheiro validando o produto",
        "seats": 1,
        "empreendimentos": 1,
        "obras": 2,
        "clientes": 20,
        "fornecedores": 20,
        "armazenamento_gb": 1,
        "analises_ia_mes": 0,
        "notas_fiscais_mes": 0,
        "cobrancas_mes": 0,
        "processamentos_drone_mes": 0,
        "banco_preco_linhas": 500,
        "importacao_linhas": 500,
        # Maps (MAP.0–MAP.5) — COGS: geocodificação fina, motor de rota e
        # storage raster custam dinheiro por uso. Declaradas e INERTES, como as
        # demais da família: medem e cobram, não travam.
        "geocodificacoes_mes": 100,
        "rotas_mes": 0,
        "storage_raster_gb": 0,
        # Prancheta (PRA.0) — o formato é a unidade de venda, e o motor é o
        # degrau. Ver §5 abaixo. No `free` entra só o que a pessoa já consegue
        # abrir hoje no celular: PDF e imagem. É de propósito — o valor do
        # módulo aparece quando ela tenta subir o DWG que veio do projetista.
        "formatos_prancheta": ["pdf", "imagem"],
        "motores_prancheta": ["livre"],
        "storage_projeto_gb": 1,
        "conversoes_pagas_mes": 0,
        # Medir com snap não entra no degrau de aquisição: é o recurso que
        # transforma "olhar a prancha no celular" em "conferir a obra", e é
        # justamente ele que faz o cliente querer pagar. Ver §5.7.
        "snap_pontos": 0,
        # Import/export (§5.2). Planilha pequena: quem está validando o produto
        # sobe a lista de clientes que tem no Excel, não a base da prefeitura.
        "impexp_max_mb": 5,
        "impexp_formatos": ["csv", "xlsx"],
        "impexp_memoria_mb": 256,
        "impexp_segundos": 30,
        "impexp_exportar_apos_cancelar_dias": 90,
    },
    "essencial": {
        "nome": "Essencial",
        "preco_mensal": 149,
        "publico": "pequeno construtor",
        "seats": 3,
        "empreendimentos": 2,
        "obras": 8,
        "clientes": 100,
        "fornecedores": 100,
        "armazenamento_gb": 5,
        "analises_ia_mes": 30,
        "notas_fiscais_mes": 0,
        "cobrancas_mes": 0,
        "processamentos_drone_mes": 0,
        "banco_preco_linhas": 20_000,
        "importacao_linhas": 5_000,
        "geocodificacoes_mes": 1_000,
        "rotas_mes": 20,
        "storage_raster_gb": 2,
        # Os formatos livres e leves: DXF resolve com `ezdxf`, KMZ/GeoJSON com
        # GDAL. Custo marginal quase zero e já cobrem o construtor pequeno, que
        # recebe DXF do projetista e KMZ do topógrafo.
        "formatos_prancheta": ["pdf", "imagem", "dxf", "kmz", "geojson"],
        "motores_prancheta": ["livre"],
        "storage_projeto_gb": 5,
        "conversoes_pagas_mes": 0,
        # 2,3× a prancha mediana do acervo medido (65.411 pontos). O pequeno
        # construtor recebe DXF do projetista e mede a planta inteira; a de
        # fundação, que é o caso denso, esbarra — e é aí que o pacote vende.
        "snap_pontos": 150_000,
        "impexp_max_mb": 10,
        "impexp_formatos": ["csv", "xlsx"],
        "impexp_memoria_mb": 512,
        "impexp_segundos": 60,
        "impexp_exportar_apos_cancelar_dias": 90,
    },
    "profissional": {
        "nome": "Profissional",
        "preco_mensal": 449,
        "publico": "sweet spot de margem (financeiro + CRM)",
        "seats": 12,
        "empreendimentos": 10,
        "obras": 40,
        "clientes": 1_000,
        "fornecedores": 1_000,
        "armazenamento_gb": 100,
        "analises_ia_mes": 300,
        "notas_fiscais_mes": 100,
        "cobrancas_mes": 200,
        "processamentos_drone_mes": 0,  # add-on
        "banco_preco_linhas": 150_000,
        "importacao_linhas": 40_000,
        "geocodificacoes_mes": 10_000,
        "rotas_mes": 200,
        "storage_raster_gb": 25,
        # O pacote livre COMPLETO: entra o DWG (motor LibreDWG) e o IFC
        # (IfcOpenShell), que é o que a maioria das construtoras realmente
        # recebe. Continua sem APS — DWG abre aqui com fidelidade de motor
        # livre, e é essa diferença que o degrau seguinte vende (planta §4.1).
        "formatos_prancheta": [
            "pdf", "imagem", "dxf", "dwg", "ifc", "bcf",
            "kmz", "geojson", "shp", "gpkg", "qgis", "geotiff",
        ],
        "motores_prancheta": ["livre"],
        "storage_projeto_gb": 50,
        "conversoes_pagas_mes": 0,
        # Cobre a cauda inteira do acervo medido (472.410 pontos, a maior folha
        # de 175 desenhos) com folga. Quem chega aqui não deveria descobrir o
        # teto operando — só a prancha excepcional o encontra.
        "snap_pontos": 600_000,
        # O PDF de tabela entra aqui, e é degrau de CUSTO, não de valor: extrair
        # tabela de PDF é o caminho mais caro e mais frágil do motor (§6 da
        # planta do impexp). Quem sobe a publicação da prefeitura em PDF está
        # operando, não experimentando.
        "impexp_max_mb": 25,
        "impexp_formatos": ["csv", "xlsx", "pdf"],
        "impexp_memoria_mb": 1_024,
        "impexp_segundos": 120,
        "impexp_exportar_apos_cancelar_dias": 90,
    },
    "empresarial": {
        "nome": "Empresarial",
        "preco_mensal": 1_199,
        "publico": "captura o drone (alto valor, alto COGS)",
        "seats": 40,
        "empreendimentos": 50,
        "obras": 200,
        "clientes": 10_000,
        "fornecedores": 10_000,
        "armazenamento_gb": 500,
        "analises_ia_mes": 1_500,
        "notas_fiscais_mes": 500,
        "cobrancas_mes": 1_000,
        "processamentos_drone_mes": 25,
        "banco_preco_linhas": 600_000,
        "importacao_linhas": 120_000,
        "geocodificacoes_mes": 50_000,
        "rotas_mes": 1_000,
        "storage_raster_gb": 150,
        # Tudo, porque é aqui que entra o motor premium (APS). RVT e DGN **só**
        # existem neste degrau: nenhum motor livre os traduz, então vendê-los num
        # plano sem APS seria vender arquivo que fica parado.
        # `conversoes_pagas_mes` é COGS — mede e cobra o excedente, não trava
        # (regra de ouro do monetizacao.md §4).
        #
        # **NWD e SKP NÃO entram, nem aqui** (PRA.5a, 08/08/2026): a plataforma
        # não sabe reconhecê-los pelos bytes — o contêiner do NWD é proprietário
        # e sem assinatura publicada, e o SKP muda de cabeçalho a cada versão.
        # Com a R16/R17 valendo, o que não se reconhece não entra, e o que não
        # entra não se vende. O `None` abaixo já os exclui: quem filtra é
        # `moduloprancheta.planos.formatos_do_plano`, contra
        # `formatos.SEM_ASSINATURA_CONHECIDA`. Voltam na PRA.4, com a assinatura
        # medida sobre arquivo real (planta da Prancheta §12.0).
        "formatos_prancheta": None,  # None = todos os do registry que são reconhecíveis
        "motores_prancheta": ["livre", "premium"],
        "storage_projeto_gb": 300,
        "conversoes_pagas_mes": 200,
        # 4,2× a maior folha medida. **É o teto onde o gargalo troca de lado**:
        # 2 milhões de pontos são ~22 MB para o navegador baixar e segurar, e no
        # 4G do canteiro quem sofre é o celular, não o servidor. Subir daqui pede
        # o índice por região visível, não um número maior.
        "snap_pontos": 2_000_000,
        "impexp_max_mb": 50,
        "impexp_formatos": None,  # None = todos os do registry de entrada
        "impexp_memoria_mb": 1_536,
        "impexp_segundos": 180,
        "impexp_exportar_apos_cancelar_dias": 180,
    },
    "sob_medida": {
        "nome": "Sob Medida",
        "preco_mensal": None,  # orçamento por situação
        "publico": "grande construtora, preço e SLA negociados",
        # Tudo negociado: o provisionamento grava os valores acordados em
        # `AssinaturaTenant.limites`, que têm precedência sobre estes.
        "seats": None,
        "empreendimentos": None,
        "obras": None,
        "clientes": None,
        "fornecedores": None,
        "armazenamento_gb": None,
        "analises_ia_mes": None,
        "notas_fiscais_mes": None,
        "cobrancas_mes": None,
        "processamentos_drone_mes": None,
        "banco_preco_linhas": None,
        "importacao_linhas": None,
        "geocodificacoes_mes": None,
        "rotas_mes": None,
        "storage_raster_gb": None,
        "formatos_prancheta": None,
        "motores_prancheta": None,
        "storage_projeto_gb": None,
        "conversoes_pagas_mes": None,
        "snap_pontos": None,
        # `None` em tamanho/memória/relógio NÃO vira ilimitado no motor: o
        # `funcoesimpexp/limites.py` cai no teto de infraestrutura, pela mesma
        # razão de `requisicoes_hora_default` logo abaixo — contrato ilimitado
        # que derruba o worker derruba os outros tenants junto.
        "impexp_max_mb": None,
        "impexp_formatos": None,
        "impexp_memoria_mb": None,
        "impexp_segundos": None,
        "impexp_exportar_apos_cancelar_dias": None,
        # Sem teto contratado, um plano "ilimitado" não pode virar ilimitado de
        # verdade no eixo de requisições: cairia no teto de infraestrutura e
        # derrubaria os outros tenants. O contrato preenche
        # `limites["requisicoes_hora"]`; sem ele vale este valor.
        "requisicoes_hora_default": RATE_TETO_INFRA_HORA,
    },
}

# Ordem de venda (menor → maior). Usada para exibir a régua de upgrade e para
# decidir qual plano é "acima" do atual num CTA.
ORDEM_PLANOS: tuple[str, ...] = (
    "free",
    "essencial",
    "profissional",
    "empresarial",
    "sob_medida",
)

# ---------------------------------------------------------------------------
# 4. Quais quotas TRAVAM de verdade (D24)
# ---------------------------------------------------------------------------
# Declarar uma quota na tabela acima NÃO a faz valer. Ela só passa a barrar o
# cliente se o nome dela aparecer aqui. Esta lista é, portanto, um botão
# COMERCIAL, e é por isso que ela mora neste arquivo e não no código:
#
#   - tirar um nome daqui = aquele limite deixa de morder. O cliente do `free`
#     cadastra obra sem parar e nunca vê motivo para pagar. É vazamento de
#     receita, e SILENCIOSO: nada quebra, nenhum erro aparece no log.
#   - pôr um nome aqui sem que exista contador do outro lado = o oposto, e pior:
#     o cliente é barrado por um limite que ninguém sabe medir. Há um teste que
#     falha nesse caso (backend/nucleo/test_quotas.py), justamente para que essa
#     divergência não chegue em produção.
#
# A separação abaixo não é organizacional, é a **regra de ouro** do
# docs/arquitetura/monetizacao.md §4, e mexer nela mexe na margem:
#
#   - limite de VALOR (barato de servir) → TRAVA e gera upsell;
#   - limite de CUSTO/COGS (IA, NF, boleto, drone, armazenamento) → NÃO trava:
#     mede e cobra o excedente. Travar o cliente no meio de um fechamento fiscal
#     para vender um pacote custa mais caro que o excedente que se evitaria.
#
# Ou seja: mover uma quota de COGS para cá troca "cobrar excedente" por "barrar
# o cliente". É uma decisão de negócio, com efeito direto no faturamento.

# Quotas de objeto — contadas no backend, onde os objetos existem.
#
# `banco_preco_linhas` entrou com o Orçamento (ORC.5b): é o acervo de tabela de
# preço própria que a empresa mantém — a tabela da prefeitura importada, o banco
# histórico. Limite de VALOR e não de COGS: servir uma linha a mais custa quase
# nada, mas o tamanho do acervo separa quem está testando de quem opera. Por isso
# trava, e por isso o `free` é apertado (500 linhas dão para uma obra pequena, não
# para carregar uma SINAPI estadual inteira dentro do tenant).
QUOTAS_DE_OBJETO: tuple[str, ...] = (
    "empreendimentos",
    "obras",
    "clientes",
    "fornecedores",
    "banco_preco_linhas",
)

# Seats — contado na IAM, que é quem cria usuário. Seat = usuário ATIVO, então
# desativar quem saiu da empresa libera a vaga sem passar pelo checkout.
QUOTA_SEATS = "seats"

# Tetos por OPERAÇÃO — não contam acervo, limitam uma chamada. Não entram em
# `QUOTAS_DE_OBJETO` (não há tabela para contar) mas precisam viajar na claim,
# porque quem decide é o backend no meio da operação.
#
# `importacao_linhas` protege processamento, não armazenamento: ler e classificar
# um arquivo de 90 mil linhas prende um worker e enche a área de conferência. O
# cliente que precisa de mais divide o arquivo — o acervo total continua regido
# por `banco_preco_linhas`.
QUOTAS_POR_OPERACAO: tuple[str, ...] = ("importacao_linhas",)

# Tudo que morde hoje. O que não está aqui está declarado e inerte.
QUOTAS_APLICADAS: tuple[str, ...] = (QUOTA_SEATS, *QUOTAS_DE_OBJETO, *QUOTAS_POR_OPERACAO)

# ---------------------------------------------------------------------------
# 5. CAPACIDADES por plano — knobs que não são número (PRA.0)
# ---------------------------------------------------------------------------
# `formatos_prancheta` e `motores_prancheta` são de outra natureza que as quotas
# acima: não medem quanto, decidem **o quê**. Por isso não entram em
# `QUOTAS_APLICADAS` (não há o que contar) e não viajam na claim `quotas` do
# token — o backend as lê aqui direto, pelo nome do plano que já vem na claim
# `plano`. `None` significa "todos".
#
# A régua comercial que elas materializam é a decisão do dono registrada na
# planta §6: **não há um "pacote Prancheta"**. Cada capacidade é um degrau, e o
# degrau do DWG é o MOTOR, não o formato — LibreDWG nos planos básicos, APS nos
# premium (planta §4.1). Duas consequências ao mexer nesta lista:
#
#   - formato aqui que não exista em `backend/moduloprancheta/formatos.py` = o
#     cliente contrata o que ninguém sabe ler;
#   - formato cujo motor exija um tier que `motores_prancheta` não habilita = o
#     upload passa, ocupa storage e a conversão nunca roda. É o caso do RVT, que
#     só a APS traduz — por isso ele só aparece no `empresarial`;
#   - formato **sem assinatura de bytes conhecida** (PRA.5a) = a porta única o
#     recusa na entrada, então vendê-lo é vender uma porta fechada. Hoje são o
#     NWD e o SKP, e a exclusão é automática: `formatos_do_plano` filtra por
#     `formatos.SEM_ASSINATURA_CONHECIDA`, inclusive quando o plano diz `None`.
#
# `backend/moduloprancheta/tests.py::RegistryEPlanosTests` falha nos dois primeiros
# casos; o terceiro é garantido pelo filtro, não pela lista.
#
# **Quem APLICA esta lista mudou na PRA.5a**, e vale saber ao editá-la: era o
# `uploads.py` da Prancheta, na porta dele; passou a ser o motor de import/export
# na porta única, pelo gancho `Recurso.formatos_contratados`. O efeito prático é o
# que a decisão de 08/08/2026 pedia — **o formato é comprado uma vez e vale onde
# quer que a visualização seja invocada**, e não "dentro da Prancheta" (ver
# `docs/arquitetura/monetizacao.md §3.1`).
#
# `storage_projeto_gb` e `conversoes_pagas_mes` são COGS (storage de CAD/BIM e
# tradução paga por arquivo): DECLARADAS E INERTES, como a família do Maps e da
# IA — medem e cobram o excedente, não travam o cliente no meio de uma obra.
CAPACIDADES_PRANCHETA: tuple[str, ...] = ("formatos_prancheta", "motores_prancheta")

# ---------------------------------------------------------------------------
# 5.7 O teto do snap é PONTO INDEXADO, e o motivo está medido
# ---------------------------------------------------------------------------
# `snap_pontos` é quantos pontos notáveis (extremidade, meio, centro, quadrante,
# nó, interseção) a plataforma indexa por FOLHA para a mira grudar no traço.
#
# **Por que não é megabyte de arquivo.** A medição de 15/08/2026
# (`docs/medicoes/custo-snap.md`) pegou dois casos que sozinhos matam a ideia:
#
#     fundações_3.4.dwg    0,18 MB  →  464.268 pontos
#     Poligonal.dwg        6,36 MB  →        466 pontos
#
# Trinta e cinco vezes maior em disco, mil vezes menor em custo. Cobrar por
# megabyte cobraria caro do levantamento topográfico, que é barato, e liberaria
# de graça a planta de fundação, que é o caso caro.
#
# **A régua que converte teto em custo** (constantes estáveis na amostra inteira):
#
#     banda  ≈ 10,9 bytes por ponto   (o sidecar que o navegador baixa)
#     RAM    ≈ 0,23 KB por ponto      (pico durante a extração, no worker)
#
# Então 150.000 pontos ≈ 1,6 MB e ~35 MB de RAM; 2.000.000 ≈ 22 MB e ~460 MB.
#
# **O teto não recusa a prancha.** Passou, o índice sai parcial — indexa primeiro
# linha, arco e polilinha (onde se mede), preenchimento depois — e a tela diz
# "snap parcial" com a oferta do pacote. Medir continua funcionando sempre, com
# ou sem mira grudando: cobrar não pode virar prancha que não abre.
#
# **É teto MOLE**, conferido entre entidades e não entre pontos: o índice pode
# passar em até ~2% (medido: 13.186 sobre 600.000) pela cauda da polilinha que o
# cruzou. Erra para o lado do cliente de propósito — quem pagou 600 mil nunca
# recebe menos que isso. Ver `motores/snap.py::indice_de_snap`.
SNAP_BYTES_POR_PONTO = 10.9
SNAP_KB_DE_RAM_POR_PONTO = 0.23

# ---------------------------------------------------------------------------
# 5.1 O degrau do DWG é o TAMANHO do arquivo (PRA.1b, D47)
# ---------------------------------------------------------------------------
# **É um número medido, não arbitrado.** Varrendo os 102 DWGs acima de 5 MB do
# acervo real (planta §4.1): 93% abrem até 20 MB, 64% de 20 a 40 MB e **0% —
# zero de dez — acima de 40 MB**. Todos os dez falham com a mesma assinatura
# (`checksum CRC mismatch` → `Invalid section_array_size`), que é o LibreDWG
# esbarrando no próprio limite ao percorrer o mapa de seções de um DWG grande.
#
# **ATENÇÃO — a justificativa acima envelheceu, e o número não foi remedido**
# *(09/08/2026, [D43](../docs/historico-correcoes.md))*. A PRA.1b concluía que "o
# teto é do binário e não há para onde subir", porque a 0.13.3 era a última
# versão estável e as nightlies não pagariam o custo de licença. **A segunda
# metade caiu:** o build stage passou a compilar um commit fixado (0.14.8566), a
# oferta de fonte da GPLv3 foi resolvida embarcando o próprio fonte na imagem, e
# a cobertura do acervo foi de 84,4% para **99,4%**.
#
# O que a remedição de 160 arquivos diz por faixa de tamanho — e o que ela NÃO
# diz:
#
#     0–5 MB   141 arquivos   100%        20–40 MB    2 arquivos   100%
#     5–10 MB    9 arquivos   100%        acima de 40  1 arquivo      0%
#     10–20 MB   7 arquivos   100%
#
# A faixa de 20–40 MB era 64% e virou 100%. Acima de 40 MB **este corpus tem um
# arquivo só**, então ele não confirma nem refuta o teto — e o único que há
# falhou por `recurso_excedido` (o orçamento de memória, PRANCHETA_CONVERSAO_
# MEMORIA_MB), e **não** pela assinatura de CRC que originou este degrau. São
# coisas diferentes: uma é limite do decodificador, a outra é teto nosso.
#
# **Portanto o 40 continua valendo por precaução, não por medida.** Quem decide
# mexer tem um trabalho barato pela frente: repetir a varredura dos 10 DWGs acima
# de 40 MB do acervo real com o motor novo. Se eles abrirem, este degrau está
# cobrando por algo que o plano básico já entrega — que é o [D34](../docs/historico-correcoes.md)
# ao contrário, e o tipo de erro que esta planta existe para não cometer.
#
# Por que isso é knob comercial e mora aqui: acima deste peso o caminho livre não
# entrega NADA, e é exatamente onde mora o projeto executivo completo. O degrau é
# defensável ("seu plano abre desenho de disciplina; o executivo inteiro está no
# plano superior"), o cliente entende, e a plataforma sabe ANTES de converter —
# então a resposta sai no upload, não depois de 138 MB de espera.
#
# 0 desliga o aviso. Enquanto o motor premium não existe (PRA.4), isto **avisa e
# deixa passar**: recusar seria cobrar por um plano que ainda não abre o arquivo.
DWG_MB_MOTOR_LIVRE: int = 40

# ---------------------------------------------------------------------------
# 5.2 Import/export — TODO limite é knob comercial, inclusive o técnico
# ---------------------------------------------------------------------------
# Decisão do dono (07/08/2026, na análise de segurança do `funcoesimpexp`): teto
# de tamanho, lista de formato aceito, orçamento de memória e de relógio do parse
# **não são constantes de engenharia**. Vivem aqui, por plano, "para ser mais
# fácil mudar". Antes disso, o teto de tamanho vinha de `ConfiguracaoArquivos` do
# tenant (10 MB, invisível ao dono) e memória/relógio simplesmente não existiam —
# um XLSX de 10 MB podia expandir sem limite, no worker que também carrega
# cobrança e NF-e.
#
# **É o método do assinador gov.br**, e ele resolve três coisas de uma vez:
#
#   1. a capacidade é atributo do NÍVEL, não do código — conta bronze não assina,
#      prata e ouro assinam. Aqui: `free` não lê PDF de tabela, `profissional` lê;
#   2. a lista de formatos é uma ALLOWLIST publicada (.doc/.docx/.odt/.jpg/.png/
#      .pdf, até 100 MB), anunciada ANTES do envio — nunca "tente e descubra";
#   3. o teto de tamanho é um número dito na tela, não uma surpresa no erro.
#
# E é o método da Shopify no eixo que importa para o custo: ela não limita por
# CONTAGEM de requisições, limita por **custo calculado**. `impexp_memoria_mb` e
# `impexp_segundos` são isso — o limite na unidade em que a conta chega, que é a
# lição do D57/D61 (lá, na conversão de DWG; aqui, no parse de planilha).
#
# Efeito de mexer em cada um:
#
#   - `impexp_max_mb` — teto do arquivo de ENTRADA. Sobe = arquivo maior aceito e
#     mais memória por operação. Vale para todo recurso de todo módulo.
#   - `impexp_formatos` — allowlist de formato de entrada (`None` = todos os do
#     registry). Tirar `pdf` de um plano tira o caminho MAIS CARO do motor.
#     Formato aqui que não exista no registry = o cliente contrata o que ninguém
#     sabe ler; há teste que falha nesse caso.
#   - `impexp_memoria_mb` / `impexp_segundos` — orçamento de uma operação. Baixo
#     demais recusa arquivo legítimo; alto demais devolve o consumo ilimitado que
#     estes números existem para fechar. Estourar vira 402 com motivo, nunca
#     worker morto.
#   - `impexp_exportar_apos_cancelar_dias` — janela de PORTABILIDADE: por quantos
#     dias depois de cancelar um módulo o admin do tenant ainda exporta os dados
#     dele. É o padrão de mercado (Salesforce retém 180 dias; HubSpot rebaixa
#     para o free em vez de apagar), e existe porque prender o dado do cliente no
#     dia do cancelamento é o comportamento que gera processo, não receita.
#     **DECLARADO E INERTE**: aplicar a janela exige a IAM emitir a data de
#     cancelamento na claim — hoje o token só traz `modules`, que é o estado de
#     agora. Enquanto isso a exportação pelo admin é permitida e AUDITADA, e a
#     importação exige o módulo contratado (é entrada de dado em produto não
#     pago, que a janela nunca cobriu).
CAPACIDADES_IMPEXP: tuple[str, ...] = (
    "impexp_max_mb",
    "impexp_formatos",
    "impexp_memoria_mb",
    "impexp_segundos",
    "impexp_exportar_apos_cancelar_dias",
)

# Tetos DUROS de infraestrutura, acima de qualquer plano — o mesmo papel do
# `RATE_TETO_INFRA_HORA` na fórmula de requisições. `None` num plano ("Sob
# Medida", ou token sem plano conhecido) cai AQUI, e não em ilimitado: contrato
# negociado não pode comprar o direito de derrubar o worker compartilhado.
IMPEXP_TETO_INFRA_MB: int = 100
IMPEXP_TETO_INFRA_MEMORIA_MB: int = 2_048
IMPEXP_TETO_INFRA_SEGUNDOS: int = 300

# Teto do que entra como ARQUIVO (IE.3), e ele é outro número porque descreve
# outra coisa. `IMPEXP_TETO_INFRA_MB` limita planilha — arquivo que o motor
# **abre** e explode em linhas, onde 100 MB de XLSX já é descompressão demais.
# Prancha, foto e documento o motor não abre: ele recebe, confere e guarda, e o
# custo é banda e disco, não memória.
#
# 300 MB é o que o **caminho de upload direto** aguenta, não o que os formatos
# pedem: um E57 de levantamento passa de 10 GB e um RVT de obra grande de 1 GB.
# Subir daqui exige upload retomável (chunked/presigned) — é a mesma fronteira
# que `moduloprancheta/formatos.py` já registrava, e ela subiu para cá junto com
# a porta, para não haver dois números dizendo a mesma coisa.
IMPEXP_TETO_INFRA_ARQUIVO_MB: int = 300

# ---------------------------------------------------------------------------
# 5.3 Prancheta — o tamanho de cada formato, e os tetos do BCF
# ---------------------------------------------------------------------------
# **Decisão do dono (08/08/2026): TODO teto ou limite mora aqui.** A 5.2 já tinha
# trazido os do import/export; estes ficaram para trás e eram os últimos números
# de tamanho escritos no código de engenharia. O sintoma que os denunciou foi
# pequeno e exato: o teto do snapshot era constante em `bcf.py`, a recusa por
# tamanho é sempre **402** e a frase do 402 oferece "faça upgrade do plano" — um
# upgrade que não existia, porque nenhum plano vendia um recorte de tela maior.
# Teto que o dono não vê é teto que promete o que ninguém pode cumprir.
#
# `moduloprancheta/formatos.py` continua sendo o registry de ENGENHARIA — quais
# formatos existem, por quais extensões chegam, que assinatura de bytes têm e que
# motor os abre. O que saiu de lá foi só o **número**, que é comercial: é ele que
# responde "até que tamanho o meu plano aceita uma prancha".
#
# **Os números são medidos, não arbitrados**, e cada família tem uma razão:
#
#   - **documento** (PDF 100 MB, imagem 25) — o degrau de entrada, e o que o
#     navegador abre sem motor nenhum;
#   - **CAD 2D** (150) — prancha de disciplina. O executivo completo passa disso e
#     é o degrau do `DWG_MB_MOTOR_LIVRE` acima, que é outra pergunta (o motor, não
#     o tamanho);
#   - **BIM / nuvem** (200–300) — modelo federado e levantamento. Encostam no teto
#     de infraestrutura de propósito: é o caminho de upload direto que não
#     aguenta mais, não o formato que não pede mais.
#
# Efeito de mexer: subir um número acima de `IMPEXP_TETO_INFRA_ARQUIVO_MB` não
# compra nada — o motor aplica o menor dos dois — e há teste que falha para dizer
# isso em vez de deixar o número mentir na tela do catálogo. Formato que existir
# no registry e faltar aqui entra com teto 0 e cai no do plano, que é o errado
# para prancha; o mesmo teste cobra a lista completa.
PRANCHETA_MB_POR_FORMATO: dict[str, int] = {
    # documento
    "pdf": 100,
    "imagem": 25,
    # CAD 2D
    "dxf": 150,
    "dwg": 150,
    "dwf": 150,
    # BIM 3D
    "ifc": 300,
    "rvt": 300,
    "nwd": 300,
    "dgn": 200,
    "skp": 200,
    # geo
    "kmz": 100,
    "shp": 200,
    "geojson": 100,
    "gpkg": 300,
    "qgis": 100,
    "geotiff": 300,
    # nuvem de pontos
    "las": 300,
    "copc": 300,
    "e57": 300,
    # colaboração
    "bcf": 50,
}

# O recorte de tela que acompanha uma marcação (PRA.3). **Teto de infraestrutura,
# e não knob por plano** — a distinção importa e é a mesma do bloco acima: o
# cliente compra "abrir DWG de 150 MB", ninguém compra "tirar um print maior".
# Vale para os dois caminhos do mesmo dado, a imagem que chega solta pelo
# `ponto-de-vista/` e a que vem dentro de um `.bcfzip`; um número só é o que
# impede os dois de divergirem.
PRANCHETA_TETO_SNAPSHOT_MB: int = 10

# Os três tetos da leitura de um `.bcfzip`, todos de infraestrutura pela mesma
# razão — são defesa, não oferta:
#
#   - `DESCOMPRIMIDO` é a guarda de *zip bomb*: um pacote de 2 MB pode declarar
#     40 GB, e este número é lido do cabeçalho ANTES de descomprimir qualquer
#     coisa. Note que ele NÃO é o teto de entrada do arquivo — esse é o `bcf` do
#     mapa acima (50 MB, o pacote como chega, aplicado na porta única);
#   - `XML` limita o `markup.bcf` de um tópico;
#   - `TOPICOS` limita quantas marcações uma importação traz. É o único dos três
#     que um dia pode virar knob por plano (volume de interoperabilidade é algo
#     que se vende); enquanto não for, fica aqui com os outros.
PRANCHETA_TETO_BCF_DESCOMPRIMIDO_MB: int = 200
PRANCHETA_TETO_BCF_XML_MB: int = 4
PRANCHETA_TETO_BCF_TOPICOS: int = 2_000

# ---------------------------------------------------------------------------
# 5.4 Prancheta — o orçamento de UMA conversão (D57/D63)
# ---------------------------------------------------------------------------
# Os gêmeos de `IMPEXP_TETO_INFRA_MEMORIA_MB`/`_SEGUNDOS` do lado da conversão, e
# vêm para cá pela mesma decisão de 08/08/2026. Estavam em `config/settings.py`,
# que é o arquivo de **deploy** — o dono não o abre, e a assimetria era gritante:
# o orçamento do parse de planilha morava aqui e o da conversão de DWG, não, sendo
# que é o segundo que custa caro (é ele que o D57 e o D61 mediram).
#
# **Continuam sobrescritíveis por variável de ambiente** — quem opera a máquina
# precisa poder apertar sem editar código, e uma VM pequena tem outro orçamento
# que uma grande. O que muda é de onde sai o PADRÃO: destes números, à vista do
# dono, e não de uma string no meio de 700 linhas de settings.
#
# **A invariante que não pode quebrar ao mexer** (D71/D76): o freio que sabe
# EXPLICAR tem de estourar antes do que só mata. `PRANCHETA_CONVERSAO_MEMORIA_MB`
# vira `RLIMIT_AS` e produz `recurso_excedido` — erro legível na fila do cockpit;
# o `CELERY_WORKER_MAX_MEMORY_PER_CHILD` (2 GiB) e o `mem_limit` do container só
# matam o processo. Subir este número acima daqueles troca uma mensagem por um
# worker morto sem rastro.
PRANCHETA_CONVERSAO_MEMORIA_MB: int = 1_536
PRANCHETA_CONVERSAO_SEGUNDOS: int = 300

# ---------------------------------------------------------------------------
# 5.4b O orçamento do arquivo INTEIRO, somado entre as voltas à fila
# ---------------------------------------------------------------------------
# *(decisão do dono, 16/08/2026: "se esse arquivo não terminar em tantos
# segundos, volta pro final da fila e continua assim até terminar" — e, quando
# perguntado como desistir, "teto de tempo total acumulado".)*
#
# **Por que dois relógios e não um.** O `PRANCHETA_CONVERSAO_SEGUNDOS` acima é o
# de UMA passada, e ele não mudou de significado: é o quanto um arquivo pode
# segurar o worker de uma vez. O que mudou é o que acontece ao estourá-lo — antes
# a conversão morria inteira; agora ela **grava as folhas que terminou e volta
# para o fim da fila**, e a passada seguinte continua da folha em que parou. Sem
# um segundo teto, um arquivo que nunca converge giraria a frota para sempre, um
# turno de 300 s por vez.
#
# **Por que o teto é de TEMPO e não de número de voltas.** Contar voltas mede a
# nossa política, não o custo: um arquivo que faz 30 folhas por volta e outro que
# faz uma gastariam o mesmo "orçamento" tendo custado dez vezes diferente. O que
# a máquina paga é segundo de CPU, e é isso que se soma.
#
# **O que o cliente vê ao estourar:** `recurso_excedido` com as folhas que já
# converteram **preservadas** — a prancha abre pelo que deu, e a mensagem diz
# quantas faltaram. É a mesma degradação honesta do resto do módulo: nunca a
# folha fabricada, nunca a tela em branco sem explicação.
#
# 1.800 s = 6 passadas cheias de 300 s. Sai daqui, e não do `settings.py`, pela
# mesma razão que os dois de cima: é limite comercial — quanto de máquina o plano
# paga por arquivo —, e limite comercial é do dono.
PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS: int = 1_800

# ---------------------------------------------------------------------------
# 5.4c A frota de trabalho pesado — quem senta, e quantas cadeiras (D98)
# ---------------------------------------------------------------------------
# *(decisões do dono, 16/08/2026.)* O `worker-conversao` sempre teve freio
# (`--concurrency 1`, `mem_limit`, o orçamento de `limites.py`) e nunca teve
# **porteiro**: quem chegava primeiro ocupava, e quem chegava depois esperava sem
# ordem, sem posição e sem garantia. Estes números são a política do porteiro, e
# moram aqui porque dizem **quanto de máquina cada plano compra** — que é preço,
# não engenharia. Quem os aplica é [nucleo/frota.py](../backend/nucleo/frota.py).
#
# **Fração da frota, nunca número absoluto** — a decisão, nas palavras do dono:
# *"você não pode deixar 40 cadeiras premium e quando o programa lançar haver
# 100.000.000 de pessoas na fila"*. Fração escala sozinha com a frota e com a
# demanda; número fixo vira gargalo no dia do lançamento.
#
# **Reserva nos DOIS sentidos, e é isso que a torna diferente de prioridade.**
# Prioridade pura faz o premium com volume alijar o free indefinidamente. Aqui
# uma parte das cadeiras é de quem paga mais **e** uma parte fica garantida a
# quem paga menos: o free espera mais, nunca uma eternidade.
#
# ⚠️ **NÚMEROS PROVISÓRIOS — falta o estudo** *(decisão do dono, 16/08/2026:
# "isso tem que ser feito um estudo para determinar")*. O que o estudo precisa
# medir antes de estes valores deixarem de ser palpite:
#   1. a distribuição real de plano na base (uma base 90% free quer outra
#      repartição que uma 50/50 — hoje não há base);
#   2. o tempo mediano e de cauda de uma conversão por plano, que é o que
#      converte "cadeira" em "minutos de espera" — a única unidade que o cliente
#      sente;
#   3. quantas vagas a frota terá de fato (hoje é UMA, `--concurrency 1`), porque
#      abaixo de ~5 vagas toda fração arredonda para zero e a reserva vira
#      simplesmente ordem de prioridade.
# Enquanto o estudo não existe, o comportamento está correto e as proporções são
# arbitradas. Trocar estes três números não exige tocar em código nenhum — é
# exatamente por isso que eles são variáveis e não constantes espalhadas.
#
# **A FROTA CRESCE COM A DEMANDA, e a condição é a eficiência** *(decisão do
# dono, 16/08/2026: "a quantidade de filas irá subir à medida que o projeto
# precisa, se isso for eficiente")*. Três coisas que essa decisão fixa:
#
#   1. **Cresce em CADEIRAS, não em filas.** A fila é uma só — foi decisão do
#      dono em 16/08, e é o que torna a reserva por plano possível: filas
#      paralelas não sabem quantas cadeiras a classe vizinha está usando, e a
#      repartição vira palpite. Somar capacidade é somar `FROTA_VAGAS`, que
#      acompanha o `--concurrency` do worker.
#   2. **"Se isso for eficiente" tem número, e o número é o aproveitamento.** A
#      bancada de 16/08 mediu **100%** (279,6 s de CPU para 278,4 s de relógio):
#      a conversão é trabalho de CPU de uma linha só, então cada cadeira nova
#      exige um NÚCLEO novo, não só mais memória — vCPU compartilhada faz a
#      cadeira andar mais devagar e ainda sofrer com o vizinho. Cadeira que não
#      ganha núcleo dedicado não é cadeira, é ilusão de vazão.
#   3. **O gatilho é ESPERA, não custo.** O estudo de viabilidade
#      ([docs/medicoes/viabilidade-economica.md](../docs/medicoes/viabilidade-economica.md))
#      mostrou que converter é desprezível — centavos por acervo inteiro — e que
#      uma cadeira custa cerca de R$ 130/mês. Então o que decide comprar a
#      próxima cadeira não é a margem, que aguenta: é a fila do cliente novo, que
#      cai no primeiro uso, o momento de maior churn. A grandeza a vigiar é
#      `frota.situacao_da_fila` — posição e espera —, não a conta de infra.
FROTA_FRACAO_RESERVADA_PREMIUM: float = 0.50
FROTA_FRACAO_RESERVADA_FREE: float = 0.20
# O resto (1 − premium − free) é de quem chegar primeiro, qualquer que seja o
# plano. Fica implícito e não como terceira variável de propósito: uma soma que
# alguém pode escrever como 0,6 + 0,6 é uma soma que um dia alguém escreve.

#: Quais planos contam como "premium" para efeito de cadeira. Lista e não um
#: campo em `PLANOS` porque a fronteira é da FROTA e pode não coincidir com a de
#: nenhum outro recurso — um plano do meio pode um dia comprar cadeira premium
#: sem virar premium em mais nada.
FROTA_PLANOS_PREMIUM: tuple[str, ...] = ("empresarial", "enterprise")
#: E quais contam como "free" — os que têm a cota garantida contra a fome.
FROTA_PLANOS_FREE: tuple[str, ...] = ("free", "gratuito")

#: Quantas cadeiras um add-on de fila dá a quem o compra, **somadas à fração do
#: plano** (`pacote_fila_prioritaria` em [addons.py](addons.py)).
#:
#: **É o gancho que o dono pediu junto com o estudo**, e ele já muda o desenho
#: mesmo sem preço definido: sem um lugar para o add-on entrar, a única forma de
#: um cliente comprar mais vazão seria trocar de plano inteiro — que é upsell
#: grosso, e o modelo do `monetizacao.md` §5.1 é híbrido de propósito. Zero
#: desliga o mecanismo sem remover o caminho.
FROTA_CADEIRAS_POR_ADDON: int = 1

#: Quão atrás o job que consumiu um turno recomeça, e quanto ele sobe por volta.
#:
#: **São dois números porque "volta pro fim, mas com prioridade crescente" são
#: duas coisas** (decisão do dono, 16/08/2026), e a primeira versão só tinha a
#: segunda — o que a fazia mentir: com o degrau sozinho, a primeira volta já
#: punha o arquivo à frente de todo mundo do mesmo plano, que é o oposto de
#: "volta pro fim".
#:
#: - **`PENALIDADE`** é o "fim da fila": quem gastou um turno recomeça atrás de
#:   quem ainda não gastou nenhum.
#: - **`DEGRAU`** é o "crescente": a penalidade decai a cada volta, e depois de
#:   `PENALIDADE / DEGRAU` voltas o arquivo passa a ultrapassar os recém-chegados.
#:   Sem isso, um arquivo de 40 MB atrás de um fluxo contínuo de arquivos pequenos
#:   nunca terminaria.
#:
#: Com 10 e 1: cede a vez nas dez primeiras voltas e começa a furar na décima
#: primeira — some de vista sem nunca sumir.
FROTA_PENALIDADE_DA_VOLTA: int = 10
FROTA_DEGRAU_POR_VOLTA: int = 1

#: Quanto o envelhecimento pode empurrar a prioridade **para fora do patamar do
#: plano**. Zero em cima: um job nunca chega ao patamar da classe de cima.
#:
#: **Existe porque prioridade e classe são coisas diferentes e ficaram acopladas
#: uma vez.** A primeira versão do despachante deduzia a classe de cadeira da
#: faixa de prioridade — e como o envelhecimento mexe na prioridade, um job free
#: com trinta voltas passava a ser lido como `comum` e sentava em cadeira que não
#: era dele. Hoje a classe sai do **plano**, que é imutável na linha; este teto
#: continua existindo para a ordem dentro do patamar não virar sopa.
FROTA_BANDA_DE_ENVELHECIMENTO: int = 50

# Orçamento do SUBPROCESSO de conversão — hoje só o `dwg2dxf` (D78, 09/08/2026).
#
# **Por que ele precisa ser separado, e não herdado.** `RLIMIT_AS` é herdado pelo
# filho, então até aqui o `dwg2dxf` corria sob o teto do PAI — um número
# dimensionado para o trabalho em processo (o `ezdxf` desenhando), aplicado a um
# programa em C com outro perfil de alocação. Pior: o LibreDWG não confere o
# retorno do `malloc`, então estourar não produzia `MemoryError`, produzia
# **SIGSEGV** — e a plataforma lia a morte por sinal como "o motor não deu conta"
# e mandava o cliente comprar o plano superior. Três DWGs do acervo provaram o
# mecanismo: convertem limpos soltos, morrem sob o teto.
#
# **O número é provisório e está declarado como tal.** Ele NÃO sobe o que a
# plataforma gasta: o filho hoje herda `VA_do_processo + 1536`, que no
# `worker-conversao` dá ~2,6 GB efetivos — 2.048 é mais APERTADO que isso, e a
# escolha por apertar em vez de afrouxar é deliberada enquanto o custo real não
# foi medido (decisão do dono, 09/08/2026: "não vamos subir o teto sem antes
# saber o custo real da operação").
#
# **O que vai substituí-lo:** a remedição dos 10 arquivos acima de 40 MB com a
# instrumentação de custo (parcial v3) mede o pico de verdade. Até lá, é possível
# que um arquivo que converte hoje passe a falhar aqui — e falhará como
# `recurso_excedido`, que é nosso e legível, nunca como upsell.
#
# **A invariante do bloco acima continua valendo:** este teto tem de ficar abaixo
# do `mem_limit` do container (`worker-conversao`, 3 GB), senão o cgroup mata o
# processo antes de o freio que sabe explicar chegar a explicar.
PRANCHETA_SUBPROCESSO_MEMORIA_MB: int = 2_048

# Quantas FOLHAS um único arquivo pode render (PRA.1c). Cada desenho separado vira
# **um arquivo** no storage, então sem teto um DXF patológico geraria milhares de
# derivadas — e a conta de armazenamento é do dono, que é exatamente por isso que
# o número mora aqui. Estourar não é silencioso: o excedente fica no último
# desenho e a memória de conversão registra `desenhos_truncados`.
PRANCHETA_TETO_FOLHAS_POR_ARQUIVO: int = 64

# Teto de elementos tesselados numa conversão de IFC. Acima dele um único modelo
# monopoliza o worker por dezenas de minutos e atrasa a fila de **todos** os
# tenants — é COGS de tempo, e a resposta honesta é dizer que o modelo é grande
# demais para este caminho. Subir exige tesselação em partes, a mesma fatia do
# upload retomável que destrava o `IMPEXP_TETO_INFRA_ARQUIVO_MB`.
PRANCHETA_TETO_ELEMENTOS_IFC: int = 250_000

# Relógio dos SUBPROCESSOS da conversão. O `PRANCHETA_CONVERSAO_SEGUNDOS` acima
# cobre o que roda em processo (o `ezdxf` desenhando); estes cobrem o binário
# externo, que não vê o `SIGALRM` — o LibreDWG é C e precisa do próprio `timeout`.
# Os dois números são medidos: um DWG de projeto executivo passa de 60 s no
# `dwg2dxf`, e o preview embutido (§4.4) é ordens de grandeza mais barato.
PRANCHETA_TIMEOUT_DWG_SEGUNDOS: int = 180
PRANCHETA_TIMEOUT_PREVIEW_SEGUNDOS: int = 60

# Lado da miniatura, em pixels. É teto de tamanho como qualquer outro — decide
# quanto storage cada card do acervo custa, multiplicado por prancha. 600 px é o
# que a planta chama de "reconhecer a prancha, não ler a cota".
PRANCHETA_LADO_MINIATURA_PX: int = 600

# Tetos do comando de bancada `medir_cobertura_dwg` — a medição dos 160 DWGs.
# **Não limitam cliente nenhum**, e vêm para cá mesmo assim: são o que impede a
# medição de ocupar a estação de quem a dispara (foi o que aconteceu em 06/08),
# e a régua é que todo teto é visível aqui. O `RESGATE` é maior porque a segunda
# passada decodifica o mesmo arquivo com mais folga.
PRANCHETA_MEDICAO_TETO_SEGUNDOS: int = 120
PRANCHETA_MEDICAO_TIMEOUT_RESGATE_SEGUNDOS: int = 180

# ---------------------------------------------------------------------------
# 5.4d A MEMÓRIA é o degrau do arquivo grande — e ela é por plano (D101)
# ---------------------------------------------------------------------------
# *(decisão do dono, 16/08/2026, depois da medição do maior DWG do acervo.)*
#
# **O que a medição mostrou, e derrubou a explicação anterior.** O arquivo de
# 64,9 MB era citado como "o que nem chega ao motor". Rodando o `dwg2dxf` **sem o
# nosso orçamento**, ele converte: sai `0` e produz um DXF de **531,8 MB** (8,2×).
# Quem o mata somos nós — os 2.048 MB do `PRANCHETA_SUBPROCESSO_MEMORIA_MB`, em
# 9,7 s. Não é limite do LibreDWG, não é a assinatura de CRC da §5.1: é teto
# nosso, e teto nosso mora aqui e sobe por plano.
#
# **Por que o eixo é memória e não MB de arquivo.** É a mesma conclusão da PRA.1b
# por outro caminho: nenhum corte em MB ordena o custo (§5.1), porque o DWG guarda
# hachura como *declaração* — área ÷ espaçamento —, grandeza que o tamanho do
# arquivo não limita. O que o plano compra é **quanta RAM a plataforma gasta por
# você**, e essa é a grandeza que de fato para o arquivo. O `DWG_MB_MOTOR_LIVRE`
# (40 MB) continua existindo como aviso comercial, mas ele mede o eixo errado e
# está marcado como tal desde a remedição.
#
# **A INVARIANTE QUE NÃO PODE QUEBRAR** (a mesma do 5.4, agora com números): o
# freio que sabe EXPLICAR tem de estourar antes do que só mata. Hoje a escada é
#
#     1.536 MB  nosso teto        → `recurso_excedido`, erro legível no cockpit
#     2.048 MB  Celery/subprocesso → mata o filho, sem rastro para o cliente
#     3.072 MB  `mem_limit` do contêiner → mata tudo
#
# **Consequência medida, e é uma pendura real:** o degrau de cima destes mapas
# **não cabe na máquina de hoje**. O `dwg2SVG` pede 2.410–3.069 MB nos 7 pesados
# do acervo (roadmap PRA.1f) e o 64,9 MB pede mais de 2.048 no subprocesso — ou
# seja, servir esse arquivo exige subir TAMBÉM o
# `CELERY_WORKER_MAX_MEMORY_PER_CHILD` e o `mem_limit`, que são dimensionamento de
# máquina e não moram aqui. Por isso os valores abaixo param onde a escada ainda
# é válida: prometer 4 GB num contêiner de 3 GB seria vender o worker morto sem
# rastro, que é o D71/D76 ao contrário. Quem crescer a máquina sobe estes números
# no mesmo commit — e `nucleo/test_tetos_no_payment.py` cobra a escada.
#
# Plano ausente do mapa cai no valor base acima, que é o comportamento de sempre.
PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO: dict[str, int] = {
    "free": 1_024,
    "essencial": 1_280,
    "profissional": 1_536,
    "empresarial": 1_900,
    "sob_medida": 1_900,
}

#: Idem para o subprocesso (`dwg2dxf`/`dwg2SVG`), que é processo à parte e por
#: isso não responde ao `RLIMIT_AS` da conversão. O teto dele encosta no
#: `mem_limit` do contêiner, não no do Celery.
#:
#: ⚠️ **O topo é 2.048 por MEDIÇÃO, não por escolha** (16/08/2026). A primeira
#: versão deste mapa dava 2.800 MB ao `empresarial`, e o teste no acervo real
#: mostrou o estrago: com 2.048 o DWG de 64,9 MB devolve `RecursoExcedido` em
#: 8,9 s — erro legível, prancha explicada; com 2.800 o processo morre com
#: **exit 137 (SIGKILL do contêiner)**, sem exceção, sem mensagem e sem rastro.
#: A conta é simples e não tinha sido feita: o `mem_limit` de 3.072 MB é do
#: contêiner INTEIRO, e o Python pai já nasce com ~1.150 MB de VA reservada — o
#: subprocesso não tem 3 GB para si, tem o que sobra.
#:
#: Enquanto a máquina não crescer ([D103](../docs/pendencias.md)), nenhum degrau
#: pode passar de `PRANCHETA_SUBPROCESSO_MEMORIA_MB`, e é isso que o
#: `EscadaDeMemoriaPorPlanoTests` cobra. Degrau achatado no topo é upsell que não
#: entrega — mas é melhor que upsell que mata o worker.
PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO: dict[str, int] = {
    "free": 1_024,
    "essencial": 1_536,
    "profissional": 2_048,
    "empresarial": 2_048,
    "sob_medida": 2_048,
}

# ---------------------------------------------------------------------------
# 5.4e Disco por tarefa suspensa — PROVISÓRIO, a medir perto do lançamento
# ---------------------------------------------------------------------------
# *(decisão do dono, 16/08/2026: "o disco será determinado por medição quando o
# software estiver próximo do lançamento. Coloque uma variável e salve em
# documentação".)*
#
# **A que pergunta este número responde.** A pesquisa de 16/08 (laudo
# [`docs/medicoes/fila-da-frota.md`](../docs/medicoes/fila-da-frota.md) §10) mostrou
# que a indústria resolve "arquivo grande não pode travar os pequenos" de quatro
# jeitos, e o que o dono descreveu — suspender guardando o estado em disco — é o
# mais caro deles: no SLURM ele exige DMTCP/CRIU, e o tempo de checkpoint do CRIU
# é **linear no tamanho da memória**. Se um dia guardarmos estado entre as voltas
# em vez de recomputá-lo, cada tarefa suspensa passa a ocupar disco: ~85 MB só do
# DXF intermediário no arquivo comum, **531,8 MB no de 64,9 MB**, e mais que isso
# se a geometria gravada também for persistida.
#
# **Por que ele já existe valendo zero.** Zero desliga: nada é guardado e a
# retomada segue recomputando, que é o comportamento de hoje. O número entra
# quando houver medição — e ele é knob comercial pela mesma régua dos outros
# (é espaço que a plataforma paga por cliente), não constante de engenharia.
#
# ⚠️ **NÃO É MEDIDO.** Quem for medir precisa de três grandezas que ninguém tem
# ainda: quantas tarefas ficam suspensas ao mesmo tempo em carga real, o tamanho
# mediano e de cauda do estado por tarefa, e o custo em segundos de serializar e
# reler esse estado — que pode comer a economia que ele existe para gerar.
FROTA_DISCO_POR_TAREFA_SUSPENSA_MB: int = 0

# ---------------------------------------------------------------------------
# 5.5 Os tetos dos demais módulos
# ---------------------------------------------------------------------------
# Mesma decisão de 08/08/2026, aplicada ao resto do backend: **todo limite mora
# aqui**. O que a varredura achou fora da Prancheta estava em cinco arquivos
# diferentes, e nenhum deles é lido por quem decide o produto.

# Teto de upload do caminho genérico de `nucleo` — o fallback de quando o tenant
# não tem `ConfiguracaoArquivos` própria. É a porta antiga, anterior à R17; o que
# a substituiu é o `impexp_max_mb`, e este número segue valendo enquanto houver
# anexo que ainda não migrou para a porta única (IE.4–IE.7).
UPLOAD_PADRAO_MAX_MB: int = 10

# **O corte entre síncrono e job** (R10 do `funcoesimpexp`). Abaixo dele a
# operação responde na requisição; acima vira Celery com progresso. São dois
# números porque descrevem custos diferentes: exportar materializa linhas em
# memória para escrever o arquivo, importar as classifica uma a uma. Subir
# qualquer um dos dois troca "espera com barra de progresso" por "timeout no
# gateway e o usuário reenviando".
IMPEXP_LIMITE_SINCRONO_EXPORTACAO: int = 2_000
IMPEXP_LIMITE_SINCRONO_IMPORTACAO: int = 3_000

# Antecedência máxima de um lembrete de calendário, em minutos (4 semanas). Teto
# de entrada do usuário: sem ele, um offset absurdo agenda uma task para daqui a
# séculos e ela fica na fila para sempre.
CALENDAR_MAX_OFFSET_LEMBRETE_MIN: int = 4 * 7 * 24 * 60

# Quantas notificações a lista do sino devolve numa chamada.
NOTIFICACOES_LIMITE_LISTA: int = 50

# Profundidade máxima da explosão de uma composição de preço. O SINAPI aninha
# composições auxiliares em 2–3 níveis; 12 é folga larga **e** o freio contra
# dado circular que escape da checagem de visitados — é o teto que impede uma
# base de terceiro mal formada de girar até estourar a pilha.
ORCAMENTO_PROFUNDIDADE_MAXIMA_COMPOSICAO: int = 12

# Quantas **parciais de medição** uma linha orçada aceita (ORC.7 — a memória do
# quantitativo). Um serviço com muitas frentes chega a algumas dezenas de
# parciais; 500 é folga larga para o uso honesto e é o freio contra a planilha
# colada de um arquivo errado, que entraria como milhares de linhas por item e
# faria o recálculo da árvore arrastar a grade inteira.
ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM: int = 500

# Profundidade máxima de parênteses na **fórmula** de uma parcial de medição.
# Mesmo espírito do teto de composição acima: a avaliação é por AST restrita
# (sem nome, sem chamada), então o risco não é execução — é uma expressão
# aninhada de propósito para consumir pilha na hora de avaliar.
ORCAMENTO_PROFUNDIDADE_MAXIMA_FORMULA: int = 8

# **Tamanho de página das listagens**, por módulo. É limite dos dois lados: o
# `PADRAO` é quanto vem sem ninguém pedir e o `MAXIMA` é o teto do `?page_size=`
# que o cliente manda — sem ele, `?page_size=100000` transforma toda listagem
# numa exportação sem gate. A Prancheta é a exceção medida: o acervo de uma obra
# tem dezenas de pranchas por disciplina e paginar de 25 faria o canteiro rolar.
#
# Módulo que ganhar paginador e não aparecer aqui falha no teste do `nucleo`.
PAGINA_PADRAO: dict[str, int] = {
    "catalogo": 25,
    "clientes": 50,
    "empreendimentos": 100,
    "erp": 25,
    "maps": 50,
    "orcamento": 25,
    "prancheta": 50,
    "scm": 25,
    "sil": 25,
}
PAGINA_MAXIMA: dict[str, int] = {
    "catalogo": 100,
    "clientes": 300,
    "empreendimentos": 300,
    "erp": 200,
    "maps": 500,
    "orcamento": 100,
    "prancheta": 500,
    "scm": 100,
    "sil": 100,
}

# ---------------------------------------------------------------------------
# 5.5b A carga da base oficial (ORC.8) — o que sai da nossa máquina para a Caixa
# ---------------------------------------------------------------------------
# O ORC.8 trocou "alguém baixa o ZIP e roda o comando" por um botão. Com isso o
# backend passou a **sair para a internet** buscando arquivo de terceiro, e todo
# número desse caminho é limite: diz até onde a nossa máquina vai atrás de um
# artefato que não controlamos.
#
# Por que aqui e não em `config/settings.py` (que é arquivo de *deploy*): quem
# decide "um ZIP de 200 MB ainda vale a pena?" é o dono, não quem opera o
# contêiner. E o efeito de cada um é comercial antes de ser técnico:
#
#   - `ORCAMENTO_CARGA_TETO_MB` — teto do ZIP baixado. O nacional de 2026 tem
#     ~16 MB; 250 é folga de uma ordem de grandeza para o mês em que a Caixa
#     resolver publicar tudo junto. Baixo demais recusa publicação legítima;
#     alto demais deixa uma URL errada (uma ISO, um espelho) encher o disco do
#     worker. O corte acontece **durante** o stream, não depois de gravar.
#   - `ORCAMENTO_CARGA_SEGUNDOS` — relógio de uma carga inteira (baixar + ler +
#     gravar). 54 publicações de ~17 mil linhas é trabalho de minutos, e é por
#     isso que a carga é job e não requisição.
#   - `ORCAMENTO_CARGA_MEMORIA_MB` — orçamento do processo enquanto lê o XLSX
#     largo. Mesma unidade do `impexp_memoria_mb`: o limite na moeda em que a
#     conta chega. Estourar vira carga `falhou` com motivo, nunca worker morto.
#   - `ORCAMENTO_CARGA_TENTATIVAS` / `_ESPERA_INICIAL_S` / `_ESPERA_MAXIMA_S` —
#     a **pausa** do download. O WAF da Caixa (Azion) limita por taxa: rajada
#     derruba tudo para 429, inclusive a URL boa. Backoff exponencial de 5 s,
#     teto de 60 s, 4 tentativas. Subir as tentativas não acelera nada — só faz
#     o job segurar por mais tempo a cadeira que pegou na frota.
#   - `ORCAMENTO_CARGA_PAUSA_ENTRE_ARQUIVOS_S` — intervalo entre dois downloads
#     da mesma corrida. Existe porque o formato até 12/2024 era 1 ZIP por UF ×
#     regime: uma carga daquele formato são 54 hits, e 54 hits sem pausa é
#     exatamente a rajada que o WAF corta.
#   - `ORCAMENTO_CARGA_TETO_PUBLICACOES` — quantas publicações uma carga pode
#     criar. O ZIP nacional rende 27 UFs × 3 regimes = 81 no pior caso; 120 é
#     folga para a Caixa acrescentar regime ou território sem o job parar, e é
#     freio contra layout inesperado em que a detecção de UF ache coluna demais
#     e a carga escreva publicação que ninguém pediu.
#
# Nenhum destes é por plano, e a razão é a §11.1 do `moduloorcamento.md`: a
# base-mãe é da PLATAFORMA. Quem paga a conta desta carga somos nós, uma vez por
# mês, para todos os clientes de uma vez — o tenant nem sabe que ela aconteceu.
ORCAMENTO_CARGA_TETO_MB: int = 250
ORCAMENTO_CARGA_SEGUNDOS: int = 1_800
ORCAMENTO_CARGA_MEMORIA_MB: int = 2_048
ORCAMENTO_CARGA_TENTATIVAS: int = 4
ORCAMENTO_CARGA_ESPERA_INICIAL_S: float = 5.0
ORCAMENTO_CARGA_ESPERA_MAXIMA_S: float = 60.0
ORCAMENTO_CARGA_PAUSA_ENTRE_ARQUIVOS_S: float = 2.0
ORCAMENTO_CARGA_TETO_PUBLICACOES: int = 120

# ---------------------------------------------------------------------------
# 5.6 O que NÃO é limite — e por isso continua no código de engenharia
# ---------------------------------------------------------------------------
# A régua é "todo teto ou limite vive aqui", e ela tem uma fronteira: número que
# não diz *até onde o cliente vai* não é limite, é **fato**. Mover esses para cá
# faria o arquivo do dono virar depósito de constante e esconderia os que
# importam. A lista fica registrada para a varredura não se repetir:
#
#   - **constantes físicas e de protocolo** — `RAIO_TERRA_M`, `M_POR_GRAU_LAT`,
#     `SRID = 4326` (`modulomaps`): geodésia não é decisão de produto;
#   - **parâmetros de parsing** — `JANELA = 180` caracteres em torno do CEP
#     (`modulomaps/deteccao.py`): é a largura de contexto que o extrator lê, e
#     mudá-la muda o *acerto*, não o quanto o cliente pode;
#   - **janelas de protocolo de terceiro** — `SEEN_TTL` (`funcoeswhatsapp`) é a
#     janela de reentrega **da Meta**; não somos nós que a escolhemos;
#   - **larguras de campo** — `LARGURA_CODIGO_INTERNO = 40` (`moduloorcamento`) é
#     o `max_length` da coluna `catalogo.Item.codigo_interno`, não um teto de uso.
#     Chamava-se `LIMITE_*` e por isso aparecia em toda varredura como falso
#     positivo: o nome mentia, e foi ele que mudou;
#   - **TTL de cache** — `CACHE_TTL` de CEP/município (`nucleo/geo.py`): é
#     desempenho, e o dado que ele guarda é público e estável;
#   - **limiar de conferência** — `LIMIAR_SEMELHANCA` (`moduloorcamento/
#     identidade.py`, D110): a partir de qual semelhança duas descrições são
#     tidas como o mesmo insumo. Mesma família do `JANELA` do extrator de CEP —
#     mexer nele muda o *acerto* da conferência (quantos falsos positivos e
#     falsos negativos), não o quanto o cliente pode adotar ou classificar.
