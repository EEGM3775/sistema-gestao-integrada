// backend/funcoesia/routes/analiseRoutes.js
const express = require('express');
const router = express.Router();
const analiseController = require('../controllers/analiseController');
const { verifyServiceToken } = require('../middleware/authMiddleware');
const rateLimit = require('express-rate-limit');

// Configura o limitador de taxa para os endpoints de análise
const analiseLimiter = rateLimit({
	windowMs: 15 * 60 * 1000, // 15 minutos
	max: 300, // Limita cada IP a 300 requisições por janela
	standardHeaders: true,
	legacyHeaders: false,
    message: 'Muitas requisições enviadas deste IP, por favor, tente novamente após 15 minutos.',
});

// Rota para listar tipos de análise disponíveis organizados por categoria
router.get('/tipos', verifyServiceToken, analiseController.listarTiposAnalise);

// Rota para obter recomendações de tipos de análise baseado na categoria/fase
router.get('/recomendacoes', verifyServiceToken, analiseController.recomendarTipos);

// Rota para validar um tipo específico de análise
router.get('/tipos/:tipo/validar', verifyServiceToken, analiseController.validarTipoAnalise);

// Rota para iniciar o processo de análise de uma imagem
router.post('/', analiseLimiter, verifyServiceToken, analiseController.iniciarAnalise);

module.exports = router;
