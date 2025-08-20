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
}

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
});
