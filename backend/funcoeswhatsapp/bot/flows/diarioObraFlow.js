// backend/funcoeswhatsapp/bot/flows/diarioObraFlow.js
const { sendTextMessage, sendListMessage, sendQuickReplyButtons } = require('../../services/whatsappService');
const apiService = require('../../services/apiService');
const STEPS = require('../conversationSteps');

const ITEMS_PER_PAGE = 9; // 9 itens + 1 "mais" = 10

/**
 * Envia uma lista paginada (empreendimentos ou obras).
 */
const sendPaginatedList = async (context, items, page, text, buttonText, step, idPrefix) => {
  const { from, setState, state } = context;
  const startIndex = (page - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const pageItems = items.slice(startIndex, endIndex);

  const listItems = pageItems.map(item => ({
    id: `${idPrefix}_${item.empreendimento_id || item.obra_id}`,
    title: item.nome_empreendimento || item.nome_obra,
    description: `ID: ${item.empreendimento_id || item.obra_id}`,
  }));

  if (items.length > endIndex) {
    listItems.push({ id: `mais_${step}`, title: 'Mais opções' });
  }

  const newState = { ...state, step: step, allItems: items, page: page };
  await setState(newState);
  await sendListMessage(from, text, buttonText, listItems);
};

const handleState = async (context) => {
  const { from, message, state, setState, clearState, user } = context;
  const messageBody = message.body.toLowerCase().trim();

  switch (state.step) {
    case STEPS.AWAITING_START_CONFIRMATION: {
      if (messageBody === 'sim') {
        const { empreendimentos, error } = await apiService.getEmpreendimentosByFuncionario(user.id);
        if (error || !empreendimentos || empreendimentos.length === 0) {
          await sendTextMessage(from, "Não encontrei empreendimentos sob sua responsabilidade. Por favor, contate o administrador.");
          await clearState();
          return;
        }
        await sendPaginatedList(context, empreendimentos, 1, "Selecione o empreendimento:", "Ver Empreendimentos", STEPS.AWAITING_EMPREENDIMENTO_SELECTION, 'emp');
      } else {
        await sendTextMessage(from, "Ok, quando precisar, é só chamar!");
        await clearState();
      }
      break;
    }

    case STEPS.AWAITING_EMPREENDIMENTO_SELECTION: {
      if (messageBody === `mais_${STEPS.AWAITING_EMPREENDIMENTO_SELECTION}`) {
        const nextPage = state.page + 1;
        await sendPaginatedList(context, state.allItems, nextPage, "Selecione o empreendimento:", "Ver Empreendimentos", STEPS.AWAITING_EMPREENDIMENTO_SELECTION, 'emp');
        return;
      }

      if (!messageBody.startsWith('emp_')) {
        await sendTextMessage(from, "Por favor, selecione uma das opções da lista.");
        return;
      }

      const empreendimentoId = parseInt(messageBody.replace('emp_', ''), 10);
      const { obras, error } = await apiService.getObrasByEmpreendimento(empreendimentoId, user.id);
      if (error || !obras || obras.length === 0) {
        await sendTextMessage(from, "Não encontrei obras ativas sob sua responsabilidade para este empreendimento.");
        await clearState();
        return;
      }
      await sendPaginatedList(context, obras, 1, "Agora, selecione a obra:", "Ver Obras", STEPS.AWAITING_OBRA_SELECTION, 'obra');
      break;
    }

    case STEPS.AWAITING_OBRA_SELECTION: {
      if (messageBody === `mais_${STEPS.AWAITING_OBRA_SELECTION}`) {
        const nextPage = state.page + 1;
        await sendPaginatedList(context, state.allItems, nextPage, "Selecione a obra:", "Ver Obras", STEPS.AWAITING_OBRA_SELECTION, 'obra');
        return;
      }

      if (!messageBody.startsWith('obra_')) {
        await sendTextMessage(from, "Por favor, selecione uma das opções da lista.");
        return;
      }

      const obraId = parseInt(messageBody.replace('obra_', ''), 10);
      const { diario, error } = await apiService.getTodaysDiario(user.usuario.id, obraId);

      if (error) {
        await sendTextMessage(from, error);
        await clearState();
        return;
      }

      const obraSelecionada = state.allItems.find(o => o.obra_id === obraId);
      const nomeObra = obraSelecionada ? obraSelecionada.nome_obra : "da obra selecionada";

      if (diario) {
        const newState = { ...state, step: STEPS.AWAITING_CONTINUE_DIARIO_CONFIRMATION, obraId: obraId, diarioId: diario.diario_obra_id };
        await setState(newState);
        const text = `Você já iniciou um diário para a obra "${nomeObra}" hoje. Deseja continuar adicionando informações a ele?`;
        const buttons = [
          { id: 'continuar_sim', title: 'Sim, continuar' },
          { id: 'continuar_nao', title: 'Não, começar do zero' }
        ];
        await sendQuickReplyButtons(from, text, buttons);
      } else {
        const newState = { ...state, step: STEPS.COLLECTING_REPORT_CONTENT, obraId: obraId, descricao: '', pendingMediaIds: [] };
        await setState(newState);
        await sendTextMessage(from, `Iniciando novo diário para a obra "${nomeObra}". Envie o texto, fotos e vídeos. Quando terminar, digite 'salvar'.`);
      }
      break;
    }

    case STEPS.AWAITING_CONTINUE_DIARIO_CONFIRMATION: {
      const newState = { ...state, step: STEPS.COLLECTING_REPORT_CONTENT };
      await setState(newState);
      if (messageBody === 'continuar_sim') {
        await sendTextMessage(from, "Ok, continuando o diário. Envie mais informações ou digite 'salvar'.");
      } else { // 'continuar_nao'
        newState.descricao = '';
        newState.pendingMediaIds = [];
        await sendTextMessage(from, "Ok, começando um novo relatório para hoje. Envie o texto, fotos e vídeos. Quando terminar, digite 'salvar'.");
      }
      break;
    }

    case STEPS.COLLECTING_REPORT_CONTENT: {
      if (messageBody === 'salvar') {
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
          await clearState();
          return;
        }

        if (pendingMediaIds.length > 0) {
          await sendTextMessage(from, `Relatório de texto salvo. Agora, enviando ${pendingMediaIds.length} arquivo(s) de mídia. Aguarde...`);
          const uploadPromises = pendingMediaIds.map(mediaId => 
            apiService.downloadAndUploadMedia(mediaId, diario.diario_obra_id)
          );
          const results = await Promise.all(uploadPromises);
          const uploadSuccessCount = results.filter(doc => doc !== null).length;
          await sendTextMessage(from, `Diário salvo com sucesso! ${uploadSuccessCount} de ${pendingMediaIds.length} arquivos de mídia foram enviados.`);
        } else {
          await sendTextMessage(from, "Diário salvo com sucesso!");
        }
        await clearState();
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
  }
};

const diarioObraFlow = {
  async start(context) {
    const { from, setState, user } = context;
    const newState = { flow: 'diarioObra', step: STEPS.AWAITING_START_CONFIRMATION };
    await setState(newState);
    const text = `Olá, ${user.nome_completo}! Pronto para iniciar ou continuar um diário de obra?`;
    const buttons = [{ id: 'sim', title: 'Sim' }, { id: 'nao', title: 'Não' }];
    await sendQuickReplyButtons(from, text, buttons);
  },

  async handleMessage(context) {
    await handleState(context);
  }
};

module.exports = diarioObraFlow;
