"""A classe de cada ação — o que decide cache, consistência e o modo de falha.

docs/acesso-e-permissoes.md §10.8, com a lista de atos críticos **fixada pelo
dono** (24/09/2026: "as classes ficam como estão — tempos e lista de atos
críticos"). Esta tabela traduz a lista para os códigos do catálogo; ela não a
estende. Quem quiser pôr um código novo em C muda a planta primeiro.

| Classe | O que é | Cache | Consistência | PDP fora |
|---|---|---|---|---|
| A | leitura comum | 60 s | ao menos a última mudança | serve o cache; depois nega |
| B | dado pessoal, financeiro ou de saúde; escrita comum | 5 s | ao menos a última mudança | idem, por segundos |
| C | move dinheiro, muda quem pode, tira dado | nenhum | total | nega na hora |

A planta dizia "a mais rápida" para A; a E2E da virada mostrou que isso anula a
invalidação (ver `nucleo/autorizacao_pdp._consistencia`). Os tempos e a lista
de atos críticos — o que o dono fixou — não mudaram.

**Os TTLs não são teto do `planos.py`** — a §5.6 de lá põe TTL de cache fora da
régua: é desempenho, não até onde o cliente vai. Quem garante a revogação em
segundos não é o TTL, é a invalidação por evento (o Watch); o TTL é só o pior
caso quando o invalidador está fora.
"""
from __future__ import annotations

A, B, C = "A", "B", "C"

TTL_S = {A: 60, B: 5, C: 0}

#: A lista do dono, código por código. Cada linha diz de qual item da lista vem.
CRITICOS = frozenset({
    "pdca.medicao.atestar",           # atestar medição — e liberar retenção, que é o mesmo verbo
    "pdca.aditivo.aprovar",           # aditivo
    "erp.conta_pagar.baixar",         # pagar
    "erp.lote_remessa.create",        # pagar (o lote vai ao banco)
    "plataforma.papel.gerir",         # mudar papel
    "plataforma.fluxo_aprovacao.edit",  # mudar alçada ou escada
    "plataforma.lgpd.exportar",       # exportar dado pessoal / LGPD
    "plataforma.lgpd.excluir",        # tirar dado da plataforma (LGPD)
    "plataforma.lixo.purgar",         # purgar lixeira
    "pdca.ocorrencia.emitir_cat",     # emitir CAT
})

#: Leituras que ficam em B porque mostram dado pessoal, financeiro ou de saúde.
#: As demais leituras são A.
LEITURAS_SENSIVEIS = frozenset({
    # RH: tudo é dado de pessoa, menos o cadastro de cargos
    "rh.funcionario.view", "rh.cpf.view", "rh.documento.view", "rh.dado_medico.view",
    "rh.dado_bancario.view", "rh.folha.view",
    # financeiro
    "erp.conta_pagar.view", "erp.conta_receber.view", "erp.transacao.view",
    "erp.revisao_baixa.view", "erp.lote_remessa.view", "erp.nf.view",
    "erp.relatorio.view", "erp.cobranca.view",
    "obra.empreend_conta.view", "obra.empreend_custo.view",
    "pdca.contrato.view", "pdca.medicao.view",
    # dado pessoal de cliente e fornecedor
    "cadastro.cliente_doc.view", "cadastro.cliente_banco.view",
    "cadastro.fornecedor_banco.view",
    "crm.lead.view", "crm.contato.view",
    # saúde e segurança do trabalho
    "pdca.ocorrencia.view",
    # a trilha de quem fez o quê
    "plataforma.auditoria.view",
})

#: As perguntas que não são código do catálogo.
CLASSE_DE_USA_MODULO = A      # a porta do módulo: a ação dentro dele tem a própria classe
CLASSE_DE_ADMINISTRA = B      # "é admin?" abre escrita
CLASSE_DE_SUPERVISIONA = B    # "é o supervisor?" abre a base-mãe e o incidente LGPD


def classe_do_codigo(codigo: str) -> str:
    if codigo in CRITICOS:
        return C
    if codigo.endswith(".view") and codigo not in LEITURAS_SENSIVEIS:
        return A
    return B
