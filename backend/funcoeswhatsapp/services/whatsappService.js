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

  try {
    const payload = {
      messaging_product: 'whatsapp',
      to: to,
      type: 'interactive',
      interactive: {
        type: 'list',
        header: {
          type: 'text',
          text: 'Opções Disponíveis', // Título da lista
        },
        body: {
          text: text,
        },
        footer: {
          text: 'Selecione uma opção', // Rodapé opcional
        },
        action: {
          button: buttonText.substring(0, 20),
          sections: [
            {
              title: 'Seções', // Título da seção é obrigatório
              rows: items.map(item => ({
                id: item.id,
                title: item.title.substring(0, 24), // Limite de 24 chars
                description: item.description ? item.description.substring(0, 72) : '', // Limite de 72 chars
              })),
            },
          ],
        },
      },
    };
    await whatsappApi.post(`/${config.meta.phoneNumberId}/messages`, payload);
    logger.info(`Mensagem de lista enviada para ${to}.`);
  } catch (error) {
    logger.error(`Erro ao enviar mensagem de lista para ${to}:`, error.response?.data || error.message);
  }
};

module.exports = {
  sendTextMessage,
  sendQuickReplyButtons,
  sendListMessage,
};
