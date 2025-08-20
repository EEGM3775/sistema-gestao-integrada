# 📄 Sistema de Emissão NFS-e

Frontend simplificado para demonstração das funcionalidades de emissão de Nota Fiscal de Serviço (NFS-e) do Sistema de Gestão Integrada.

## 🚀 Funcionalidades

### ✅ Implementadas
- **Listagem de Faturas**: Carrega faturas reais do banco via API Django
- **Seleção Intuitiva**: Interface clean para seleção de faturas
- **Emissão NFS-e**: Integração com microserviço Node.js + NFE.io
- **Status em Tempo Real**: Acompanhamento do status das notas fiscais
- **Responsivo**: Interface adaptada para desktop e mobile

### 🔄 Fluxo de Emissão
1. Sistema carrega faturas do tipo "A_RECEBER" com status "PENDENTE"
2. Usuário seleciona uma fatura da lista
3. Formulário é preenchido automaticamente com dados da fatura
4. Usuário pode adicionar/editar descrição do serviço
5. Sistema envia requisição para API Django `/api/erp/faturas/{id}/emitir-nfse/`
6. Django aciona microserviço Node.js na porta 3002
7. Microserviço integra com NFE.io para emissão real da NF
8. Status é atualizado em tempo real

## 🏗️ Arquitetura

```
[Frontend NFS-e] ←→ [Django API] ←→ [Microserviço Node.js] ←→ [NFE.io]
     (HTML/JS)        (Python)         (Port 3002)        (External API)
```

## 📋 APIs Utilizadas

### Django REST Framework
- `GET /api/erp/faturas/` - Lista faturas
- `POST /api/erp/faturas/{id}/emitir-nfse/` - Emite NFS-e
- `GET /api/erp/notas-fiscais-servico/` - Status das NFs de serviço
- `GET /api/erp/notas-fiscais-produto/` - Status das NFs de produto

### Microserviço Node.js (Porta 3002)
- `POST /api/emitir-nfse` - Processo de emissão via NFE.io
- `POST /api/emitir-nfe` - Emissão de NF de produto

## 🎨 Interface

### Tecnologias Frontend
- **HTML5**: Estrutura semântica
- **CSS3**: Grid Layout + Flexbox para responsividade
- **JavaScript ES6+**: Fetch API, async/await
- **Font Awesome**: Ícones modernos

### Design System
- **Cores**: Gradiente roxo-azul (#667eea → #764ba2)
- **Tipografia**: Segoe UI (system fonts)
- **Componentes**: Cards com glass morphism effect
- **Animações**: Smooth transitions e hover effects

## 🔧 Como Executar

1. **Inicie o Django**:
   ```bash
   cd backend
   python3 manage.py runserver 0.0.0.0:8000
   ```

2. **Inicie o Microserviço** (se disponível):
   ```bash
   cd funcoesia
   npm start
   ```

3. **Acesse o Frontend**:
   - Sistema NFS-e: http://localhost:8000/nfse/
   - Página principal: http://localhost:8000/

## 📱 Screenshots

### Desktop
- Lista de faturas em grid responsivo
- Formulário de emissão com dados pré-preenchidos
- Painel de status das notas fiscais

### Mobile
- Layout adaptativo com colunas únicas
- Navegação touch-friendly
- Formulário otimizado para mobile

## 🔍 Demonstração

### Dados de Exemplo
O sistema carregará suas faturas reais do banco de dados. Para demonstração, certifique-se de ter:
- Faturas do tipo "RECEBER"
- Status "PENDENTE" 
- Cliente cadastrado
- Valores e descrições preenchidas

### Fluxo de Teste
1. Acesse `/nfse/`
2. Veja suas faturas reais carregadas
3. Clique em uma fatura para selecioná-la
4. Revise/edite a descrição do serviço
5. Clique em "Emitir NFS-e"
6. Acompanhe o processamento
7. Veja o status atualizado no painel inferior

## 🚦 Status do Sistema

- ✅ **Frontend**: Funcional e responsivo
- ✅ **API Django**: Integrada e funcionando
- ✅ **Banco de Dados**: Usando faturas reais
- 🔄 **Microserviço Node.js**: Dependente da configuração NFE.io
- 🔄 **NFE.io**: Requer credenciais válidas

## 📞 Suporte

Para demonstração das funcionalidades completas:
1. Configure as credenciais da NFE.io no microserviço
2. Certifique-se de que o Node.js está rodando na porta 3002
3. Teste com faturas reais do seu banco de dados

---

**Desenvolvido para apresentação do Sistema de Gestão Integrada**
*Integração Django + Node.js + NFE.io*
