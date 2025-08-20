# Frontend - Sistema de Gestão Integrada

Este é o frontend simplificado do Sistema de Gestão Integrada, criado para apresentação das funcionalidades do sistema.

## 📁 Estrutura do Frontend

```
frontend/
├── index.html          # Página principal
├── styles.css          # Estilos CSS
├── script.js           # JavaScript
├── favicon.svg         # Ícone do sistema
├── README.md          # Este arquivo
└── FATURAS.md         # Documentação da seleção de faturas
```

## ✨ Funcionalidades

### 🏠 Página Inicial
- Visão geral do sistema
- Estatísticas e recursos principais
- Design responsivo e moderno

### 📄 Sistema de Notas Fiscais
- **Interface para emissão de NFS-e** (Nota Fiscal de Serviço)
- **✨ NOVO: Seleção de faturas em lote**
  - Lista paginada de faturas com filtros
  - Seleção múltipla com checkboxes
  - Emissão de várias NF simultaneamente
  - Resumo de valores e quantidades
- **Demonstração do fluxo de trabalho:**
  1. Busca dados da fatura no Django
  2. Processamento via microserviço Node.js
  3. Comunicação com a API NFE.io
  4. Armazenamento automático dos resultados

### 🧩 Módulos do Sistema
Apresentação visual de todos os 17+ módulos integrados:
- Clientes e Fornecedores
- Empreendimentos
- Funções NF (Microserviço)
- WhatsApp Integration
- CRM, ERP, RH, SCM
- E muito mais...

## 🎨 Design e UX

### Características do Design:
- **Responsivo**: Adaptado para desktop, tablet e mobile
- **Moderno**: Gradientes, sombras e animações suaves
- **Intuitivo**: Navegação clara e componentes familiares
- **Acessível**: Cores contrastantes e textos legíveis

### Elementos Visuais:
- Gradientes azul/roxo (#667eea → #764ba2)
- Ícones Font Awesome
- Cards com hover effects
- Modais com animações
- Sistema de notificações

## 🔧 Como Funciona

### Integração com Django
1. O Django tenta servir `../frontend/index.html`
2. Se não encontrar, usa o fallback HTML interno
3. Arquivos estáticos (CSS/JS) são servidos via `serve_frontend_file()`

### JavaScript Interativo
- **Navegação SPA**: Troca de seções sem reload
- **Modais funcionais**: Para emissão de NF
- **Sistema de notificações**: Feedback visual
- **Simulação de API**: Para demonstração

### CSS Responsivo
- Grid layouts adaptativos
- Breakpoints para mobile (768px, 480px)
- Animações e transições suaves
- Estados de hover e focus

## 🚀 Funcionalidades Implementadas

### ✅ Funcional
- [x] Navegação entre seções
- [x] Modal de emissão de NFS-e individual
- [x] **Sistema de seleção de faturas em lote**
- [x] **Filtros e busca de faturas**
- [x] **Emissão de múltiplas NF simultaneamente**
- [x] Formulário funcional (com simulação)
- [x] Sistema de notificações
- [x] Design responsivo
- [x] Apresentação dos módulos
- [x] Links para admin Django

### 🔄 Em Desenvolvimento
- [ ] Integração real com APIs
- [ ] Emissão de NF-e (produtos)
- [ ] Consulta de status das notas
- [ ] Dashboard com métricas reais

## 💡 Para Apresentação

### Pontos de Destaque:
1. **Sistema Modular**: 17+ módulos integrados
2. **Microserviço NF**: Node.js dedicado para notas fiscais
3. **Integração NFE.io**: Emissão automatizada
4. **Design Profissional**: Interface moderna e intuitiva
5. **Arquitetura Robusta**: Django + Node.js + APIs externas

### Como Demonstrar:
1. Mostrar a página inicial com overview
2. Navegar para seção de Notas Fiscais
3. **Demonstrar a nova seleção de faturas em lote:**
   - Filtros de busca e status
   - Seleção múltipla com checkboxes
   - Modal de emissão em lote
   - Processamento simulado
4. Apresentar todos os módulos
5. Mostrar o painel admin Django

## 🔗 Integração com Backend

### URLs Django Relacionadas:
- `/` → Serve o frontend ou fallback
- `/admin/` → Painel administrativo
- `/api/` → Informações da API
- `/<arquivo>` → Serve arquivos estáticos do frontend

### Microserviço NF (Port 3002):
- Comunicação com NFE.io
- Processamento assíncrono
- Callback para Django
- Logs detalhados

## 📱 Responsividade

### Desktop (>768px):
- Layout em grid com múltiplas colunas
- Cards organizados em grade
- Menu horizontal completo

### Tablet (768px):
- Adaptação dos grids
- Menu responsivo
- Cards em 2 colunas

### Mobile (<480px):
- Layout em coluna única
- Menu compacto
- Cards empilhados
- Modais otimizados

## 🔧 Personalização

### Para modificar cores:
Edite as variáveis CSS no início do `styles.css`:
```css
:root {
    --primary-color: #667eea;
    --secondary-color: #764ba2;
}
```

### Para adicionar novas seções:
1. Adicione a seção no `index.html`
2. Crie o link de navegação
3. Implemente a função no `script.js`

### Para integrar APIs reais:
Substitua a função `simulateNfeEmission()` no `script.js` por chamadas reais às suas APIs.

---

**💻 Desenvolvido como frontend de apresentação para o Sistema de Gestão Integrada**
