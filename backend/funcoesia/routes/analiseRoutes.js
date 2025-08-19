// backend/funcoesia/routes/analiseRoutes.js
const express = require('express');
const router = express.Router();
const analiseController = require('../controllers/analiseController');
const { verifyServiceToken } = require('../middleware/authMiddleware');
const rateLimit = require('express-rate-limit');

// Configura o limitador de taxa para o endpoint de análise
const analiseLimiter = rateLimit({
	windowMs: 15 * 60 * 1000, // 15 minutos
	max: 300, // Limita cada IP a 300 requisições por janela (aqui, por 15 minutos)
	standardHeaders: true, // Retorna informações do limite nos cabeçalhos `RateLimit-*`
	legacyHeaders: false, // Desabilita os cabeçalhos `X-RateLimit-*`
    message: 'Muitas requisições enviadas deste IP, por favor, tente novamente após 15 minutos.',
});

// Rota para iniciar o processo de análise de uma imagem
// A rota agora está protegida com token e com limitador de taxa.
router.post('/', analiseLimiter, verifyServiceToken, analiseController.iniciarAnalise);

module.exports = router;
