const redis = require('redis');

// Cria o cliente Redis
const redisClient = redis.createClient({
  url: process.env.REDIS_URL,
});

// Gerencia a conexão
redisClient.on('connect', () => console.log('Conectado ao Redis com sucesso!'));
redisClient.on('error', (err) => console.error('Erro de Conexão com o Redis:', err));

// Conecta ao Redis assim que o serviço inicia
redisClient.connect();

const CONVERSATION_PREFIX = 'whatsapp_state:';
const CONVERSATION_TIMEOUT_SECONDS = 3600; // 1 hora

/**
 * Obtém o estado da conversa de um usuário.
 * @param {string} fromNumber 
 * @returns {Promise<object|null>}
 */
const getState = async (fromNumber) => {
  try {
    const key = `${CONVERSATION_PREFIX}${fromNumber}`;
    const stateJSON = await redisClient.get(key);
    return stateJSON ? JSON.parse(stateJSON) : null;
  } catch (error) {
    console.error('Erro ao obter estado do Redis:', error);
    return null;
  }
};

/**
 * Define o estado da conversa de um usuário.
 * @param {string} fromNumber 
 * @param {object} state 
 */
const setState = async (fromNumber, state) => {
  try {
    const key = `${CONVERSATION_PREFIX}${fromNumber}`;
    await redisClient.set(key, JSON.stringify(state), {
      EX: CONVERSATION_TIMEOUT_SECONDS, // Define um tempo de expiração
    });
  } catch (error) {
    console.error('Erro ao definir estado no Redis:', error);
  }
};

/**
 * Deleta o estado da conversa de um usuário.
 * @param {string} fromNumber 
 */
const deleteState = async (fromNumber) => {
  try {
    const key = `${CONVERSATION_PREFIX}${fromNumber}`;
    await redisClient.del(key);
  } catch (error) {
    console.error('Erro ao deletar estado do Redis:', error);
  }
};

module.exports = {
  getState,
  setState,
  deleteState,
};
