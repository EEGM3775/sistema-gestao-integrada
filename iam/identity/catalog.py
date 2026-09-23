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
#    placeholder (dms/pdca) entram quando ganharem backend.
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
    # --- Orçamento — planilha orçamentária e controle de custo (módulo 'orcamento') ---
    #     A base referencial (SINAPI/ORSE) é catálogo PÚBLICO de plataforma: só
    #     leitura pela API e escrita por comando de importação, daí não haver
    #     `.edit` nela. Adotar um item da base ESCREVE no catálogo do tenant, então
    #     é permissão própria (quem consulta preço não necessariamente cadastra).
    Perm("orcamento.base.view", "Consultar bases referenciais (SINAPI/ORSE/SICRO)", "orcamento"),
    Perm("orcamento.base.adotar", "Adotar item da base referencial no catálogo da empresa", "orcamento"),
    #     ORC.9 — o banco de preço **da empresa** deixou de andar junto com
    #     `orcamento.orcamento.edit`. A planta previa a separação: "se na prática
    #     quem cuida do banco de preço virar um papel distinto de quem orça, aí
    #     sim vale criar `orcamento.banco.*`". Virou — decisão do dono
    #     (20/08/2026): quem monta a régua de preço da casa é função específica,
    #     não o orçamentista de plantão. O custo é o de sempre (rebuild da
    #     imagem da IAM + re-seed), pago de uma vez.
    Perm("orcamento.banco.view", "Ver os bancos de preço próprios da empresa", "orcamento"),
    Perm("orcamento.banco.edit", "Manter banco de preço próprio (itens, importação, trava)", "orcamento"),
    Perm("orcamento.orcamento.view", "Ver orçamentos de obra", "orcamento"),
    Perm("orcamento.orcamento.edit", "Criar/editar orçamentos de obra", "orcamento"),
    Perm("orcamento.orcamento.aprovar", "Aprovar orçamento (congela a régua de custo)", "orcamento"),
    Perm("orcamento.orcamento.revisar", "Revisar orçamento aprovado (aditivo/supressão)", "orcamento"),
    Perm("orcamento.item.view", "Ver as linhas da planilha orçamentária", "orcamento"),
    Perm("orcamento.item.edit", "Editar as linhas da planilha orçamentária", "orcamento"),
    Perm("orcamento.relatorio.view", "Ver curva ABC, curva S e orçado × realizado", "orcamento"),
    # --- Maps — dimensão espacial (módulo 'maps', com uma metade de fundação) ---
    #     `mapa.local` é a metade FUNDAÇÃO e por isso está em "base", não em
    #     "maps": georreferenciar obra, fornecedor e almoxarifado é atributo de
    #     cadastro (o ViewSet correspondente não tem `RequireModule`). Se ficasse
    #     no módulo, quem não assina Maps teria SIL e SCM sem saber onde as
    #     coisas ficam — ver docs/modulos/modulomaps.md §1.
    Perm("mapa.local.view", "Ver locais georreferenciados", "base"),
    Perm("mapa.local.edit", "Georreferenciar: criar/editar local e mover o pin", "base"),
    #     Daqui para baixo é o produto: acervo raster, missão de voo e rota têm
    #     custo próprio (storage, motor de rota, geocodificação fina).
    Perm("mapa.feicao.view", "Ver camadas e feições do mapa", "maps"),
    Perm("mapa.feicao.edit", "Desenhar e editar camadas/feições", "maps"),
    Perm("mapa.ortofoto.view", "Ver o acervo de ortofotos no mapa", "maps"),
    Perm("mapa.ortofoto.edit", "Indexar/editar ortofotos do acervo", "maps"),
    Perm("mapa.plano_voo.view", "Ver planos de voo", "maps"),
    Perm("mapa.plano_voo.edit", "Criar, calcular e exportar plano de voo", "maps"),
    Perm("mapa.rota.view", "Ver rotas de entrega", "maps"),
    Perm("mapa.rota.edit", "Planejar e otimizar rotas de entrega", "maps"),
    Perm("mapa.geofence.view", "Ver cercas (geofence) de canteiro", "maps"),
    Perm("mapa.geofence.edit", "Criar e editar cercas de canteiro", "maps"),
    # --- Prancheta — o projeto da obra, aberto em campo (módulo 'prancheta') ---
    #     Diferente do Maps, NÃO há metade de fundação: nenhum outro módulo
    #     depende do acervo de projeto para funcionar, e o custo (storage de
    #     CAD/BIM + motor de conversão) é todo do módulo — então tudo fica atrás
    #     do entitlement. Ver docs/modulos/moduloprancheta.md §2.
    Perm("prancheta.documento.view", "Ver documentos de projeto e suas revisões", "prancheta"),
    Perm("prancheta.documento.edit", "Cadastrar documento e enviar revisão (rascunho)", "prancheta"),
    #     `publicar` é ato SEPARADO de `editar`, de propósito: publicar muda o
    #     que o campo vai executar. Mesma classe do `orcamento.orcamento.aprovar`
    #     — e a lição do D28 é que o verbo separado só vale se alguma persona o
    #     tiver, senão na prática só o admin do tenant publica. A `projetista`
    #     abaixo é essa persona.
    Perm("prancheta.revisao.publicar", "Publicar revisão (torna-a a vigente em campo)", "prancheta"),
    #     PRA.1: reprocessar é verbo próprio porque QUEIMA RECURSO — CPU agora e,
    #     com a APS da PRA.4, dinheiro por tradução. Quem lê o acervo não deve
    #     poder mandar reconverter tudo. Vem com persona (`projetista`) na mesma
    #     fatia, que é a lição do D28.
    Perm("prancheta.conversao.reprocessar", "Reconverter revisão (refaz as derivadas)", "prancheta"),
    #     PRA.3 — marcar e medir. `edit` cobre criar marcação, comentar e medir:
    #     no canteiro é um gesto só ("está errado, e está 12 cm fora"), e separar
    #     medir de apontar daria um interruptor que ninguém saberia quando
    #     desligar.
    Perm("prancheta.marcacao.view", "Ver marcações e medições sobre as pranchas", "prancheta"),
    Perm("prancheta.marcacao.edit", "Marcar, comentar e medir sobre a prancha", "prancheta"),
    #     `resolver` é verbo SEPARADO pelo mesmo motivo de `publicar`: quem
    #     aponta o problema não é quem declara que ele acabou. O `campo` recebe
    #     as duas primeiras e NÃO esta — senão o apontamento se fecharia antes de
    #     o projetista responder, e a fila esvaziaria pelo lado errado.
    Perm("prancheta.marcacao.resolver", "Encerrar ou reabrir marcação", "prancheta"),
    #     `.acervo.importar` entra com a fatia que a implementa (PRA.5). Declarar
    #     agora poria na tela de papéis um interruptor ligado a nada.
    #     (A importação de BCF do PRA.3 NÃO tem permissão própria: ela cria
    #     marcação, então é `marcacao.edit` — e a parede dela é comercial, o
    #     formato `bcf` em payment/planos.py.)
    # --- PDCA — planejar, executar, verificar, agir (módulo 'pdca') ---
    #     A fatia PDCA.0 traz a fundação: onde (a hierarquia construtiva) e
    #     quando (o calendário de trabalho). O resto do vocabulário da §8 da
    #     planta — `pdca.cronograma.*`, `pdca.medicao.*`, `pdca.nc.*` — entra
    #     junto da fatia que o implementa: permissão declarada antes do endpoint
    #     é interruptor ligado a nada na tela de papéis (a lição do D28).
    Perm("pdca.local.view", "Ver a hierarquia de locais da obra", "pdca"),
    Perm("pdca.local.edit", "Criar/editar locais e gerar a árvore em lote", "pdca"),
    Perm("pdca.local.delete", "Excluir local da obra", "pdca"),
    #     Calendário de TRABALHO, não o de eventos (`calendario.evento.*`, base).
    #     São coisas diferentes: um diz quando a empresa trabalha e governa o
    #     prazo do cronograma; o outro é a agenda compartilhada.
    Perm("pdca.calendario.view", "Ver calendários de trabalho e dias úteis", "pdca"),
    Perm("pdca.calendario.edit", "Definir jornada, dias trabalhados e exceções", "pdca"),
    #     PDCA.1 — o plano de tempo. São QUATRO verbos, e não o par
    #     `view`/`edit`, porque montar um plano e assumi-lo perante a obra são
    #     atos diferentes: `edit` mexe no rascunho; `publicar` transforma o
    #     rascunho na régua contra a qual o atraso de todo mundo passa a ser
    #     medido; `replanejar` admite que a régua anterior não vale mais e abre
    #     outra. É a segregação que o ORC.6 provou necessária — quem executa não
    #     aprova —, aplicada ao prazo em vez de ao custo.
    Perm("pdca.cronograma.view", "Ver o cronograma, o caminho crítico e a linha de base", "pdca"),
    Perm("pdca.cronograma.edit", "Montar a WBS, durações e precedências no rascunho", "pdca"),
    Perm("pdca.cronograma.publicar", "Publicar o cronograma (rascunho → vigente)", "pdca"),
    Perm("pdca.cronograma.replanejar", "Replanejar — abrir a versão seguinte com motivo", "pdca"),
    #     PDCA.2 — o avanço. Ler e apontar são **verbos diferentes de pessoas
    #     diferentes**: a diretoria e o gestor de contrato leem o percentual da
    #     obra; quem aponta é quem está no canteiro. E apontar não é `edit`: o
    #     lançamento nasce e não muda mais (o livro é append-only), então um
    #     verbo chamado "editar" prometeria na tela de papéis um poder que a API
    #     não tem.
    Perm("pdca.avanco.view", "Ver o avanço apontado e a curva S realizada", "pdca"),
    Perm("pdca.avanco.apontar", "Apontar avanço de atividade (e estornar o próprio erro)", "pdca"),
    #     PDCA.3 — o dinheiro. O contrato tem o par `view`/`edit` (montar a
    #     planilha contratual é um ato só), mas a medição tem **três** verbos,
    #     porque são três pessoas:
    #       · `view` lê o boletim — gestor, diretoria, quem recebe relatório;
    #       · `apurar` abre a medição do período e confere a proposta que nasceu
    #         do avanço. É o gesto de quem acompanha a obra;
    #       · `atestar` decide. É o que faz o dinheiro sair, e é por isso que ele
    #         não é `edit`: aprovar não é uma edição mais forte, é outro ato.
    #     Quem apura não ateste — a máquina do `nucleo` já recusa o autoatesto
    #     por padrão, e separar os verbos aqui é o que torna essa recusa
    #     configurável (o tenant liga `permite_autoatesto` por escrito) em vez de
    #     acidental.
    Perm("pdca.contrato.view", "Ver contratos de obra, itens e saldo", "pdca"),
    Perm("pdca.contrato.edit", "Cadastrar contrato e montar a planilha contratual", "pdca"),
    Perm("pdca.medicao.view", "Ver medições e o que elas pagam", "pdca"),
    Perm("pdca.medicao.apurar", "Abrir a medição do período e conferir a proposta", "pdca"),
    Perm("pdca.medicao.atestar", "Atestar medição e liberar retenção — o dinheiro sai daqui", "pdca"),
    # PDCA.4 — o contrato deixa de ser imutável, e os dois verbos seguem a
    #     mesma separação da medição: **montar** o aditivo é do gestor de
    #     contratos; **autorizar** a empresa a gastar acima do contratado é
    #     de quem tem alçada. Juntar os dois numa pessoa faria quem negocia
    #     com o empreiteiro aprovar sozinho o próprio acréscimo — que é o
    #     achado clássico de auditoria de obra.
    Perm("pdca.aditivo.edit", "Montar aditivo de contrato (quantidade, preço, item, prazo)", "pdca"),
    Perm("pdca.aditivo.aprovar", "Aprovar aditivo — autoriza gastar acima do contratado", "pdca"),
    # PDCA.5 — o Last Planner. São **cinco** verbos em dois recursos, e a
    #     divisão segue a mesma lição da medição: cada um é um ato diferente de
    #     uma pessoa diferente, não um `edit` mais forte.
    #       · `restricao.view|edit` — registrar o que trava a obra é gesto de
    #         quem planeja e de quem executa, e os dois fazem isso o tempo todo;
    #       · `restricao.remover` é separado porque **é o ato que conclui** (a
    #         §5.4 da planta o põe ao lado de atestar e comprometer): declarar
    #         que a trava saiu libera a atividade para ser assumida, e quem
    #         abre a pendência não é necessariamente quem pode declarar que ela
    #         acabou. Ele carrega a nota que a reunião seguinte lê;
    #       · `programacao.view` lê o quadro e o PPC — diretoria, planejador,
    #         e o mestre que precisa saber o que a equipe assumiu;
    #       · `programacao.comprometer` monta a parede **e** assume: puxar
    #         cartão e assinar embaixo são o mesmo gesto, e separá-los criaria
    #         um papel que arruma o quadro sem responder por ele;
    #       · `programacao.encerrar` julga o que saiu e o que não saiu, e é o
    #         que produz o índice. É separado de `comprometer` pela razão de
    #         sempre nesta casa — quem se compromete não deveria ser o único a
    #         dizer se cumpriu.
    Perm("pdca.restricao.view", "Ver as restrições que travam a obra", "pdca"),
    Perm("pdca.restricao.edit", "Registrar restrição e gerar demanda de compra a partir dela", "pdca"),
    Perm("pdca.restricao.remover", "Remover restrição — declara que a trava saiu e libera o serviço", "pdca"),
    Perm("pdca.programacao.view", "Ver a programação da semana, o PPC e o ranking de causas", "pdca"),
    Perm("pdca.programacao.comprometer", "Montar o quadro da semana e assumir os compromissos", "pdca"),
    Perm("pdca.programacao.encerrar", "Encerrar a semana — julgar o que saiu e registrar a causa do que não saiu", "pdca"),
    #       · `programacao.encerrar_antecipado` é o **sexto** verbo, e nasceu de
    #         um defeito: dava para fechar na segunda-feira a semana que ia até
    #         domingo, julgando como fracasso o que ainda tinha cinco dias de
    #         prazo. O índice que sai daí entra na série valendo o mesmo que os
    #         outros, e ninguém que a lê depois consegue distinguir.
    #         **Não é proibição, é alçada** *(dono, 15/09/2026)*: a obra que para
    #         na quinta de um feriado prolongado precisa da retrospectiva antes
    #         de todo mundo sumir, e trancar de todo faria o time julgar de
    #         memória na segunda seguinte — que é pior do que julgar cedo. Quem
    #         tem este verbo encerra antes **dando motivo por escrito**, e a
    #         semana fica marcada na série.
    Perm("pdca.programacao.encerrar_antecipado", "Encerrar a semana antes de ela acabar — exige motivo, e marca o ponto na série", "pdca"),
    #     PDCA.7 — a máquina de verificação. Sete verbos, e a régua é a de
    #     sempre nesta casa: quem executa não aprova o próprio trabalho.
    #       · `verificacao.view` lê a biblioteca de fichas e as inspeções feitas;
    #       · `verificacao.modelo_edit` **escreve o método da empresa** — o que
    #         toda obra passa a conferir e com que critério numérico. É de quem
    #         responde pela qualidade no escritório, não de quem está na frente:
    #         um `edit` único daria ao campo o poder de afrouxar o critério da
    #         FVS no momento exato em que ela reprovasse, que é quando alguém
    #         quer;
    #       · `verificacao.aplicar` abre a ficha e a responde item a item. É o
    #         gesto do canteiro, e é a razão de a fatia existir;
    #       · `nc.view` lê o defeito, o plano de ação e a eficácia;
    #       · `nc.abrir` registra que algo saiu errado — quem descobre é quem
    #         está lá, a mesma lição do `restricao.edit` da PDCA.5;
    #       · `nc.tratar` monta o 5W2H e declara a ação executada;
    #       · `nc.verificar_eficacia` é **o verbo que dá sentido aos outros
    #         seis**. Ele registra que alguém voltou à frente e olhou, e é o
    #         único que encerra a NC. Separado de `tratar` pela mesma razão que
    #         separa `apurar` de `atestar` na medição: quem consertou não assina
    #         que o conserto funcionou — sem isso o laço do §4.5 vira carimbo.
    #     A planta §8 lista os cinco verbos de escrita; os dois `view` entram
    #     junto porque todo recurso desta casa tem um, e sem eles as telas de
    #     leitura (fila de decisão, painel de conformidade) não teriam porta.
    Perm("pdca.verificacao.view", "Ver as fichas de verificação e a biblioteca de modelos", "pdca"),
    Perm("pdca.verificacao.modelo_edit", "Montar os modelos de verificação — o que a empresa confere e com que critério", "pdca"),
    Perm("pdca.verificacao.aplicar", "Aplicar a ficha numa frente e responder item a item", "pdca"),
    Perm("pdca.nc.view", "Ver as não-conformidades, os planos de ação e a eficácia", "pdca"),
    Perm("pdca.nc.abrir", "Registrar uma não-conformidade", "pdca"),
    Perm("pdca.nc.tratar", "Montar o plano de ação 5W2H e declarar a ação executada", "pdca"),
    Perm("pdca.nc.verificar_eficacia", "Verificar a eficácia e encerrar a NC — o único verbo que a fecha", "pdca"),
    # --- PDCA.8 — SSMA: o diálogo de segurança e a ocorrência ---
    #     **A planta §8 reservou `pdca.ssma.*`, e o reservado não era realizável.**
    #     O catálogo cobra código com exatamente dois pontos (`modulo.recurso.acao`,
    #     conferido em `tests.py`), então `pdca.ssma.dds.registrar` quebraria a
    #     suíte, e um recurso `ssma` único empilharia num só nome coisas que
    #     precisam de donos diferentes. A fatia faz o que a PDCA.7 fez com
    #     `verificacao` e `nc`: **dois recursos**, porque são dois objetos com
    #     ciclos de vida distintos — a roda de conversa antes do turno e o fato
    #     que ninguém queria que acontecesse.
    #
    #     A segregação desta fatia é **registrar × classificar**, e ela é nova
    #     nesta casa. As anteriores separavam quem faz de quem aprova (`apurar` ×
    #     `atestar`, `tratar` × `verificar_eficacia`); esta separa **quem é
    #     medido de quem classifica a própria medida**. Registrar tem de ser
    #     fácil e de baixo atrito — o quase-acidente é o dado mais valioso da
    #     segurança e o mais fácil de não anotar —, mas dizer *"foi acidente com
    #     afastamento, e foram nove dias perdidos"* muda o indicador pelo qual a
    #     própria obra é cobrada. Fossem o mesmo verbo, o encarregado cujo bônus
    #     depende da taxa de frequência classificaria o próprio acidente.
    #       · `dds.view` lê os diálogos e a lista de presença;
    #       · `dds.registrar` abre a roda e colhe a presença. É gesto de canteiro,
    #         no molde do `avanco.apontar` e do `nc.abrir`;
    #       · `ocorrencia.view` lê o que aconteceu — **sem o bloco clínico**, que
    #         tem verbo próprio abaixo;
    #       · `ocorrencia.registrar` é a porta larga, de propósito. Quem viu o
    #         andaime ceder é quem está lá;
    #       · `ocorrencia.classificar` decide tipo, afastamento e dias perdidos —
    #         os três campos de que a taxa de frequência e a de gravidade nascem;
    #       · `ocorrencia.emitir_cat` registra que a CAT foi emitida e guarda o
    #         protocolo. É da família do `erp.nf.emitir`: ato para **terceiro**,
    #         com prazo em lei (1º dia útil; imediato na morte) e multa por
    #         omissão. Quem o exerce no mundo real é o RH, que é quem fala com o
    #         INSS — por isso ele **não** vai para a persona de segurança;
    #       · `ocorrencia.dado_medico` abre natureza da lesão, CID e atestado.
    #         É a **primeira PII do grupo `pdca`** (LGPD art. 11, dado de saúde),
    #         e nasce separada do `view` pela mesma régua do `rh.dado_medico`:
    #         para classificar o acidente ninguém precisa do diagnóstico.
    Perm("pdca.dds.view", "Ver os diálogos de segurança e quem esteve presente", "pdca"),
    Perm("pdca.dds.registrar", "Registrar o diálogo de segurança e colher a lista de presença", "pdca"),
    Perm("pdca.ocorrencia.view", "Ver as ocorrências de segurança — quase-acidente, incidente e acidente", "pdca"),
    Perm("pdca.ocorrencia.registrar", "Registrar uma ocorrência de segurança", "pdca"),
    Perm("pdca.ocorrencia.classificar", "Classificar a ocorrência — tipo, afastamento e dias perdidos", "pdca"),
    Perm("pdca.ocorrencia.emitir_cat", "Registrar a emissão da CAT e o protocolo — prazo legal de 1 dia útil", "pdca"),
    Perm("pdca.ocorrencia.dado_medico", "Abrir o bloco clínico da ocorrência — lesão, CID e atestado (dado de saúde)", "pdca"),
    # --- Obras/empreendimentos e cadastros base (sem entitlement de módulo) ---
    #     O percentual da etapa é digitado à mão desde sempre. Com atividades do
    #     PDCA vinculadas a ela, ele passa a ser **apurado** — e esta permissão é
    #     a que devolve a caneta a alguém (planta do PDCA §11.2). Nasce no grupo
    #     `base`, e não no `pdca`: quem a exerce é o dono da etapa, que existe
    #     mesmo em tenant que não contrata o módulo.
    Perm("obra.etapa.percentual_manual", "Digitar o percentual da etapa mesmo quando ele é apurado pelo cronograma", "base"),
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
    #     Tipo de item é recurso à parte de `cadastro.item` de propósito:
    #     cadastrar item é trabalho diário de quem compra e de quem orça, mas
    #     **definir um tipo** muda como o sistema calcula todos os itens que o
    #     usam (encargo social, entrada na relação de compra, saldo em estoque).
    #     Mesma classe de ato que criar/excluir cliente — decisão de cadastro-
    #     mestre, entregue pelo admin do tenant a quem responde por ele.
    Perm("cadastro.tipo_item.view", "Ver os tipos próprios de item da empresa", "base"),
    Perm("cadastro.tipo_item.edit", "Criar/editar tipo próprio de item (natureza e flags)", "base"),
    Perm("cadastro.cliente_doc.view", "Ver CPF/CNPJ do cliente (PII)", "base"),
    Perm("cadastro.cliente_banco.view", "Ver dados bancários do cliente (PII)", "base"),
    Perm("cadastro.cliente_banco.edit", "Editar dados bancários do cliente (PII)", "base"),
    # Venda de unidade — separada de `cadastro.cliente` de propósito. Registrar
    # uma venda compromete estoque (a unidade sai da praça) e gerar o carnê cria
    # títulos a receber no ERP: são atos comerciais e financeiros, não edição de
    # cadastro. Enquanto dividiam a mesma permissão, quem podia corrigir um
    # telefone podia vender um lote e emitir a dívida do comprador.
    Perm("cadastro.venda.view", "Ver vendas/aquisições de unidades", "base"),
    Perm("cadastro.venda.edit", "Registrar e alterar venda de unidade", "base"),
    Perm("cadastro.venda.gerar_carne", "Gerar o carnê da venda (cria títulos a receber)", "base"),
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
    Perm("plataforma.lixo.restaurar", "Restaurar item da lixeira", "plataforma"),
    #     Purgar saiu de dentro de `.restaurar` (D116): restaurar devolve dado à
    #     circulação, purgar **destrói antes do prazo** o que ainda dava para
    #     recuperar. Quem confere o que foi apagado por engano não é
    #     necessariamente quem pode encurtar a janela de 15 dias que o plano
    #     vendeu — e `gestor_lixo` continua tendo os dois pelo `.*`.
    Perm("plataforma.lixo.purgar", "Purgar item da lixeira antes do prazo (irreversível)", "plataforma"),
    #     A escada de atesto (PDCA.0) mora no `nucleo` e é de PLATAFORMA: quantas
    #     assinaturas o dinheiro precisa antes de sair é decisão da empresa, e
    #     vale para a medição de obra hoje e para o pagamento acima de alçada do
    #     ERP depois. **Atestar não tem permissão aqui** de propósito: quem manda
    #     é o degrau, que declara a permissão que exige (§8 da planta do PDCA) —
    #     um `…aprovacao.atestar` genérico daria a quem o tivesse a alçada de
    #     todos os degraus de uma vez, que é o oposto do que a escada existe para
    #     fazer.
    #     **`.edit` fica com o administrador do tenant de propósito**, e isto é
    #     uma exceção consciente à lição do D28 (permissão sem persona só o admin
    #     exerce). Criar um degrau que exige a permissão X é, na prática,
    #     **decidir quem tem alçada sobre o dinheiro** — mesma classe de ato que
    #     `plataforma.papel.gerir`, que também é só do admin pelo mesmo motivo.
    #     Uma persona de fábrica com este verbo poderia rebaixar a própria escada
    #     que a controla. `.view` vai para a `diretoria`: quem responde pela
    #     empresa precisa enxergar quantas assinaturas o dinheiro atravessa.
    Perm("plataforma.fluxo_aprovacao.view", "Ver os fluxos de aprovação da empresa", "plataforma"),
    Perm("plataforma.fluxo_aprovacao.edit", "Definir a escada de aprovação (níveis e alçadas)", "plataforma"),
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
        "cadastro.venda.view",
        "mapa.local.view", "mapa.feicao.view", "mapa.ortofoto.view",
        "prancheta.documento.view", "prancheta.marcacao.view",
        "plataforma.config.view", "plataforma.integracao.view",
        # Quantas assinaturas o dinheiro atravessa antes de sair é leitura de
        # quem responde pela empresa. Definir a escada continua sendo do admin.
        "plataforma.fluxo_aprovacao.view",
        # Lê o planejamento da obra pelo mesmo motivo que lê o custo dela.
        "pdca.local.view", "pdca.calendario.view", "pdca.cronograma.view",
        "pdca.avanco.view",
        # PDCA.3 — **o único verbo de escrita desta persona, e ele é uma
        # assinatura, não uma edição.** A §5.3 da planta põe "fiscal / gerente"
        # na fila de atesto, e o gerente que existe hoje neste catálogo é este.
        # Dar o `atestar` a quem já lê contrato e medição é o que torna a
        # escada montável no primeiro dia, sem o tenant precisar desenhar uma
        # persona antes de emitir a primeira medição. O que ela **não** ganha é
        # `apurar`: quem monta o boletim é o `gestor_contratos`, e juntar os dois
        # numa pessoa é exatamente o que a §8 manda separar.
        "pdca.contrato.view", "pdca.medicao.view", "pdca.medicao.atestar",
        # PDCA.4: aprova aditivo pelo mesmo motivo — é alçada, não edição.
        "pdca.aditivo.aprovar",
        # PDCA.5 — o **PPC é indicador de diretoria** (§5.3 da planta põe o
        # diretor na carteira multi-obra com SPI/CPI, PPC e desvio). Leitura
        # apenas: o ciclo semanal é da obra, e um diretor que julgasse o
        # compromisso de uma equipe que ele não acompanha produziria um índice
        # sem relação com o que aconteceu no canteiro.
        "pdca.programacao.view", "pdca.restricao.view",
        # PDCA.7 — **lê a qualidade e verifica a eficácia**, que é o segundo
        # verbo de escrita desta persona em todo o catálogo e, como o primeiro,
        # é uma assinatura e não uma edição. Ela não trata (montar o 5W2H é de
        # quem está na obra) e não aplica ficha; o que ela faz é o ato que
        # encerra — voltar e conferir se o conserto pegou. É a mesma forma do
        # `medicao.atestar`: quem responde pela empresa não executa, decide.
        "pdca.verificacao.view", "pdca.nc.view", "pdca.nc.verificar_eficacia",
        # PDCA.8 — **lê a segurança, e só isso**. Taxa de frequência e ranking de
        # causa são leitura de direção, da mesma família do PPC. Não registra,
        # não classifica e não abre o bloco clínico: a diretoria da construtora
        # não tem por que ver o CID de um pedreiro.
        "pdca.dds.view", "pdca.ocorrencia.view",
    ],
    # RH completo, MENOS o prontuário médico (segregação médico × gestor).
    "rh_gestor": [
        "rh.funcionario.*", "rh.cpf.view", "rh.cargo.*",
        "rh.documento.*", "rh.folha.*", "rh.dado_bancario.*",
        # PDCA.8 — **é ele quem comunica a CAT**, e o verbo mora aqui e em
        # nenhum outro lugar. A CAT é ato para terceiro (o INSS) com prazo em
        # lei e multa por omissão, na família do `erp.nf.emitir`; quem fala com
        # o INSS é o RH, não o canteiro. Ele lê a ocorrência para montá-la e
        # **não** a classifica — o tipo e os dias de afastamento são de quem
        # esteve na obra.
        "pdca.ocorrencia.view", "pdca.ocorrencia.emitir_cat",
    ],
    # Médico do trabalho: só PII médica.
    #
    # PDCA.8 — o bloco clínico da ocorrência (natureza da lesão, CID, atestado)
    # é dado de saúde do art. 11 da LGPD, vizinho de porta do ASO, e por isso
    # tem o mesmo dono. É a primeira PII do grupo `pdca`.
    "rh_medico": [
        "rh.funcionario.view", "rh.dado_medico.*",
        "pdca.ocorrencia.view", "pdca.ocorrencia.dado_medico",
    ],
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
        # Materializa o carnê: os títulos nascem nas contas a receber que esta
        # persona já governa.
        "cadastro.venda.view", "cadastro.venda.gerar_carne",
    ],
    # Tesouraria: cobrança/boletos Asaas + conciliação (precisa do banco do cliente).
    "tesouraria": [
        "erp.conta_receber.view", "erp.conta_receber.baixar",
        "erp.cobranca.*", "erp.relatorio.view",
        "cadastro.cliente.view", "cadastro.cliente_doc.view",
        "cadastro.cliente_banco.*", "cadastro.venda.view",
    ],
    # Fiscal: emissão e gestão de NF (precisa do CPF/CNPJ do cliente p/ a NF).
    "fiscal": [
        "erp.nf.*", "erp.conta_receber.view", "erp.relatorio.view",
        "cadastro.cliente.view", "cadastro.cliente_doc.view",
    ],
    # Comercial: CRM completo + documento do cliente (fechamento/contrato).
    # Vende a unidade, mas **não** gera o carnê: emitir os títulos a receber é
    # ato do financeiro, depois da conferência da proposta.
    "comercial": [
        "crm.*", "cadastro.cliente.*", "cadastro.cliente_doc.view",
        "cadastro.venda.view", "cadastro.venda.edit",
    ],
    # Engenharia: empreendimentos, obras, diário (+ IA), agenda, custos.
    # Georreferencia e desenha no mapa: quem responde pela obra é quem sabe onde
    # o canteiro começa e o que há dentro dele.
    "engenharia": [
        "obra.empreendimento.*", "obra.empreend_custo.*", "obra.obra.*",
        "obra.diario.*", "ia.analise.*", "calendario.evento.*",
        "cadastro.fornecedor.view", "drone.projeto.view", "drone.medicao.view",
        "mapa.local.*", "mapa.feicao.*", "mapa.ortofoto.view", "mapa.geofence.*",
        # Lê o projeto da obra que gere; publicar revisão é do `projetista`.
        "prancheta.documento.view",
        # Mas RESOLVE marcação: quem gere a obra é quem decide que o apontamento
        # do campo está encerrado. Sem isto, o D28 se repetiria — verbo criado,
        # e na prática só o admin do tenant o exerce.
        "prancheta.marcacao.*",
        # PDCA.0: quem responde pela obra desenha o esqueleto dela. A árvore de
        # locais é cadastro de obra antes de ser insumo de cronograma — é o
        # endereço da não-conformidade e do apontamento, que esta persona já
        # governa pelo diário. O calendário de trabalho é só leitura: mudar a
        # jornada muda o prazo de todas as obras que herdam o padrão, e isso é
        # do `planejador`.
        #
        # PDCA.1: **lê** o cronograma, e não o edita. Quem responde pela obra
        # precisa saber o que está no caminho crítico para decidir onde põe a
        # equipe — mas mudar o plano publicado é replanejar, e replanejar é o
        # ato que move o prazo contratual da obra inteira.
        "pdca.local.*", "pdca.calendario.view", "pdca.cronograma.view",
        #
        # PDCA.2: **aponta**. Quem responde pela obra é quem responde pelo quanto
        # ela andou — é a mesma pessoa que já assina o diário. E leva o
        # `percentual_manual` junto: com o cronograma vinculado à etapa o número
        # passa a ser apurado, e destravar a caneta na exceção (a etapa que o
        # plano ainda não cobre) é decisão de quem gere a obra, não de TI.
        "pdca.avanco.*", "obra.etapa.percentual_manual",
        #
        # PDCA.5: **o Last Planner é desta persona, inteiro.** A §5.3 da planta
        # põe "engenheiro de obra" no quadro de programação, no apontamento e
        # nas restrições — e a `engenharia` é quem esta casa já tem nesse papel
        # (a PDCA.2 recusou criar uma gêmea dela, e a decisão vale aqui igual).
        # Leva os verbos todos porque o ciclo é dela de ponta a ponta: registra
        # a trava, declara que ela saiu, monta o quadro, assume e julga.
        #
        # **Inclusive o `encerrar_antecipado`**, e é deliberado: quem sabe que a
        # obra vai parar na quinta é quem está nela. O curinga o alcança, e a
        # trava que importa não é a de quem pode — é a do **motivo por escrito**,
        # que fica na série para a reunião seguinte ler.
        "pdca.restricao.*", "pdca.programacao.*",
        #
        # PDCA.7: **aplica, abre e trata — e não verifica a própria eficácia.**
        # Quem responde pela obra é quem inspeciona a frente, registra o defeito
        # e monta o 5W2H que o conserta; é o mesmo par de mãos que já aponta o
        # avanço e assina o diário. O que ela não tem é o verbo que **encerra**:
        # declarar que o próprio conserto funcionou é conferir o próprio dever
        # de casa, e é exatamente a separação que a medição já faz entre apurar
        # e atestar. Quem encerra é a `diretoria` ou o `fiscal_de_obra`.
        #
        # E não leva `verificacao.modelo_edit`: escrever o método da empresa
        # muda o que **toda** obra passa a conferir, e isso é de quem responde
        # pela qualidade, não de quem responde por uma obra.
        "pdca.verificacao.view", "pdca.verificacao.aplicar",
        "pdca.nc.view", "pdca.nc.abrir", "pdca.nc.tratar",
        #
        # PDCA.8: conduz o diálogo, registra a ocorrência **e a classifica**.
        # Aqui ela vai um verbo além do `campo`, e a razão é a mesma que lhe deu
        # o `restricao.remover`: classificar é ato de quem responde pela obra, e
        # o encarregado da frente onde o acidente aconteceu não é essa pessoa.
        # Onde o tenant tiver SESMT de verdade, o `tecnico_seguranca` divide o
        # verbo com ela — mas a construtora de uma obra só não tem TST, e sem
        # isto a ocorrência dela nasceria sem classificação nenhuma.
        #
        # **Não emite CAT** (é do RH, que fala com o INSS) nem abre o bloco
        # clínico.
        "pdca.dds.*", "pdca.ocorrencia.view", "pdca.ocorrencia.registrar",
        "pdca.ocorrencia.classificar",
    ],
    # Campo: apontamentos do diário + upload de drone (sem gestão).
    # Lê a prancha vigente no celular — é o caso de uso central da Prancheta, e
    # é justamente quem NÃO pode publicar: conferir a medida antes de executar é
    # trabalho de campo; decidir qual desenho vale, não.
    "campo": [
        "obra.obra.view", "obra.diario.view", "obra.diario.create",
        "ia.analise.view", "calendario.evento.view",
        "drone.projeto.view", "drone.imagem.upload",
        "mapa.local.view", "mapa.feicao.view",
        "prancheta.documento.view",
        # PRA.3 — apontar o que está errado no desenho É o trabalho do campo, e
        # é a razão de a fatia existir. Sem `resolver`: quem aponta não fecha.
        "prancheta.marcacao.view", "prancheta.marcacao.edit",
        # PDCA.2 — apontar quanto a frente andou é o gesto do canteiro, e é a
        # razão de a fatia existir. Lê o cronograma para saber **em que**
        # apontar; não o edita, que é ato de quem assume o prazo.
        "pdca.cronograma.view", "pdca.avanco.view", "pdca.avanco.apontar",
        # PDCA.5 — **quem descobre a trava é quem está no canteiro.** O mestre
        # vê que o material não chegou e que a frente anterior não liberou a
        # área; obrigá-lo a telefonar para alguém registrar isso é o que faz o
        # log de restrição nascer desatualizado. Ele **não** remove: declarar
        # que a trava saiu libera o serviço para ser assumido, e esse é o ato de
        # quem responde pela obra. E lê a programação porque precisa saber com o
        # que a equipe dele se comprometeu na semana.
        "pdca.restricao.view", "pdca.restricao.edit", "pdca.programacao.view",
        # PDCA.7 — **é a persona do 5º instrumento** (planta §5.2: uma mão,
        # luva, sol, uma pergunta por vez). Responder a ficha e fotografar o
        # defeito são o gesto do canteiro, e a fatia existe para que eles
        # aconteçam onde o defeito está, não numa planilha à noite. Não trata:
        # montar o plano de ação é decidir o que a obra vai fazer a respeito, e
        # isso é de quem responde por ela.
        "pdca.verificacao.view", "pdca.verificacao.aplicar",
        "pdca.nc.view", "pdca.nc.abrir",
        # **A porta da SSMA é larga de propósito** (PDCA.8). Quem conduz a roda
        # antes do turno é o encarregado, e quem viu o andaime ceder é quem
        # estava lá — exigir que ele telefone para alguém registrar é o que faz
        # o quase-acidente não ser registrado, e o quase-acidente é o dado mais
        # valioso da segurança. O que ele **não** faz é `classificar`: dizer
        # "foi com afastamento, nove dias" mexe no indicador pelo qual a própria
        # frente dele é cobrada.
        "pdca.dds.view", "pdca.dds.registrar",
        "pdca.ocorrencia.view", "pdca.ocorrencia.registrar",
    ],
    # Analista de drone: processamento e medições. Ganhou o acervo e a missão —
    # é a mesma pessoa que hoje já opera o voo, agora com o plano na plataforma.
    "drone_analista": [
        "drone.projeto.*", "drone.imagem.upload",
        "drone.processamento.executar", "drone.medicao.*",
        "mapa.ortofoto.*", "mapa.plano_voo.*", "mapa.local.view", "mapa.feicao.view",
    ],
    # Topógrafo: a persona do território. Marca, mede e voa — não mexe em
    # financeiro nem em cadastro comercial.
    "topografo": [
        "mapa.local.*", "mapa.feicao.*", "mapa.ortofoto.*", "mapa.plano_voo.*",
        "mapa.geofence.*", "mapa.rota.view",
        "obra.obra.view", "obra.empreendimento.view",
        "drone.projeto.view", "drone.medicao.view",
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
        "mapa.local.view",
    ],
    # Suprimentos: catálogo de produtos, ofertas de fornecedores e centros de custo.
    # `mapa.local.view` + `mapa.rota.view` porque distância entrega→canteiro é
    # critério de compra tanto quanto preço e reputação.
    "suprimentos": [
        "scm.*", "cadastro.fornecedor.view", "cadastro.item.*", "cadastro.tipo_item.view",
        # PDCA.5 — o outro lado do seam: a restrição de material vira demanda
        # nesta fila, e quem compra precisa ver **o que ela está segurando** na
        # obra. Sem isso, a demanda gerada por uma restrição chega aqui como
        # mais uma linha, sem a informação que decide a urgência dela.
        "pdca.restricao.view",
        "mapa.local.view", "mapa.rota.view",
    ],
    # Almoxarife: estoque & logística interna. `sil.*` + leitura do item-mestre
    # (o que se estoca) e dos selects do domínio (obra do canteiro/requisição,
    # fornecedor da devolução/lote).
    "almoxarife": [
        "sil.*", "cadastro.item.view", "cadastro.tipo_item.view",
        "obra.obra.view", "cadastro.fornecedor.view",
        "rh.funcionario.view",  # picker de colaborador em EPI/ferramentaria
        # Roteirização de transferência e entrega ao canteiro é trabalho de
        # almoxarifado, não de mapa: quem carrega o caminhão define a ordem.
        "mapa.rota.*", "mapa.local.view", "mapa.geofence.view",
    ],
    # Orçamentista: monta, aprova e revisa a planilha orçamentária. Precisa GERIR
    # o item-mestre (adotar da base referencial cria item no catálogo) e LER o que
    # dá custo real — compras do SCM e consumo/custo médio do SIL —, porque é
    # disso que sai o preço honesto do próximo orçamento.
    #
    # `aprovar`/`revisar` entraram aqui em 26/07/2026 por decisão do dono do
    # produto (D28). Até então a régua dizia que congelar o custo era "de quem
    # responde pela obra" e a permissão ficava de fora — só que ela não estava em
    # NENHUMA persona de fábrica, e o efeito prático era que apenas o
    # administrador do tenant conseguia aprovar (ele bypassa o RequirePermission).
    # Alçada é decisão do dono; quem quiser separar de novo cria uma persona só
    # de aprovação e tira as duas linhas daqui.
    # `orcamento.banco.*` e `cadastro.tipo_item.*` entram aqui por padrão para o
    # módulo continuar utilizável no dia seguinte ao deploy — e são exatamente as
    # duas linhas que o admin do tenant tira daqui quando quiser um curador de
    # preços separado de quem orça. É o desenho pedido: destacável, não
    # obrigatoriamente destacado.
    "orcamentista": [
        "orcamento.base.*", "orcamento.banco.*", "orcamento.orcamento.*",
        "orcamento.item.*", "orcamento.relatorio.view",
        "cadastro.item.*", "cadastro.tipo_item.*",
        "obra.obra.view", "obra.empreendimento.view",
        "scm.oferta.view", "scm.pedido.view", "sil.saldo.view", "sil.relatorio.view",
    ],
    # Projetista: dono do acervo de projeto. É a única persona de fábrica que
    # PUBLICA revisão — o ato que define qual desenho o canteiro executa. Lê obra
    # e etapa porque é onde a prancha se pendura; não toca em financeiro, cadastro
    # comercial nem estoque.
    "projetista": [
        "prancheta.documento.*", "prancheta.revisao.publicar",
        # Dono do acervo é também quem responde o apontamento do campo e o
        # encerra — é o outro lado do laço que a PRA.3 fecha.
        "prancheta.marcacao.*",
        # Reprocessar fica aqui e só aqui: é quem conhece o arquivo que sabe se a
        # derivada saiu torta. `engenharia` lê o acervo, mas mandar reconverter o
        # acervo inteiro de uma obra é gasto, não leitura.
        "prancheta.conversao.reprocessar",
        "obra.obra.view", "obra.empreendimento.view",
        "mapa.local.view",
    ],
    # Planejador: a persona que a PDCA.0 estreia. Desenha o esqueleto da obra
    # (a hierarquia de locais) e diz quando se trabalha — e é só isso que existe
    # para fazer nesta fatia. Lê o orçamento porque a régua de custo por etapa é
    # o que vai pesar a atividade na PDCA.1, e lê obra/mapa porque é onde a
    # árvore se pendura. Não toca em financeiro, cadastro comercial nem estoque.
    #
    # **As outras quatro personas da §8 da planta** — `engenheiro_de_obra`,
    # `gestor_contratos`, `tecnico_qualidade` e o fiscal de obra — chegam com a
    # fatia que lhes dá verbo (PDCA.2, .3, .5, .7). Criá-las agora produziria
    # papel que só sabe ler dois cadastros, e a tela de papéis passaria a
    # oferecer quatro personas indistinguíveis entre si. É a mesma lição do D28,
    # do outro lado: permissão sem persona não se exerce, persona sem permissão
    # não se explica.
    #
    # (O nome do fiscal de obra terá de ser `fiscal_de_obra`: `fiscal` já é a
    # persona de nota fiscal, e são pessoas diferentes em empresas diferentes.)
    "planejador": [
        # PDCA.1: é a persona do plano de tempo, e por isso leva os quatro
        # verbos do cronograma — inclusive `publicar` e `replanejar`. Numa
        # construtora com departamento de planejamento, é este cargo que assume
        # o prazo; separar `publicar` daqui só faria sentido se houvesse alguém
        # acima dele no organograma do planejamento, e não há — quem está acima
        # é a diretoria, que lê.
        "pdca.local.*", "pdca.calendario.*", "pdca.cronograma.*",
        # PDCA.2: **lê** o avanço — é contra o plano dele que o desvio é
        # medido. Apontar é do canteiro; o planejador que apontasse o
        # próprio avanço estaria conferindo o próprio dever de casa.
        "pdca.avanco.view",
        # PDCA.3: lê o contrato e a medição — o plano dele é o denominador do
        # que se mede. Não apura nem ateste: são atos do contrato, não do prazo.
        "pdca.contrato.view", "pdca.medicao.view",
        # PDCA.5: **lê** a restrição e o quadro, e não assume nem julga. O
        # make-ready e o compromisso são atos de quem está com a equipe na
        # semana; o que interessa ao planejamento é a leitura — quais travas
        # ameaçam o caminho crítico, e o que o PPC diz sobre a confiabilidade do
        # plano que ele desenhou. Um planejador que julgasse o próprio plano
        # cumprido estaria de novo conferindo o próprio dever de casa.
        "pdca.restricao.view", "pdca.programacao.view",
        # PDCA.7: **lê** a qualidade, e só. O retrabalho é o que estoura o
        # prazo que ele desenhou — a NC aberta numa frente do caminho crítico é
        # informação de planejamento —, mas inspecionar, tratar e encerrar são
        # atos de quem está na obra.
        "pdca.verificacao.view", "pdca.nc.view",
        "obra.obra.view", "obra.empreendimento.view", "obra.diario.view",
        "orcamento.orcamento.view", "orcamento.item.view", "orcamento.relatorio.view",
        "calendario.evento.view", "mapa.local.view",
        "prancheta.documento.view",
    ],
    # PDCA.3 — a persona que a planta §8 previu, entrando com a fatia que lhe dá
    # verbo. Ela é **nova de verdade**, e não gêmea de ninguém: a `engenharia`
    # responde pela execução (aponta avanço, assina diário), o `financeiro` paga
    # o título depois de pronto, e entre os dois havia um vazio — quem fecha o
    # contrato com o empreiteiro, confere a medição do período e a leva à
    # assinatura. Numa construtora esse cargo existe com nome próprio.
    #
    # **Apura e não ateste.** Leva `pdca.medicao.apurar`, não `atestar`: montar o
    # boletim e decidir que ele vira dinheiro são os dois lados que a §8 manda
    # separar. Quem ateste é quem o tenant puser nos degraus da escada — em
    # geral a `diretoria` ou um papel próprio do cliente.
    "gestor_contratos": [
        "pdca.contrato.*", "pdca.medicao.view", "pdca.medicao.apurar",
        # PDCA.4: **monta** o aditivo e não o aprova, exatamente como a
        # medição — quem negocia o acréscimo não é quem o autoriza.
        "pdca.aditivo.edit",
        # Lê o plano e o avanço porque é deles que a medição nasce: conferir a
        # proposta sem poder ver o apontamento que a gerou é conferir no escuro.
        "pdca.cronograma.view", "pdca.avanco.view", "pdca.local.view",
        "obra.obra.view", "obra.empreendimento.view", "obra.diario.view",
        "cadastro.fornecedor.view",
        # O orçamento é a régua contra a qual o preço contratado é julgado.
        "orcamento.orcamento.view", "orcamento.item.view",
        # **Lê** o título que a medição gerou, e não mexe nele: o ERP decide
        # quando o dinheiro sai da conta (§7 da planta — o PDCA não paga).
        "erp.conta_pagar.view",
        "plataforma.fluxo_aprovacao.view",
    ],
    # PDCA.7 — as duas últimas personas que a planta §8 previu, entrando com a
    # fatia que lhes dá verbo. E elas passam no teste que a §8 impõe: nenhuma é
    # gêmea de alguém que já existe.
    #
    # O `tecnico_qualidade` é o único cargo desta casa cujo trabalho **é** a
    # máquina de verificação. A `engenharia` responde pela obra e inspeciona de
    # passagem; este escreve o método (`modelo_edit`, que nenhuma outra persona
    # tem), aplica a ficha e monta o plano de ação — e não toca em cronograma,
    # contrato nem medição, que é o que o separa de todas as outras.
    #
    # **Ele não verifica a própria eficácia**, e essa é a linha inteira da
    # fatia: quem escreveu a ficha, reprovou o item e montou o conserto não
    # assina que o conserto funcionou. É a forma que a medição já tem entre
    # `apurar` e `atestar`, aplicada à qualidade.
    "tecnico_qualidade": [
        "pdca.verificacao.*", "pdca.nc.view", "pdca.nc.abrir", "pdca.nc.tratar",
        # Lê o plano para saber **em que** aplicar a ficha, e a árvore de locais
        # porque é ela o endereço da não-conformidade (planta §4.1).
        "pdca.cronograma.view", "pdca.local.view",
        # Trava a frente quando o defeito é grave: é o seam vivo com o Last
        # Planner, e sem `restricao.edit` o `gerar-restricao` da NC seria um
        # botão que recusa. Não remove — declarar que a trava saiu libera o
        # serviço, e esse é ato de quem responde pela obra.
        "pdca.restricao.view", "pdca.restricao.edit", "pdca.programacao.view",
        # Ancora a NC no desenho e a exporta em BCF (planta §6).
        "prancheta.documento.view", "prancheta.marcacao.view",
        "prancheta.marcacao.edit",
        "obra.obra.view", "obra.diario.view", "calendario.evento.view",
    ],
    # O `fiscal_de_obra` é o outro lado: ele **não executa nada** e assina os
    # dois atos que encerram — a medição e a não-conformidade. É o cargo que a
    # obra pública brasileira chama assim (o representante que fiscaliza e
    # atesta) e que a obra privada chama de gerente de contrato do cliente.
    #
    # **O nome tem `_de_obra` porque `fiscal` já é a persona de nota fiscal**
    # neste catálogo, e são pessoas diferentes em empresas diferentes — a §8 da
    # planta registra a colisão.
    #
    # Ele repete o `medicao.atestar` da `diretoria` de propósito: a diretoria o
    # tem para que a escada seja montável no primeiro dia, e esta persona existe
    # para o tenant que tem o cargo de verdade e não quer pôr o diretor em toda
    # fila de atesto.
    "fiscal_de_obra": [
        "pdca.verificacao.view", "pdca.nc.view", "pdca.nc.verificar_eficacia",
        "pdca.medicao.view", "pdca.medicao.atestar",
        "pdca.contrato.view", "pdca.aditivo.aprovar",
        "pdca.cronograma.view", "pdca.avanco.view", "pdca.local.view",
        "pdca.programacao.view", "pdca.restricao.view",
        # PDCA.8 — lê o que a obra registrou de segurança, na mesma régua do
        # resto desta persona: ela confere e assina, não executa. Sem verbo de
        # escrita aqui, e sem o bloco clínico.
        "pdca.dds.view", "pdca.ocorrencia.view",
        "obra.obra.view", "obra.empreendimento.view", "obra.diario.view",
        "prancheta.documento.view", "prancheta.marcacao.view",
        "plataforma.fluxo_aprovacao.view",
    ],
    # O `tecnico_seguranca` é o **TST do SESMT** (NR-4), e é o cargo que a obra
    # brasileira acima de certo porte é obrigada a ter. Ele estreia com a PDCA.8
    # pela régua de sempre: a persona chega com a fatia que lhe dá verbo.
    #
    # **Ele passa no teste da gêmea, e por pouco — então vale dizer onde.** Com o
    # `tecnico_qualidade` ele divide o miolo da verificação (aplicar ficha, abrir
    # e tratar NC, travar a frente), porque inspeção de segurança **é** a mesma
    # máquina da §4.5 com outro domínio. O que os separa são os dois extremos:
    #   · ele tem `dds.*` e `ocorrencia.*`, que nenhuma outra persona de obra
    #     tem — e é por isso que esses verbos **não** foram dados ao técnico de
    #     qualidade, senão as duas personas viravam a mesma lista;
    #   · ele **não** tem `verificacao.modelo_edit`, que é o verbo exclusivo do
    #     técnico de qualidade: escrever o método da empresa é um cargo só.
    #
    # **E ele não emite CAT.** Parece contraintuitivo — é o profissional de
    # segurança —, mas quem protocola CAT no INSS é o RH, e dar-lhe o verbo
    # criaria duas portas para um ato com prazo legal e multa. Ele classifica; o
    # RH comunica. Também **não** vê o bloco clínico: para dizer "acidente com
    # afastamento, nove dias" ninguém precisa do CID.
    #
    # `sil.epi.view` é o que faz o seam do EPI funcionar sem a PDCA.8 duplicar a
    # entrega (planta §4.6): ele lê a ficha de EPI de quem está na obra, e só
    # ela — não o estoque, não o inventário, não a devolução ao fornecedor.
    "tecnico_seguranca": [
        "pdca.dds.*", "pdca.ocorrencia.view", "pdca.ocorrencia.registrar",
        "pdca.ocorrencia.classificar",
        # A inspeção de segurança é a máquina da PDCA.7 no domínio `seguranca` —
        # ele aplica a ficha e trata o desvio, sem escrever o modelo.
        "pdca.verificacao.view", "pdca.verificacao.aplicar",
        "pdca.nc.view", "pdca.nc.abrir", "pdca.nc.tratar",
        # Interditar a frente é o dente da fatia: risco grave vira `Restricao` e
        # a atividade sai do quadro da semana. Não remove — declarar que o risco
        # cessou é ato de quem responde pela obra, a mesma linha do D.
        "pdca.restricao.view", "pdca.restricao.edit", "pdca.programacao.view",
        "pdca.cronograma.view", "pdca.local.view",
        # Lê a ficha de EPI de quem está na obra (planta §4.6) — a entrega
        # continua sendo do SIL, que é o dono do estoque.
        "sil.epi.view",
        "rh.funcionario.view",
        "obra.obra.view", "obra.diario.view",
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
    "engenharia": "Empreendimentos, obras, diário de obra (com IA), agenda técnica e o avanço físico da obra (aponta e destrava o percentual da etapa).",
    "campo": "Registro de diário de obra, apontamento de avanço das frentes e envio de imagens de drone. Sem gestão.",
    "drone_analista": "Processamento, medições e anotações de projetos de drone.",
    "auditor": "Somente leitura ampla + trilha de auditoria e operações de titular (LGPD).",
    "suprimentos": "Suprimentos: catálogo de produtos, ofertas/preços de fornecedores e centros de custo.",
    "almoxarife": "Estoque e logística interna: saldos, movimentações, requisições, transferências, devoluções, lotes e inventário.",
    "orcamentista": "Planilha orçamentária da obra: bases referenciais (SINAPI/ORSE), composições, curva ABC e orçado × realizado. Aprova e revisa o orçamento.",
    "planejador": "Planejamento da obra: cronograma (WBS, CPM, linha de base), hierarquia de locais, calendário de trabalho e leitura do avanço apontado.",
    "gestor_contratos": "Contratos de empreitada: planilha contratual, medição do período apurada a partir do avanço e acompanhamento do saldo. Apura a medição; quem ateste é a escada de aprovação.",
    "tecnico_qualidade": "Qualidade da obra: monta os modelos de verificação (FVS, segurança, ambiental, entrega), aplica a ficha no canteiro, registra a não-conformidade e monta o plano de ação. Não verifica a própria eficácia — quem encerra a NC é o fiscal ou a diretoria.",
    "fiscal_de_obra": "Fiscalização: atesta a medição, aprova aditivo e verifica a eficácia do tratamento das não-conformidades. Só assina — não apura, não trata e não executa.",
    "tecnico_seguranca": "Segurança do trabalho (TST/SESMT): conduz o diálogo de segurança, registra e classifica a ocorrência, aplica a inspeção de segurança, trata o desvio e interdita a frente quando o risco é grave. Lê a ficha de EPI de quem está na obra. Não comunica CAT (é do RH) nem abre o bloco clínico.",
    "topografo": "Território: georreferenciamento, camadas e feições do mapa, acervo de ortofotos e planos de voo.",
    "projetista": "Acervo de projeto: cadastra documentos, envia revisões e PUBLICA a revisão vigente — a que o canteiro executa.",
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
