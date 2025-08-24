const express = require('express');
const { verifyWebhook, handleWebhook } = require('../controllers/whatsappController');
const rateLimit = require('express-rate-limit');

const router = express.Router();

// Configura um limitador de taxa para o endpoint que recebe os webhooks
const webhookLimiter = rateLimit({
	windowMs: 60 * 1000, // 1 minuto
	max: 500, // Limita cada IP a 500 requisições por minuto
	standardHeaders: true,
	legacyHeaders: false,
    message: 'Muitas requisições recebidas deste IP. Tente novamente em um minuto.',
    trustProxy: true, // Confia em proxies como ngrok
    keyGenerator: (req) => {
        // Use o IP real ou um fallback
        return req.ip || req.connection.remoteAddress || 'unknown';
    }
});

// Rota para a verificação do webhook da Meta (GET)
// Não precisa de middleware de corpo.
router.get('/webhook', verifyWebhook);

// Rota para receber as mensagens (POST)
// Aplica o limitador de taxa antes de processar a requisição.
// Usa o middleware 'express.raw' para obter o corpo da requisição como um buffer,
// o que é essencial para a validação da assinatura.
router.post('/webhook', webhookLimiter, express.raw({ type: 'application/json' }), handleWebhook);

module.exports = router;
