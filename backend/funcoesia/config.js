// backend/funcoesia/config.js
const dotenv = require('dotenv');
const path = require('path');

// Carrega as variáveis de ambiente do arquivo .env específico do módulo
dotenv.config({ path: path.resolve(__dirname, '.env') });

const requiredEnvVars = [
  'NODE_ENV',
  'IA_PORT',
  'GOOGLE_API_KEY',
  'DJANGO_API_URL',
  'DJANGO_API_TOKEN',
  'IA_SERVICE_SECRET_TOKEN',
];

// Valida se todas as variáveis de ambiente necessárias estão definidas
requiredEnvVars.forEach((varName) => {
  if (!process.env[varName]) {
    throw new Error(`Variável de ambiente obrigatória '${varName}' não está definida.`);
  }
});

module.exports = {
  nodeEnv: process.env.NODE_ENV || 'development',
  port: process.env.IA_PORT || 3002,
  googleApiKey: process.env.GOOGLE_API_KEY,
  djangoApiUrl: process.env.DJANGO_API_URL,
  djangoApiToken: process.env.DJANGO_API_TOKEN,
  iaServiceSecretToken: process.env.IA_SERVICE_SECRET_TOKEN,
  logLevel: process.env.LOG_LEVEL || 'info',
};
