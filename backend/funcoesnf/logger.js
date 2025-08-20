const winston = require('winston');

const { combine, timestamp, json, errors } = winston.format;

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: combine(
    errors({ stack: true }), // Inclui o stack trace nos erros
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

module.exports = logger;
