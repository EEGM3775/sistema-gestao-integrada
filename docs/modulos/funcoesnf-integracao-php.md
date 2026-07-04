# Integração PHP Support com NFE.io

## 🎯 Visão Geral

O arquivo `consultarNF.js` agora é a **função principal** que integra com a API NFE.io através do **PHP Support**, mantendo o Node.js como interface principal enquanto usa PHP internamente para comunicação com NFE.io.

## 🏗️ Arquitetura da Integração

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐    ┌─────────────┐
│   Django        │    │   Node.js        │    │   PHP Support   │    │   NFE.io    │
│   Backend       │───▶│   Microservice   │───▶│   Library       │───▶│   API       │
│                 │    │   (consultarNF)  │    │                 │    │             │
└─────────────────┘    └──────────────────┘    └─────────────────┘    └─────────────┘
```

## 📁 Estrutura de Arquivos

### Arquivo Principal: `consultarNF.js`

- **Localização**: `/home/eegm/02sistema_gestao_integrada/backend/funcoesnf/consultarNF.js`
- **Função**: Interface principal para consulta de notas fiscais
- **Tecnologia**: Node.js que executa scripts PHP internamente

### Suporte PHP

- **Pasta**: `/home/eegm/02sistema_gestao_integrada/backend/funcoesnf/php-support/`
- **Biblioteca**: NFE.io PHP oficial (versão 2.5)
- **Autoloader**: Composer para gerenciamento de dependências

## 🔧 Funcionalidades Implementadas

### 1. Consulta de Nota Fiscal

```javascript
// Função principal no consultarNF.js
consultarNF(nfId, invoiceId)
```

- **Entrada**: ID da NF no Django + ID da invoice na NFE.io
- **Processo**: Executa script PHP para consultar NFE.io
- **Saída**: Status e dados da nota fiscal

### 2. Download de PDF

```javascript
baixarPDF(nfId, invoiceId, filename)
```

- **Função**: Baixar PDF da nota fiscal via PHP
- **Retorno**: Link ou arquivo baixado

### 3. Listagem de Notas

```javascript
listarNF(filtros)
```

- **Função**: Listar notas fiscais com filtros
- **Filtros**: Por data, status, etc.

## 📡 Endpoints da API

### Microserviço Node.js (Porta 3002)

1. **POST** `/api/consultar-nf` - Consulta assíncrona
2. **POST** `/api/consultar-nf-sync` - Consulta síncrona (via PHP)
3. **POST** `/api/baixar-pdf` - Download PDF (via PHP)
4. **POST** `/api/listar-nf` - Listagem (via PHP)
5. **GET** `/api/php-status` - Status do PHP Support

### Exemplo de Uso

```bash
# Consulta síncrona via PHP
curl -X POST http://localhost:3002/api/consultar-nf-sync \\
  -H "Content-Type: application/json" \\
  -d '{"invoice_id": "12345"}'

# Status do PHP Support
curl -X GET http://localhost:3002/api/php-status
```

## 🔧 Scripts PHP Auto-gerados

O `consultarNF.js` cria automaticamente scripts PHP conforme necessário:

### 1. `consultar_bridge.php`

```php
<?php
require_once(__DIR__ . '/vendor/autoload.php');
require_once(__DIR__ . '/src/NotaFiscalManager.php');

use FuncoesNF\\PHPSupport\\NotaFiscalManager;

$invoiceId = $argv[1] ?? '';
$nfManager = new NotaFiscalManager();
$resultado = $nfManager->consultarNFS($invoiceId);
echo json_encode(['success' => true, 'data' => $resultado]);
?>
```

### 2. `download_bridge.php` e `listar_bridge.php`

Scripts similares para outras operações.

## ⚙️ Configuração

### 1. Credenciais NFE.io

Edite o arquivo `/php-support/src/Config.php`:

```php
<?php
class Config {
    const API_KEY = 'SUA_CHAVE_NFEIO';
    const COMPANY_ID = 'SUA_EMPRESA_ID';
    const ENVIRONMENT = 'production'; // ou 'development'
}
?>
```

### 2. Verificação do Sistema

```bash
# Testar PHP Support
curl -X GET http://localhost:3002/api/php-status

# Resposta esperada:
{
  "phpSupportExists": true,
  "composerInstalled": true,
  "configExists": true,
  "scriptsCreated": {
    "consultar": false,  // Criado sob demanda
    "download": false,   // Criado sob demanda
    "listar": false      // Criado sob demanda
  }
}
```

## 🚀 Fluxo de Execução

### Consulta de Nota Fiscal

1. **Django** chama endpoint `/api/consultar-nf-sync`
2. **Node.js** (`consultarNF.js`) recebe a requisição
3. **Função `executarPHPConsulta()`**:
   - Verifica se script PHP existe (cria se necessário)
   - Executa `php consultar_bridge.php [invoiceId]`
   - Captura output JSON do PHP
4. **PHP Script**:
   - Carrega biblioteca NFE.io
   - Consulta API da NFE.io
   - Retorna dados em JSON
5. **Node.js** retorna resultado para Django

### Vantagens desta Arquitetura

✅ **Biblioteca Oficial**: Usa biblioteca PHP oficial da NFE.io
✅ **Flexibilidade**: Node.js continua sendo a interface principal
✅ **Confiabilidade**: PHP tem melhor suporte para NFE.io
✅ **Manutenibilidade**: Scripts são auto-gerenciados
✅ **Performance**: Execução sob demanda dos scripts PHP

## 🛠️ Troubleshooting

### Problema: Scripts PHP não executam

```bash
# Verificar PHP
php --version

# Verificar permissões
chmod +x /path/to/php-support/install.sh

# Verificar dependências
cd php-support && composer install --no-dev
```

### Problema: NFE.io API não responde

1. Verificar credenciais em `Config.php`
2. Testar conectividade:

```bash
cd php-support
php -r "require 'vendor/autoload.php'; echo 'OK';"
```

## 📝 Logs e Debug

Os logs são centralizados no logger do Node.js:

```javascript
logger.info('Consulta PHP concluída para NF:', invoiceId);
logger.error('Erro na consulta PHP:', error);
```

## 🔄 Atualizações Futuras

Para adicionar novas funcionalidades:

1. **Node.js**: Adicionar função em `consultarNF.js`
2. **PHP**: Criar método em `NotaFiscalManager.php`
3. **Bridge**: Será criado automaticamente pelo Node.js

---

## 📞 Suporte

Esta integração mantém o `consultarNF.js` como função principal, usando PHP apenas como intermediário para a NFE.io, conforme solicitado.
