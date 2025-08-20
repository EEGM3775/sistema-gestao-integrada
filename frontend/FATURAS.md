# 📋 Sistema de Seleção de Faturas para Emissão em Lote

## 🎯 Objetivo
Permitir que o usuário selecione múltiplas faturas de uma lista e execute a emissão de notas fiscais em lote, otimizando o processo de faturamento.

## ✨ Funcionalidades Implementadas

### 🔍 Filtros e Busca
- **Busca por texto**: Buscar por ID, cliente ou descrição da fatura
- **Filtro por status**: Pendente, Aprovada, Paga
- **Botão limpar filtros**: Reset rápido de todos os filtros

### ☑️ Sistema de Seleção
- **Checkbox individual**: Para cada fatura na lista
- **Selecionar todos**: Da página atual ou de todas as faturas filtradas
- **Desmarcar todos**: Limpa todas as seleções
- **Contador dinâmico**: Mostra quantas faturas estão selecionadas
- **Visual diferenciado**: Faturas selecionadas têm destaque visual

### 📊 Lista de Faturas
- **Colunas informativas**:
  - ID da fatura
  - Nome do cliente
  - Descrição do serviço/produto
  - Valor (formatado em reais)
  - Data de vencimento (com indicador de atraso)
  - Status da fatura
  - Status da nota fiscal

### 📄 Paginação
- **Navegação por páginas**: Anterior/Próximo
- **Informações de paginação**: "Mostrando X-Y de Z faturas"
- **10 itens por página**: Para performance otimizada

### 🚀 Emissão em Lote
- **Modal dedicado**: Interface limpa para configuração
- **Resumo da operação**: Quantidade de faturas e valor total
- **Configurações globais**: Tipo de NF e descrição padrão
- **Preview das faturas**: Lista das faturas que serão processadas
- **Processamento simulado**: Com feedback visual de progresso

## 🎨 Interface Visual

### Design Responsivo
- **Desktop**: Grid completo com todas as colunas
- **Tablet**: Layout adaptado com colunas essenciais
- **Mobile**: Layout simplificado em coluna única

### Elementos Visuais
- **Cards modernos**: Com sombras e bordas arredondadas
- **Cores semânticas**:
  - 🟢 Verde: Status "aprovada" e "emitida"
  - 🟠 Laranja: Status "pendente" e "processando"
  - 🔵 Azul: Status "paga"
  - 🔴 Vermelho: Status "erro" e faturas em atraso

### Estados Interativos
- **Hover effects**: Em cards e botões
- **Estados de loading**: Durante processamento
- **Notificações**: Feedback de sucesso/erro
- **Animações suaves**: Transições CSS

## 🔧 Funcionalidades Técnicas

### Integração com API Django
```javascript
// Buscar faturas reais
const response = await fetch('/api/erp/faturas/');
const faturas = await response.json();

// Emitir NF de serviço para uma fatura
const response = await fetch(`/api/erp/faturas/${faturaId}/emitir-nfse/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
});
```

### Estrutura de Dados Real
```javascript
// Fatura da API Django
{
    fatura_id: 1001,
    tipo: "RECEBER",
    status: "PENDENTE", 
    descricao: "Consultoria em TI",
    valor: "2500.00",
    data_emissao: "2025-01-15",
    data_vencimento: "2025-01-30", 
    cliente: { nome_completo: "João Silva Ltda" },
    nota_fiscal_servico: null,
    transacoes: []
}
```

### Funções Principais
- `fetchFaturasFromAPI()`: Busca faturas reais da API Django
- `loadFaturas()`: Carrega e renderiza a lista
- `toggleFaturaSelection()`: Alterna seleção individual
- `filterFaturas()`: Aplica filtros de busca
- `processBulkEmission()`: Emissão real via API Django
- `showBulkEmissionModal()`: Abre modal de emissão

### Estados de NF (Baseados na API)
- **sem-nf**: Fatura sem nota fiscal vinculada
- **aguardando**: NF criada, aguardando processamento
- **processando**: NF em processamento no microserviço
- **emitida**: NF emitida com sucesso
- **erro**: Erro na emissão
- **cancelada**: NF cancelada

### Status de Fatura (Django)
- **PENDENTE**: Fatura pendente de pagamento
- **PAGA**: Fatura paga
- **ATRASADA**: Fatura em atraso
- **CANCELADA**: Fatura cancelada

## 🎯 Fluxo de Uso

### 1. Acessar a Seleção
- Clicar no menu "Seleção de Faturas"
- Ou clicar em "Emissão em Lote" na seção de Notas Fiscais

### 2. Filtrar Faturas
- Usar a busca por texto livre
- Filtrar por status específico
- Sistema atualiza a lista dinamicamente

### 3. Selecionar Faturas
- Marcar faturas individualmente
- Usar "Selecionar Todos" para seleção em massa
- Acompanhar contador de selecionadas

### 4. Emitir em Lote
- Clicar no botão de emissão (mostra quantidade)
- Revisar resumo no modal
- Configurar tipo de NF e descrição
- Confirmar processamento

### 5. Acompanhar Resultado
- Receber notificação de sucesso/erro
- Ver status atualizado na lista
- Faturas processadas marcadas como "processando"

## 📱 Responsividade

### Desktop (>1200px)
- Grid completo com 8 colunas
- Todos os filtros visíveis
- Modal largo para melhor visualização

### Tablet (768px - 1200px)
- Grid adaptado com 6 colunas principais
- Filtros reorganizados
- Modal responsivo

### Mobile (<768px)
- Layout em coluna única
- Filtros empilhados
- Botões em largura total
- Colunas não essenciais ocultas

### 🔮 Próximos Passos

### ✅ Integração Completa
- [x] Conectar com API real do Django
- [x] Buscar faturas do banco de dados
- [x] Implementar emissão real via microserviço Node.js
- [ ] Sincronizar status em tempo real (WebSocket)
- [ ] Tratamento robusto de erros de rede

### Funcionalidades Extras
- [ ] Exportar lista de faturas (PDF/Excel)
- [ ] Histórico de emissões
- [ ] Filtros avançados (data, valor, etc.)
- [ ] Ordenação por colunas
- [ ] Busca com autocomplete

### Melhorias de UX
- [ ] Drag & drop para seleção
- [ ] Atalhos de teclado
- [ ] Salvamento de filtros favoritos
- [ ] Templates de emissão

## 🔧 Tecnologias Utilizadas

- **HTML5**: Estrutura semântica
- **CSS3**: Grid, Flexbox, animações
- **JavaScript ES6+**: Programação funcional
- **Font Awesome**: Ícones
- **Responsive Design**: Media queries

---

**💡 Esta implementação fornece uma base sólida para o sistema de emissão de notas fiscais em lote, com interface moderna e experiência de usuário otimizada.**
