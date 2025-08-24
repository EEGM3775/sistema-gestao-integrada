# NFE.io PHP Support

Esta pasta contém uma integração completa com a API do NFE.io usando PHP, fornecendo funcionalidades avançadas para gerenciar notas fiscais de serviço.

## 📁 Estrutura de Arquivos

```
php-support/
├── composer.json              # Dependências do projeto
├── src/
│   ├── Config.php            # Configurações da API NFE.io
│   └── NotaFiscalManager.php # Classe principal para gerenciar NFS-e
├── examples/
│   ├── emitir_nfs.php        # Exemplo: emitir nota fiscal
│   ├── consultar_nfs.php     # Exemplo: consultar nota fiscal
│   └── listar_nfs.php        # Exemplo: listar notas fiscais
├── api_bridge.php            # API Bridge para integração com Node.js
└── README.md                 # Esta documentação
```

## 🚀 Instalação

### 1. Instalar Dependências

```bash
cd /home/eegm/02sistema_gestao_integrada/backend/funcoesnf/php-support
composer install
```

### 2. Configurar API Keys

Edite o arquivo `src/Config.php` e configure suas credenciais:

```php
const NFE_API_KEY = 'sua_chave_api_aqui';
const COMPANY_ID = 'id_da_sua_empresa_aqui';
```

Obtenha suas credenciais em: https://app.nfe.io/account/apikeys

## 📚 Funcionalidades

### ✅ Emitir NFS-e
- Criação completa de notas fiscais de serviço
- Validação de dados obrigatórios
- Suporte a dados do tomador completos

### ✅ Consultar NFS-e
- Consulta detalhada do status da nota
- Recuperação de todos os dados da NFS-e
- URLs para PDF e XML quando disponíveis

### ✅ Cancelar NFS-e
- Cancelamento de notas fiscais emitidas
- Verificação de status antes do cancelamento
- Motivo personalizado para cancelamento

### ✅ Baixar PDF/XML
- Download automático de PDFs
- Organização em estrutura de pastas
- Nomenclatura padronizada de arquivos

### ✅ Listar NFS-e
- Listagem completa das notas da empresa
- Filtros e ordenação
- Resumo de status e valores

## 🔧 Como Usar

### Uso Básico com PHP

```php
require_once('src/NotaFiscalManager.php');

use FuncoesNF\PHPSupport\NotaFiscalManager;

$nfManager = new NotaFiscalManager();

// Emitir nota fiscal
$resultado = $nfManager->emitirNFS([
    'cityServiceCode' => '1401',
    'description' => 'Serviços de TI',
    'servicesAmount' => 1500.00,
    'borrower' => [
        'name' => 'Cliente Exemplo',
        'email' => 'cliente@exemplo.com',
        // ... outros dados
    ]
]);

if ($resultado['success']) {
    echo "NF emitida: " . $resultado['data']['id'];
} else {
    echo "Erro: " . $resultado['error'];
}
```

### Uso via API Bridge (HTTP)

A API Bridge permite usar as funcionalidades PHP via requisições HTTP:

```bash
# Emitir NFS-e
curl -X POST http://localhost/api_bridge.php/emitir \
  -H "Content-Type: application/json" \
  -d '{
    "cityServiceCode": "1401",
    "description": "Serviços de TI",
    "servicesAmount": 1500.00
  }'

# Consultar NFS-e
curl -X GET http://localhost/api_bridge.php/consultar?id=INVOICE_ID

# Listar NFS-e
curl -X GET http://localhost/api_bridge.php/listar
```

## 🔌 Integração com Node.js

Para integrar com o microserviço Node.js existente, adicione as seguintes rotas:

```javascript
// No arquivo index.js do Node.js
const axios = require('axios');

app.post('/api/consultar-nfs-php', async (req, res) => {
  try {
    const response = await axios.get(
      `http://localhost/api_bridge.php/consultar?id=${req.body.invoiceId}`
    );
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});
```

## 📋 Exemplos Práticos

### Executar Exemplos

```bash
# Emitir uma nota fiscal de exemplo
php examples/emitir_nfs.php

# Consultar a última nota emitida
php examples/consultar_nfs.php

# Listar todas as notas fiscais
php examples/listar_nfs.php
```

## 📊 Status das Notas Fiscais

| Status NFE.io | Descrição | Ação Possível |
|---|---|---|
| `WaitingCalculateTaxes` | Aguardando cálculo de impostos | Aguardar |
| `WaitingDefineRpsNumber` | Aguardando definição do número RPS | Aguardar |
| `WaitingSend` | Aguardando envio | Aguardar |
| `Processing` | Processando | Aguardar |
| `Issued` | Emitida | Cancelar, Baixar PDF/XML |
| `Cancelled` | Cancelada | Nenhuma |
| `Error` | Erro | Verificar logs |

## 🛡️ Códigos de Serviço Suportados

| Código | Descrição |
|---|---|
| `010701` | Serviços de consultoria |
| `1401` | Serviços de tecnologia da informação |
| `2690` | Outros serviços |
| `1701` | Serviços de engenharia |
| `1101` | Serviços advocatícios |
| `1301` | Serviços de contabilidade |

## 🔍 Logs e Monitoramento

Os logs são salvos automaticamente em:
- `logs/php_bridge.log` - Logs da API Bridge
- `logs/nf_operations.log` - Logs das operações de NF

## 🚨 Tratamento de Erros

A biblioteca trata automaticamente os seguintes erros:
- ❌ Dados obrigatórios ausentes
- ❌ Valores inválidos
- ❌ Status incorreto para operações
- ❌ Falhas de comunicação com a API
- ❌ Timeouts de requisição

## 🔐 Segurança

- 🛡️ API Keys são configuráveis via variáveis de ambiente
- 🛡️ Validação rigorosa de dados de entrada
- 🛡️ Logs de auditoria de todas as operações
- 🛡️ Headers CORS configurados para integração segura

## 📈 Performance

- ⚡ Cache automático de configurações
- ⚡ Reutilização de conexões HTTP
- ⚡ Processamento assíncrono quando possível
- ⚡ Timeouts configuráveis

## 🔧 Configurações Avançadas

Edite `src/Config.php` para personalizar:
- Timeout de requisições HTTP
- Diretórios de armazenamento
- Códigos de serviço personalizados
- URLs da API NFE.io
- Configurações de ambiente

## 🆘 Suporte e Troubleshooting

### Problemas Comuns:

1. **Erro de API Key inválida**
   - Verifique se a chave está correta em `Config.php`
   - Confirme se a empresa está ativa no painel NFE.io

2. **Timeout nas requisições**
   - Aumente o valor em `Config::HTTP_TIMEOUT`
   - Verifique a conectividade com a API

3. **Erros de validação**
   - Consulte os logs em `logs/` para detalhes
   - Verifique se todos os campos obrigatórios estão preenchidos

4. **PDF/XML não baixa**
   - Verifique permissões da pasta `media/`
   - Confirme se a nota está com status `Issued`

## 🔄 Atualizações

Para atualizar a biblioteca NFE.io:

```bash
composer update nfe/nfe
```

## 📞 Contato

- 📧 Documentação NFE.io: https://nfe.io/docs/
- 🐛 Issues: Reporte problemas no repositório do projeto
- 💬 Suporte: Contate o suporte NFE.io para questões da API
