// backend/funcoeswhatsapp/bot/commandRouter.js
const diarioObraFlow = require('./flows/diarioObraFlow');
const { sendTextMessage } = require('../services/whatsappService');
const { getObras } = require('../services/api/obraService');
const logger = require('../logger');

// Mapeia palavras-chave para os fluxos e define as permissões de acesso.
const commandMap = {
  'diario': { flow: diarioObraFlow, allowedRoles: ['funcionario'], checkResponsavelTecnico: true },
  'diário': { flow: diarioObraFlow, allowedRoles: ['funcionario'], checkResponsavelTecnico: true },
  'relatorio': { flow: diarioObraFlow, allowedRoles: ['funcionario'], checkResponsavelTecnico: true },
  'relatório': { flow: diarioObraFlow, allowedRoles: ['funcionario'], checkResponsavelTecnico: true },
  'obra': { flow: diarioObraFlow, allowedRoles: ['funcionario'], checkResponsavelTecnico: true },
  // Exemplo futuro:
  // 'fatura': { flow: faturaFlow, allowedRoles: ['cliente'] },
  // 'pedido': { flow: pedidoFlow, allowedRoles: ['fornecedor'] },
};

const getCommandConfig = (command) => {
  return commandMap[command];
};

const handleCommand = async (context) => {
  const { message, user, userRole } = context;
  const command = message.body.toLowerCase().trim();

  console.log('DEBUG commandRouter: comando recebido =', command);
  console.log('DEBUG commandRouter: userRole =', userRole);
  console.log('DEBUG commandRouter: user =', user);

  const commandConfig = getCommandConfig(command);

  if (commandConfig) {
    console.log('DEBUG commandRouter: comando encontrado no mapa');
    // 1. Verifica se o perfil do usuário (role) tem permissão
    if (commandConfig.allowedRoles.includes(userRole)) {
      console.log('DEBUG commandRouter: usuário tem permissão');
      
      // 2. Verifica se é necessário ser responsável técnico de alguma obra
      if (commandConfig.checkResponsavelTecnico) {
        console.log('DEBUG commandRouter: verificando se é responsável técnico');
        try {
          const obras = await getObras();
          const isResponsavelTecnico = obras.some(obra => 
            obra.responsaveis_tecnicos && obra.responsaveis_tecnicos.includes(user.funcionario_id)
          );

          console.log('DEBUG commandRouter: isResponsavelTecnico =', isResponsavelTecnico);
          
          if (!isResponsavelTecnico) {
            logger.warn(`Funcionário ${user.nome_completo} tentou acessar o comando '${command}' mas não é responsável técnico de nenhuma obra.`);
            await sendTextMessage(context.from, "Desculpe, apenas funcionários que são responsáveis técnicos de uma ou mais obras podem iniciar esta operação.");
            return;
          }
        } catch (error) {
          await sendTextMessage(context.from, "Ocorreu um erro ao verificar suas permissões. Por favor, tente novamente mais tarde.");
          return;
        }
      }
      
      console.log('DEBUG commandRouter: iniciando fluxo');
      // Se todas as verificações passarem, inicia o fluxo.
      await commandConfig.flow.start(context);

    } else {
      // Se o perfil do usuário não tem permissão
      console.log('DEBUG commandRouter: usuário não tem permissão');
      logger.warn(`Usuário com perfil '${userRole}' tentou acessar o comando '${command}' sem permissão.`);
      await sendTextMessage(context.from, "Desculpe, você não tem permissão para executar este comando.");
    }
  } else {
    console.log('DEBUG commandRouter: comando não encontrado, enviando ajuda');
    // Mensagem de ajuda padrão se o comando não for encontrado
    await sendTextMessage(context.from, 
      "Olá! Sou o assistente da empresa. Para iniciar o registro de um Diário de Obra, envie 'diario'. Para cancelar qualquer operação, envie 'sair'."
    );
  }
};

module.exports = {
  handleCommand,
  getCommandConfig,
};
