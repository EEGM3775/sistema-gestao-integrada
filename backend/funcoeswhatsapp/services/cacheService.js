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
 * Obtém um valor genérico do cache.
 * @param {string} key 
 * @returns {Promise<any|null>}
 */
const get = async (key) => {
  try {
    const valueJSON = await redisClient.get(key);
    return valueJSON ? JSON.parse(valueJSON) : null;
  } catch (error) {
    console.error(`Erro ao obter a chave '${key}' do Redis:`, error);
    return null;
  }
};

/**
 * Define um valor genérico no cache com um TTL (tempo de vida).
 * @param {string} key 
 * @param {any} value 
 * @param {number} ttlSeconds - Tempo de expiração em segundos.
 */
const set = async (key, value, ttlSeconds) => {
  try {
    await redisClient.set(key, JSON.stringify(value), {
      EX: ttlSeconds,
    });
  } catch (error) {
    console.error(`Erro ao definir a chave '${key}' no Redis:`, error);
  }
};

/**
 * Obtém o estado da conversa de um usuário.
 * @param {string} fromNumber 
 * @returns {Promise<object|null>}
 */
const getState = async (fromNumber) => {
  const key = `${CONVERSATION_PREFIX}${fromNumber}`;
  return await get(key);
};

/**
 * Define o estado da conversa de um usuário.
 * @param {string} fromNumber 
 * @param {object} state 
 */
const setState = async (fromNumber, state) => {
  const key = `${CONVERSATION_PREFIX}${fromNumber}`;
  await set(key, state, CONVERSATION_TIMEOUT_SECONDS);
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
  get,
  set,
  getState,
  setState,
  deleteState,
};
