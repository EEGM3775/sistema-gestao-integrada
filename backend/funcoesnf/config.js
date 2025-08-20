module.exports = {
  DJANGO_API_URL: process.env.DJANGO_API_URL || 'http://localhost:8000/api/erp',
  NFE_IO_API_KEY: process.env.NFE_IO_API_KEY || 'SUA_CHAVE_DE_API_AQUI', // Substitua pela sua chave de API da NFE.io
  NFE_IO_COMPANY_ID: process.env.NFE_IO_COMPANY_ID || 'SEU_ID_DA_EMPRESA_AQUI', // Substitua pelo ID da sua empresa na NFE.io
};