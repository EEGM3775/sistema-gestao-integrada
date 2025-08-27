const winston = require('winston');
const axios = require('axios');

const { combine, timestamp, json, errors } = winston.format;

// URL do endpoint de log no backend Django
const LOG_API_URL = process.env.DJANGO_LOG_API_URL || 'http://localhost:8000/api/log-interno/';

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: combine(
    errors({ stack: true }),
    timestamp(),
    json()
  ),
  transports: [
    // Em produção, você poderia adicionar outros transportes,
    // como um para enviar logs para um serviço externo.
  ],
});

// Se não estivermos em produção, também logamos no console
// com um formato mais legível.
if (process.env.NODE_ENV !== 'production') {
  logger.add(new winston.transports.Console({
    format: winston.format.combine(
      winston.format.colorize(),
      winston.format.simple()
    ),
  }));
} else {
    // Em produção, usamos o formato JSON no console.
    logger.add(new winston.transports.Console());
}

/**
 * Envia um registro de log para o backend Django.
 * @param {string} acao A ação que está sendo registrada.
 * @param {string} entidade_alvo O nome do microserviço ou componente.
 * @param {object} detalhes Objeto com os detalhes do log.
 * @param {string|number} [user_id] ID do usuário associado à ação.
 */
async function logToDjango(acao, entidade_alvo, detalhes, user_id = null) {
  try {
    await axios.post(LOG_API_URL, {
      acao,
      entidade_alvo,
      detalhes,
      user_id,
    }, {
      headers: {
        // Adicione aqui um token de serviço se necessário para autenticação entre serviços
        'Authorization': `Token ${process.env.DJANGO_API_TOKEN}`
      }
    });
    logger.info('Log enviado com sucesso para o Django.');
  } catch (error) {
    logger.error('Falha ao enviar log para o Django:', {
      errorMessage: error.message,
      requestUrl: LOG_API_URL,
      responseStatus: error.response ? error.response.status : null,
      responseData: error.response ? error.response.data : null,
    });
  }
}

module.exports = {
    logger,
    logToDjango
};
