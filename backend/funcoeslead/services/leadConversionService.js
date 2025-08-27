// backend/funcoeslead/services/leadConversionService.js
const djangoApi = require('./djangoApiService');
const logger = require('../logger');

/**
 * Converte um Lead em Account, Contact e Opportunity.
 * @param {string} leadId O ID do Lead a ser convertido.
 * @returns {Promise<object>} Um objeto com os IDs das novas entidades criadas.
 */
async function convertLead(leadId) {
    logger.info(`Iniciando processo de conversão para o Lead ID: ${leadId}`);

    // 1. Buscar o Lead
    const lead = await djangoApi.getObject('/crm/leads/', leadId);

    // 2. Validar o status do Lead
    if (lead.status !== 'QUALIFICADO') {
        logger.warn(`Tentativa de converter Lead ${leadId} com status inválido: ${lead.status}`);
        throw new Error(`O Lead precisa ter o status 'QUALIFICADO' para ser convertido.`);
    }

    // 3. Encontrar ou Criar a Conta (Account)
    let account;
    // Tenta encontrar uma conta com o mesmo nome da empresa do lead
    // NOTA: Esta é uma busca simples. Uma implementação mais robusta poderia usar
    // um endpoint de busca mais sofisticado no Django.
    try {
        const accountsResponse = await djangoApi.apiClient.get(`/crm/accounts/?name=${encodeURIComponent(lead.company)}`);
        if (accountsResponse.data && accountsResponse.data.length > 0) {
            account = accountsResponse.data[0];
            logger.info(`Conta existente encontrada para a empresa "${lead.company}": ID ${account.id}`);
        } else {
            logger.info(`Nenhuma conta encontrada para "${lead.company}". Criando uma nova.`);
            account = await djangoApi.createObject('/crm/accounts/', {
                name: lead.company,
                email: lead.email, // Pode ser o email geral da empresa
                phone: lead.phone,
                assigned_to_id: lead.assigned_to?.id
            });
        }
    } catch (error) {
        logger.error('Erro ao buscar ou criar a conta:', error);
        throw error;
    }

    // 4. Criar o Contato (Contact)
    const contact = await djangoApi.createObject('/crm/contacts/', {
        first_name: lead.first_name,
        last_name: lead.last_name,
        email: lead.email,
        phone: lead.phone,
        account_id: account.id
    });
    logger.info(`Contato criado para ${lead.first_name} ${lead.last_name}: ID ${contact.id}`);

    // 5. Criar a Oportunidade (Opportunity)
    const opportunity = await djangoApi.createObject('/crm/opportunities/', {
        name: `Oportunidade - ${account.name}`,
        account_id: account.id,
        contact_id: contact.id,
        stage: 'PROPOSTA', // O estágio inicial após a conversão
        // O valor pode vir de um campo customizado no lead ou ser definido depois
        amount: lead.valor_estimado || 0,
        close_date: new Date(new Date().setDate(new Date().getDate() + 30)).toISOString().split('T')[0], // Estima 30 dias para fechar
        assigned_to_id: lead.assigned_to?.id
    });
    logger.info(`Oportunidade criada para a conta ${account.name}: ID ${opportunity.id}`);

    // 6. Atualizar o Lead
    await djangoApi.updateObject('/crm/leads/', leadId, { status: 'PERDIDO' }); // Usando 'PERDIDO' como convertido para remover da lista de ativos
    logger.info(`Status do Lead ${leadId} atualizado para convertido.`);

    // 7. Retornar o resultado
    const result = {
        message: 'Lead convertido com sucesso!',
        accountId: account.id,
        contactId: contact.id,
        opportunityId: opportunity.id
    };

    logger.info('Processo de conversão concluído.', result);
    return result;
}

module.exports = {
    convertLead
};
