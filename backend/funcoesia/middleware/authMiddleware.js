// backend/funcoesia/middleware/authMiddleware.js
const config = require('../config');
const logger = require('../logger');

function verifyServiceToken(req, res, next) {
  const token = req.headers['x-internal-service-token'];

  if (!token) {
    logger.warn('Tentativa de acesso sem token de serviço.');
    return res.status(401).json({ error: 'Token de autenticação não fornecido.' });
  }

  if (token !== config.iaServiceSecretToken) {
    logger.warn('Tentativa de acesso com token de serviço inválido.');
    return res.status(403).json({ error: 'Token de autenticação inválido.' });
  }

  next();
}

module.exports = {
  verifyServiceToken,
};
