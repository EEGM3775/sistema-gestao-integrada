// backend/funcoeslead/index.js
const express = require('express');
const config = require('./config');
const logger = require('./logger');

const app = express();

// Middleware
app.use(express.json());

// Rota de Health Check
app.get('/', (req, res) => {
    res.status(200).json({ status: 'ok', service: 'funcoeslead' });
});

// Rotas da aplicação
const leadRoutes = require('./routes/leadRoutes');
const agendaRoutes = require('./routes/agendaRoutes');
const notificationService = require('./services/notificationService');

app.use('/api/leads', leadRoutes);
app.use('/api', agendaRoutes);

// Iniciar o worker de notificação
notificationService.startNotificationWorker();

// Iniciar o servidor
app.listen(config.port, () => {
    logger.info(`Serviço de Funções de Lead rodando na porta ${config.port}`);
});

// Tratamento de erros não capturados
process.on('uncaughtException', (error) => {
    logger.error('Uncaught Exception:', error);
    process.exit(1);
});

process.on('unhandledRejection', (reason, promise) => {
    logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
});
