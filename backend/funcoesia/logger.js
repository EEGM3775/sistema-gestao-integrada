// backend/funcoesia/logger.js
const winston = require('winston');
const config = require('./config');

const { combine, timestamp, printf, colorize, json } = winston.format;

// Formato de log para desenvolvimento (console colorido)
const devFormat = combine(
  colorize(),
  timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
  printf(({ timestamp, level, message, ...meta }) => {
    let metaStr = '';
    if (Object.keys(meta).length) {
      try {
        metaStr = JSON.stringify(meta, null, 2);
      } catch (error) {
        metaStr = '[Object with circular reference]';
      }
    }
    return `${timestamp} [${level}]: ${message} ${metaStr}`;
  })
);

// Formato de log para produção (JSON)
const prodFormat = combine(
  timestamp(),
  json()
);

const logger = winston.createLogger({
  level: config.logLevel,
  format: config.nodeEnv === 'production' ? prodFormat : devFormat,
  transports: [new winston.transports.Console()],
  exitOnError: false,
});

module.exports = logger;
