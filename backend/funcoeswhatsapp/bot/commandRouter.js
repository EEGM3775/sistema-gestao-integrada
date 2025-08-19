// backend/funcoeswhatsapp/bot/commandRouter.js
const diarioObraFlow = require('./flows/diarioObraFlow');
const { sendTextMessage } = require('../services/whatsappService');
const logger = require('../logger');

// Mapeia palavras-chave para os fluxos e define as permissões de acesso.
const commandMap = {
  'diario': { flow: diarioObraFlow, allowedRoles: ['funcionario'] },
  'diário': { flow: diarioObraFlow, allowedRoles: ['funcionario'] },
  'relatorio': { flow: diarioObraFlow, allowedRoles: ['funcionario'] },
  'relatório': { flow: diarioObraFlow, allowedRoles: ['funcionario'] },
  'obra': { flow: diarioObraFlow, allowedRoles: ['funcionario'] },
  // Exemplo futuro:
  // 'fatura': { flow: faturaFlow, allowedRoles: ['cliente'] },
  // 'pedido': { flow: pedidoFlow, allowedRoles: ['fornecedor'] },
};

const handleCommand = async (context) => {
  const { message, userRole } = context;
  const command = message.body.toLowerCase().trim();

  const commandConfig = commandMap[command];

  if (commandConfig) {
    // Verifica se o perfil do usuário tem permissão para usar este comando
    if (commandConfig.allowedRoles.includes(userRole)) {
      await commandConfig.flow.start(context);
    } else {
      // Se o comando existe mas o usuário não tem permissão
      logger.warn(`Usuário com perfil '${userRole}' tentou acessar o comando '${command}' sem permissão.`);
      await sendTextMessage(context.from, "Desculpe, você não tem permissão para executar este comando.");
    }
  } else {
    // Mensagem de ajuda padrão se o comando não for encontrado
    await sendTextMessage(context.from, 
      "Olá! Sou o assistente da empresa. Para iniciar o registro de um Diário de Obra, envie 'diario'. Para cancelar qualquer operação, envie 'sair'."
    );
  }
};

module.exports = {
  handleCommand,
};
