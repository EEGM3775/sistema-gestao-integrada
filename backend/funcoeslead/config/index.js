// backend/funcoeslead/config/index.js
const dotenv = require('dotenv');
const path = require('path');

// Carrega o arquivo .env do diretório do serviço
dotenv.config({ path: path.resolve(__dirname, '../.env') });

const config = {
    port: process.env.LEAD_SERVICE_PORT || 3004,
    djangoApiUrl: process.env.DJANGO_API_URL,
    djangoApiToken: process.env.DJANGO_API_TOKEN,
    logLevel: process.env.LOG_LEVEL || 'info',
};

// Validação simples para garantir que as variáveis críticas foram definidas
if (!config.djangoApiUrl || !config.djangoApiToken) {
    throw new Error('Variáveis de ambiente críticas (DJANGO_API_URL, DJANGO_API_TOKEN) não foram definidas.');
}

module.exports = config;
