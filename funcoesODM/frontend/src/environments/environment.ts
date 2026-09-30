export const environment = {
  production: false,
  // Integração (Fase 2): o gateway roteia /odm-api -> Java (/api/v1). O nginx
  // interno do drone também expõe /odm-api, então vale standalone e integrado.
  apiUrl: '/odm-api',
  // SSO: para onde redirecionar quando não houver token (modo standalone).
  // Vazio = usa a tela de login local. Em produção integrada, aponte à IAM.
  iamLoginUrl: '',
};
