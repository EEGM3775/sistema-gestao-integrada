
const agendaService = require('../services/agendaService');
const logger = require('../logger');

async function getAgenda(req, res) {
    const { userId } = req.params;
    const { start, end } = req.query; // Parâmetros que o FullCalendar envia

    if (!userId || !start || !end) {
        return res.status(400).json({ error: 'userId, start e end são parâmetros obrigatórios.' });
    }

    try {
        logger.info(`Requisição de agenda para o usuário: ${userId}`);
        const events = await agendaService.getAgendaForUser(userId, start, end);
        res.status(200).json(events);
    } catch (error) {
        logger.error(`Erro no controller ao buscar agenda para o usuário ${userId}:`, error);
        res.status(500).json({ error: error.message });
    }
}

module.exports = {
    getAgenda
};
