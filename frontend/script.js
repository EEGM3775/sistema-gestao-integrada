console.log('[frontend] script.js carregado');
// Authentication functionality
let currentUser = null;

// Verificar autenticação na inicialização
document.addEventListener('DOMContentLoaded', function() {
    checkAuthentication();
});

async function checkAuthentication() {
    try {
        const response = await fetch('/auth/login/', {
            method: 'GET',
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (data.authenticated) {
            currentUser = data.user;
            updateUIForLoggedUser();
        } else {
            // Usuário não autenticado, redirecionar para login
            window.location.href = '/login.html';
        }
    } catch (error) {
        console.error('Erro ao verificar autenticação:', error);
        window.location.href = '/login.html';
    }
}

function updateUIForLoggedUser() {
    // Atualizar interface para usuário logado
    const userInfo = document.createElement('div');
    userInfo.className = 'user-info';
    userInfo.innerHTML = `
        <span>Olá, ${currentUser.username}</span>
        <button onclick="logout()" class="logout-btn">Sair</button>
    `;
    
    // Adicionar ao header se não existir
    const header = document.querySelector('.header .container');
    if (header && !header.querySelector('.user-info')) {
        header.appendChild(userInfo);
    }
}

async function logout() {
    try {
        const response = await fetch('/auth/logout/', {
            method: 'POST',
            credentials: 'include'
        });
        
        if (response.ok) {
            currentUser = null;
            localStorage.removeItem('user');
            window.location.href = '/login.html';
        }
    } catch (error) {
        console.error('Erro no logout:', error);
        // Mesmo com erro, redirecionar para login
        window.location.href = '/login.html';
    }
}

// Interceptor para adicionar autenticação às requisições
const originalFetch = window.fetch;
window.fetch = async function(url, options = {}) {
    // Adicionar credenciais a todas as requisições para APIs
    if (url.startsWith('/api/')) {
        options.credentials = 'include';
        
        // Garantir que o header de Content-Type está presente para POST/PUT/PATCH
        if (['POST', 'PUT', 'PATCH'].includes(options.method)) {
            options.headers = options.headers || {};
            if (!options.headers['Content-Type']) {
                options.headers['Content-Type'] = 'application/json';
            }
        }
    }
    
    const response = await originalFetch(url, options);
    
    // Se receber 401, redirecionar para login
    if (response.status === 401 && !url.includes('/auth/')) {
        console.log('Token expirado ou usuário não autenticado');
        window.location.href = '/login.html';
    }
    
    return response;
};

// Navigation functionality
function showSection(sectionId) {
    // Hide all sections
    const sections = document.querySelectorAll('.section');
    sections.forEach(section => {
        section.classList.remove('active');
    });
    
    // Remove active class from all nav links
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.classList.remove('active');
    });
    
    // Show selected section
    document.getElementById(sectionId).classList.add('active');
    
    // Add active class to clicked nav link
    const activeLink = document.querySelector(`[href="#${sectionId}"]`);
    if (activeLink) {
        activeLink.classList.add('active');
    }
    
    // Carregar faturas quando a seção for mostrada
    if (sectionId === 'faturas') {
        setTimeout(() => loadFaturas(), 100);
    }
    
    // Carregar análises quando a seção for mostrada
    if (sectionId === 'analises') {
        setTimeout(() => {
            carregarObrasParaFiltro();
            carregarDocumentosComAnalise();
        }, 100);
    }
}

// (removido) exportações antecipadas – serão definidas ao final do arquivo após as funções

// NFe Modal functionality
function showNfeForm(tipo) {
    const modal = document.getElementById('nfeModal');
    const modalTitle = document.getElementById('modalTitle');
    const tipoSelect = document.getElementById('tipoNF');
    
    modalTitle.textContent = tipo === 'servico' ? 'Emitir NFS-e (Serviço)' : 'Emitir NF-e (Produto)';
    tipoSelect.value = tipo;
    
    modal.style.display = 'block';
    
    // Animate modal appearance
    setTimeout(() => {
        modal.querySelector('.modal-content').style.animation = 'modalSlideIn 0.3s ease-out';
    }, 10);
}

function closeModal() {
    const modal = document.getElementById('nfeModal');
    modal.style.display = 'none';
    
    // Reset form
    document.getElementById('nfeForm').reset();
}

function showNfeConsulta() {
    const modal = document.getElementById('consultaModal');
    modal.style.display = 'block';
    
    // Animate modal appearance
    setTimeout(() => {
        modal.querySelector('.modal-content').style.animation = 'modalSlideIn 0.3s ease-out';
    }, 10);
}

function closeConsultaModal() {
    const modal = document.getElementById('consultaModal');
    modal.style.display = 'none';
}

// Form submission
document.addEventListener('DOMContentLoaded', function() {
    const nfeForm = document.getElementById('nfeForm');
    
    nfeForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const formData = {
            faturaId: document.getElementById('faturaId').value,
            tipoNF: document.getElementById('tipoNF').value,
            descricao: document.getElementById('descricao').value
        };
        
        // Show loading state
        const submitBtn = nfeForm.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando...';
        submitBtn.disabled = true;
        
        // Simulate API call (replace with actual API call)
        simulateNfeEmission(formData)
            .then(result => {
                if (result.success) {
                    let message = result.message || 'Nota Fiscal enviada para processamento com sucesso!';
                    let type = 'success';
                    
                    // Se há aviso, mostrar como warning
                    if (result.warning) {
                        message += ` (${result.warning})`;
                        type = 'warning';
                    }
                    
                    showNotification(message, type);
                    closeModal();
                } else if (result.action_required) {
                    // Nota fiscal já existe - mostrar opções ao usuário
                    handleExistingInvoiceOptions(result, formData);
                } else {
                    showNotification('Erro ao processar a emissão da Nota Fiscal: ' + result.error, 'error');
                }
            })
            .catch(error => {
                showNotification('Erro na comunicação com o servidor: ' + error.message, 'error');
            })
            .finally(() => {
                // Restore button state
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            });
    });
});

// Simulate NFe emission - INTEGRAÇÃO REAL
async function simulateNfeEmission(formData) {
    try {
        const response = await fetch(`/api/erp/faturas/${formData.faturaId}/emitir-nfse/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                descricao: formData.descricao || null
            })
        });

        if (response.ok) {
            const result = await response.json();
            
            // Verificar se há aviso sobre microserviço
            if (result.warning) {
                console.warn('Aviso:', result.warning);
            }
            
            // Verificar se é uma situação que requer ação do usuário
            if (result.action_required === 'reemit_or_view') {
                return {
                    success: false,
                    action_required: true,
                    message: result.message,
                    existing_nf: result.existing_nf,
                    options: result.options
                };
            }
            
            return {
                success: true,
                nfId: result.data?.numero || result.data?.id || `NF-${formData.faturaId}`,
                status: result.data?.status || 'PROCESSANDO',
                message: result.message,
                warning: result.warning
            };
        } else {
            const error = await response.json();
            return {
                success: false,
                error: error.error || error.detail || 'Erro na emissão da nota fiscal'
            };
        }
    } catch (error) {
        return {
            success: false,
            error: 'Erro na comunicação com o servidor: ' + error.message
        };
    }
}

// Handle existing invoice options
function handleExistingInvoiceOptions(result, originalFormData) {
    const modalContent = `
        <div class="existing-invoice-modal">
            <h3><i class="fas fa-file-invoice"></i> Nota Fiscal Existente</h3>
            <p>${result.message}</p>
            
            <div class="existing-nf-info">
                <h4>Informações da Nota Fiscal:</h4>
                <p><strong>ID:</strong> ${result.existing_nf.id}</p>
                <p><strong>Status:</strong> ${result.existing_nf.status}</p>
                <p><strong>Descrição:</strong> ${result.existing_nf.description || result.existing_nf.items_data?.[0]?.descricao || 'N/A'}</p>
                <p><strong>Valor:</strong> R$ ${parseFloat(result.existing_nf.services_amount || result.existing_nf.items_data?.[0]?.valor_total || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2})}</p>
                <p><strong>Criada em:</strong> ${new Date(result.existing_nf.criado_em).toLocaleString('pt-BR')}</p>
            </div>
            
            <div class="options-buttons">
                <button type="button" class="btn btn-secondary" onclick="closeModal()">
                    <i class="fas fa-times"></i> Cancelar
                </button>
                <button type="button" class="btn btn-info" onclick="viewExistingInvoice(${result.existing_nf.id})">
                    <i class="fas fa-eye"></i> Visualizar
                </button>
                <button type="button" class="btn btn-warning" onclick="reemitInvoice(${JSON.stringify(originalFormData).replace(/"/g, '&quot;')})">
                    <i class="fas fa-redo"></i> Re-emitir Nova
                </button>
            </div>
        </div>
    `;
    
    // Update modal content
    const modalBody = document.querySelector('#nfeModal .modal-body');
    if (modalBody) {
        modalBody.innerHTML = modalContent;
    }
}

// View existing invoice
function viewExistingInvoice(nfId) {
    showNotification(`Visualizando Nota Fiscal ID: ${nfId}`, 'info');
    closeModal();
    // Here you could implement actual viewing functionality
}

// Re-emit invoice with force flag
async function reemitInvoice(formData) {
    const submitBtn = document.querySelector('.btn-submit');
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Re-emitindo...';
    submitBtn.disabled = true;
    
    try {
        // Add force_reemit flag to form data
        const reemitData = { ...formData, force_reemit: true };
        
        const result = await simulateNfeEmission(reemitData);
        
        if (result.success) {
            let message = 'Nova Nota Fiscal emitida com sucesso!';
            let type = 'success';
            
            if (result.warning) {
                message += ` (${result.warning})`;
                type = 'warning';
            }
            
            showNotification(message, type);
            closeModal();
        } else {
            showNotification('Erro ao re-emitir a Nota Fiscal: ' + result.error, 'error');
        }
    } catch (error) {
        showNotification('Erro na comunicação com o servidor: ' + error.message, 'error');
    } finally {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
    }
}

// Notification system
function showNotification(message, type = 'info') {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll('.notification');
    existingNotifications.forEach(notification => notification.remove());
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <i class="fas ${getNotificationIcon(type)}"></i>
            <span>${message}</span>
            <button class="notification-close" onclick="this.parentElement.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    
    // Add styles
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 3000;
        min-width: 300px;
        max-width: 500px;
        background: ${getNotificationColor(type)};
        color: white;
        border-radius: 10px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        animation: slideInRight 0.3s ease-out;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    `;
    
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideInRight {
            from {
                opacity: 0;
                transform: translateX(100%);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        .notification-content {
            padding: 15px 20px;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .notification-content i {
            font-size: 1.2rem;
        }
        .notification-close {
            background: none;
            border: none;
            color: white;
            cursor: pointer;
            padding: 5px;
            border-radius: 3px;
            margin-left: auto;
            opacity: 0.8;
            transition: opacity 0.3s ease;
        }
        .notification-close:hover {
            opacity: 1;
            background: rgba(255,255,255,0.1);
        }
    `;
    document.head.appendChild(style);
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.animation = 'slideOutRight 0.3s ease-in';
            setTimeout(() => notification.remove(), 300);
        }
    }, 5000);
}

function getNotificationIcon(type) {
    const icons = {
        'success': 'fa-check-circle',
        'error': 'fa-exclamation-circle',
        'warning': 'fa-exclamation-triangle',
        'info': 'fa-info-circle'
    };
    return icons[type] || icons['info'];
}

function getNotificationColor(type) {
    const colors = {
        'success': 'linear-gradient(135deg, #4CAF50, #45a049)',
        'error': 'linear-gradient(135deg, #f44336, #da190b)',
        'warning': 'linear-gradient(135deg, #ff9800, #f57c00)',
        'info': 'linear-gradient(135deg, #667eea, #764ba2)'
    };
    return colors[type] || colors['info'];
}

// Close modals when clicking outside
window.addEventListener('click', function(event) {
    const nfeModal = document.getElementById('nfeModal');
    const consultaModal = document.getElementById('consultaModal');
    
    if (event.target === nfeModal) {
        closeModal();
    }
    
    if (event.target === consultaModal) {
        closeConsultaModal();
    }
});

// Close modals with Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const nfeModal = document.getElementById('nfeModal');
        const consultaModal = document.getElementById('consultaModal');
        
        if (nfeModal.style.display === 'block') {
            closeModal();
        }
        
        if (consultaModal.style.display === 'block') {
            closeConsultaModal();
        }
    }
});

// Smooth scrolling for internal links
document.addEventListener('DOMContentLoaded', function() {
    const links = document.querySelectorAll('a[href^="#"]');
    
    links.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            const targetId = this.getAttribute('href').substring(1);
            if (targetId) {
                showSection(targetId);
            }
        });
    });
});

// Module cards hover effects
document.addEventListener('DOMContentLoaded', function() {
    const moduleCards = document.querySelectorAll('.module-card');
    
    moduleCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-10px) scale(1.02)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });
});

// Add loading states for better UX
function addLoadingState(element, loadingText = 'Carregando...') {
    const originalText = element.innerHTML;
    element.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${loadingText}`;
    element.disabled = true;
    
    return () => {
        element.innerHTML = originalText;
        element.disabled = false;
    };
}

// Console welcome message
console.log(`
🏢 Sistema de Gestão Integrada
=====================================
Desenvolvido com Django + Node.js
Integração com NFE.io para emissão de NF
=====================================
Para mais informações, acesse /admin/
`);

// Performance monitoring
window.addEventListener('load', function() {
    const loadTime = performance.now();
    console.log(`⚡ Página carregada em ${Math.round(loadTime)}ms`);
});

// ==========================================
// SISTEMA DE SELEÇÃO DE FATURAS - INTEGRAÇÃO REAL
// ==========================================

// Dados das faturas carregados da API
let faturasData = [];
let filteredFaturas = [];
let selectedFaturas = new Set();
let currentPage = 1;
const itemsPerPage = 10;

// Carrega faturas da API do Django
async function fetchFaturasFromAPI() {
    try {
        const response = await fetch('/api/erp/faturas/', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            throw new Error(`Erro HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Faturas carregadas da API:', data);
        
        // Filtrar apenas faturas A_RECEBER (que podem ter NF emitida)
        faturasData = data.filter(fatura => fatura.tipo === 'RECEBER');
        filteredFaturas = [...faturasData];
        
        return faturasData;
    } catch (error) {
        console.error('Erro ao carregar faturas da API:', error);
        throw error; // Re-lança o erro para que seja tratado pelo chamador
    }
}


// Carrega as faturas na interface
async function loadFaturas() {
    const faturasContainer = document.getElementById('faturasList');
    const noFaturasMessage = document.getElementById('noFaturasMessage');
    
    if (!faturasContainer) return;
    
    // Se ainda não carregou os dados, buscar da API
    if (faturasData.length === 0) {
        faturasContainer.innerHTML = '<div class="loading-faturas"><i class="fas fa-spinner fa-spin"></i> Carregando faturas...</div>';
        
        try {
            await fetchFaturasFromAPI();
        } catch (error) {
            faturasContainer.innerHTML = `
                <div class="error-loading">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>Erro ao carregar faturas: ${error.message}</p>
                    <p>Verifique se o servidor está rodando.</p>
                </div>
            `;
            return;
        }
    }
    
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const paginatedFaturas = filteredFaturas.slice(startIndex, endIndex);
    
    if (paginatedFaturas.length === 0) {
        faturasContainer.style.display = 'none';
        noFaturasMessage.style.display = 'block';
        return;
    }
    
    faturasContainer.style.display = 'block';
    noFaturasMessage.style.display = 'none';
    
    faturasContainer.innerHTML = paginatedFaturas.map(fatura => `
        <div class="fatura-item ${selectedFaturas.has(fatura.fatura_id) ? 'selected' : ''}" data-id="${fatura.fatura_id}">
            <div class="checkbox-col">
                <input type="checkbox" class="fatura-checkbox" value="${fatura.fatura_id}" 
                       ${selectedFaturas.has(fatura.fatura_id) ? 'checked' : ''} 
                       onchange="toggleFaturaSelection(${fatura.fatura_id})">
            </div>
            <div class="id-col">#${fatura.fatura_id}</div>
            <div class="cliente-col">
                <div class="cliente-nome">${getClienteName(fatura)}</div>
            </div>
            <div class="descricao-col">
                <div class="descricao-texto" title="${fatura.descricao}">${fatura.descricao}</div>
            </div>
            <div class="valor-col">
                <div class="valor-fatura">R$ ${formatCurrency(parseFloat(fatura.valor))}</div>
            </div>
            <div class="vencimento-col">
                <div class="vencimento-data ${isOverdue(fatura.data_vencimento) ? 'overdue' : ''}">${formatDate(fatura.data_vencimento)}</div>
            </div>
            <div class="status-col">
                <div class="status-badge ${fatura.status.toLowerCase()}">${getStatusLabel(fatura.status)}</div>
            </div>
            <div class="nf-col">
                <div class="nf-status ${getNfStatus(fatura)}">${getNfStatusLabel(getNfStatus(fatura))}</div>
            </div>
        </div>
    `).join('');
    
    updatePagination();
    updateSelectedCount();
    updateSelectAllCheckbox();
}

// Alterna seleção de uma fatura
function toggleFaturaSelection(faturaId) {
    if (selectedFaturas.has(faturaId)) {
        selectedFaturas.delete(faturaId);
    } else {
        selectedFaturas.add(faturaId);
    }
    
    updateSelectedCount();
    updateSelectAllCheckbox();
    
    // Atualizar visual da linha
    const faturaItem = document.querySelector(`[data-id="${faturaId}"]`);
    if (faturaItem) {
        faturaItem.classList.toggle('selected', selectedFaturas.has(faturaId));
    }
}

// Selecionar todos/desmarcar todos
function toggleSelectAll(checkbox) {
    const currentPageFaturas = getCurrentPageFaturas();
    
    if (checkbox.checked) {
        currentPageFaturas.forEach(fatura => {
            selectedFaturas.add(fatura.fatura_id);
        });
    } else {
        currentPageFaturas.forEach(fatura => {
            selectedFaturas.delete(fatura.fatura_id);
        });
    }
    
    loadFaturas(); // Recarrega para atualizar visual
}

// Funções dos botões de seleção
function selectAll() {
    filteredFaturas.forEach(fatura => {
        selectedFaturas.add(fatura.fatura_id);
    });
    loadFaturas();
}

function deselectAll() {
    selectedFaturas.clear();
    loadFaturas();
}

// Filtros
function filterFaturas() {
    const searchTerm = document.getElementById('searchFatura')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('statusFilter')?.value || '';
    
    filteredFaturas = faturasData.filter(fatura => {
        const matchesSearch = !searchTerm || 
            fatura.fatura_id.toString().includes(searchTerm) ||
            getClienteName(fatura).toLowerCase().includes(searchTerm) ||
            fatura.descricao.toLowerCase().includes(searchTerm);
        
        const matchesStatus = !statusFilter || mapStatusFilter(fatura.status, statusFilter);
        
        return matchesSearch && matchesStatus;
    });
    
    currentPage = 1;
    loadFaturas();
}

function resetFilters() {
    document.getElementById('searchFatura').value = '';
    document.getElementById('statusFilter').value = '';
    filteredFaturas = [...faturasData];
    currentPage = 1;
    loadFaturas();
}

// Paginação
function changePage(direction) {
    const totalPages = Math.ceil(filteredFaturas.length / itemsPerPage);
    const newPage = currentPage + direction;
    
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        loadFaturas();
    }
}

function updatePagination() {
    const totalPages = Math.ceil(filteredFaturas.length / itemsPerPage);
    const startItem = (currentPage - 1) * itemsPerPage + 1;
    const endItem = Math.min(currentPage * itemsPerPage, filteredFaturas.length);
    
    // Atualizar informações
    const paginationInfo = document.getElementById('paginationInfo');
    if (paginationInfo) {
        paginationInfo.textContent = `Mostrando ${startItem}-${endItem} de ${filteredFaturas.length} faturas`;
    }
    
    // Atualizar botões
    const prevBtn = document.getElementById('prevPage');
    const nextBtn = document.getElementById('nextPage');
    
    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
}

// Modal de emissão em lote
function showBulkEmissionModal() {
    if (selectedFaturas.size === 0) {
        showNotification('Selecione pelo menos uma fatura para continuar.', 'warning');
        return;
    }
    
    const modal = document.getElementById('bulkEmissionModal');
    const selectedFaturasList = document.getElementById('selectedFaturasList');
    const bulkSelectedCount = document.getElementById('bulkSelectedCount');
    const bulkTotalValue = document.getElementById('bulkTotalValue');
    
    // Atualizar contadores
    bulkSelectedCount.textContent = selectedFaturas.size;
    
    // Calcular valor total
    const totalValue = Array.from(selectedFaturas).reduce((total, faturaId) => {
        const fatura = faturasData.find(f => f.fatura_id === faturaId);
        return total + (fatura ? parseFloat(fatura.valor) : 0);
    }, 0);
    
    bulkTotalValue.textContent = `R$ ${formatCurrency(totalValue)}`;
    
    // Listar faturas selecionadas
    const selectedFaturasArray = Array.from(selectedFaturas).map(faturaId => 
        faturasData.find(f => f.fatura_id === faturaId)
    ).filter(f => f);
    
    selectedFaturasList.innerHTML = selectedFaturasArray.map(fatura => `
        <div class="selected-fatura-item">
            <div class="selected-fatura-info">
                <span class="selected-fatura-id">#${fatura.fatura_id}</span>
                <span class="selected-fatura-cliente">${getClienteName(fatura)}</span>
            </div>
            <span class="selected-fatura-valor">R$ ${formatCurrency(parseFloat(fatura.valor))}</span>
        </div>
    `).join('');
    
    modal.style.display = 'block';
}

function closeBulkEmissionModal() {
    const modal = document.getElementById('bulkEmissionModal');
    modal.style.display = 'none';
    
    // Reset form
    document.getElementById('bulkEmissionForm').reset();
}

// Processar emissão em lote
document.addEventListener('DOMContentLoaded', function() {
    const bulkEmissionForm = document.getElementById('bulkEmissionForm');
    
    if (bulkEmissionForm) {
        bulkEmissionForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = {
                faturaIds: Array.from(selectedFaturas),
                tipoNF: document.getElementById('bulkTipoNF').value,
                descricaoPadrao: document.getElementById('bulkDescricao').value
            };
            
            // Show loading state
            const submitBtn = bulkEmissionForm.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando emissão...';
            submitBtn.disabled = true;
            
            // Simulate bulk emission
            processBulkEmission(formData)
                .then(result => {
                    if (result.success) {
                        let message = `${result.processedCount} notas fiscais enviadas para processamento com sucesso!`;
                        if (result.errorCount > 0) {
                            message += ` ${result.errorCount} falharam.`;
                        }
                        showNotification(message, result.errorCount > 0 ? 'warning' : 'success');
                        
                        // Recarregar faturas da API para obter status atualizados
                        faturasData = [];
                        selectedFaturas.clear();
                        loadFaturas();
                        closeBulkEmissionModal();
                    } else {
                        showNotification('Erro durante o processamento: ' + result.error, 'error');
                    }
                })
                .catch(error => {
                    showNotification('Erro na comunicação com o servidor: ' + error.message, 'error');
                })
                .finally(() => {
                    // Restore button state
                    submitBtn.innerHTML = originalText;
                    submitBtn.disabled = false;
                });
        });
    }
});

// Processar emissão em lote - INTEGRAÇÃO REAL
async function processBulkEmission(formData) {
    try {
        const results = [];
        let successCount = 0;
        let errorCount = 0;

        // Processar cada fatura selecionada
        for (const faturaId of formData.faturaIds) {
            try {
                const response = await fetch(`/api/erp/faturas/${faturaId}/emitir-nfse/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({
                        descricao: formData.descricaoPadrao || null
                    })
                });

                if (response.ok) {
                    const result = await response.json();
                    results.push({ faturaId, success: true, data: result });
                    successCount++;
                } else {
                    const error = await response.json();
                    results.push({ faturaId, success: false, error: error });
                    errorCount++;
                }
            } catch (error) {
                results.push({ faturaId, success: false, error: error.message });
                errorCount++;
            }

            // Pequeno delay entre as requisições para não sobrecarregar o servidor
            await new Promise(resolve => setTimeout(resolve, 200));
        }

        return {
            success: successCount > 0,
            processedCount: successCount,
            errorCount: errorCount,
            results: results,
            processedIds: results.filter(r => r.success).map(r => r.faturaId)
        };

    } catch (error) {
        console.error('Erro no processamento em lote:', error);
        return {
            success: false,
            error: error.message,
            processedCount: 0,
            errorCount: formData.faturaIds.length
        };
    }
}



// Funções auxiliares
function getCurrentPageFaturas() {
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    return filteredFaturas.slice(startIndex, endIndex);
}

function updateSelectedCount() {
    const selectedCountSpan = document.getElementById('selectedCount');
    const bulkEmitBtn = document.getElementById('bulkEmitBtn');
    
    if (selectedCountSpan) {
        selectedCountSpan.textContent = selectedFaturas.size;
    }
    
    if (bulkEmitBtn) {
        bulkEmitBtn.disabled = selectedFaturas.size === 0;
    }
}

function updateSelectAllCheckbox() {
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    if (!selectAllCheckbox) return;
    
    const currentPageFaturas = getCurrentPageFaturas();
    const currentPageIds = currentPageFaturas.map(f => f.fatura_id);
    const allCurrentPageSelected = currentPageIds.length > 0 && 
                                  currentPageIds.every(id => selectedFaturas.has(id));
    
    selectAllCheckbox.checked = allCurrentPageSelected;
    selectAllCheckbox.indeterminate = !allCurrentPageSelected && 
                                     currentPageIds.some(id => selectedFaturas.has(id));
}

function getClienteName(fatura) {
    if (fatura.cliente && fatura.cliente.nome_completo) {
        return fatura.cliente.nome_completo;
    }
    return fatura.cliente_nome || 'Cliente não informado';
}

function getNfStatus(fatura) {
    if (fatura.nota_fiscal_servico && fatura.nota_fiscal_servico.status) {
        return fatura.nota_fiscal_servico.status.toLowerCase();
    }
    if (fatura.nota_fiscal_produto && fatura.nota_fiscal_produto.status) {
        return fatura.nota_fiscal_produto.status.toLowerCase();
    }
    return 'sem-nf';
}

function mapStatusFilter(faturaStatus, filterValue) {
    // Mapear status do Django para os filtros do frontend
    const statusMap = {
        'pendente': ['PENDENTE'],
        'paga': ['PAGA'],
        'atrasada': ['ATRASADA']
    };
    
    return statusMap[filterValue] && statusMap[filterValue].includes(faturaStatus);
}

function getCsrfToken() {
    // Buscar token CSRF do Django
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrfToken) {
        return csrfToken.value;
    }
    
    // Buscar do cookie se disponível
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrftoken') {
            return value;
        }
    }
    
    return '';
}

function formatCurrency(value) {
    return new Intl.NumberFormat('pt-BR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('pt-BR');
}

function isOverdue(dateString) {
    return new Date(dateString) < new Date();
}

function getStatusLabel(status) {
    const labels = {
        'PENDENTE': 'Pendente',
        'PAGA': 'Paga',
        'ATRASADA': 'Atrasada',
        'CANCELADA': 'Cancelada'
    };
    return labels[status] || status;
}

function getNfStatusLabel(nfStatus) {
    const labels = {
        'sem-nf': 'Sem NF',
        'aguardando': 'Aguardando',
        'processando': 'Processando',
        'emitida': 'Emitida',
        'erro': 'Erro',
        'cancelada': 'Cancelada'
    };
    return labels[nfStatus] || nfStatus;
}

// Inicializar quando a seção de faturas for mostrada
document.addEventListener('DOMContentLoaded', function() {
    // Carregar faturas quando a página carregar se a seção estiver ativa
    if (document.getElementById('faturas')?.classList.contains('active')) {
        loadFaturas();
    }
    
    // Carregar análises se a seção estiver ativa
    if (document.getElementById('analises')?.classList.contains('active')) {
        carregarObrasParaFiltro();
        carregarDocumentosComAnalise();
    }
});

// Funções para Análises de IA
let tiposAnaliseDisponiveis = [];

// Carregar obras para o filtro
async function carregarObrasParaFiltro() {
    try {
        const response = await fetch('/api/obras/');
        if (!response.ok) throw new Error('Erro ao carregar obras');
        
        const data = await response.json();
        const select = document.getElementById('filtroObra');
        
        // Limpar opções existentes (exceto "Todas as obras")
        select.innerHTML = '<option value="">Todas as obras</option>';
        
        // Verificar se a resposta tem formato paginado ou é array direto
        const obras = data.results || data;
        
        // Verificar se obras é um array
        if (Array.isArray(obras)) {
            obras.forEach(obra => {
                const option = document.createElement('option');
                option.value = obra.obra_id;
                option.textContent = obra.nome;
                select.appendChild(option);
            });
        } else {
            console.warn('Formato de resposta inesperado para obras:', data);
        }
    } catch (error) {
        console.error('Erro ao carregar obras:', error);
    }
}

// Carregar tipos de análise disponíveis
async function carregarTiposAnalise() {
    try {
        // Usar a API do Django que fará proxy para o serviço de IA
        const response = await fetch('/api/ia/analise/tipos');
        if (!response.ok) {
            // Se o serviço não estiver disponível, usar fallback
            throw new Error('Serviço de IA indisponível');
        }
        
        const data = await response.json();
        
        // Converter a estrutura { tipos_por_categoria: {...} } para um array plano
        if (data.tipos_por_categoria) {
            tiposAnaliseDisponiveis = [];
            Object.values(data.tipos_por_categoria).forEach(categoria => {
                tiposAnaliseDisponiveis.push(...categoria);
            });
        } else {
            // Fallback se a estrutura for diferente
            tiposAnaliseDisponiveis = Array.isArray(data) ? data : [];
        }
    } catch (error) {
        console.error('Erro ao carregar tipos de análise:', error);
        // Fallback com tipos básicos quando o serviço não está disponível
        tiposAnaliseDisponiveis = [
            { id: 'residencial', nome: 'Construção Residencial' },
            { id: 'comercial', nome: 'Construção Comercial' },
            { id: 'infraestrutura', nome: 'Infraestrutura' },
            { id: 'industrial', nome: 'Construção Industrial' }
        ];
    }
}

// Carregar documentos com análise
async function carregarDocumentosComAnalise() {
    const loadingEl = document.getElementById('loadingAnalises');
    const gridEl = document.getElementById('documentosAnalises');
    
    loadingEl.style.display = 'block';
    gridEl.innerHTML = '';
    
    try {
        const obraId = document.getElementById('filtroObra').value;
        const status = document.getElementById('filtroStatus').value;
        
        let url = '/api/diario/documentos-com-analise/';
        const params = new URLSearchParams();
        
        if (obraId) params.append('obra', obraId);
        if (status) params.append('status', status);
        
        if (params.toString()) {
            url += '?' + params.toString();
        }
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Erro ao carregar documentos');
        
        const data = await response.json();
        const documentos = data.documentos || [];
        
        if (documentos.length === 0) {
            gridEl.innerHTML = `
                <div class="no-documents">
                    <i class="fas fa-search"></i>
                    <h3>Nenhum documento encontrado</h3>
                    <p>Não há documentos com análises para os filtros selecionados.</p>
                </div>
            `;
        } else {
            documentos.forEach(documento => {
                const card = criarCardDocumento(documento);
                gridEl.appendChild(card);
            });

            // Bind dos botões "Reprocessar" renderizados
            const reprocessButtons = gridEl.querySelectorAll('.btn-reprocessar');
            reprocessButtons.forEach((btn) => {
                // Evitar múltiplos bindings em recriação da lista
                if (!btn.dataset.bound) {
                    btn.addEventListener('click', (e) => {
                        e.preventDefault();
                        const documentoId = Number(btn.dataset.documentoId);
                        const nomeDocumento = btn.dataset.documentoNome || 'Documento';
                        console.log('🟢 Clique em Reprocessar:', { documentoId, nomeDocumento });
                        if (!isNaN(documentoId)) {
                            abrirModalReprocessar(documentoId, nomeDocumento);
                        } else {
                            console.warn('Documento ID inválido no botão Reprocessar:', btn.dataset.documentoId);
                        }
                    });
                    btn.dataset.bound = 'true';
                }
            });
        }
    } catch (error) {
        console.error('Erro ao carregar documentos:', error);
        gridEl.innerHTML = `
            <div class="no-documents">
                <i class="fas fa-exclamation-triangle"></i>
                <h3>Erro ao carregar</h3>
                <p>Ocorreu um erro ao carregar os documentos. Tente novamente.</p>
            </div>
        `;
    } finally {
        loadingEl.style.display = 'none';
    }
}

// Criar card de documento
function criarCardDocumento(documento) {
    const card = document.createElement('div');
    card.className = 'documento-card';
    
    const statusClass = documento.status_analise ? `status-${documento.status_analise}` : 'status-erro';
    const statusText = getStatusText(documento.status_analise);
    
    card.innerHTML = `
        <div class="documento-header">
            <h3>${documento.nome}</h3>
            <div class="obra-info">Obra: ${documento.obra_nome || 'N/A'}</div>
        </div>
        <div class="documento-body">
            <div class="documento-info">
                <div class="info-item">
                    <span class="info-label">Data:</span>
                    <span>${formatDate(documento.data_upload)}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Status:</span>
                    <span class="status-badge ${statusClass}">${statusText}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Tipo de Análise:</span>
                    <span>${documento.tipo_analise || 'N/A'}</span>
                </div>
            </div>
            
            ${documento.resultado_analise ? `
                <div class="analise-info">
                    <h4>Resultado da Análise:</h4>
                    <div class="analise-preview">${documento.resultado_analise.substring(0, 200)}...</div>
                </div>
            ` : ''}
            
            <div class="documento-actions">
                <button class="btn-reprocessar" data-documento-id="${documento.id}" data-documento-nome="${documento.nome}">
                    <i class="fas fa-sync"></i> Reprocessar
                </button>
                <button class="btn-ver-detalhes" onclick="verDetalhesAnalise(${documento.id})">
                    <i class="fas fa-eye"></i> Detalhes
                </button>
            </div>
        </div>
    `;
    
    return card;
}

// Listener delegado global como fallback para cliques em Reprocessar
if (!window.__reprocessListenerAdded) {
    document.addEventListener('click', (ev) => {
        const btn = ev.target && ev.target.closest && ev.target.closest('.btn-reprocessar');
        if (!btn) return;
        ev.preventDefault();
        const documentoId = Number(btn.dataset.documentoId);
        const nomeDocumento = btn.dataset.documentoNome || 'Documento';
        console.log('🟢 (Delegado) Clique em Reprocessar:', { documentoId, nomeDocumento });
        if (!isNaN(documentoId)) {
            abrirModalReprocessar(documentoId, nomeDocumento);
        }
    });
    window.__reprocessListenerAdded = true;
}

// Função auxiliar para formatar data
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Função auxiliar para texto do status
function getStatusText(status) {
    const statusMap = {
        'completa': 'Completa',
        'em_andamento': 'Em andamento',
        'erro': 'Com erro'
    };
    return statusMap[status] || 'Desconhecido';
}

// Abrir modal para reprocessar análise
function abrirModalReprocessar(documentoId, nomeDocumento) {
    console.log('🔄 Abrindo modal de reprocessar para documento:', documentoId, nomeDocumento);
    
    // Verificação defensiva para garantir que temos um array
    if (!Array.isArray(tiposAnaliseDisponiveis) || tiposAnaliseDisponiveis.length === 0) {
        console.log('📋 Carregando tipos de análise...');
        carregarTiposAnalise().then(() => {
            console.log('📋 Tipos carregados:', tiposAnaliseDisponiveis);
            mostrarModalReprocessar(documentoId, nomeDocumento);
        });
    } else {
        console.log('📋 Usando tipos já carregados:', tiposAnaliseDisponiveis);
        mostrarModalReprocessar(documentoId, nomeDocumento);
    }
}

// Mostrar modal de reprocessamento
function mostrarModalReprocessar(documentoId, nomeDocumento) {
    console.log('📱 Criando modal de reprocessar...');
    console.log('📊 Tipos disponíveis:', tiposAnaliseDisponiveis);
    
    // Verificação defensiva para garantir que temos um array
    if (!Array.isArray(tiposAnaliseDisponiveis)) {
        console.warn('⚠️ tiposAnaliseDisponiveis não é um array, inicializando fallback');
        tiposAnaliseDisponiveis = [
            { id: 'completa', nome: 'Análise Completa da Obra', descricao: 'Análise abrangente incluindo progresso, segurança e qualidade' }
        ];
    }
    
    // Remover modal anterior se existir para evitar duplicidade
    const modalExistente = document.getElementById('modalReprocessar');
    if (modalExistente) {
        console.log('♻️ Removendo modal anterior antes de criar um novo');
        modalExistente.remove();
    }

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'modalReprocessar';
    
    const tiposHtml = tiposAnaliseDisponiveis.map(tipo => `
        <div class="tipo-option" data-tipo="${tipo.id}" onclick="selecionarTipo('${tipo.id}')">
            <strong>${tipo.nome}</strong>
            <div style="font-size: 12px; color: #666; margin-top: 5px;">
                ${tipo.descricao || 'Análise especializada para este tipo de construção'}
            </div>
        </div>
    `).join('');
    
    console.log('🎨 HTML dos tipos:', tiposHtml);
    
    modal.innerHTML = `
        <div class="modal">
            <h3>Reprocessar Análise</h3>
            <p style="margin-bottom: 20px; color: #666;">
                Documento: <strong>${nomeDocumento}</strong>
            </p>
            <p style="margin-bottom: 20px;">Escolha o tipo de análise:</p>
            <div class="tipo-analise-grid">
                ${tiposHtml}
            </div>
            <div class="modal-actions">
                <button class="btn-modal btn-cancel" onclick="fecharModal()">Cancelar</button>
                <button class="btn-modal btn-confirm" onclick="confirmarReprocessamento(${documentoId})" disabled id="btnConfirmar" data-documento-id="${documentoId}">
                    Reprocessar
                </button>
            </div>
        </div>
    `;
    
    console.log('🎯 Adicionando modal ao body');
    document.body.appendChild(modal);
    console.log('✅ Modal adicionado');

    // Auto-selecionar tipo padrão (completa ou primeiro disponível)
    const preferido = (Array.isArray(tiposAnaliseDisponiveis) && tiposAnaliseDisponiveis.find(t => t.id === 'completa'))
        ? 'completa'
        : (Array.isArray(tiposAnaliseDisponiveis) && tiposAnaliseDisponiveis[0] ? tiposAnaliseDisponiveis[0].id : null);
    if (preferido) {
        console.log('✅ Auto-selecionando tipo padrão:', preferido);
        selecionarTipo(preferido);
    }
}

// Selecionar tipo de análise
function selecionarTipo(tipoId) {
    console.log('🎯 Selecionando tipo:', tipoId);
    
    // Remove seleção anterior
    const modal = document.getElementById('modalReprocessar');
    const lista = modal ? modal.querySelectorAll('.tipo-option') : document.querySelectorAll('.tipo-option');
    lista.forEach(el => {
        el.classList.remove('selected');
        console.log('🔄 Removendo seleção de:', el.dataset.tipo);
    });
    
    // Adiciona seleção atual
    const tipoElement = (modal ? modal.querySelector(`[data-tipo="${tipoId}"]`) : document.querySelector(`[data-tipo="${tipoId}"]`));
    if (tipoElement) {
        tipoElement.classList.add('selected');
        console.log('✅ Tipo selecionado:', tipoId);
    } else {
        console.error('❌ Elemento não encontrado para tipo:', tipoId);
    }
    
    // Habilita botão de confirmar
    const btnConfirmar = modal ? modal.querySelector('#btnConfirmar') : document.getElementById('btnConfirmar');
    if (btnConfirmar) {
        btnConfirmar.disabled = false;
        btnConfirmar.dataset.tipo = tipoId;
        console.log('✅ Botão habilitado com tipo:', tipoId);
    } else {
        console.error('❌ Botão confirmar não encontrado');
    }
}

// Fechar modal
function fecharModal() {
    const modal = document.getElementById('modalReprocessar');
    if (modal) {
        modal.remove();
    }
}

// Listener delegado para seleção de tipo dentro do modal
document.addEventListener('click', (ev) => {
    const opt = ev.target && ev.target.closest && ev.target.closest('.tipo-option');
    if (!opt) return;
    const tipoId = opt.dataset.tipo;
    if (tipoId) {
        selecionarTipo(tipoId);
    }
});

// Listener delegado para confirmar reprocessamento (robustez)
document.addEventListener('click', (ev) => {
    const confirmBtn = ev.target && ev.target.closest && ev.target.closest('#btnConfirmar');
    if (!confirmBtn) return;
    ev.preventDefault();
    const documentoIdAttr = confirmBtn.dataset.documentoId;
    const documentoId = documentoIdAttr ? Number(documentoIdAttr) : null;
    console.log('🟠 Clique em Confirmar detectado (delegado):', { documentoId, tipo: confirmBtn.dataset.tipo });
    if (documentoId) {
        confirmarReprocessamento(documentoId);
    } else {
        console.warn('DocumentoId ausente no botão confirmar');
    }
});

// Expor funções no escopo global (após declaração de todas as funções)
window.abrirModalReprocessar = abrirModalReprocessar;
window.verDetalhesAnalise = verDetalhesAnalise;
window.carregarDocumentosComAnalise = carregarDocumentosComAnalise;
window.selecionarTipo = selecionarTipo;
window.confirmarReprocessamento = confirmarReprocessamento;
window.fecharModal = fecharModal;

// Confirmar reprocessamento
async function confirmarReprocessamento(documentoId) {
    const modal = document.getElementById('modalReprocessar');
    const btnConfirmar = modal ? modal.querySelector('#btnConfirmar') : document.getElementById('btnConfirmar');
    const tipoAnalise = btnConfirmar.dataset.tipo;
    
    if (!tipoAnalise) {
        alert('Selecione um tipo de análise');
        return;
    }
    
    btnConfirmar.disabled = true;
    btnConfirmar.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando...';
    console.log('🚀 Iniciando reprocessamento via frontend:', { documentoId, tipoAnalise });
    
    try {
        const response = await fetch('/api/diario/reprocessar-analise/', {
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
            throw new Error('Erro ao reprocessar análise');
        }
        
        const resultado = await response.json();
        
        alert('Reprocessamento iniciado com sucesso! A análise será atualizada em breve.');
        fecharModal();
        
        // Recarregar lista de documentos
        setTimeout(() => {
            carregarDocumentosComAnalise();
        }, 1000);
        
    } catch (error) {
        console.error('Erro ao reprocessar:', error);
        alert('Erro ao iniciar reprocessamento. Tente novamente.');
        btnConfirmar.disabled = false;
        btnConfirmar.innerHTML = 'Reprocessar';
    }
}

// Ver detalhes da análise
async function verDetalhesAnalise(documentoId) {
    try {
        // Buscar os detalhes do documento específico
        const response = await fetch(`/api/diario/documento-analise/${documentoId}/`);
        if (!response.ok) {
            if (response.status === 404) {
                throw new Error('Documento não encontrado ou não possui análise');
            }
            throw new Error('Erro ao carregar documento');
        }
        
        const documento = await response.json();
        
        // Preencher e exibir o modal
        preencherModalAnalise(documento);
        
        // Exibir o modal
        const modal = document.getElementById('analiseModal');
        modal.style.display = 'block';
        
    } catch (error) {
        console.error('Erro ao carregar detalhes da análise:', error);
        alert(`Erro ao carregar os detalhes da análise: ${error.message}`);
    }
}

function preencherModalAnalise(documento) {
    // Informações gerais
    document.getElementById('analiseNome').textContent = documento.nome;
    document.getElementById('analiseObra').textContent = documento.obra_nome || 'Não especificada';
    document.getElementById('analiseData').textContent = documento.data_analise;
    
    // Status com classe CSS
    const statusElement = document.getElementById('analiseStatus');
    statusElement.textContent = documento.status_analise;
    statusElement.className = `status-badge ${documento.status_analise.toLowerCase()}`;
    
    // Imagem do documento
    const imagemElement = document.getElementById('analiseImagem');
    if (documento.url_imagem) {
        imagemElement.src = documento.url_imagem;
    } else {
        // Fallback para imagem não disponível
        imagemElement.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgdmlld0JveD0iMCAwIDMwMCAyMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMDAiIGhlaWdodD0iMjAwIiBmaWxsPSIjRjhGOUZBIi8+CjxwYXRoIGQ9Ik0xNTAgNzVMMTI1IDEwMEwxNzUgMTAwTDE1MCA3NVoiIGZpbGw9IiM2QzU0N0QiLz4KPHJlY3QgeD0iMTI1IiB5PSIxMDAiIHdpZHRoPSI1MCIgaGVpZ2h0PSI1MCIgZmlsbD0iIzZDNzU3RCIvPgo8dGV4dCB4PSIxNTAiIHk9IjE2MCIgZm9udC1mYW1pbHk9IkFyaWFsLCBzYW5zLXNlcmlmIiBmb250LXNpemU9IjEyIiBmaWxsPSIjNkM3NTdEIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5JbWFnZW0gbsOjbyBkaXNwb27DrXZlbDwvdGV4dD4KPC9zdmc+';
        imagemElement.alt = 'Imagem não disponível';
    }
    
    // Resultado da análise
    if (documento.resultado) {
        // Progresso
        preencherProgresso(documento.resultado.progresso);
        
        // Atividades
        preencherAtividades(documento.resultado.atividades_identificadas);
        
        // Riscos
        preencherRiscos(documento.resultado.riscos_seguranca);
        
        // Pessoal
        preencherPessoal(documento.resultado.reconhecimento_pessoal);
    }
}

function preencherProgresso(progresso) {
    const container = document.getElementById('analiseProgresso');
    if (!progresso) {
        container.innerHTML = '<p>Informações de progresso não disponíveis.</p>';
        return;
    }
    
    container.innerHTML = `
        <div class="progresso-item">
            <strong>Resumo:</strong> ${progresso.resumo}
        </div>
        <div class="progresso-item">
            <strong>Percentual concluído:</strong>
            <span class="progresso-percentual">${progresso.percentual_concluido_etapa}%</span>
        </div>
    `;
}

function preencherAtividades(atividades) {
    const container = document.getElementById('analiseAtividades');
    if (!atividades || atividades.length === 0) {
        container.innerHTML = '<p>Nenhuma atividade identificada.</p>';
        return;
    }
    
    const lista = atividades.map(atividade => 
        `<li>${atividade}</li>`
    ).join('');
    
    container.innerHTML = `<ul class="atividades-lista">${lista}</ul>`;
}

function preencherRiscos(riscos) {
    const container = document.getElementById('analiseRiscos');
    if (!riscos || riscos.length === 0) {
        container.innerHTML = '<p>Nenhum risco identificado.</p>';
        return;
    }
    
    const riscosHtml = riscos.map(risco => {
        const nivel = risco.nivel_criticidade.toLowerCase().replace('é', 'e');
        return `
            <div class="risco-item ${nivel}">
                <div class="risco-nivel ${nivel}">${risco.nivel_criticidade}</div>
                <div class="risco-descricao">${risco.risco}</div>
            </div>
        `;
    }).join('');
    
    container.innerHTML = `<div class="riscos-lista">${riscosHtml}</div>`;
}

function preencherPessoal(pessoal) {
    const container = document.getElementById('analisePessoal');
    if (!pessoal || !pessoal.resumo) {
        container.innerHTML = '<p>Informações de pessoal não disponíveis.</p>';
        return;
    }
    
    container.innerHTML = `
        <div class="pessoal-resumo">
            ${pessoal.resumo}
        </div>
    `;
}

function fecharModalAnalise() {
    const modal = document.getElementById('analiseModal');
    modal.style.display = 'none';
}

// Fechar modal ao clicar fora dele
window.onclick = function(event) {
    const modal = document.getElementById('analiseModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
}

// Inicializar seção quando carregada
document.addEventListener('DOMContentLoaded', function() {
    // Carregar tipos de análise ao inicializar
    carregarTiposAnalise();
});
