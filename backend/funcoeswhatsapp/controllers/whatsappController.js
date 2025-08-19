const crypto = require('crypto');
const bot = require('../bot/bot');
const logger = require('../logger');
const config = require('../config');
const { sanitizeWebhookPayload } = require('../utils');

// Função para a verificação do webhook (GET)
const verifyWebhook = (req, res) => {
  const verifyToken = config.meta.verifyToken;

  if (req.query['hub.mode'] === 'subscribe' && req.query['hub.verify_token'] === verifyToken) {
    logger.info("Webhook verificado com sucesso!");
    res.status(200).send(req.query['hub.challenge']);
  } else {
    logger.error("Falha na verificação do webhook. Tokens não correspondem.", {
      query: req.query
    });
    res.sendStatus(403);
  }
};

// Função para lidar com as mensagens recebidas (POST)
const handleWebhook = (req, res) => {
  // 1. Validar a assinatura da requisição (Segurança)
  const signature = req.headers['x-hub-signature-256'];
  if (!signature) {
    logger.error("Requisição de webhook descartada: Assinatura não encontrada.");
    return res.sendStatus(403);
  }

  const appSecret = config.meta.appSecret;
  const expectedSignature = crypto.createHmac('sha256', appSecret).update(req.body).digest('hex');

  if (signature !== `sha256=${expectedSignature}`) {
    logger.error("Requisição de webhook descartada: Assinatura inválida.");
    return res.sendStatus(403);
  }

  // 2. Processar a mensagem
  let data;
  try {
    // Como o corpo é um buffer, precisamos convertê-lo para string antes do JSON.parse
    data = JSON.parse(req.body.toString());
    
    // Log seguro do payload recebido
    logger.info('Payload de webhook recebido.', { payload: sanitizeWebhookPayload(data) });

    if (data.object === 'whatsapp_business_account' && data.entry?.[0]?.changes?.[0]?.value?.messages?.[0]) {
      const messageData = data.entry[0].changes[0].value.messages[0];
      const from = messageData.from;
      
      let messageBody = '';
      let mediaId = null;
      const messageType = messageData.type;

      if (messageType === 'text') {
        messageBody = messageData.text.body.trim();
      } else if (messageType === 'interactive') {
        const interactiveType = messageData.interactive.type;
        if (interactiveType === 'button_reply') {
          messageBody = messageData.interactive.button_reply.id;
        } else if (interactiveType === 'list_reply') {
          messageBody = messageData.interactive.list_reply.id;
        }
      } else if (['image', 'video', 'audio', 'document'].includes(messageType)) {
        mediaId = messageData[messageType].id;
      } else {
        logger.info(`Tipo de mensagem '${messageType}' ignorado.`);
        return res.sendStatus(200);
      }

      // Monta um objeto de mensagem padronizado
      const message = {
        body: messageBody,
        mediaId: mediaId,
        type: messageType,
      };

      // Envia para o orquestrador do bot
      bot.handleMessage(from, message);
    }
  } catch (error) {
    logger.error("Erro ao processar webhook:", { 
      error: error.message,
      stack: error.stack,
      // Loga o payload sanitizado em caso de erro para depuração segura
      payload: data ? sanitizeWebhookPayload(data) : 'Payload não pôde ser parseado'
    });
  }

  // 3. Responder imediatamente à Meta
  res.sendStatus(200);
};

module.exports = {
  verifyWebhook,
  handleWebhook,
};
