export const environment = {
  production: true,
  // Integração (Fase 2): /odm-api -> Java (/api/v1) via gateway/nginx do drone.
  apiUrl: '/odm-api',
  // SSO: para onde redirecionar quando não houver token (modo standalone).
  // Vazio = usa a tela de login local. Em produção integrada, aponte à IAM.
  iamLoginUrl: '',
};
