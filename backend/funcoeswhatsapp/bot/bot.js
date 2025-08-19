// backend/funcoeswhatsapp/bot/bot.js
const { identifyUser } = require('../services/apiService');
const { sendTextMessage } = require('../services/whatsappService');
const cache = require('../services/cacheService');
const commandRouter = require('./commandRouter');
const fs = require('fs');
const path = require('path');

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
    await sendTextMessage(from, "Sessão encerrada. Para começar de novo, envie uma palavra-chave como 'diario'.");
    return;
  }

  const currentState = await cache.getState(from);

  // Se o usuário já está em um fluxo, o contexto já existe.
  if (currentState && currentState.flow && flows[currentState.flow]) {
    const context = {
      from,
      message,
      user: currentState.user,
      userRole: currentState.role,
      state: currentState,
      setState: (newState) => cache.setState(from, newState),
      clearState: () => cache.deleteState(from),
    };
    const activeFlow = flows[currentState.flow];
    await activeFlow.handleMessage(context);
  } else {
    // Se não há fluxo, identifica o usuário antes de prosseguir.
    const { user, role, error } = await identifyUser(`+${from}`);
    if (error) {
      await sendTextMessage(from, error);
      return;
    }

    const context = {
      from,
      message,
      user,
      userRole: role,
      state: currentState, // será null aqui
      setState: (newState) => cache.setState(from, { ...newState, user, role }), // Garante que user e role sejam salvos no estado
      clearState: () => cache.deleteState(from),
    };
    
    await commandRouter.handleCommand(context);
  }
};

module.exports = {
  handleMessage,
};
