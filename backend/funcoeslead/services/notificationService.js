const djangoApi = require('./djangoApiService');
const logger = require('../logger');
const nodemailer = require('nodemailer');

const config = require('../config');

// Configuração do Nodemailer
let transporter;
if (config.mail.host && config.mail.user && config.mail.pass) {
    transporter = nodemailer.createTransport({
        host: config.mail.host,
        port: config.mail.port,
        secure: config.mail.port === 465, // true for 465, false for other ports
        auth: {
            user: config.mail.user,
            pass: config.mail.pass
        }
    });
} else {
    logger.warn('Serviço de notificação por e-mail desabilitado. Configure as variáveis de ambiente MAIL_HOST, MAIL_USER e MAIL_PASS.');
}

/**
 * Busca tarefas próximas do vencimento.
 */
async function getUpcomingTasks() {
    const now = new Date();
    const tomorrow = new Date(now);
    tomorrow.setDate(now.getDate() + 1);

    const params = {
        interaction_type: 'tarefa',
        status__in: ['pendente', 'em_andamento'],
        due_date__gte: now.toISOString(),
        due_date__lte: tomorrow.toISOString(),
    };

    try {
        logger.info('Buscando tarefas com vencimento próximo...');
        const response = await djangoApi.apiClient.get('/crm/interactions/', { params });
        return response.data;
    } catch (error) {
        logger.error('Erro ao buscar tarefas do Django API:', error);
        return [];
    }
}

/**
 * Envia uma notificação por e-mail.
 * @param {object} task A tarefa para a qual enviar a notificação.
 */
async function sendNotificationEmail(task) {
    if (!transporter) {
        return; // Não envia e-mail se o transporter não estiver configurado
    }

    if (!task.assigned_to) {
        logger.warn(`A tarefa ${task.id} não tem um responsável definido.`);
        return;
    }

    let email = null;
    let name = null;

    // O DRF alinha o objeto real dentro de 'assigned_to' 
    // e o tipo de conteúdo estará em um campo como 'assigned_to_content_type_name'
    const assignedObject = task.assigned_to;
    const objectType = task.assigned_to_content_type_name; // Exemplo, o nome real pode variar

    if (objectType.includes('usuario')) {
        email = assignedObject.email;
        name = assignedObject.first_name;
    } else if (objectType.includes('funcionario')) {
        email = assignedObject.email_pessoal;
        name = assignedObject.nome_completo;
    } else if (objectType.includes('fornecedor')) {
        email = assignedObject.email;
        name = assignedObject.razao_social;
    }

    if (!email) {
        logger.warn(`Não foi possível encontrar um e-mail para o responsável da tarefa ${task.id} (tipo: ${objectType})`);
        return;
    }

    const mailOptions = {
        from: '"Sistema de Gestão" <noreply@sistemagestao.com>',
        to: email,
        subject: `Lembrete de Tarefa: ${task.subject}`,
        html: `
            <p>Olá, ${name || ''}!</p>
            <p>Esta é um lembrete de que a tarefa "<b>${task.subject}</b>" está com o vencimento próximo.</p>
            <p><b>Data de Vencimento:</b> ${new Date(task.due_date).toLocaleDateString('pt-BR')}</p>
            <p><b>Notas:</b></p>
            <p>${task.notes || 'Nenhuma nota adicional.'}</p>
            <p>Por favor, verifique o sistema para mais detalhes.</p>
            <br>
            <p>Atenciosamente,</p>
            <p><b>Sistema de Gestão Integrada</b></p>
        `
    };

    try {
        const info = await transporter.sendMail(mailOptions);
        logger.info(`E-mail de notificação enviado para ${email} (ID da Mensagem: ${info.messageId})`);
        logger.info(`URL de Preview: ${nodemailer.getTestMessageUrl(info)}`);
    } catch (error) {
        logger.error(`Erro ao enviar e-mail de notificação para a tarefa ${task.id}:`, error);
    }
}

/**
 * Inicia o worker de notificação para verificar tarefas periodicamente.
 */
function startNotificationWorker() {
    if (!transporter) {
        logger.warn('Worker de notificação não iniciado pois o serviço de e-mail não está configurado.');
        return;
    }

    logger.info('Iniciando o Worker de Notificação de Tarefas.');

    // Executa a cada 1 hora (3600000 ms)
    setInterval(async () => {
        logger.info('Executando verificação de tarefas...');
        const upcomingTasks = await getUpcomingTasks();

        if (upcomingTasks.length > 0) {
            logger.info(`${upcomingTasks.length} tarefa(s) encontrada(s) com vencimento próximo.`);
            for (const task of upcomingTasks) {
                await sendNotificationEmail(task);
            }
        } else {
            logger.info('Nenhuma tarefa com vencimento próximo encontrada.');
        }
    }, 3600000);

    // Executa uma vez logo ao iniciar para teste
    (async () => {
        const upcomingTasks = await getUpcomingTasks();
        if (upcomingTasks.length > 0) {
            for (const task of upcomingTasks) {
                await sendNotificationEmail(task);
            }
        }
    })();
}

module.exports = {
    startNotificationWorker
};