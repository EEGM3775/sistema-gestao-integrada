const MimeTypeMap = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp',
    'video/mp4': 'mp4',
    'audio/mpeg': 'mp3',
    'application/pdf': 'pdf',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.ms-excel': 'xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
};

/**
 * Converte um MIME type para uma extensão de arquivo comum.
 * @param {string} mimeType O MIME type a ser convertido.
 * @returns {string} A extensão do arquivo ou 'bin' se não for encontrada.
 */
function getExtensionFromMimeType(mimeType) {
    if (!mimeType) return 'bin';
    return MimeTypeMap[mimeType.toLowerCase()] || mimeType.split('/')[1] || 'bin';
}

/**
 * Remove ou mascara dados sensíveis de um payload de webhook do WhatsApp para logging seguro.
 * @param {object} payload O objeto do webhook (depois de JSON.parse).
 * @returns {object} Um novo objeto seguro para ser logado.
 */
function sanitizeWebhookPayload(payload) {
    if (!payload || typeof payload !== 'object') {
        return { sanitized: true, original_type: typeof payload };
    }

    // Cria uma cópia profunda para evitar modificar o objeto original
    const safePayload = JSON.parse(JSON.stringify(payload));

    if (safePayload.entry) {
        safePayload.entry.forEach(entry => {
            if (entry.changes) {
                entry.changes.forEach(change => {
                    if (change.value) {
                        // Mascara o número de telefone do contato
                        if (change.value.contacts) {
                            change.value.contacts.forEach(contact => {
                                if (contact.wa_id) {
                                    contact.wa_id = `...${contact.wa_id.slice(-4)}`;
                                }
                                if (contact.profile && contact.profile.name) {
                                    contact.profile.name = '[REMOVIDO]';
                                }
                            });
                        }
                        // Remove o conteúdo da mensagem
                        if (change.value.messages) {
                            change.value.messages.forEach(message => {
                                if (message.from) {
                                    message.from = `...${message.from.slice(-4)}`;
                                }
                                if (message.text && message.text.body) {
                                    message.text.body = '[CONTEÚDO REMOVIDO]';
                                }
                                // Outros tipos de mídia (imagem, vídeo) não contêm PII direto no corpo,
                                // o ID da mídia é seguro para logar.
                            });
                        }
                    }
                });
            }
        });
    }

    return safePayload;
}

module.exports = {
    getExtensionFromMimeType,
    sanitizeWebhookPayload,
};
