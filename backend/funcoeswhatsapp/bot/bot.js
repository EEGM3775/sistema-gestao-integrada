// backend/funcoeswhatsapp/bot/bot.js
const { identifyUser } = require('../services/api/authService');
const { sendTextMessage } = require('../services/whatsappService');
const cache = require('../services/cacheService');
const commandRouter = require('./commandRouter');
const fs = require('fs');
const path = require('path');
const logger = require('../logger');
const empreendimentoService = require('../services/api/empreendimentoService');
const obraService = require('../services/api/obraService');
const diarioObraFlow = require('./flows/diarioObraFlow');

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

  console.log('DEBUG bot.js: mensagem recebida =', messageBody);
  console.log('DEBUG bot.js: from =', from);

  if (messageBody && messageBody.toLowerCase() === 'sair') {
    await cache.deleteState(from);
    await sendTextMessage(from, "Sessão encerrada. Para começar de novo, envie uma mensagem.");
    return;
  }

  // 1. Identificação obrigatória a cada mensagem recebida
  console.log('DEBUG bot.js: chamando identifyUser');
  const { user, role, error } = await identifyUser(`+${from}`);
  console.log('DEBUG bot.js: user =', user);
  console.log('DEBUG bot.js: role =', role);
  console.log('DEBUG bot.js: error =', error);
  
  if (error) {
    await sendTextMessage(from, error);
    return;
  }

  const context = {
    from,
    message,
    user,
    userRole: role,
    // O estado será buscado depois, se necessário
    state: null,
    setState: (newState) => cache.setState(from, { ...newState, user, role }),
    clearState: () => cache.deleteState(from),
  };

  // Lógica de automação para funcionário com obra única
  if (role === 'funcionario' && user.funcionario_id) {
    const commandConfig = commandRouter.getCommandConfig(messageBody.toLowerCase().trim());
    if (!commandConfig) { // A mensagem não é um comando explícito
      const { empreendimentos } = await empreendimentoService.getEmpreendimentosByFuncionario(user.funcionario_id);
      if (empreendimentos && empreendimentos.length === 1) {
        const unicoEmpreendimento = empreendimentos[0];
        const { obras } = await obraService.getObrasByEmpreendimento(unicoEmpreendimento.empreendimento_id, user.funcionario_id);
        if (obras && obras.length === 1) {
          // É um funcionário com obra única, e a mensagem não é um comando.
          // Tratar como entrada automática de diário.
          await diarioObraFlow.handleAutomaticEntry(context, obras[0]);
          return; // Finaliza o processamento aqui
        }
      }
    }
  }

  // 2. Verificação de conversa ativa (fluxo normal)
  const currentState = await cache.getState(from);
  context.state = currentState;
  console.log('DEBUG bot.js: currentState (fluxo normal) =', currentState);

  // 3. Roteamento da lógica
  if (currentState) {
    console.log('DEBUG bot.js: estado ativo encontrado, usando fluxo:', currentState.flow);
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
    console.log('DEBUG bot.js: nova conversa, role =', role);
    // Conversa nova
    if (role === 'unknown') {
      console.log('DEBUG bot.js: usuário desconhecido, iniciando pré-cadastro');
      await flows.preCadastro.start(context);
    } else {
      console.log('DEBUG bot.js: usuário conhecido, chamando commandRouter');
      // Para usuários conhecidos, vai para o roteador de comandos para iniciar um novo fluxo
      await commandRouter.handleCommand(context);
    }
  }
};

module.exports = {
  handleMessage,
};