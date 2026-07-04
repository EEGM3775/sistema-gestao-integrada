// backend/funcoeslead/services/leadScoringService.js
const djangoApi = require('./djangoApiService');
const logger = require('../logger');

/**
 * Calcula a pontuação de um Lead com base em regras pré-definidas.
 * @param {object} lead O objeto do Lead.
 * @returns {number} A pontuação calculada.
 */
function calculateScore(lead) {
    let score = 0;

    // Critério 1: Origem do Lead
    if (lead.source) {
        switch (lead.source.toLowerCase()) {
            case 'indicação':
                score += 30;
                break;
            case 'site':
                score += 20;
                break;
            case 'evento':
                score += 10;
                break;
        }
    }

    // Critério 2: Informações de Contato
    if (lead.company) {
        score += 20;
    }
    if (lead.phone) {
        score += 10;
    }

    logger.info(`Pontuação calculada para o Lead ${lead.id}: ${score}`);
    return score;
}

/**
 * Busca um lead, calcula sua pontuação e o atualiza no Django.
 * @param {string} leadId O ID do Lead a ser pontuado.
 * @returns {Promise<object>} O lead atualizado com a nova pontuação.
 */
async function scoreLead(leadId) {
    logger.info(`Iniciando processo de pontuação para o Lead ID: ${leadId}`);

    // 1. Buscar o Lead
    const lead = await djangoApi.getObject('/crm/leads/', leadId);

    // 2. Calcular a pontuação
    const score = calculateScore(lead);

    // 3. Atualizar o Lead com a nova pontuação
    const updatedLead = await djangoApi.updateObject('/crm/leads/', leadId, { score });

    logger.info(`Lead ${leadId} atualizado com a pontuação: ${score}`);
    
    return updatedLead;
}

module.exports = {
    scoreLead,
    calculateScore
};
