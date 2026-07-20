"""Add-ons — o "híbrido" do modelo: plano base + upsell contínuo.

Valores comerciais; ver `payment/README.md`. Racional: monetizacao.md §5.1.

Nada aqui é aplicado ainda (o checkout é o D24). Estão declarados porque o
**usuário extra** já tem efeito no desenho do D23: comprar um seat aumenta
`seats` e o teto de requisições sobe junto, sem ninguém ajustar limite.
É o que faz o limite acompanhar a receita em vez de brigar com ela.
"""
from __future__ import annotations

# Preço mensal em reais, salvo onde indicado.
ADDONS: dict[str, dict] = {
    "usuario_extra": {
        "nome": "Usuário extra",
        "preco_mensal": 29,
        "unidade": "usuário",
        # Cada unidade soma 1 seat -> soma RATE_POR_SEAT_HORA ao teto (D23).
        "incrementa": {"seats": 1},
    },
    "empreendimento_extra": {
        "nome": "Empreendimento extra",
        "preco_mensal": 19,
        "unidade": "empreendimento",
        "incrementa": {"empreendimentos": 1},
    },
    "pacote_10_obras": {
        "nome": "Pacote de 10 obras",
        "preco_mensal": 49,
        "unidade": "pacote",
        "incrementa": {"obras": 10},
    },
    "modulo_drone": {
        "nome": "Módulo Drone (sobre Essencial/Profissional)",
        "preco_mensal": 349,
        "unidade": "assinatura",
        "incrementa": {"processamentos_drone_mes": 10, "armazenamento_gb": 100},
    },
    "processamento_drone_extra": {
        "nome": "Processamento de drone avulso",
        "preco_mensal": None,
        "preco_unitario": 25,
        "unidade": "processamento",
        "incrementa": {"processamentos_drone_mes": 1},
    },
    "armazenamento_100gb": {
        "nome": "Armazenamento +100 GB",
        "preco_mensal": 79,
        "unidade": "pacote",
        "incrementa": {"armazenamento_gb": 100},
    },
    "pacote_ia_500": {
        "nome": "Pacote IA +500 análises/mês",
        "preco_mensal": 99,
        "unidade": "pacote",
        "incrementa": {"analises_ia_mes": 500},
    },
}

# Excedentes cobrados por unidade (COGS): não travam a operação, viram fatura.
# Regra de ouro (monetizacao.md §4): limite de VALOR trava e faz upsell; limite
# de CUSTO mede e cobra o excedente — travar o cliente no meio de um fechamento
# fiscal para vender um pacote custa mais caro que o excedente.
EXCEDENTES: dict[str, dict] = {
    "nota_fiscal": {"nome": "NF-e excedente", "preco_unitario": 0.60},
    "cobranca": {"nome": "Boleto excedente", "preco_unitario": 0.50, "mais_repasse": "asaas"},
    "sms": {"nome": "SMS", "preco_unitario": 0.19},
}
