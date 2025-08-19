// backend/funcoeswhatsapp/bot/flows/diarioObraFlow.js
const { sendTextMessage } = require('../../services/whatsappService');
const apiService = require('../../services/apiService');
const STEPS = require('../conversationSteps');

// Função auxiliar para lidar com a lógica de máquina de estados
const handleState = async (context) => {
  const { from, message, state, setState, clearState, user } = context;
  const messageBody = message.body;

  switch (state.step) {
    // ... (toda a lógica do switch case do diarioObraBot.js virá aqui) ...
    case STEPS.AWAITING_WORK_NAME: {
      const { obras, error } = await apiService.getObrasByName(messageBody);

      if (error) {
        await sendTextMessage(from, error);
        clearState();
        return;
      }

      if (obras.length === 0) {
        const newState = { ...state, step: STEPS.AWAITING_CREATE_WORK_CONFIRMATION, obraNome: messageBody };
        setState(newState);
        await sendTextMessage(from, `A obra '${messageBody}' não foi encontrada. Deseja criar uma nova com este nome? (Responda 'sim' ou 'não')`);
      } else if (obras.length === 1) {
        const obra = obras[0];
        if (obra.status_obra !== 'em_andamento') {
          await sendTextMessage(from, `A obra '${obra.nome_obra}' não está 'Em Andamento' e não pode receber novos registros. Por favor, inicie novamente com outra obra.`);
          clearState();
          return;
        }
        const newState = { ...state, step: STEPS.AWAITING_REPORT_CONTENT, obraId: obra.id, descricao: '', pendingMediaIds: [] };
        setState(newState);
        await sendTextMessage(from, `Obra '${obra.nome_obra}' encontrada. Envie o texto, fotos e vídeos do seu relatório. Quando terminar, digite 'salvar'.`);
      } else {
        let responseText = `Encontrei mais de uma obra com o nome '${messageBody}'. Por favor, escolha a correta digitando o número:
`;
        const possibleObras = {};
        obras.forEach((obra, index) => {
          const i = index + 1;
          const detalheExtra = obra.empreendimento ? ` (Empreendimento: ${obra.empreendimento.empreendimento})` : "";
          responseText += `
${i}. ${obra.nome_obra}${detalheExtra}`;
          possibleObras[i] = obra.id;
        });
        
        const newState = { ...state, step: STEPS.AWAITING_WORK_CLARIFICATION, possibleObras };
        setState(newState);
        await sendTextMessage(from, responseText);
      }
      break;
    }

    case STEPS.AWAITING_WORK_CLARIFICATION: {
      const choice = messageBody.trim();
      const obraId = state.possibleObras[choice];

      if (!obraId) {
        await sendTextMessage(from, "Opção inválida. Por favor, responda apenas com o número correspondente à obra desejada (por exemplo: 1).");
        return;
      }

      const { obra, error } = await apiService.getObraById(obraId);
      if (error) {
        await sendTextMessage(from, error);
        clearState();
        return;
      }

      if (obra.status_obra !== 'em_andamento') {
        await sendTextMessage(from, `A obra '${obra.nome_obra}' não está 'Em Andamento' e não pode receber novos registros. Por favor, inicie novamente com outra obra.`);
        clearState();
        return;
      }

      const newState = { ...state, step: STEPS.AWAITING_REPORT_CONTENT, obraId: obra.id, descricao: '', pendingMediaIds: [] };
      setState(newState);
      await sendTextMessage(from, `Obra '${obra.nome_obra}' selecionada. Envie o texto, fotos e vídeos do seu relatório. Quando terminar, digite 'salvar'.`);
      break;
    }

    case STEPS.AWAITING_CREATE_WORK_CONFIRMATION: {
      const resposta = messageBody.toLowerCase().trim();
      if (['sim', 's'].includes(resposta)) {
        const newState = { ...state, step: STEPS.AWAITING_NEW_WORK_ADDRESS };
        setState(newState);
        await sendTextMessage(from, `Ótimo! Por favor, envie o endereço completo para a nova obra '${state.obraNome}'.`);
      } else if (['não', 'nao', 'n'].includes(resposta)) {
        await sendTextMessage(from, "Ok, a obra não foi criada. Para tentar novamente, digite o nome de outra obra. Para sair, digite 'sair'.");
        const newState = { ...state, step: STEPS.AWAITING_WORK_NAME };
        setState(newState);
      } else {
        await sendTextMessage(from, "Resposta inválida. Por favor, responda com 'sim' ou 'não'.");
      }
      break;
    }

    case STEPS.AWAITING_NEW_WORK_ADDRESS: {
      const obraNome = state.obraNome;
      const endereco = messageBody;
      
      const { obra, error } = await apiService.createObra({
        nome: obraNome,
        endereco: endereco,
        responsavelId: user.id,
      });

      if (error) {
        await sendTextMessage(from, error);
      } else {
        await sendTextMessage(from, `Obra '${obra.nome_obra}' criada com sucesso! Ela precisa ser aprovada e ter seu status alterado para 'Em Andamento' antes de poder receber registros no diário.`);
      }
      
      clearState();
      break;
    }

    case STEPS.AWAITING_REPORT_CONTENT: {
      if (messageBody.toLowerCase() === 'salvar') {
        const { obraId, descricao, pendingMediaIds } = state;

        if (!descricao && pendingMediaIds.length === 0) {
          await sendTextMessage(from, "Nenhum conteúdo foi enviado. Envie texto ou mídia e depois digite 'salvar', ou 'sair' para cancelar.");
          return;
        }

        const { diario, error: diarioError } = await apiService.createOrUpdateDiario({
          obraId: obraId,
          descricao: descricao.trim(),
          usuarioId: user.usuario.id,
        });

        if (diarioError) {
          await sendTextMessage(from, diarioError);
          clearState();
          return;
        }

        if (pendingMediaIds.length > 0) {
          await sendTextMessage(from, `Relatório de texto salvo. Agora, enviando ${pendingMediaIds.length} arquivo(s) de mídia. Aguarde...`);

          const uploadPromises = pendingMediaIds.map(mediaId => 
            apiService.downloadAndUploadMedia(mediaId, diario.id)
          );

          const results = await Promise.all(uploadPromises);
          const uploadSuccessCount = results.filter(doc => doc !== null).length;

          await sendTextMessage(from, `Diário salvo com sucesso! ${uploadSuccessCount} de ${pendingMediaIds.length} arquivos de mídia foram enviados.`);
        } else {
          await sendTextMessage(from, "Diário salvo com sucesso!");
        }

        clearState();

      } else {
        const newState = { ...state };
        if (message.body) {
          newState.descricao += message.body + '\n';
        }
        if (message.mediaId) {
          newState.pendingMediaIds.push(message.mediaId);
        }
        setState(newState);
        await sendTextMessage(from, "Conteúdo recebido. Envie mais ou digite 'salvar'.");
      }
      break;
    }

    default:
      await sendTextMessage(from, "Desculpe, não entendi. Para recomeçar, digite 'sair' e envie uma nova mensagem.");
      break;
  }
};

const diarioObraFlow = {
  /**
   * Inicia o fluxo de conversa do Diário de Obra.
   * @param {object} context - O contexto da conversa (from, setState, funcionario, etc.).
   */
  async start(context) {
    const { from, setState, user } = context;
    const newState = { flow: 'diarioObra', step: STEPS.AWAITING_WORK_NAME };
    await setState(newState);
    await sendTextMessage(from, `Olá, ${user.nome_completo}! Para iniciar um relatório, por favor, digite o nome da Obra.`);
  },

  /**
   * Lida com as mensagens subsequentes do usuário dentro deste fluxo.
   * @param {object} context - O contexto da conversa.
   */
  async handleMessage(context) {
    // Se não há estado, algo está errado. O fluxo deve sempre ter um estado.
    if (!context.state) {
      await sendTextMessage(context.from, "Ocorreu um erro. Reiniciando a conversa.");
      await this.start(context);
      return;
    }
    await handleState(context);
  }
};

module.exports = diarioObraFlow;
