
const express = require('express');
const router = express.Router();
const { getAgenda } = require('../controllers/agendaController');

/**
 * @swagger
 * /api/users/{userId}/agenda:
 *   get:
 *     summary: Retorna a agenda de um usuário com base em um período.
 *     tags: [Agenda]
 *     parameters:
 *       - in: path
 *         name: userId
 *         schema:
 *           type: string
 *         required: true
 *         description: O ID do usuário.
 *       - in: query
 *         name: start
 *         schema:
 *           type: string
 *           format: date-time
 *         required: true
 *         description: Data de início do período.
 *       - in: query
 *         name: end
 *         schema:
 *           type: string
 *           format: date-time
 *         required: true
 *         description: Data de fim do período.
 *     responses:
 *       200:
 *         description: Lista de eventos da agenda.
 *         content:
 *           application/json:
 *             schema:
 *               type: array
 *               items:
 *                 type: object
 *       400:
 *         description: Parâmetros obrigatórios não fornecidos.
 *       500:
 *         description: Erro interno do servidor.
 */
router.get('/users/:userId/agenda', getAgenda);

module.exports = router;
