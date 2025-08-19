// backend/funcoeswhatsapp/bot/commandRouter.js
const diarioObraFlow = require('./flows/diarioObraFlow');
const { sendTextMessage } = require('../services/whatsappService');
const logger = require('../logger');

// Mapeia palavras-chave para os fluxos e define as permissões de acesso.
const commandMap = {
  'diario': { flow: diarioObraFlow, allowedRoles: ['funcionario'], requiredRole: 'responsavel_tecnico' },
  'diário': { flow: diarioObraFlow, allowedRoles: ['funcionario'], requiredRole: 'responsavel_tecnico' },
  'relatorio': { flow: diarioObraFlow, allowedRoles: ['funcionario'], requiredRole: 'responsavel_tecnico' },
  'relatório': { flow: diarioObraFlow, allowedRoles: ['funcionario'], requiredRole: 'responsavel_tecnico' },
  'obra': { flow: diarioObraFlow, allowedRoles: ['funcionario'], requiredRole: 'responsavel_tecnico' },
  // Exemplo futuro:
  // 'fatura': { flow: faturaFlow, allowedRoles: ['cliente'] },
  // 'pedido': { flow: pedidoFlow, allowedRoles: ['fornecedor'] },
};

const handleCommand = async (context) => {
  const { message, user, userRole } = context;
  const command = message.body.toLowerCase().trim();

  const commandConfig = commandMap[command];

  if (commandConfig) {
    // 1. Verifica se o perfil do usuário (role) tem permissão
    if (commandConfig.allowedRoles.includes(userRole)) {
      
      // 2. Verifica se um cargo específico é necessário
      if (commandConfig.requiredRole) {
        // Assumindo que o objeto 'user' (Funcionario) tem um campo 'cargo' com um 'nome'.
        // Esta lógica pode precisar de ajuste dependendo da estrutura exata do seu modelo.
        const cargoNome = user.cargo?.nome?.toLowerCase() || '';
        if (!cargoNome.includes(commandConfig.requiredRole)) {
          logger.warn(`Funcionário ${user.nome_completo} com cargo '${cargoNome}' tentou acessar o comando '${command}' restrito.`);
          await sendTextMessage(context.from, "Desculpe, apenas um Responsável Técnico pode iniciar esta operação.");
          return;
        }
      }
      
      // Se todas as verificações passarem, inicia o fluxo.
      await commandConfig.flow.start(context);

    } else {
      // Se o perfil do usuário não tem permissão
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
