console.log('[analises-ia] script carregado');

// Estado global da aplicação
let tiposAnaliseDisponiveis = [];
let documentosCarregados = [];
let documentosDisponiveis = []; // Para nova análise
let currentUser = null;

// Carregar documentos disponíveis para nova análise
async function carregarDocumentosDisponiveis() {
    console.log('📄 Carregando documentos disponíveis para análise...');
    
    try {
        console.log('🔗 Fazendo requisição para /api/diario/documentos/');
        const response = await fetch('/api/diario/documentos/');
        
        console.log('📡 Status da resposta:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('🚨 Erro na resposta:', errorText);
            throw new Error('Erro ' + response.status + ': ' + errorText);
        }

        const data = await response.json();
        console.log('📊 Dados recebidos:', data);
        
        documentosDisponiveis = data || [];
        console.log('✅ ' + documentosDisponiveis.length + ' documentos disponíveis carregados');
        
        // Atualiza a interface
        preencherSelectDocumentos();
        
    } catch (error) {
        console.error('❌ Erro ao carregar documentos:', error);
        mostrarNotificacao('Erro ao carregar documentos: ' + error.message, 'error');
    }
}


// Preencher o select de documentos
function preencherSelectDocumentos() {
    const selectDocumento = document.getElementById('selectDocumento');
    if (!selectDocumento) return;
    
    // Limpar opções existentes
    selectDocumento.innerHTML = '<option value="">Selecione um documento...</option>';
    
    // Adicionar documentos disponíveis
    documentosDisponiveis.forEach(doc => {
        const option = document.createElement('option');
        option.value = doc.id;
        option.textContent = (doc.nome_original || doc.nome) + ' - ' + (doc.obra_nome || 'Obra não definida');
        selectDocumento.appendChild(option);
    });
    
    console.log('📋 Select preenchido com ' + documentosDisponiveis.length + ' documentos');
}

// Carregar tipos de análise disponíveis
async function carregarTiposAnalise() {
    console.log('🔬 Carregando tipos de análise...');
    
    try {
        const response = await fetch('/api/ia/analise/tipos/');
        
        if (!response.ok) {
            throw new Error('Erro ' + response.status + ': ' + response.statusText);
        }

        const data = await response.json();
        console.log('📊 Resposta dos tipos:', data);
        
        // Extrair tipos de todas as categorias se for um objeto estruturado
        if (data && data.tipos_por_categoria) {
            let todosTipos = [];
            for (const categoria in data.tipos_por_categoria) {
                todosTipos = todosTipos.concat(data.tipos_por_categoria[categoria]);
            }
            tiposAnaliseDisponiveis = todosTipos;
        } else {
            tiposAnaliseDisponiveis = data.tipos || data || [];
        }
        
        console.log('✅ ' + tiposAnaliseDisponiveis.length + ' tipos de análise carregados:', tiposAnaliseDisponiveis);
        
        // Atualiza a interface
        preencherSelectTiposAnalise();
        
    } catch (error) {
        console.error('❌ Erro ao carregar tipos de análise:', error);
        mostrarNotificacao('Erro ao carregar tipos de análise: ' + error.message, 'error');
    }
}

// Preencher o select de tipos de análise
function preencherSelectTiposAnalise() {
    const selectTipoAnalise = document.getElementById('selectTipoAnalise');
    if (!selectTipoAnalise) return;
    
    // Limpar opções existentes
    selectTipoAnalise.innerHTML = '<option value="">Selecione o tipo de análise...</option>';
    
    // Adicionar tipos disponíveis
    tiposAnaliseDisponiveis.forEach(tipo => {
        const option = document.createElement('option');
        option.value = tipo.id || tipo.codigo;
        option.textContent = (tipo.nome || tipo.name || '') + ' - ' + (tipo.descricao || tipo.description || '');
        selectTipoAnalise.appendChild(option);
    });
    
    console.log('📋 Select preenchido com ' + tiposAnaliseDisponiveis.length + ' tipos de análise');
}

// Iniciar nova análise
async function iniciarNovaAnalise() {
    console.log('🚀 Iniciando nova análise...');
    
    const selectDocumento = document.getElementById('selectDocumento');
    const selectTipoAnalise = document.getElementById('selectTipoAnalise');
    
    const documentoId = selectDocumento ? selectDocumento.value : null;
    const tipoAnalise = selectTipoAnalise ? selectTipoAnalise.value : null;
    
    if (!documentoId) {
        mostrarNotificacao('Selecione um documento para analisar', 'warning');
        return;
    }
    
    if (!tipoAnalise) {
        mostrarNotificacao('Selecione o tipo de análise', 'warning');
        return;
    }
    
    // Encontrar documento selecionado
    const documento = documentosDisponiveis.find(d => d.id == documentoId);
    if (!documento) {
        mostrarNotificacao('Documento não encontrado', 'error');
        return;
    }
    
    // Encontrar tipo de análise selecionado
    const tipoAnaliseObj = tiposAnaliseDisponiveis.find(t => t.codigo === tipoAnalise);
    if (!tipoAnaliseObj) {
        mostrarNotificacao('Tipo de análise não encontrado', 'error');
        return;
    }
    
    console.log('📝 Iniciando análise "' + tipoAnaliseObj.nome + '" para documento "' + documento.nome + '"');
    
    try {
        // Mostrar loading
        mostrarLoading('Iniciando análise...');
        
        const response = await fetch('/api/ia/analise/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                documento_id: documentoId,
                tipo_analise: tipoAnalise
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Erro ' + response.status);
        }
        
        const data = await response.json();
        console.log('✅ Análise iniciada:', data);
        
        mostrarNotificacao(
            'Análise "' + tipoAnaliseObj.nome + '" iniciada com sucesso! A análise será processada em segundo plano.', 
            'success'
        );
        
        // Resetar formulário
        selectDocumento.value = '';
        selectTipoAnalise.value = '';
        
        // Recarregar documentos com análise após um pequeno delay
        setTimeout(() => {
            carregarDocumentosComAnalise();
        }, 2000);
        
    } catch (error) {
        console.error('❌ Erro ao iniciar análise:', error);
        mostrarNotificacao('Erro ao iniciar análise: ' + error.message, 'error');
    } finally {
        esconderLoading();
    }
}

// Carregar documentos com análise
async function carregarDocumentosComAnalise() {
    console.log('📊 Carregando documentos com análise...');
    
    try {
        mostrarLoading('Carregando análises...');
        
        const response = await fetch('/api/diario/documentos-com-analise/');
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('🚨 Erro na resposta:', errorText);
            throw new Error('Erro ' + response.status + ': ' + errorText);
        }

        const data = await response.json();
        console.log('📊 Dados de análises recebidos:', data);
        
        documentosCarregados = data.documentos || [];
        console.log('✅ ' + documentosCarregados.length + ' documentos com análise carregados');
        
        // Atualiza a interface
        exibirDocumentosComAnalise();
        
    } catch (error) {
        console.error('❌ Erro ao carregar documentos com análise:', error);
        mostrarNotificacao('Erro ao carregar análises: ' + error.message, 'error');
    } finally {
        esconderLoading();
    }
}

// Exibir documentos com análise
function exibirDocumentosComAnalise() {
    console.log('🎨 Exibindo documentos com análise...');
    
    const container = document.getElementById('documentosAnalises');
    if (!container) {
        console.error('❌ Container não encontrado');
        return;
    }
    
    if (documentosCarregados.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-search"></i><h3>Nenhuma análise encontrada</h3><p>Comece criando uma nova análise usando o formulário acima.</p></div>';
        return;
    }
    
    container.innerHTML = '';
    
    documentosCarregados.forEach(documento => {
        const card = criarCardDocumento(documento);
        container.appendChild(card);
    });
    
    console.log('✅ ' + documentosCarregados.length + ' cards de documento exibidos');
}

// Criar card para um documento
function criarCardDocumento(documento) {
    console.log('🎴 Criando card para documento:', documento);
    console.log('📊 Status original do documento:', documento.status);
    
    const card = document.createElement('div');
    card.className = 'documento-card';
    card.setAttribute('data-documento-id', documento.id);
    
    // Usar funções utilitárias para mapear status
    const statusExibicao = mapearStatus(documento.status);
    const statusClass = 'status-' + statusExibicao;
    const textoStatus = obterTextoStatus(statusExibicao);
    
    console.log('🔄 Status mapeado:', documento.status, '=>', statusExibicao, '=>', textoStatus);
    
    // HTML do card usando concatenação
    let cardHTML = '<div class="documento-header">';
    cardHTML += '<h3>' + (documento.nome_original || documento.nome) + '</h3>';
    cardHTML += '<div class="obra-info"><i class="fas fa-building"></i> ' + (documento.obra_nome || 'Obra não definida') + '</div>';
    
    // Adicionar info de arquivo se diferente do nome
    if (documento.nome_arquivo && documento.nome_arquivo !== documento.nome) {
        cardHTML += '<div class="arquivo-info"><i class="fas fa-file"></i> ' + documento.nome_arquivo + '</div>';
    }
    
    cardHTML += '</div>';
    
    // Corpo do card
    cardHTML += '<div class="documento-body">';
    
    // Imagem se disponível
    if (documento.url_imagem) {
        cardHTML += '<div class="documento-imagem">';
        cardHTML += '<img src="' + documento.url_imagem + '" alt="' + (documento.nome_original || documento.nome) + '" ';
        cardHTML += 'style="max-width: 100%; height: 150px; object-fit: cover; border-radius: 8px; margin-bottom: 15px;">';
        cardHTML += '</div>';
    }
    
    cardHTML += '<div class="documento-info">';
    cardHTML += '<div class="info-item"><span class="info-label"><i class="fas fa-calendar"></i> Data:</span><span>' + formatDate(documento.data_criacao) + '</span></div>';
    cardHTML += '<div class="info-item"><span class="info-label"><i class="fas fa-microscope"></i> Análise:</span><span>' + (documento.tipo_analise || 'Não especificado') + '</span></div>';
    cardHTML += '<div class="info-item"><span class="info-label"><i class="fas fa-info-circle"></i> Status:</span>';
    cardHTML += '<span class="status-badge ' + statusClass + '">' + textoStatus + '</span></div>';
    
    if (documento.data_ultima_analise) {
        cardHTML += '<div class="info-item"><span class="info-label"><i class="fas fa-clock"></i> Última análise:</span><span>' + formatDate(documento.data_ultima_analise) + '</span></div>';
    }
    
    cardHTML += '</div></div>';
    
    // Ações
    cardHTML += '<div class="documento-actions">';
    const detalhesDisabled = statusExibicao !== 'completa' ? 'disabled' : '';
    cardHTML += '<button class="btn btn-primary" onclick="verDetalhesAnalise(' + documento.id + ')" ' + detalhesDisabled + '>';
    cardHTML += '<i class="fas fa-eye"></i> Ver Detalhes</button>';
    cardHTML += '<button class="btn btn-secondary" onclick="reprocessarAnalise(' + documento.id + ')">';
    cardHTML += '<i class="fas fa-redo"></i> Reprocessar</button>';
    cardHTML += '</div>';
    
    card.innerHTML = cardHTML;
    
    return card;
}

// Ver detalhes da análise
async function verDetalhesAnalise(documentoId) {
    console.log('👁️ Visualizando detalhes da análise para documento ' + documentoId);
    
    try {
        mostrarLoading('Carregando detalhes...');
        
        const response = await fetch('/api/diario/documento-analise/' + documentoId + '/');
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Erro ' + response.status);
        }
        
        const data = await response.json();
        console.log('📊 Detalhes da análise recebidos:', data);
        
        // Mostrar modal com detalhes
        mostrarModalDetalhes(data);
        
    } catch (error) {
        console.error('❌ Erro ao carregar detalhes:', error);
        mostrarNotificacao('Erro ao carregar detalhes: ' + error.message, 'error');
    } finally {
        esconderLoading();
    }
}

// Reprocessar análise
async function reprocessarAnalise(documentoId) {
    console.log('🔄 Reprocessando análise para documento ' + documentoId);
    
    // Encontrar o documento
    const documento = documentosCarregados.find(d => d.id === documentoId);
    if (!documento) {
        mostrarNotificacao('Documento não encontrado', 'error');
        return;
    }
    
    const confirmacao = confirm('Deseja reprocessar a análise do documento "' + (documento.nome_original || documento.nome) + '"?\n\nIsso pode levar alguns minutos.');
    if (!confirmacao) return;
    
    try {
        mostrarLoading('Reprocessando análise...');
        
        const response = await fetch('/api/diario/reprocessar-analise/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                documento_id: documentoId
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Erro ' + response.status);
        }
        
        const data = await response.json();
        console.log('✅ Reprocessamento iniciado:', data);
        
        mostrarNotificacao('Análise sendo reprocessada! O resultado será atualizado em breve.', 'success');
        
        // Recarregar documentos após um delay
        setTimeout(() => {
            carregarDocumentosComAnalise();
        }, 2000);
        
    } catch (error) {
        console.error('❌ Erro ao reprocessar análise:', error);
        mostrarNotificacao('Erro ao reprocessar: ' + error.message, 'error');
    } finally {
        esconderLoading();
    }
}

// Mostrar modal com detalhes da análise
function mostrarModalDetalhes(dados) {
    console.log('🎨 Mostrando modal de detalhes');
    
    // Criar modal se não existir
    let modal = document.getElementById('modalDetalhes');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'modalDetalhes';
        modal.className = 'modal';
        document.body.appendChild(modal);
    }
    
    // HTML do modal
    let modalHTML = '<div class="modal-content modal-detalhes">';
    modalHTML += '<div class="modal-header">';
    modalHTML += '<h2><i class="fas fa-chart-line"></i> Detalhes da Análise</h2>';
    modalHTML += '<button class="modal-close" onclick="fecharModal(\'modalDetalhes\')"><i class="fas fa-times"></i></button>';
    modalHTML += '</div>';
    modalHTML += '<div class="modal-body">';
    
    // Informações do documento
    modalHTML += '<div class="documento-info-completa">';
    modalHTML += '<div class="info-grid">';
    modalHTML += '<div class="info-item"><label><i class="fas fa-file"></i> Documento:</label><span>' + (dados.nome_original || dados.nome) + '</span></div>';
    modalHTML += '<div class="info-item"><label><i class="fas fa-building"></i> Obra:</label><span>' + (dados.obra_nome || 'Não definida') + '</span></div>';
    modalHTML += '<div class="info-item"><label><i class="fas fa-calendar"></i> Data de criação:</label><span>' + formatDate(dados.data_criacao) + '</span></div>';
    modalHTML += '<div class="info-item"><label><i class="fas fa-microscope"></i> Tipo de análise:</label><span>' + (dados.tipo_analise || 'Não especificado') + '</span></div>';
    modalHTML += '<div class="info-item"><label><i class="fas fa-clock"></i> Data da análise:</label><span>' + (formatDate(dados.data_analise) || 'Não disponível') + '</span></div>';
    
    // Usar funções utilitárias para mapear status
    const statusExibicaoModal = mapearStatus(dados.status);
    const textoStatusModal = obterTextoStatus(statusExibicaoModal);
    
    modalHTML += '<div class="info-item"><label><i class="fas fa-info-circle"></i> Status:</label><span class="status-badge status-' + statusExibicaoModal + '">' + textoStatusModal + '</span></div>';
    modalHTML += '</div></div>';
    
    // Imagem do documento
    if (dados.url_imagem) {
        modalHTML += '<div class="analise-imagem">';
        modalHTML += '<h3><i class="fas fa-image"></i> Imagem do Documento</h3>';
        modalHTML += '<img src="' + dados.url_imagem + '" alt="' + (dados.nome_original || dados.nome) + '" ';
        modalHTML += 'style="max-width: 100%; max-height: 400px; object-fit: contain; border-radius: 8px;">';
        modalHTML += '</div>';
    }
    
    // Resultado da análise
    modalHTML += '<div class="resultado-analise">';
    modalHTML += '<h3><i class="fas fa-brain"></i> Resultado da Análise</h3>';
    modalHTML += '<div class="resultado-conteudo">' + formatarResultadoAnalise(dados.resultado_analise) + '</div>';
    modalHTML += '</div>';
    
    modalHTML += '</div></div>';
    
    modal.innerHTML = modalHTML;
    
    // Mostrar modal
    modal.style.display = 'block';
    
    // Fechar modal ao clicar fora
    modal.onclick = function(e) {
        if (e.target === modal) {
            fecharModal('modalDetalhes');
        }
    };
}

// Formatar resultado da análise
function formatarResultadoAnalise(resultado) {
    if (!resultado) {
        return '<p class="sem-resultado">Nenhum resultado de análise disponível.</p>';
    }
    
    // Se for string, tentar fazer parse para JSON
    let dadosAnalise = resultado;
    if (typeof resultado === 'string') {
        try {
            dadosAnalise = JSON.parse(resultado);
        } catch (e) {
            // Se não for JSON válido, retornar como texto simples formatado
            return '<div class="resultado-texto">' + resultado.replace(/\n/g, '<br>') + '</div>';
        }
    }
    
    // Se não for objeto, retornar como texto
    if (typeof dadosAnalise !== 'object') {
        return '<div class="resultado-texto">' + String(dadosAnalise).replace(/\n/g, '<br>') + '</div>';
    }
    
    // Formatar objeto JSON estruturado
    let html = '<div class="analise-estruturada">';
    
    for (const [secao, conteudo] of Object.entries(dadosAnalise)) {
        html += '<div class="analise-secao">';
        html += '<h4 class="secao-titulo">' + getIconeSecao(secao) + ' ' + formatarTituloSecao(secao) + '</h4>';
        html += '<div class="secao-conteudo">' + processarConteudoSecao(conteudo) + '</div>';
        html += '</div>';
    }
    
    html += '</div>';
    return html;
}

// Fechar modal
function fecharModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

// Processar conteúdo de uma seção
function processarConteudoSecao(conteudo) {
    if (!conteudo) return '<p class="sem-conteudo">Não disponível</p>';
    
    if (typeof conteudo === 'string') {
        return '<p>' + conteudo.replace(/\n/g, '<br>') + '</p>';
    }
    
    if (Array.isArray(conteudo)) {
        let html = '<ul class="lista-itens">';
        conteudo.forEach(item => {
            html += '<li>' + processarConteudoSecao(item) + '</li>';
        });
        html += '</ul>';
        return html;
    }
    
    if (typeof conteudo === 'object') {
        let html = '<div class="subsecao">';
        for (const [chave, valor] of Object.entries(conteudo)) {
            html += '<div class="item-subsecao">';
            html += '<strong>' + formatarTituloSecao(chave) + ':</strong>';
            html += '<span>' + processarConteudoSecao(valor) + '</span>';
            html += '</div>';
        }
        html += '</div>';
        return html;
    }
    
    return '<span>' + String(conteudo) + '</span>';
}

// Formatar título de seção
function formatarTituloSecao(titulo) {
    const mapeamentos = {
        'resumo_executivo': 'Resumo Executivo',
        'analise_detalhada': 'Análise Detalhada',
        'pontos_atencao': 'Pontos de Atenção',
        'recomendacoes': 'Recomendações',
        'conclusoes': 'Conclusões',
        'observacoes': 'Observações',
        'dados_tecnicos': 'Dados Técnicos',
        'conformidade': 'Conformidade',
        'seguranca': 'Segurança',
        'qualidade': 'Qualidade',
        'impacto_ambiental': 'Impacto Ambiental',
        'custos': 'Custos',
        'cronograma': 'Cronograma'
    };
    
    return mapeamentos[titulo] || titulo.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

// Obter ícone para seção
function getIconeSecao(secao) {
    const icones = {
        'resumo_executivo': '<i class="fas fa-clipboard-list"></i>',
        'analise_detalhada': '<i class="fas fa-microscope"></i>',
        'pontos_atencao': '<i class="fas fa-exclamation-triangle"></i>',
        'recomendacoes': '<i class="fas fa-lightbulb"></i>',
        'conclusoes': '<i class="fas fa-check-circle"></i>',
        'observacoes': '<i class="fas fa-eye"></i>',
        'dados_tecnicos': '<i class="fas fa-cogs"></i>',
        'conformidade': '<i class="fas fa-shield-alt"></i>',
        'seguranca': '<i class="fas fa-hard-hat"></i>',
        'qualidade': '<i class="fas fa-star"></i>',
        'impacto_ambiental': '<i class="fas fa-leaf"></i>',
        'custos': '<i class="fas fa-dollar-sign"></i>',
        'cronograma': '<i class="fas fa-calendar-alt"></i>'
    };
    
    return icones[secao] || '<i class="fas fa-info-circle"></i>';
}

// Utilitários
function mapearStatus(statusOriginal) {
    const statusMap = {
        'pendente': 'pendente',
        'processando': 'processando', 
        'concluido': 'completa',
        'concluída': 'completa',
        'completo': 'completa',
        'completa': 'completa',
        'erro': 'erro',
        'error': 'erro',
        'falhou': 'erro'
    };
    
    return statusMap[statusOriginal?.toLowerCase()] || statusOriginal || 'pendente';
}

function obterTextoStatus(statusMapeado) {
    const statusTexto = {
        'pendente': 'Pendente',
        'processando': 'Processando',
        'completa': 'Completa',
        'erro': 'Erro'
    };
    
    return statusTexto[statusMapeado] || statusMapeado.charAt(0).toUpperCase() + statusMapeado.slice(1);
}

function formatDate(dateString) {
    if (!dateString) return 'Data não disponível';
    
    try {
        const date = new Date(dateString);
        return date.toLocaleString('pt-BR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (error) {
        console.error('Erro ao formatar data:', error);
        return dateString;
    }
}

function getCsrfToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const parts = cookie.trim().split('=');
        if (parts[0] === 'csrftoken') {
            return decodeURIComponent(parts[1]);
        }
    }
    
    // Fallback: tentar obter do meta tag
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        return metaTag.getAttribute('content');
    }
    
    return '';
}

function mostrarNotificacao(mensagem, tipo) {
    tipo = tipo || 'info';
    
    // Criar container de notificações se não existir
    let container = document.getElementById('notificacoes-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notificacoes-container';
        container.className = 'notificacoes-container';
        document.body.appendChild(container);
    }
    
    // Criar notificação
    const notificacao = document.createElement('div');
    notificacao.className = 'notificacao notificacao-' + tipo;
    
    const icones = {
        success: 'fas fa-check-circle',
        error: 'fas fa-exclamation-circle',
        warning: 'fas fa-exclamation-triangle',
        info: 'fas fa-info-circle'
    };
    
    notificacao.innerHTML = '<i class="' + (icones[tipo] || icones.info) + '"></i>';
    notificacao.innerHTML += '<span>' + mensagem + '</span>';
    notificacao.innerHTML += '<button class="notificacao-fechar" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>';
    
    container.appendChild(notificacao);
    
    // Auto-remover após 5 segundos
    setTimeout(() => {
        if (notificacao.parentElement) {
            notificacao.remove();
        }
    }, 5000);
}

function mostrarLoading(mensagem) {
    mensagem = mensagem || 'Carregando...';
    
    let loading = document.getElementById('loading-overlay');
    if (!loading) {
        loading = document.createElement('div');
        loading.id = 'loading-overlay';
        loading.className = 'loading-overlay';
        document.body.appendChild(loading);
    }
    
    loading.innerHTML = '<div class="loading-content"><div class="loading-spinner"></div><p>' + mensagem + '</p></div>';
    loading.style.display = 'flex';
}

function esconderLoading() {
    const loading = document.getElementById('loading-overlay');
    if (loading) {
        loading.style.display = 'none';
    }
}

// Inicialização
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 DOM carregado, inicializando aplicação...');
    
    // Carregar dados iniciais
    carregarTiposAnalise();
    carregarDocumentosDisponiveis();
    carregarDocumentosComAnalise();
    
    // Event listeners
    const btnNovaAnalise = document.getElementById('btnNovaAnalise');
    if (btnNovaAnalise) {
        btnNovaAnalise.addEventListener('click', iniciarNovaAnalise);
        console.log('✅ Event listener para nova análise configurado');
    }
    
    const btnAtualizarAnalises = document.getElementById('btnAtualizarAnalises');
    if (btnAtualizarAnalises) {
        btnAtualizarAnalises.addEventListener('click', carregarDocumentosComAnalise);
        console.log('✅ Event listener para atualizar análises configurado');
    }
    
    // Fechar modais com ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modalsAbertos = document.querySelectorAll('.modal[style*="display: block"]');
            modalsAbertos.forEach(modal => modal.style.display = 'none');
        }
    });
    
    console.log('✅ Aplicação de análises IA inicializada com sucesso!');
});
