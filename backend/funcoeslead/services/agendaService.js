
const djangoApi = require('./djangoApiService');
const logger = require('../logger');
const googleApiService = require('./googleApiService');

async function getAgendaForUser(userId, startDate, endDate) {
    logger.info(`Buscando agenda para o usuário ${userId} de ${startDate} a ${endDate}`);

    try {
        // Busca interações do CRM
        const crmParams = {
            assigned_to_id: userId,
            interaction_type__in: ['tarefa', 'reuniao'],
            due_date__gte: startDate,
            due_date__lte: endDate,
            lead__isnull: false,
        };
        const interactions = await djangoApi.apiClient.get('/crm/interactions/', { params: crmParams });
        const crmEvents = interactions.data.map(interaction => ({
            title: interaction.subject,
            start: interaction.due_date,
            end: interaction.due_date,
            allDay: true,
            extendedProps: {
                type: interaction.interaction_type,
                notes: interaction.notes,
                status: interaction.status,
            }
        }));
        logger.info(`${crmEvents.length} eventos de CRM encontrados para o usuário ${userId}`);

        let googleEvents = [];
        try {
            const response = await djangoApi.apiClient.get(`/api/api/google-accounts/get-by-user/${userId}/`);
            const googleAccount = response.data;
            if (googleAccount && googleAccount.access_token) {
                const tokens = {
                    access_token: googleAccount.access_token,
                    refresh_token: googleAccount.refresh_token,
                    expiry_date: new Date(googleAccount.expires_at).getTime(),
                };
                googleEvents = await googleApiService.getCalendarEvents(tokens, startDate, endDate);
            }
        } catch (error) {
            if (error.response && error.response.status === 404) {
                logger.info(`Usuário ${userId} não possui conta do Google associada.`);
            } else {
                logger.error(`Erro ao buscar eventos do Google Calendar para o usuário ${userId}:`, error);
                // Não vamos parar a execução, apenas logar o erro.
            }
        }

        const allEvents = [...crmEvents, ...googleEvents];
        logger.info(`Total de ${allEvents.length} eventos encontrados para o usuário ${userId}`);
        return allEvents;

    } catch (error) {
        logger.error(`Erro ao buscar agenda para o usuário ${userId}:`, error);
        throw new Error('Falha ao buscar dados da agenda.');
    }
}

module.exports = {
    getAgendaForUser
};
