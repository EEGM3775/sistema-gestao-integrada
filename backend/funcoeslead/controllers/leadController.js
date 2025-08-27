// backend/funcoeslead/controllers/leadController.js
const leadConversionService = require('../services/leadConversionService');
const logger = require('../logger');

/**
 * Controller para lidar com a conversão de um lead.
 */
async function convertLeadController(req, res) {
    const { leadId } = req.params;

    if (!leadId) {
        return res.status(400).json({ error: 'O ID do Lead é obrigatório.' });
    }

    try {
        logger.info(`Requisição recebida para converter o Lead ID: ${leadId}`);
        const result = await leadConversionService.convertLead(leadId);
        res.status(200).json(result);
    } catch (error) {
        logger.error(`Erro no controller ao converter o Lead ${leadId}:`, error);
        // Personaliza a mensagem de erro para o cliente
        const statusCode = error.response?.status || 500;
        const errorMessage = error.message || 'Ocorreu um erro interno no servidor.';
        res.status(statusCode).json({ error: errorMessage, details: error.response?.data });
    }
}

module.exports = {
    convertLeadController
};
