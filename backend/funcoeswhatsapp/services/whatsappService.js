const axios = require('axios');
const config = require('../config');
const logger = require('../logger');

const whatsappApi = axios.create({
  baseURL: `https://graph.facebook.com/${config.meta.apiVersion}`,
  headers: {
    'Authorization': `Bearer ${config.meta.accessToken}`,
    'Content-Type': 'application/json',
  }
});

/**
 * Envia uma mensagem de texto simples.
 * @param {string} to - Número do destinatário (sem o '+').
 * @param {string} text - O conteúdo da mensagem.
 */
const sendTextMessage = async (to, text) => {
  try {
    const payload = {
      messaging_product: 'whatsapp',
      to: to,
      type: 'text',
      text: { body: text },
    };
    await whatsappApi.post(`/${config.meta.phoneNumberId}/messages`, payload);
    logger.info(`Mensagem de texto enviada para ${to}.`);
  } catch (error) {
    logger.error(`Erro ao enviar mensagem de texto para ${to}:`, error.response?.data || error.message);
  }
};

/**
 * Envia uma mensagem interativa com botões de resposta rápida.
 * @param {string} to - Número do destinatário.
 * @param {string} text - O texto principal da mensagem.
 * @param {Array<{id: string, title: string}>} buttons - Uma lista de até 3 botões.
 */
const sendQuickReplyButtons = async (to, text, buttons) => {
  if (buttons.length > 3) {
    logger.warn("O WhatsApp permite no máximo 3 botões de resposta rápida.");
    buttons = buttons.slice(0, 3);
  }

  try {
    const payload = {
      messaging_product: 'whatsapp',
      to: to,
      type: 'interactive',
      interactive: {
        type: 'button',
        body: {
          text: text,
        },
        action: {
          buttons: buttons.map(btn => ({
            type: 'reply',
            reply: {
              id: btn.id,
              title: btn.title,
            },
          })),
        },
      },
    };
    await whatsappApi.post(`/${config.meta.phoneNumberId}/messages`, payload);
    logger.info(`Mensagem interativa enviada para ${to}.`);
  } catch (error) {
    logger.error(`Erro ao enviar mensagem interativa para ${to}:`, error.response?.data || error.message);
  }
};

/**
 * Envia uma mensagem interativa com uma lista de opções.
 * @param {string} to - Número do destinatário.
 * @param {string} text - O texto principal da mensagem (body).
 * @param {string} buttonText - O texto do botão que abre a lista (ex: "Ver Opções").
 * @param {Array<{id: string, title: string, description?: string}>} items - Uma lista de até 10 itens.
 */
const sendListMessage = async (to, text, buttonText, items) => {
  if (items.length > 10) {
    logger.warn("O WhatsApp permite no máximo 10 itens em uma mensagem de lista.");
    items = items.slice(0, 10);
  }

  console.log('DEBUG sendListMessage: items recebidos =', items);
  console.log('DEBUG sendListMessage: buttonText =', buttonText);
  console.log('DEBUG sendListMessage: text =', text);

  try {
    const payload = {
      messaging_product: 'whatsapp',
      to: to,
      type: 'interactive',
      interactive: {
        type: 'list',
        header: {
          type: 'text',
          text: 'Opções Disponíveis',
        },
        body: {
          text: text,
        },
        footer: {
          text: 'Selecione uma opção',
        },
        action: {
          button: buttonText.substring(0, 20),
          sections: [
            {
              title: 'Lista',
              rows: items.map(item => ({
                id: item.id.substring(0, 200), // Limite de ID
                title: item.title ? item.title.substring(0, 24) : 'Sem título',
                description: item.description ? item.description.substring(0, 72) : '',
              })),
            },
          ],
        },
      },
    };
    
    console.log('DEBUG sendListMessage: payload =', JSON.stringify(payload, null, 2));
    
    await whatsappApi.post(`/${config.meta.phoneNumberId}/messages`, payload);
    logger.info(`Mensagem de lista enviada para ${to}.`);
  } catch (error) {
    console.log('DEBUG sendListMessage: erro detalhado =', error.response?.data || error.message);
    logger.error(`Erro ao enviar mensagem de lista para ${to}:`, error.response?.data || error.message);
  }
};

/**
 * Baixa a mídia da URL fornecida pela Meta.
 * @param {string} mediaId
 * @returns {Promise<{fileBuffer: Buffer, mimeType: string}|null>}
 */
const downloadMedia = async (mediaId) => {
  try {
    const url_get = `https://graph.facebook.com/${config.meta.apiVersion}/${mediaId}/`;
    const headers = { "Authorization": `Bearer ${config.meta.accessToken}` };
    const mediaInfoResponse = await axios.get(url_get, { headers });
    const mediaUrl = mediaInfoResponse.data.url;

    if (!mediaUrl) {
      throw new Error("URL de download da mídia não encontrada na resposta da Meta.");
    }

    const downloadResponse = await axios.get(mediaUrl, {
      headers,
      responseType: 'arraybuffer'
    });

    return {
      fileBuffer: downloadResponse.data,
      mimeType: downloadResponse.headers['content-type'],
    };
  } catch (error) {
    logger.error(`Falha ao baixar mídia com ID ${mediaId}:`, { error: error.response ? error.response.data : error.message });
    return null;
  }
};

module.exports = {
  sendTextMessage,
  sendQuickReplyButtons,
  sendListMessage,
  downloadMedia,
};
