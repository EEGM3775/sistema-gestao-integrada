#!/bin/bash

# Script de instalação e configuração do PHP Support para NFE.io
# Este script automatiza a instalação e configuração inicial

echo "🚀 Iniciando instalação do PHP Support para NFE.io..."
echo "=================================================="

# Verificar se o PHP está instalado
if ! command -v php &> /dev/null; then
    echo "❌ PHP não encontrado. Instalando PHP..."
    sudo apt update
    sudo apt install -y php php-cli php-curl php-json php-mbstring
    echo "✅ PHP instalado com sucesso"
else
    echo "✅ PHP já está instalado: $(php --version | head -1)"
fi

# Verificar se o Composer está instalado
if ! command -v composer &> /dev/null; then
    echo "❌ Composer não encontrado. Instalando Composer..."
    curl -sS https://getcomposer.org/installer | php
    sudo mv composer.phar /usr/local/bin/composer
    echo "✅ Composer instalado com sucesso"
else
    echo "✅ Composer já está instalado: $(composer --version)"
fi

# Navegar para o diretório do projeto
PROJECT_DIR="/home/eegm/02sistema_gestao_integrada/backend/funcoesnf/php-support"
cd "$PROJECT_DIR" || exit 1

echo ""
echo "📦 Instalando dependências PHP..."
composer install --no-dev --optimize-autoloader

# Criar diretórios necessários
echo ""
echo "📁 Criando diretórios necessários..."
mkdir -p logs
mkdir -p ../../../media/nf_pdfs
mkdir -p ../../../media/nf_xmls

# Configurar permissões
echo "🔧 Configurando permissões..."
chmod 755 logs
chmod 755 ../../../media/nf_pdfs
chmod 755 ../../../media/nf_xmls

# Verificar se as configurações estão corretas
echo ""
echo "🔍 Verificando configuração..."
php -r "
require_once('src/Config.php');
use FuncoesNF\PHPSupport\Config;

echo '📋 Configurações atuais:' . PHP_EOL;
echo '   API Key: ' . (Config::getApiKey() ? '✅ Configurada' : '❌ Não configurada') . PHP_EOL;
echo '   Company ID: ' . (Config::getCompanyId() ? '✅ Configurado' : '❌ Não configurado') . PHP_EOL;
echo '   Ambiente: ' . Config::ENVIRONMENT . PHP_EOL;
"

# Testar a API Bridge
echo ""
echo "🧪 Testando API Bridge..."
if php -l api_bridge.php > /dev/null 2>&1; then
    echo "✅ API Bridge está sintáticamente correta"
else
    echo "❌ Erro de sintaxe na API Bridge"
    exit 1
fi

# Executar exemplo básico se as configurações estiverem corretas
echo ""
echo "🎯 Executando teste de configuração..."
php -r "
require_once('src/NotaFiscalManager.php');
use FuncoesNF\PHPSupport\NotaFiscalManager;

try {
    \$nfManager = new NotaFiscalManager();
    echo '✅ NotaFiscalManager inicializado com sucesso' . PHP_EOL;
} catch (Exception \$e) {
    echo '❌ Erro ao inicializar NotaFiscalManager: ' . \$e->getMessage() . PHP_EOL;
}
"

echo ""
echo "=================================================="
echo "🎉 Instalação concluída!"
echo ""
echo "📚 Próximos passos:"
echo "1. Configure suas credenciais NFE.io em: src/Config.php"
echo "2. Execute os exemplos em: examples/"
echo "3. Teste a API Bridge em: api_bridge.php"
echo ""
echo "📖 Documentação completa: README.md"
echo "🔗 Painel NFE.io: https://app.nfe.io/account/apikeys"
echo ""
echo "✨ Happy coding!"
