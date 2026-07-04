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

    // Configurações da API do Google
    google: {
        clientId: process.env.GOOGLE_CLIENT_ID,
        clientSecret: process.env.GOOGLE_CLIENT_SECRET,
        redirectUri: process.env.GOOGLE_REDIRECT_URI
    },

    // Configurações de E-mail (Nodemailer)
    mail: {
        host: process.env.MAIL_HOST,
        port: parseInt(process.env.MAIL_PORT, 10) || 587,
        user: process.env.MAIL_USER,
        pass: process.env.MAIL_PASS
    }
};

// Validação simples para garantir que as variáveis críticas foram definidas
if (
    !config.djangoApiUrl || 
    !config.djangoApiToken || 
    !config.google.clientId || 
    !config.google.clientSecret || 
    !config.google.redirectUri
) {
    throw new Error('Variáveis de ambiente críticas da API do Django ou Google não foram definidas.');
}

// Validação para as variáveis de e-mail (opcional, apenas se o serviço de notificação estiver ativo)
if (config.mail.host && (!config.mail.user || !config.mail.pass)) {
    // Apenas avisa, não quebra a aplicação, pois o envio de e-mail pode ser opcional
    console.warn('AVISO: As credenciais de e-mail (MAIL_USER, MAIL_PASS) estão incompletas, o serviço de notificação pode falhar.');
}

module.exports = config;
