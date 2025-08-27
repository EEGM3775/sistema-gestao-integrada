
const djangoApi = require('./djangoApiService');
const logger = require('../logger');

async function getAgendaForUser(userId, startDate, endDate) {
    logger.info(`Buscando agenda para o usuário ${userId} de ${startDate} a ${endDate}`);

    try {
        // Busca interações do tipo 'Tarefa' e 'Reunião' no período
        const params = {
            assigned_to_id: userId,
            interaction_type__in: ['tarefa', 'reuniao'],
            due_date__gte: startDate,
            due_date__lte: endDate,
        };

        const interactions = await djangoApi.apiClient.get('/crm/interactions/', { params });

        // Formata os eventos para o FullCalendar
        const events = interactions.data.map(interaction => ({
            title: interaction.subject,
            start: interaction.due_date,
            end: interaction.due_date, // Pode ser ajustado se houver data de fim
            allDay: true, // Assumindo que são tarefas de dia inteiro por enquanto
            extendedProps: {
                type: interaction.interaction_type,
                notes: interaction.notes,
                status: interaction.status,
            }
        }));

        logger.info(`${events.length} eventos encontrados para o usuário ${userId}`);
        return events;

    } catch (error) {
        logger.error(`Erro ao buscar agenda para o usuário ${userId}:`, error);
        throw new Error('Falha ao buscar dados da agenda do CRM.');
    }
}

module.exports = {
    getAgendaForUser
};
