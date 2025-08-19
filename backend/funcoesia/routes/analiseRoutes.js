// backend/funcoesia/routes/analiseRoutes.js
const express = require('express');
const router = express.Router();
const analiseController = require('../controllers/analiseController');
const { verifyServiceToken } = require('../middleware/authMiddleware');

// Rota para iniciar o processo de análise de uma imagem
// A rota agora está protegida e só aceita requisições com o token secreto.
router.post('/', verifyServiceToken, analiseController.iniciarAnalise);

module.exports = router;
