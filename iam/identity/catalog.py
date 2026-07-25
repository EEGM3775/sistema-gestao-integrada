"""Catálogo de permissões — a fonte única de verdade do RBAC (Fase 9, fatia A).

Por que em código (e não só no banco): *endpoints* e *serializers* referenciam
permissões por código; o vocabulário precisa ser **finito, global e versionado**.
É daqui que vem a previsibilidade — não de papéis fixos (AD-9 §2.1). A tabela
`Permissao` da IAM é **sincronizada** deste registry por `manage.py sync_authz`.

Formato do código: ``modulo.recurso.acao``.
  - Ações CRUD padrão: ``view``, ``create``, ``edit``, ``delete``.
  - Verbos de domínio quando a ação não é CRUD: ``baixar``, ``emitir``,
    ``processar``, ``exportar``, ``restaurar``…
  - Campo de PII é um recurso próprio: ``rh.dado_medico.view`` protege o
    prontuário; a máscara de campo (fatia C) lê estes mesmos códigos.

Papéis (`Perfil`) são **por tenant** e compostos deste pool. Os TEMPLATES abaixo
são a linha de base de fábrica com que um tenant novo nasce; ele pode clonar e
recompor (AD-9 §2.2). O que é global e imutável é o **catálogo**; o que é do
tenant é o **agrupamento** em papéis.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Perm:
    code: str
    nome: str
    modulo: str  # código do Modulo vendável, ou "base"/"plataforma" (sem entitlement)


# ---------------------------------------------------------------------------
# 1. CATÁLOGO — vocabulário atômico, agrupado por módulo do produto.
#    Cobre TODOS os módulos implementados (não só o RH). Módulos ainda
#    placeholder (aps/dms/pdca/scm/sil/maps) entram quando ganharem backend.
# ---------------------------------------------------------------------------
CATALOGO: tuple[Perm, ...] = (
    # --- RH (módulo 'rh') — cadastro + PII sensível separada por recurso ---
    Perm("rh.funcionario.view", "Ver funcionários", "rh"),
    Perm("rh.funcionario.create", "Cadastrar funcionário", "rh"),
    Perm("rh.funcionario.edit", "Editar funcionário", "rh"),
    Perm("rh.funcionario.delete", "Excluir funcionário", "rh"),
    Perm("rh.cpf.view", "Ver CPF do funcionário (PII)", "rh"),
    Perm("rh.cargo.view", "Ver cargos", "rh"),
    Perm("rh.cargo.edit", "Gerir cargos", "rh"),
    Perm("rh.documento.view", "Ver documentos do funcionário", "rh"),
    Perm("rh.documento.edit", "Gerir documentos do funcionário", "rh"),
    Perm("rh.dado_medico.view", "Ver prontuário/ASO (PII sensível)", "rh"),
    Perm("rh.dado_medico.edit", "Editar prontuário/ASO (PII sensível)", "rh"),
    Perm("rh.dado_bancario.view", "Ver dados bancários (PII sensível)", "rh"),
    Perm("rh.dado_bancario.edit", "Editar dados bancários (PII sensível)", "rh"),
    Perm("rh.folha.view", "Ver folha e salários", "rh"),
    Perm("rh.folha.edit", "Editar folha e pagamentos", "rh"),
    # --- ERP financeiro (módulo 'erp_financeiro') ---
    Perm("erp.conta_pagar.view", "Ver contas a pagar", "erp_financeiro"),
    Perm("erp.conta_pagar.create", "Lançar conta a pagar", "erp_financeiro"),
    Perm("erp.conta_pagar.edit", "Editar conta a pagar", "erp_financeiro"),
    Perm("erp.conta_pagar.delete", "Excluir conta a pagar", "erp_financeiro"),
    Perm("erp.conta_pagar.baixar", "Dar baixa em conta a pagar", "erp_financeiro"),
    Perm("erp.conta_receber.view", "Ver contas a receber", "erp_financeiro"),
    Perm("erp.conta_receber.create", "Lançar conta a receber", "erp_financeiro"),
    Perm("erp.conta_receber.edit", "Editar conta a receber", "erp_financeiro"),
    Perm("erp.conta_receber.delete", "Excluir conta a receber", "erp_financeiro"),
    Perm("erp.conta_receber.baixar", "Dar baixa em conta a receber", "erp_financeiro"),
    Perm("erp.transacao.view", "Ver o ledger (transações financeiras)", "erp_financeiro"),
    Perm("erp.revisao_baixa.view", "Ver a fila de baixas em revisão", "erp_financeiro"),
    Perm("erp.revisao_baixa.resolver", "Resolver baixa em revisão", "erp_financeiro"),
    Perm("erp.centro_custo.view", "Ver centros de custo/rateio", "erp_financeiro"),
    Perm("erp.centro_custo.edit", "Gerir centros de custo/rateio", "erp_financeiro"),
    Perm("erp.lote_remessa.view", "Ver lotes de remessa", "erp_financeiro"),
    Perm("erp.lote_remessa.create", "Gerar lote de remessa", "erp_financeiro"),
    Perm("erp.nf.view", "Ver notas fiscais", "erp_financeiro"),
    Perm("erp.nf.edit", "Lançar/editar nota fiscal (inclui atualização de status)", "erp_financeiro"),
    Perm("erp.nf.emitir", "Emitir nota fiscal", "erp_financeiro"),
    Perm("erp.nf.cancelar", "Cancelar nota fiscal", "erp_financeiro"),
    Perm("erp.relatorio.view", "Ver relatórios financeiros (DRE, fluxo)", "erp_financeiro"),
    # --- Cobranças Asaas (entra via 'erp_financeiro') ---
    Perm("erp.cobranca.view", "Ver cobranças/boletos", "erp_financeiro"),
    Perm("erp.cobranca.emitir", "Emitir cobrança/boleto (Asaas)", "erp_financeiro"),
    Perm("erp.cobranca.conciliar", "Conciliar retorno/divergências Asaas", "erp_financeiro"),
    # --- CRM (módulo 'crm') — recursos reais: campanha, lead, conta, contato,
    #     oportunidade, produto-da-oportunidade (o do S5) e interação/agenda ---
    Perm("crm.campanha.view", "Ver campanhas", "crm"),
    Perm("crm.campanha.edit", "Gerir campanhas", "crm"),
    Perm("crm.lead.view", "Ver leads", "crm"),
    Perm("crm.lead.create", "Criar lead", "crm"),
    Perm("crm.lead.edit", "Editar lead", "crm"),
    Perm("crm.lead.delete", "Excluir lead", "crm"),
    Perm("crm.conta.view", "Ver contas (empresas)", "crm"),
    Perm("crm.conta.edit", "Gerir contas (empresas)", "crm"),
    Perm("crm.contato.view", "Ver contatos", "crm"),
    Perm("crm.contato.edit", "Gerir contatos", "crm"),
    Perm("crm.oportunidade.view", "Ver oportunidades", "crm"),
    Perm("crm.oportunidade.create", "Criar oportunidade", "crm"),
    Perm("crm.oportunidade.edit", "Editar oportunidade", "crm"),
    Perm("crm.oportunidade.delete", "Excluir oportunidade", "crm"),
    Perm("crm.oportunidade_produto.view", "Ver produtos da oportunidade", "crm"),
    Perm("crm.oportunidade_produto.edit", "Gerir produtos da oportunidade", "crm"),
    Perm("crm.interacao.view", "Ver interações/agenda", "crm"),
    Perm("crm.interacao.create", "Registrar interação/agendar", "crm"),
    # --- Drone (módulo 'drone') ---
    Perm("drone.projeto.view", "Ver projetos de drone", "drone"),
    Perm("drone.projeto.create", "Criar projeto de drone", "drone"),
    Perm("drone.projeto.edit", "Editar projeto de drone", "drone"),
    Perm("drone.projeto.delete", "Excluir projeto de drone", "drone"),
    Perm("drone.imagem.upload", "Enviar imagens para processamento", "drone"),
    Perm("drone.processamento.executar", "Disparar processamento (ODM)", "drone"),
    Perm("drone.medicao.view", "Ver medições/anotações", "drone"),
    Perm("drone.medicao.edit", "Criar/editar medições/anotações", "drone"),
    # --- SCM — suprimentos (módulo 'scm') — fatia 1: catálogo + centro de custo ---
    #     (demanda/cotação/pedido/recebimento entram com suas fatias)
    Perm("scm.produto.view", "Ver produtos do catálogo de suprimentos", "scm"),
    Perm("scm.produto.edit", "Gerir produtos do catálogo de suprimentos", "scm"),
    Perm("scm.oferta.view", "Ver ofertas/preços de fornecedores", "scm"),
    Perm("scm.oferta.edit", "Gerir ofertas/preços de fornecedores", "scm"),
    Perm("scm.centro_custo.view", "Ver centros de custo do SCM", "scm"),
    Perm("scm.centro_custo.edit", "Gerir centros de custo do SCM", "scm"),
    # fatia 2: demanda (pivô) + cotação/proposta, com verbos de domínio
    Perm("scm.demanda.view", "Ver demandas de compra", "scm"),
    Perm("scm.demanda.edit", "Criar/editar demandas de compra", "scm"),
    Perm("scm.demanda.publicar", "Publicar demanda na rede (marketplace)", "scm"),
    Perm("scm.cotacao.view", "Ver cotações e propostas", "scm"),
    Perm("scm.cotacao.edit", "Gerir cotações e registrar propostas", "scm"),
    Perm("scm.cotacao.adjudicar", "Adjudicar cotação (escolher vencedora)", "scm"),
    # fatia 3: pedido (duas vias) → recebimento + avaliação
    Perm("scm.pedido.view", "Ver pedidos de compra", "scm"),
    Perm("scm.pedido.edit", "Editar pedidos de compra", "scm"),
    Perm("scm.pedido.criar", "Gerar pedido (compra direta / de cotação)", "scm"),
    Perm("scm.recebimento.view", "Ver recebimentos", "scm"),
    Perm("scm.recebimento.edit", "Registrar recebimentos", "scm"),
    Perm("scm.avaliacao.view", "Ver avaliações de fornecedores", "scm"),
    Perm("scm.avaliacao.edit", "Avaliar fornecedores", "scm"),
    # --- SIL — estoque & logística interna (módulo 'sil') ---
    #     locais, saldo valorado, ledger de movimentação, requisição da obra,
    #     transferência, devolução, rastreabilidade (lote) e inventário.
    Perm("sil.local.view", "Ver locais de estoque (almoxarifado/canteiro)", "sil"),
    Perm("sil.local.edit", "Gerir locais de estoque", "sil"),
    Perm("sil.saldo.view", "Ver saldo valorado de estoque", "sil"),
    Perm("sil.saldo.edit", "Definir ponto de reposição / gerar demanda de reposição", "sil"),
    Perm("sil.movimentacao.view", "Ver o ledger de movimentações", "sil"),
    Perm("sil.movimentacao.edit", "Registrar entrada/saída/ajuste", "sil"),
    Perm("sil.requisicao.view", "Ver requisições de material", "sil"),
    Perm("sil.requisicao.edit", "Criar/editar requisições de material", "sil"),
    Perm("sil.requisicao.aprovar", "Aprovar requisição (reserva o saldo)", "sil"),
    Perm("sil.requisicao.atender", "Atender requisição (baixa o saldo)", "sil"),
    Perm("sil.transferencia.view", "Ver transferências entre locais", "sil"),
    Perm("sil.transferencia.edit", "Criar/editar transferências entre locais", "sil"),
    Perm("sil.transferencia.executar", "Executar transferência entre locais", "sil"),
    Perm("sil.devolucao.view", "Ver devoluções", "sil"),
    Perm("sil.devolucao.edit", "Criar/editar devoluções", "sil"),
    Perm("sil.devolucao.executar", "Executar devolução (ao fornecedor/estoque)", "sil"),
    Perm("sil.lote.view", "Ver lotes/validade (rastreabilidade)", "sil"),
    Perm("sil.lote.edit", "Gerir lotes/validade", "sil"),
    Perm("sil.inventario.view", "Ver inventários", "sil"),
    Perm("sil.inventario.edit", "Criar/editar inventário (contagem)", "sil"),
    Perm("sil.inventario.fechar", "Fechar inventário (gera ajustes)", "sil"),
    # EPI (NR-6), ferramentaria (comodato) e relatórios de gestão (curva ABC, aplicado).
    Perm("sil.epi.view", "Ver entregas de EPI (NR-6)", "sil"),
    Perm("sil.epi.edit", "Registrar/devolver EPI (NR-6)", "sil"),
    Perm("sil.ferramenta.view", "Ver ferramentaria (ferramentas/empréstimos)", "sil"),
    Perm("sil.ferramenta.edit", "Gerir ferramentaria (emprestar/devolver/manutenção)", "sil"),
    Perm("sil.relatorio.view", "Ver relatórios de estoque (curva ABC, aplicado por obra)", "sil"),
    # --- Obras/empreendimentos e cadastros base (sem entitlement de módulo) ---
    Perm("obra.empreendimento.view", "Ver empreendimentos", "base"),
    Perm("obra.empreendimento.edit", "Gerir empreendimentos", "base"),
    Perm("obra.empreend_conta.view", "Ver contas bancárias do empreendimento", "base"),
    Perm("obra.empreend_conta.edit", "Gerir contas bancárias do empreendimento", "base"),
    Perm("obra.empreend_custo.view", "Ver custos do empreendimento", "base"),
    Perm("obra.empreend_custo.edit", "Gerir custos do empreendimento", "base"),
    Perm("obra.obra.view", "Ver obras", "base"),
    Perm("obra.obra.edit", "Gerir obras (etapas, documentos)", "base"),
    Perm("obra.diario.view", "Ver diário de obra", "base"),
    Perm("obra.diario.create", "Registrar diário de obra", "base"),
    Perm("obra.diario.edit", "Editar diário de obra", "base"),
    # IA do diário (funcoesia) — análise de imagens; sem entitlement próprio.
    Perm("ia.analise.view", "Ver análises de IA do diário", "base"),
    Perm("ia.analise.executar", "Disparar análise de IA de imagens", "base"),
    # Calendário (modulocalendar) — agenda compartilhada; sem entitlement próprio.
    Perm("calendario.evento.view", "Ver eventos do calendário", "base"),
    Perm("calendario.evento.create", "Criar evento no calendário", "base"),
    Perm("calendario.evento.edit", "Editar evento do calendário", "base"),
    Perm("calendario.evento.delete", "Excluir evento do calendário", "base"),
    # Cadastros — clientes/fornecedores + dados bancários (PII) segregados.
    Perm("cadastro.cliente.view", "Ver clientes", "base"),
    Perm("cadastro.cliente.edit", "Gerir clientes (contratos, documentos)", "base"),
    Perm("cadastro.cliente_doc.view", "Ver CPF/CNPJ do cliente (PII)", "base"),
    Perm("cadastro.cliente_banco.view", "Ver dados bancários do cliente (PII)", "base"),
    Perm("cadastro.cliente_banco.edit", "Editar dados bancários do cliente (PII)", "base"),
    Perm("cadastro.fornecedor.view", "Ver fornecedores", "base"),
    Perm("cadastro.fornecedor.edit", "Gerir fornecedores (produtos/serviços)", "base"),
    Perm("cadastro.fornecedor_banco.view", "Ver dados bancários do fornecedor (PII)", "base"),
    Perm("cadastro.fornecedor_banco.edit", "Editar dados bancários do fornecedor (PII)", "base"),
    # Catálogo-mestre de plataforma (app-fundação `catalogo`; item bem/serviço/etc.)
    Perm("cadastro.item.view", "Ver itens do catálogo-mestre", "base"),
    Perm("cadastro.item.edit", "Gerir itens do catálogo-mestre", "base"),
    # --- Plataforma / governança (transversal, sem módulo vendável) ---
    Perm("plataforma.papel.gerir", "Criar/editar/excluir papéis e permissões (personas)", "plataforma"),
    Perm("plataforma.config.view", "Ver configurações do tenant (uploads etc.)", "plataforma"),
    Perm("plataforma.config.edit", "Editar configurações do tenant", "plataforma"),
    Perm("plataforma.integracao.view", "Ver integrações (Google, gateways)", "plataforma"),
    Perm("plataforma.integracao.edit", "Gerir integrações (Google, gateways)", "plataforma"),
    Perm("plataforma.auditoria.view", "Ler a trilha de auditoria (AuditLog)", "plataforma"),
    Perm("plataforma.lgpd.exportar", "Exportar dados de titular (LGPD)", "plataforma"),
    Perm("plataforma.lgpd.excluir", "Excluir/anonimizar titular (LGPD)", "plataforma"),
    Perm("plataforma.lixo.view", "Ver a lixeira", "plataforma"),
    Perm("plataforma.lixo.restaurar", "Restaurar/purgar itens da lixeira", "plataforma"),
)

# Índice por código e conjunto de todos os códigos válidos (para conformidade).
POR_CODIGO: dict[str, Perm] = {p.code: p for p in CATALOGO}
CODIGOS: frozenset[str] = frozenset(POR_CODIGO)


# ---------------------------------------------------------------------------
# 2. TEMPLATES DE PAPEL (personas de fábrica). Um tenant novo nasce com estes;
#    pode clonar e recompor. Wildcard "modulo.recurso.*" e "modulo.*" são
#    aceitos na AUTORIA e expandidos para códigos concretos por expand().
# ---------------------------------------------------------------------------
TEMPLATES_PAPEL: dict[str, list[str]] = {
    # Leitura ampla p/ gestão, sem PII sensível (RH médico/bancário) nem exclusões.
    "diretoria": [
        "rh.funcionario.view", "rh.cargo.view", "rh.folha.view",
        "erp.conta_pagar.view", "erp.conta_receber.view", "erp.centro_custo.view",
        "erp.transacao.view", "erp.nf.view", "erp.cobranca.view", "erp.relatorio.view",
        "crm.campanha.view", "crm.lead.view", "crm.conta.view",
        "crm.oportunidade.view", "crm.interacao.view",
        "drone.projeto.view", "drone.medicao.view",
        "obra.empreendimento.view", "obra.empreend_custo.view",
        "obra.obra.view", "obra.diario.view", "ia.analise.view",
        "calendario.evento.view",
        "cadastro.cliente.view", "cadastro.cliente_doc.view", "cadastro.fornecedor.view",
        "plataforma.config.view", "plataforma.integracao.view",
    ],
    # RH completo, MENOS o prontuário médico (segregação médico × gestor).
    "rh_gestor": [
        "rh.funcionario.*", "rh.cpf.view", "rh.cargo.*",
        "rh.documento.*", "rh.folha.*", "rh.dado_bancario.*",
    ],
    # Médico do trabalho: só PII médica.
    "rh_medico": ["rh.funcionario.view", "rh.dado_medico.*"],
    # Folha de pagamento: salário + dados bancários.
    "rh_financeiro": [
        "rh.funcionario.view", "rh.folha.*", "rh.dado_bancario.*",
    ],
    # ERP contas a pagar/receber + rateio + ledger + revisão de baixa + contas do empreendimento.
    # Gere os dados bancários de cliente e fornecedor (necessário p/ pagar/receber).
    "financeiro": [
        "erp.conta_pagar.*", "erp.conta_receber.*", "erp.centro_custo.*",
        "erp.transacao.view", "erp.revisao_baixa.*", "erp.lote_remessa.*",
        "erp.relatorio.view",
        "obra.empreend_conta.*", "obra.empreend_custo.*",
        "cadastro.fornecedor.view", "cadastro.fornecedor_banco.*",
        "cadastro.cliente.view", "cadastro.cliente_doc.view", "cadastro.cliente_banco.*",
    ],
    # Tesouraria: cobrança/boletos Asaas + conciliação (precisa do banco do cliente).
    "tesouraria": [
        "erp.conta_receber.view", "erp.conta_receber.baixar",
        "erp.cobranca.*", "erp.relatorio.view",
        "cadastro.cliente.view", "cadastro.cliente_doc.view",
        "cadastro.cliente_banco.*",
    ],
    # Fiscal: emissão e gestão de NF (precisa do CPF/CNPJ do cliente p/ a NF).
    "fiscal": [
        "erp.nf.*", "erp.conta_receber.view", "erp.relatorio.view",
        "cadastro.cliente.view", "cadastro.cliente_doc.view",
    ],
    # Comercial: CRM completo + documento do cliente (fechamento/contrato).
    "comercial": ["crm.*", "cadastro.cliente.*", "cadastro.cliente_doc.view"],
    # Engenharia: empreendimentos, obras, diário (+ IA), agenda, custos.
    "engenharia": [
        "obra.empreendimento.*", "obra.empreend_custo.*", "obra.obra.*",
        "obra.diario.*", "ia.analise.*", "calendario.evento.*",
        "cadastro.fornecedor.view", "drone.projeto.view", "drone.medicao.view",
    ],
    # Campo: apontamentos do diário + upload de drone (sem gestão).
    "campo": [
        "obra.obra.view", "obra.diario.view", "obra.diario.create",
        "ia.analise.view", "calendario.evento.view",
        "drone.projeto.view", "drone.imagem.upload",
    ],
    # Analista de drone: processamento e medições.
    "drone_analista": [
        "drone.projeto.*", "drone.imagem.upload",
        "drone.processamento.executar", "drone.medicao.*",
    ],
    # Auditor LGPD: leitura ampla + trilha + operações de titular. READ-ONLY —
    # só permissões `.view` explícitas (nunca `.edit`/`.delete`/PII bancária por wildcard).
    "auditor": [
        "plataforma.auditoria.view", "plataforma.lgpd.*",
        "plataforma.config.view", "plataforma.integracao.view",
        "rh.funcionario.view", "rh.folha.view",
        "erp.conta_pagar.view", "erp.conta_receber.view",
        "erp.transacao.view", "erp.relatorio.view",
        "crm.lead.view", "crm.oportunidade.view",
        "ia.analise.view", "calendario.evento.view",
        "obra.empreendimento.view", "obra.empreend_custo.view",
        "obra.obra.view", "obra.diario.view",
        "cadastro.cliente.view", "cadastro.cliente_doc.view", "cadastro.fornecedor.view",
    ],
    # Suprimentos: catálogo de produtos, ofertas de fornecedores e centros de custo.
    "suprimentos": ["scm.*", "cadastro.fornecedor.view", "cadastro.item.*"],
    # Almoxarife: estoque & logística interna. `sil.*` + leitura do item-mestre
    # (o que se estoca) e dos selects do domínio (obra do canteiro/requisição,
    # fornecedor da devolução/lote).
    "almoxarife": [
        "sil.*", "cadastro.item.view",
        "obra.obra.view", "cadastro.fornecedor.view",
        "rh.funcionario.view",  # picker de colaborador em EPI/ferramentaria
    ],
    # Gestor da lixeira (exclusão reversível — ver arquitetura/lixo.md).
    "gestor_lixo": ["plataforma.lixo.*"],
    # Papel default de leitura básica (antes era morto).
    "operacional": [
        "obra.obra.view", "obra.diario.view", "calendario.evento.view",
        "cadastro.cliente.view", "cadastro.fornecedor.view",
    ],
}


# Descrição legível de cada persona de fábrica (o usuário-admin lê isto na tela).
DESCRICOES_TEMPLATE: dict[str, str] = {
    "diretoria": "Leitura ampla de gestão (dashboards, financeiro, obras, CRM) — sem PII sensível de RH nem exclusões.",
    "rh_gestor": "Gestão completa de RH: cadastro, cargos, documentos, folha e dados bancários. Não vê prontuário médico.",
    "rh_medico": "Médico do trabalho: acesso ao prontuário e ASO (dados médicos) dos funcionários.",
    "rh_financeiro": "Folha de pagamento: salários e dados bancários dos funcionários.",
    "financeiro": "Contas a pagar e receber, baixas, centros de custo e relatórios financeiros.",
    "tesouraria": "Cobranças e boletos (Asaas), baixa de recebíveis e conciliação.",
    "fiscal": "Emissão e gestão de notas fiscais.",
    "comercial": "CRM completo: leads, oportunidades, contas, contatos e agenda comercial.",
    "engenharia": "Empreendimentos, obras, diário de obra (com IA) e agenda técnica.",
    "campo": "Registro de diário de obra e envio de imagens de drone. Sem gestão.",
    "drone_analista": "Processamento, medições e anotações de projetos de drone.",
    "auditor": "Somente leitura ampla + trilha de auditoria e operações de titular (LGPD).",
    "suprimentos": "Suprimentos: catálogo de produtos, ofertas/preços de fornecedores e centros de custo.",
    "almoxarife": "Estoque e logística interna: saldos, movimentações, requisições, transferências, devoluções, lotes e inventário.",
    "gestor_lixo": "Restauração e expurgo de itens da lixeira (exclusão reversível).",
    "operacional": "Leitura básica de obras, diário, agenda e cadastros.",
}


def expand(padroes: list[str]) -> list[str]:
    """Expande wildcards (``rh.*``, ``rh.folha.*``) para códigos concretos do
    catálogo, preservando a ordem e sem duplicar. Um código exato inexistente é
    mantido para que o teste de conformidade acuse (falha alto, não silencia)."""
    vistos: dict[str, None] = {}
    for p in padroes:
        if p.endswith(".*"):
            prefixo = p[:-1]  # mantém o ponto: "rh." casa "rh.funcionario.view"
            for code in POR_CODIGO:
                if code.startswith(prefixo):
                    vistos.setdefault(code, None)
        else:
            vistos.setdefault(p, None)
    return list(vistos)


def codigos_do_template(nome: str) -> list[str]:
    """Códigos concretos de um template de papel de fábrica."""
    return expand(TEMPLATES_PAPEL[nome])


def templates_invalidos() -> dict[str, list[str]]:
    """Diagnóstico de conformidade: por template, os códigos que NÃO estão no
    catálogo (deve ser vazio). Usado pelo teste e pelo comando de sync."""
    problemas: dict[str, list[str]] = {}
    for nome, padroes in TEMPLATES_PAPEL.items():
        fora = [c for c in expand(padroes) if c not in CODIGOS]
        if fora:
            problemas[nome] = fora
    return problemas
