// Middleware de validação do JWT da IAM (SSO) — Fase 1.
//
// A IAM é a única autoridade de identidade e assina os tokens com HS256 usando
// o segredo COMPARTILHADO `JWT_SECRET` (o mesmo do ERP e do funcoesODM). Este
// middleware apenas valida a assinatura/expiração e expõe `req.iamUser` com o
// tenant e os módulos (entitlements) extraídos das claims.
//
// Uso (em endpoints expostos a usuários finais):
//   const { requireIamAuth, requireModule } = require('./middleware/iamAuth');
//   router.get('/rota', requireIamAuth, handler);            // exige login na IAM
//   router.get('/rota', requireModule('crm'), handler);      // exige o módulo 'crm'
//
// As chamadas internas Django -> Node continuam usando o token de serviço
// próprio de cada serviço; este middleware NÃO substitui aquele fluxo.
const jwt = require('jsonwebtoken');

const JWT_SECRET = process.env.JWT_SECRET;

function extractToken(req) {
  const header = req.headers['authorization'] || '';
  return header.startsWith('Bearer ') ? header.slice(7) : null;
}

function requireIamAuth(req, res, next) {
  if (!JWT_SECRET) {
    return res.status(500).json({ error: 'JWT_SECRET não configurado no serviço.' });
  }
  const token = extractToken(req);
  if (!token) {
    return res.status(401).json({ error: 'Token da IAM ausente.' });
  }
  try {
    const claims = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
    req.iamUser = {
      username: claims.sub,
      email: claims.email,
      tenantId: claims.tenant_id,
      tenantSlug: claims.tenant_slug,
      roles: claims.roles || [],
      modules: claims.modules || [],
    };
    return next();
  } catch (err) {
    return res.status(401).json({ error: 'Token da IAM inválido ou expirado.' });
  }
}

// Exige autenticação na IAM E o entitlement do módulo informado (403 se faltar).
function requireModule(moduleCode) {
  return function (req, res, next) {
    requireIamAuth(req, res, function () {
      if (!req.iamUser.modules.includes(moduleCode)) {
        return res.status(403).json({ error: `Módulo '${moduleCode}' não contratado.` });
      }
      return next();
    });
  };
}

module.exports = { requireIamAuth, requireModule };
