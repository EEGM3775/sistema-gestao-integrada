// backend/funcoesia/index.js
const express = require('express');
const config = require('./config');
const logger = require('./logger');

const app = express();
app.use(express.json());

// Rota de health check
app.get('/health', (req, res) => {
  res.status(200).send('OK');
});

// Futuramente, aqui entrarão as rotas da API
app.use('/api/analise', require('./routes/analiseRoutes'));

const server = app.listen(config.port, () => {
  logger.info(`Serviço de IA rodando na porta ${config.port}`);
  logger.info(`Ambiente: ${config.nodeEnv}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  logger.info('Recebido SIGTERM. Encerrando o serviço de IA...');
  server.close(() => {
    logger.info('Serviço de IA encerrado.');
    process.exit(0);
  });
});
