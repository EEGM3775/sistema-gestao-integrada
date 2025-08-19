require('dotenv').config();

const requiredEnvVars = [
  'META_ACCESS_TOKEN',
  'META_VERIFY_TOKEN',
  'META_APP_SECRET',
  'META_PHONE_NUMBER_ID',
  // 'META_API_VERSION', // Tornou-se opcional com valor padrão
  'DJANGO_API_URL',
  'DJANGO_API_TOKEN',
  'REDIS_URL',
];

const config = {
  port: process.env.WHATSAPP_PORT || 3001,
  logLevel: process.env.LOG_LEVEL || 'info',
  nodeEnv: process.env.NODE_ENV || 'development',
  
  meta: {
    accessToken: process.env.META_ACCESS_TOKEN,
    verifyToken: process.env.META_VERIFY_TOKEN,
    appSecret: process.env.META_APP_SECRET,
    phoneNumberId: process.env.META_PHONE_NUMBER_ID,
    apiVersion: process.env.META_API_VERSION || 'v18.0', // Valor padrão adicionado
  },

  django: {
    apiUrl: process.env.DJANGO_API_URL,
    apiToken: process.env.DJANGO_API_TOKEN,
  },

  redis: {
    url: process.env.REDIS_URL,
  },
};

// Verifica se todas as variáveis de ambiente obrigatórias estão definidas
const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);

if (missingVars.length > 0) {
  throw new Error(`Variáveis de ambiente obrigatórias estão faltando: ${missingVars.join(', ')}. Verifique seu arquivo .env.`);
}

module.exports = config;
