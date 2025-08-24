# Frontend - Integração PHP Support para Consulta de Notas Fiscais

## 🎯 Funcionalidades Implementadas no Frontend

### 📋 Página: `nfse.html`

A página agora possui integração completa com o **PHP Support** para consultar notas fiscais diretamente da API NFE.io através do microserviço Node.js.

## 🔧 Novas Funcionalidades

### 1. **Consulta Síncrona via PHP** 🔍
- **Botão**: "Consultar Status via PHP" (ícone: 🔍)
- **Função**: `consultarStatusPHP(btn, nfId, nfeIoId)`
- **Endpoint**: `http://localhost:3002/api/consultar-nf-sync`
- **Comportamento**: 
  - Consulta **imediata** na API NFE.io via PHP
  - Exibe detalhes completos da nota fiscal
  - Mostra modal com dados completos

### 2. **Download de PDF via PHP** 📄
- **Botão**: "Baixar PDF" (ícone: 📄)
- **Função**: `baixarPDF(btn, nfId, nfeIoId)`
- **Endpoint**: `http://localhost:3002/api/baixar-pdf`
- **Comportamento**:
  - Inicia download do PDF via PHP
  - Abre PDF em nova aba se disponível
  - Feedback visual durante processamento

### 3. **Listagem via PHP** 📊
- **Botão**: "Atualizar via PHP" (ícone: ♻️)
- **Função**: `listarNFsPHP()`
- **Endpoint**: `http://localhost:3002/api/listar-nf`
- **Comportamento**:
  - Lista até 20 NFs mais recentes da NFE.io
  - Exibe dados diretamente da API
  - Interface diferenciada (azul) para dados PHP

### 4. **Modal de Detalhes Completos** 📋
- **Função**: `mostrarDetalhesNF(nfData, nfId)`
- **Conteúdo**:
  - Status atual da nota
  - Número e chave de acesso
  - Links para PDF e XML
  - JSON completo da resposta NFE.io

## 🎨 Interface Visual

### Botões Implementados

```html
<!-- Consulta via PHP (síncrona) -->
<button class="btn btn-icon" onclick="consultarStatusPHP(...)">
    <i class="fas fa-search"></i> <!-- Ícone de lupa -->
</button>

<!-- Download PDF -->
<button class="btn btn-icon" onclick="baixarPDF(...)">
    <i class="fas fa-file-pdf"></i> <!-- Ícone PDF -->
</button>

<!-- Consulta assíncrona (original) -->
<button class="btn btn-icon" onclick="consultarStatus(...)">
    <i class="fas fa-sync-alt"></i> <!-- Ícone sincronização -->
</button>
```

### Diferenciação Visual
- **Dados locais**: Fundo cinza claro
- **Dados via PHP**: Fundo azul claro com borda azul
- **Loading states**: Spinners animados
- **Notificações**: Success (verde), Error (vermelho), Warning (amarelo)

## 🔄 Fluxo de Trabalho

### Consulta Completa de NF

1. **Usuário clica** em "Consultar Status via PHP"
2. **Frontend** chama `http://localhost:3002/api/consultar-nf-sync`
3. **Node.js** executa script PHP automaticamente
4. **PHP** consulta API NFE.io oficial
5. **Retorno** com dados completos em tempo real
6. **Modal** exibe informações detalhadas

### Exemplo de Resposta PHP

```json
{
  "success": true,
  "data": {
    "id": "12345",
    "status": "EMITIDA",
    "number": "000001",
    "accessKey": "35240212345678901234567890123456789012345",
    "urlPdf": "https://nfe.io/pdf/...",
    "urlXml": "https://nfe.io/xml/...",
    "amount": "100.00",
    "issueDate": "2025-08-20"
  }
}
```

## 🚀 Testando as Funcionalidades

### 1. Verificar Microserviço
```bash
curl -X GET http://localhost:3002/api/php-status
```

### 2. Testar Consulta Direta
```bash
curl -X POST http://localhost:3002/api/consultar-nf-sync \
  -H "Content-Type: application/json" \
  -d '{"invoice_id": "SEU_INVOICE_ID"}'
```

### 3. Testar na Interface
1. Acesse `http://localhost:8000/nfse.html`
2. Procure notas com `nfe_io_id`
3. Clique em "Consultar Status via PHP" (🔍)
4. Veja os dados em tempo real

## 📱 Responsividade

- **Desktop**: Botões lado a lado
- **Mobile**: Botões empilhados
- **Modais**: Adaptáveis a qualquer tela
- **Loading**: Visual consistente

## 🛠️ Troubleshooting

### Problema: Botões não aparecem
- **Causa**: Nota não tem `nfe_io_id`
- **Solução**: Emitir NF primeiro

### Problema: Erro de CORS
- **Causa**: Microserviço em porta diferente
- **Solução**: Verificar se está rodando na porta 3002

### Problema: PHP não responde
- **Causa**: Credenciais não configuradas
- **Solução**: Configurar `php-support/src/Config.php`

## 📊 Monitoramento

### Logs JavaScript
- Todas as operações geram logs no console
- Dados completos das respostas PHP
- Erros detalhados para debug

### Notifications
- **Success**: Operação realizada com sucesso
- **Error**: Falha na operação  
- **Warning**: Operação parcial

---

## ✅ Resultado Final

O frontend agora possui **integração completa** com o PHP Support, permitindo:

- ✅ **Consultas em tempo real** da API NFE.io
- ✅ **Download de PDFs** via PHP
- ✅ **Listagem atualizada** de todas as NFs
- ✅ **Interface intuitiva** com feedback visual
- ✅ **Dados precisos** diretamente da fonte oficial

**A consulta de notas fiscais agora é feita com valores reais da API NFE.io através do PHP Support!** 🎉
