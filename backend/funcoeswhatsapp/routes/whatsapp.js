const express = require('express');
const { verifyWebhook, handleWebhook } = require('../controllers/whatsappController');

const router = express.Router();

// Rota para a verificação do webhook da Meta (GET)
// Não precisa de middleware de corpo.
router.get('/webhook', verifyWebhook);

// Rota para receber as mensagens (POST)
// Usa o middleware 'express.raw' para obter o corpo da requisição como um buffer,
// o que é essencial para a validação da assinatura.
router.post('/webhook', express.raw({ type: 'application/json' }), handleWebhook);

module.exports = router;