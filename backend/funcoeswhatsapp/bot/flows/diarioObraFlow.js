// backend/funcoeswhatsapp/bot/flows/diarioObraFlow.js
const { sendTextMessage, sendListMessage, sendQuickReplyButtons } = require('../../services/whatsappService');
const empreendimentoService = require('../../services/api/empreendimentoService');
const obraService = require('../../services/api/obraService');
const diarioObraService = require('../../services/api/diarioObraService');
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

  console.log('DEBUG sendPaginatedList: items =', items);
  console.log('DEBUG sendPaginatedList: pageItems =', pageItems);

  const listItems = pageItems.map(item => {
    if (item.empreendimento_id) {
      return {
        id: `${idPrefix}${item.empreendimento_id}`,
        title: item.empreendimento || item.nome_empreendimento,
        description: `ID: ${item.empreendimento_id}`,
      };
    } else if (item.obra_id) {
      return {
        id: `${idPrefix}${item.obra_id}`,
        title: item.nome_obra,
        description: `ID: ${item.obra_id}`,
      };
    } else if (item.diario_obra_id) {
      // Para diários
      if (item.diario_obra_id === 0) {
        // Opção especial para criar novo diário
        return {
          id: `${idPrefix}0`,
          title: '🆕 Criar novo diário',
          description: item.descricao,
        };
      }
      
      // Usar a data do diário (não a data_criacao) para exibir
      const dataDiario = new Date(item.data).toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit'
      });
      const horaCriacao = new Date(item.data_criacao).toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit'
      });
      const descricao = item.descricao ? 
        (item.descricao.length > 50 ? item.descricao.substring(0, 50) + '...' : item.descricao) : 
        'Sem descrição';
      return {
        id: `${idPrefix}${item.diario_obra_id}`,
        title: `Diário de ${dataDiario}, ${horaCriacao}`,
        description: descricao,
      };
    }
    return {
      id: `${idPrefix}${item.id}`,
      title: item.nome || 'Item',
      description: `ID: ${item.id}`,
    };
  });

  console.log('DEBUG sendPaginatedList: listItems =', listItems);

  if (items.length > endIndex) {
    listItems.push({ id: `mais_${step}`, title: 'Mais opções' });
  }

  const newState = { ...state, step: step, allItems: items, page: page };
  await setState(newState);
  await sendListMessage(from, text, buttonText, listItems);
};

async function handleObraSelection(context, obraId) {
  const { from, setState, clearState, user, state } = context;
  
  try {
    const result = await diarioObraService.fetchTodaysDiario(user.usuario, obraId);
    const obraSelecionada = state.allItems.find(o => o.obra_id === obraId);
    const nomeObra = obraSelecionada ? obraSelecionada.nome_obra : "da obra selecionada";

    if (result.exists && result.diario && !result.multiple) {
      // Um diário encontrado para hoje - continuar automaticamente
      const newState = { 
        ...state, 
        step: STEPS.COLLECTING_REPORT_CONTENT, 
        obraId: obraId, 
        diarioId: result.diario.diario_obra_id,
        descricao: result.diario.descricao || '',
        pendingMediaIds: []
      };
      await setState(newState);
      const today = new Date().toLocaleDateString('pt-BR');
      await sendTextMessage(from, `📝Continuando o diário de hoje (${today}) para a obra "${nomeObra}". Envie texto, fotos ou vídeos. Quando terminar, digite 'salvar'.`);
    } else if (result.exists && result.multiple && result.diarios) {
      // Múltiplos diários encontrados - mostrar lista para seleção
      await sendTextMessage(from, result.message || "Encontrados múltiplos diários para hoje.");
      
      // Adicionar opção para criar novo diário
      const diariosComNovo = [
        { diario_obra_id: 0, descricao: '🆕 Criar novo diário' },
        ...result.diarios
      ];
      
      const newState = { 
        ...state, 
        step: STEPS.AWAITING_DIARIO_SELECTION, 
        obraId: obraId, 
        nomeObra: nomeObra,
        diarios: result.diarios
      };
      await setState(newState);
      await sendPaginatedList(context, diariosComNovo, 1, "Selecione o diário que deseja continuar editando", "Ver Diários", STEPS.AWAITING_DIARIO_SELECTION, 'diario_');
    } else {
      // Nenhum diário encontrado - criar novo diário do dia atual
      const newState = { 
        ...state, 
        step: STEPS.COLLECTING_REPORT_CONTENT, 
        obraId: obraId, 
        descricao: '', 
        pendingMediaIds: [],
        diarioId: null // Será criado automaticamente para hoje
      };
      await setState(newState);
      const today = new Date().toLocaleDateString('pt-BR');
      await sendTextMessage(from, `📝 Iniciando diário de hoje (${today}) para a obra "${nomeObra}". Envie o texto, fotos e vídeos. Quando terminar, digite 'salvar'.`);
    }
  } catch (error) {
    await sendTextMessage(from, "Ocorreu um erro ao acessar o diário. Por favor, tente novamente.");
    await clearState();
  }
}

const handleState = async (context) => {
  const { from, message, state, setState, clearState, user } = context;
  const messageBody = message.body.toLowerCase().trim();

  console.log('DEBUG diarioObraFlow handleState: state.step =', state.step);
  console.log('DEBUG diarioObraFlow handleState: messageBody =', messageBody);

  switch (state.step) {
    case STEPS.AWAITING_START_CONFIRMATION: {
      if (messageBody === 'sim') {
        console.log('DEBUG: user objeto:', user);
        console.log('DEBUG: user.funcionario_id:', user.funcionario_id);
        
        const { empreendimentos, error } = await empreendimentoService.getEmpreendimentosByFuncionario(user.funcionario_id);
        console.log('DEBUG: empreendimentos retornados:', empreendimentos);
        console.log('DEBUG: error:', error);
        
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
      console.log('DEBUG diarioObraFlow: AWAITING_EMPREENDIMENTO_SELECTION, messageBody =', messageBody);
      
      if (messageBody === `mais_${STEPS.AWAITING_EMPREENDIMENTO_SELECTION}`) {
        console.log('DEBUG diarioObraFlow: solicitação de mais itens');
        const nextPage = state.page + 1;
        await sendPaginatedList(context, state.allItems, nextPage, "Selecione o empreendimento:", "Ver Empreendimentos", STEPS.AWAITING_EMPREENDIMENTO_SELECTION, 'emp');
        return;
      }

      if (!messageBody.startsWith('emp')) {
        console.log('DEBUG diarioObraFlow: mensagem não começa com emp, enviando aviso');
        await sendTextMessage(from, "Por favor, selecione uma das opções da lista.");
        return;
      }

      console.log('DEBUG diarioObraFlow: processando seleção de empreendimento');
      const empreendimentoId = parseInt(messageBody.replace('emp', ''), 10);
      const { obras, error } = await obraService.getObrasByEmpreendimento(empreendimentoId, user.funcionario_id);
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

      if (!messageBody.startsWith('obra')) {
        await sendTextMessage(from, "Por favor, selecione uma das opções da lista.");
        return;
      }

      const obraId = parseInt(messageBody.replace('obra', ''), 10);
      await handleObraSelection(context, obraId);
      break;
    }

    case STEPS.AWAITING_DIARIO_SELECTION: {
      if (messageBody.toLowerCase() === 'sair') {
        await sendTextMessage(from, "Operação cancelada. Digite 'diario' para começar novamente.");
        await clearState();
        return;
      }

      if (!messageBody.startsWith('diario_')) {
        await sendTextMessage(from, "Por favor, selecione uma das opções da lista.");
        return;
      }

      const diarioId = parseInt(messageBody.replace('diario_', ''), 10);
      
      // Verificar se é a opção "criar novo diário" (ID 0)
      if (diarioId === 0) {
        // Criar novo diário
        const newState = { 
          ...state, 
          step: STEPS.COLLECTING_REPORT_CONTENT, 
          obraId: state.obraId,
          descricao: '', 
          pendingMediaIds: [],
          diarioId: null // Importante: null para criar novo
        };
        await setState(newState);
        await sendTextMessage(from, `Iniciando novo diário para hoje na obra "${state.nomeObra}". Envie o texto, fotos e vídeos. Quando terminar, digite 'salvar'.`);
        return;
      }
      
      const diarioSelecionado = state.diarios.find(d => d.diario_obra_id === diarioId);
      
      if (!diarioSelecionado) {
        await sendTextMessage(from, "Diário não encontrado. Por favor, selecione uma das opções da lista.");
        return;
      }

      // Configurar para continuar o diário selecionado
      const newState = { 
        ...state, 
        step: STEPS.AWAITING_CONTINUE_DIARIO_CONFIRMATION, 
        diarioId: diarioId,
        diarioSelecionado: diarioSelecionado
      };
      await setState(newState);

      const text = `Você selecionou o diário criado em ${new Date(diarioSelecionado.data_criacao).toLocaleString('pt-BR')} para a obra "${state.nomeObra}". Deseja continuar adicionando informações a ele?`;
      const buttons = [
        { id: 'continuar_sim', title: 'Sim, continuar' },
        { id: 'continuar_nao', title: 'Não, começar do zero' }
      ];
      await sendQuickReplyButtons(from, text, buttons);
      break;
    }

    case STEPS.AWAITING_CONTINUE_DIARIO_CONFIRMATION: {
      const newState = { ...state, step: STEPS.COLLECTING_REPORT_CONTENT };
      
      if (messageBody === 'continuar_sim') {
        // Quando continua diário existente, usar a descrição atual do diário
        newState.descricao = state.diarioSelecionado ? state.diarioSelecionado.descricao : '';
        if (!newState.pendingMediaIds) newState.pendingMediaIds = [];
        await setState(newState);
        await sendTextMessage(from, "Ok, continuando o diário. Envie mais informações ou digite 'salvar'.");
      } else { // 'continuar_nao'
        // Quando começa novo diário, limpar tudo
        newState.descricao = '';
        newState.pendingMediaIds = [];
        newState.diarioId = null; // Limpar ID para criar novo
        await setState(newState);
        await sendTextMessage(from, "Ok, começando um novo relatório para hoje. Envie o texto, fotos e vídeos. Quando terminar, digite 'salvar'.");
      }
      break;
    }

    case STEPS.COLLECTING_REPORT_CONTENT: {
      if (messageBody === 'salvar') {
        const { obraId, descricao, pendingMediaIds = [], diarioId } = state;

        if (!descricao && pendingMediaIds.length === 0) {
          await sendTextMessage(from, "Nenhum conteúdo foi enviado. Envie texto ou mídia e depois digite 'salvar', ou 'sair' para cancelar.");
          return;
        }

        try {
          // Se não há descrição mas há mídia, usar uma descrição padrão
          let finalDescricao = descricao ? descricao.trim() : '';
          if (!finalDescricao && pendingMediaIds.length > 0) {
            finalDescricao = `Registro com ${pendingMediaIds.length} arquivo(s) de mídia`;
          }

          const diario = await diarioObraService.createOrUpdateDiario({
            obraId: obraId,
            descricao: finalDescricao,
            usuarioId: user.usuario,
            diarioId: diarioId // Incluir o ID se existir para fazer update em vez de create
          });

          if (pendingMediaIds.length > 0) {
            await sendTextMessage(from, `Relatório de texto salvo. Agora, enviando ${pendingMediaIds.length} arquivo(s) de mídia. Aguarde...`);
            const uploadPromises = pendingMediaIds.map(mediaId => 
              diarioObraService.downloadAndUploadMedia(mediaId, diario.diario_obra_id)
            );
            const results = await Promise.all(uploadPromises);
            const uploadSuccessCount = results.filter(doc => doc !== null).length;
            await sendTextMessage(from, `Diário salvo com sucesso! ${uploadSuccessCount} de ${pendingMediaIds.length} arquivos de mídia foram enviados.`);
          } else {
            await sendTextMessage(from, "Diário salvo com sucesso!");
          }
          await clearState();

        } catch (error) {
          await sendTextMessage(from, "Ocorreu um erro ao salvar o relatório do diário. Por favor, tente novamente mais tarde.");
          await clearState();
        }

      } else {
        const newState = { ...state };
        if (message.body) {
          newState.descricao += message.body + '\n';
        }
        if (message.mediaId) {
          // Garantir que pendingMediaIds seja sempre inicializado
          if (!newState.pendingMediaIds) {
            newState.pendingMediaIds = [];
          }
          newState.pendingMediaIds.push(message.mediaId);
        }
        setState(newState);
        await sendTextMessage(from, "Conteúdo recebido. Envie mais ou digite 'salvar'.");
      }
      break;
    }
  }
};

const handleAutomaticEntry = async (context, unicaObra) => {
  const { from, user, message, clearState } = context;
  
  try {
    const result = await diarioObraService.fetchTodaysDiario(user.usuario, unicaObra.obra_id);
    
    let diarioToUpdate;
    
    if (result.exists && result.diario && !result.multiple) {
      diarioToUpdate = result.diario;
      if (message.body) {
        diarioToUpdate.descricao += `\n${message.body}`;
      }
    } else {
      diarioToUpdate = {
        obra: unicaObra.obra_id,
        descricao: message.body || '',
        usuario: user.usuario,
        diario_obra_id: null
      };
    }

    const savedDiario = await diarioObraService.createOrUpdateDiario({
      obraId: diarioToUpdate.obra || unicaObra.obra_id,
      descricao: diarioToUpdate.descricao,
      usuarioId: user.usuario,
      diarioId: diarioToUpdate.diario_obra_id
    });

    if (message.mediaId) {
      await diarioObraService.downloadAndUploadMedia(message.mediaId, savedDiario.diario_obra_id);
    }

    await sendTextMessage(from, `Diário de obra da obra "${unicaObra.nome_obra}" atualizado com sucesso.`);
    await clearState();

  } catch (e) {
    await sendTextMessage(from, "Ocorreu um erro ao atualizar o diário de obra.");
    await clearState();
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
  },

  handleAutomaticEntry,
};

module.exports = diarioObraFlow;