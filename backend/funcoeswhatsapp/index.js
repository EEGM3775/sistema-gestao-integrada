// Importa as dependências
const config = require('./config');
const express = require('express');
const whatsappRoutes = require('./routes/whatsapp');
const logger = require('./logger');

// Configura o servidor Express
const app = express();
const PORT = config.port;

// Middleware para processar o corpo das requisições
// A Meta exige que o 'raw body' seja usado para a verificação da assinatura,
// então o middleware de parsing é aplicado diretamente nas rotas, conforme necessário.

// Define as rotas
app.get('/', (req, res) => {
  res.send('Serviço de WhatsApp está no ar!');
});

app.use('/whatsapp', whatsappRoutes);

// Inicia o servidor
app.listen(PORT, () => {
  logger.info(`Serviço de WhatsApp rodando na porta ${PORT}`);
});
