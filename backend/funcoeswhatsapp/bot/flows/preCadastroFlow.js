// backend/funcoeswhatsapp/bot/flows/preCadastroFlow.js
const { sendTextMessage } = require('../../services/whatsappService');
const apiService = require('../../services/apiService');
const STEPS = require('../conversationSteps');

const handleState = async (context) => {
  const { from, message, state, setState, clearState } = context;
  const messageBody = message.body;

  switch (state.step) {
    case STEPS.AWAITING_PRECADASTRO_NOME: {
      const newState = { ...state, step: STEPS.AWAITING_PRECADASTRO_INTERESSE, nome: messageBody };
      await setState(newState);
      await sendTextMessage(from, `Obrigado, ${messageBody}. Qual é o seu interesse? (Responda com 'cliente', 'fornecedor' ou 'outro')`);
      break;
    }

    case STEPS.AWAITING_PRECADASTRO_INTERESSE: {
      const interesse = messageBody.toLowerCase().trim();
      const validInteresses = ['cliente', 'fornecedor', 'outro'];

      if (!validInteresses.includes(interesse)) {
        await sendTextMessage(from, "Por favor, responda apenas com 'cliente', 'fornecedor' ou 'outro'.");
        return;
      }

      const { precadastro, error } = await apiService.createPreCadastro({
        nome_completo: state.nome,
        telefone: `+${from}`,
        tipo_interesse: interesse,
        mensagem_inicial: state.mensagem_inicial,
      });

      if (error) {
        await sendTextMessage(from, error);
      } else {
        await sendTextMessage(from, "Obrigado! Suas informações foram registradas e nossa equipe entrará em contato em breve.");
      }
      
      await clearState();
      break;
    }
  }
};

const preCadastroFlow = {
  async start(context) {
    const { from, setState, message } = context;
    const newState = { 
      flow: 'preCadastro', 
      step: STEPS.AWAITING_PRECADASTRO_NOME,
      mensagem_inicial: message.body // Salva a primeira mensagem do usuário
    };
    await setState(newState);
    await sendTextMessage(from, "Olá! Verifiquei que seu número não está em nosso sistema. Para agilizar seu atendimento, por favor, informe seu nome completo.");
  },

  async handleMessage(context) {
    if (!context.state) {
      await sendTextMessage(context.from, "Ocorreu um erro. Reiniciando a conversa.");
      await this.start(context);
      return;
    }
    await handleState(context);
  }
};

module.exports = preCadastroFlow;
