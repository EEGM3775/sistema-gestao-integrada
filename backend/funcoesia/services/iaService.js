// backend/funcoesia/services/iaService.js
const { GoogleGenerativeAI } = require('@google/generative-ai');
const config = require('../config');
const logger = require('../logger');

const genAI = new GoogleGenerativeAI(config.googleApiKey);

/**
 * Analisa uma imagem usando a API do Google Gemini com um prompt específico.
 * @param {Buffer} imageBuffer - O buffer da imagem a ser analisada.
 * @param {string} mimeType - O tipo MIME da imagem (ex: 'image/jpeg').
 * @param {string} prompt - O prompt de instrução para a IA.
 * @returns {Promise<object>} - O resultado da análise em formato JSON.
 */
async function analisarImagem(imageBuffer, mimeType, prompt) {
  try {
    const model = genAI.getGenerativeModel({ model: "gemini-pro-vision" });

    const imagePart = {
      inlineData: {
        data: imageBuffer.toString("base64"),
        mimeType,
      },
    };

    const result = await model.generateContent([prompt, imagePart]);
    const response = await result.response;
    const text = response.text();

    // Limpa a resposta para garantir que seja um JSON válido
    const cleanedJson = text.replace(/```json/g, '').replace(/```/g, '').trim();
    return JSON.parse(cleanedJson);

  } catch (error) {
    logger.error('Erro ao analisar imagem com a API do Gemini:', error);
    throw new Error('Falha ao processar a imagem com a IA.');
  }
}

module.exports = {
  analisarImagem,
};
