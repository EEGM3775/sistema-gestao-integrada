// backend/funcoeslead/services/googleApiService.js
const { google } = require('googleapis');
const config = require('../config');
const logger = require('../logger');

// Cria o cliente OAuth2
const oauth2Client = new google.auth.OAuth2(
    config.google.clientId,
    config.google.clientSecret,
    config.google.redirectUri
);

/**
 * Gera a URL de autorização do Google.
 * @returns {string} A URL para o usuário autorizar o acesso.
 */
function getAuthUrl() {
    const scopes = [
        'https://www.googleapis.com/auth/calendar.readonly'
    ];
    const url = oauth2Client.generateAuthUrl({
        access_type: 'offline',
        scope: scopes
    });
    logger.info('URL de autorização do Google gerada.');
    return url;
}

/**
 * Obtém o token de acesso a partir do código de autorização.
 * @param {string} code O código de autorização retornado pelo Google.
 * @returns {Promise<object>} Os tokens de acesso.
 */
async function getAccessToken(code) {
    try {
        const { tokens } = await oauth2Client.getToken(code);
        logger.info('Token de acesso do Google obtido com sucesso.');
        // IMPORTANTE: O 'refresh_token' só é fornecido na primeira vez.
        // Você DEVE salvá-lo de forma segura para usar depois.
        return tokens;
    } catch (error) {
        logger.error('Erro ao obter o token de acesso do Google:', error);
        throw new Error('Falha ao obter o token de acesso do Google.');
    }
}

/**
 * Busca eventos do Google Calendar.
 * @param {object} tokens Os tokens de autenticação do usuário.
 * @param {string} startDate Data de início no formato ISO.
 * @param {string} endDate Data de fim no formato ISO.
 * @returns {Promise<Array>} Uma lista de eventos do calendário.
 */
async function getCalendarEvents(tokens, startDate, endDate) {
    try {
        oauth2Client.setCredentials(tokens);
        const calendar = google.calendar({ version: 'v3', auth: oauth2Client });

        const response = await calendar.events.list({
            calendarId: 'primary', // Usa o calendário principal do usuário
            timeMin: startDate,
            timeMax: endDate,
            singleEvents: true,
            orderBy: 'startTime',
        });

        const events = response.data.items.map(event => ({
            title: event.summary,
            start: event.start.dateTime || event.start.date,
            end: event.end.dateTime || event.end.date,
            allDay: !event.start.dateTime, // É um evento de dia inteiro se não tiver hora
            extendedProps: {
                type: 'google_calendar',
                location: event.location,
                description: event.description,
            }
        }));

        logger.info(`Encontrados ${events.length} eventos no Google Calendar.`);
        return events;

    } catch (error) {
        logger.error('Erro ao buscar eventos do Google Calendar:', error);
        // Se o token expirou, o erro pode ser específico (ex: 'invalid_grant')
        // Aqui você poderia implementar a lógica de refresh token.
        throw new Error('Falha ao buscar eventos do Google Calendar.');
    }
}


module.exports = {
    getAuthUrl,
    getAccessToken,
    getCalendarEvents,
    oauth2Client // Exporta para uso em outros lugares, se necessário
};
