// backend/funcoeswhatsapp/bot/bot.js
const { identifyUser } = require('../services/apiService');
const { sendTextMessage } = require('../services/whatsappService');
const cache = require('../services/cacheService');
const commandRouter = require('./commandRouter');
const fs = require('fs');
const path = require('path');
const logger = require('../logger');

// Carrega dinamicamente todos os fluxos disponíveis da pasta /flows
const flows = {};
const flowsDir = path.join(__dirname, 'flows');
fs.readdirSync(flowsDir).forEach(file => {
  if (file.endsWith('.js')) {
    const flowName = path.basename(file, '.js').replace('Flow', '');
    flows[flowName] = require(path.join(flowsDir, file));
  }
});

const handleMessage = async (from, message) => {
  const { body: messageBody } = message;

  if (messageBody && messageBody.toLowerCase() === 'sair') {
    await cache.deleteState(from);
    await sendTextMessage(from, "Sessão encerrada. Para começar de novo, envie uma mensagem.");
    return;
  }

  // 1. Identificação obrigatória a cada mensagem recebida
  const { user, role, error } = await identifyUser(`+${from}`);
  if (error) {
    await sendTextMessage(from, error);
    return;
  }

  // 2. Verificação de conversa ativa
  const currentState = await cache.getState(from);

  const context = {
    from,
    message,
    user,
    userRole: role,
    state: currentState,
    // Atualiza o estado no Redis, sempre incluindo os dados de usuário mais recentes
    setState: (newState) => cache.setState(from, { ...newState, user, role }),
    clearState: () => cache.deleteState(from),
  };

  // 3. Roteamento da lógica
  if (currentState) {
    // Conversa em andamento
    // Verificação de consistência de segurança: o perfil do usuário mudou?
    if (currentState.role !== role) {
      await context.clearState();
      await sendTextMessage(from, "Notamos uma alteração em seu cadastro. Por segurança, sua sessão foi reiniciada. Por favor, envie sua mensagem novamente.");
      return;
    }
    
    const activeFlow = flows[currentState.flow];
    if (activeFlow) {
      await activeFlow.handleMessage(context);
    } else {
      // Estado órfão (ex: fluxo foi removido), limpa e informa o usuário
      await context.clearState();
      await sendTextMessage(from, "Ocorreu um erro em sua sessão e ela foi reiniciada. Por favor, envie sua mensagem novamente.");
    }
  } else {
    // Conversa nova
    if (role === 'unknown') {
      await flows.preCadastro.start(context);
    } else {
      // Para usuários conhecidos, vai para o roteador de comandos para iniciar um novo fluxo
      await commandRouter.handleCommand(context);
    }
  }
};

module.exports = {
  handleMessage,
};
