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
