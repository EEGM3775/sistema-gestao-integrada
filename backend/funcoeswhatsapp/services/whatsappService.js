const axios = require('axios');

const sendTextMessage = async (to, text) => {
  const url = `https://graph.facebook.com/${process.env.META_API_VERSION}/${process.env.META_PHONE_NUMBER_ID}/messages`;
  const headers = {
    "Authorization": `Bearer ${process.env.META_ACCESS_TOKEN}`,
    "Content-Type": "application/json",
  };
  const payload = {
    "messaging_product": "whatsapp",
    "to": to,
    "text": { "body": text },
  };

  try {
    await axios.post(url, payload, { headers });
    console.log(`Mensagem enviada para ${to}: "${text}"`);
  } catch (error) {
    console.error(`Erro ao enviar mensagem para ${to}:`, error.response ? error.response.data : error.message);
  }
};

module.exports = {
  sendTextMessage,
};
