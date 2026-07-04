// backend/funcoeslead/controllers/googleController.js
const googleApiService = require('../services/googleApiService');
const logger = require('../logger');
const djangoApi = require('../services/djangoApiService');

/**
 * Redireciona o usuário para a tela de autorização do Google.
 */
function redirectToGoogleAuth(req, res) {
    const { userId } = req.query;
    if (!userId) {
        return res.status(400).json({ error: 'O ID do usuário (userId) é obrigatório.' });
    }

    const authUrl = googleApiService.getAuthUrl();
    // Armazena o userId na sessão para usar no callback
    // req.session.userId = userId; // Requer configuração de sessão (ex: express-session)
    // Por enquanto, vamos passar o userId no estado para simplificar
    const state = Buffer.from(JSON.stringify({ userId })).toString('base64');
    const finalAuthUrl = `${authUrl}&state=${state}`;

    logger.info(`Redirecionando usuário ${userId} para autorização do Google.`);
    res.redirect(finalAuthUrl);
}

/**
 * Lida com o callback do Google após a autorização.
 */
async function handleGoogleCallback(req, res) {
    const { code, state } = req.query;

    if (!code || !state) {
        return res.status(400).json({ error: 'Código de autorização ou estado não encontrado.' });
    }

    let userId;
    try {
        const decodedState = JSON.parse(Buffer.from(state, 'base64').toString('ascii'));
        userId = decodedState.userId;
    } catch (error) {
        logger.error('Erro ao decodificar o estado do OAuth:', error);
        return res.status(400).json({ error: 'Estado (state) inválido.' });
    }

    if (!userId) {
        return res.status(400).json({ error: 'ID do usuário não encontrado no estado.' });
    }

    try {
        const tokens = await googleApiService.getAccessToken(code);
        logger.info(`Tokens recebidos para o usuário ${userId}.`);

        const expiryDate = new Date(tokens.expiry_date);

        const googleAccountData = {
            user: userId,
            access_token: tokens.access_token,
            refresh_token: tokens.refresh_token,
            expires_at: expiryDate.toISOString(),
        };

        try {
            // Tenta obter a conta existente
            const response = await djangoApi.apiClient.get(`/api/api/google-accounts/get-by-user/${userId}/`);
            const existingAccountId = response.data.id;
            // Se existir, atualiza (PATCH)
            await djangoApi.apiClient.patch(`/api/api/google-accounts/${existingAccountId}/`, googleAccountData);
            logger.info(`Tokens para o usuário ${userId} foram atualizados no Django.`);
        } catch (error) {
            if (error.response && error.response.status === 404) {
                // Se não existir, cria (POST)
                await djangoApi.apiClient.post(`/api/api/google-accounts/`, googleAccountData);
                logger.info(`Tokens para o usuário ${userId} foram criados no Django.`);
            } else {
                // Outro erro
                throw error;
            }
        }

        res.status(200).send('<h1>Autorização concedida!</h1><p>Você já pode fechar esta janela.</p>');

    } catch (error) {
        logger.error(`Erro no callback do Google para o usuário ${userId}:`, error);
        res.status(500).json({ error: 'Falha ao processar a autorização do Google.' });
    }
}

module.exports = {
    redirectToGoogleAuth,
    handleGoogleCallback
};
