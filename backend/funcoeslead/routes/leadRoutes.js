// backend/funcoeslead/routes/leadRoutes.js
const express = require('express');
const router = express.Router();
const { convertLeadController } = require('../controllers/leadController');

/**
 * @swagger
 * /api/leads/{leadId}/convert:
 *   post:
 *     summary: Converte um Lead qualificado em Conta, Contato e Oportunidade.
 *     tags: [Leads]
 *     parameters:
 *       - in: path
 *         name: leadId
 *         schema:
 *           type: string
 *           format: uuid
 *         required: true
 *         description: O ID do Lead a ser convertido.
 *     responses:
 *       200:
 *         description: Lead convertido com sucesso.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 message:
 *                   type: string
 *                 accountId:
 *                   type: string
 *                 contactId:
 *                   type: string
 *                 opportunityId:
 *                   type: string
 *       400:
 *         description: ID do Lead não fornecido ou inválido.
 *       404:
 *         description: Lead não encontrado.
 *       500:
 *         description: Erro interno do servidor.
 */
router.post('/:leadId/convert', convertLeadController);

module.exports = router;
