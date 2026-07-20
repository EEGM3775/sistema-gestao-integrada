"""
Configuração do serviço IAM (Identity & Access Management).

Serviço separado, autoridade única de identidade da plataforma: dono de
tenants, usuários, papéis/permissões e entitlements de módulo. Emite e
assina os JWTs consumidos por todos os produtos (backend, funcoesODM, Node).
Ver docs/arquitetura.md (Fase 0.2).
"""
from datetime import timedelta
from pathlib import Path
import os
import sys

from dotenv import load_dotenv

# Carrega o .env da raiz do repositório (um nível acima de iam/)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

# Pacotes COMPARTILHADOS na raiz do repositório, não apps deste serviço:
#   `funcoesemail` — textos e transporte de e-mail (também usado pelo backend);
#   `payment`      — valores comerciais: planos, quotas e tetos (ver payment/README.md).
# Na imagem Docker são copiados para dentro de /app e o import funciona direto;
# rodando local (manage.py a partir de iam/) a raiz não está no sys.path, então a
# acrescentamos. A condição lista os dois de propósito: amarrar a existência de um
# à do outro faria o `payment` sumir em silêncio se o `funcoesemail` mudasse de casa.
if any((BASE_DIR.parent / pacote).is_dir() for pacote in ("funcoesemail", "payment")):
    sys.path.insert(0, str(BASE_DIR.parent))

from django.core.exceptions import ImproperlyConfigured

# S4 — segurança por padrão: IAM_DEBUG default = False. Fora do dev a IAM assume
# PRODUÇÃO e se recusa a subir sem configuração, em vez de subir com segredos
# conhecidos. A IAM é a autoridade de identidade: um segredo previsível aqui
# permitiria forjar login de qualquer usuário/tenant.
DEBUG = os.getenv("IAM_DEBUG", "False").lower() == "true"


def _config(name, dev_default):
    """Valor obrigatório em produção; cai no default de dev só quando DEBUG (fail-fast S4)."""
    val = os.getenv(name)
    if val:
        return val
    if DEBUG:
        return dev_default
    raise ImproperlyConfigured(
        f"{name} é obrigatório em produção (IAM_DEBUG=False). Defina-o no ambiente, "
        f"ou rode em desenvolvimento com IAM_DEBUG=True."
    )


SECRET_KEY = _config("IAM_SECRET_KEY", "django-insecure-iam-dev-apenas")
ALLOWED_HOSTS = _config("IAM_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# S4 — endurecimento ligado só em produção (atrás do gateway, que termina o TLS).
# Importa em especial para o cookie HttpOnly de refresh emitido pela IAM (Fase 10.6).
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False").lower() == "true"

INSTALLED_APPS = [
    "identity",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
]

MIDDLEWARE = [
    # Observabilidade (Fase 10.1): request_id + timing + log de acesso + métricas.
    "identity.middleware.ObservabilityMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "iam_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "iam_project.wsgi.application"

AUTH_USER_MODEL = "identity.Usuario"

# Banco próprio do IAM (Postgres em produção; SQLite no dev local).
if os.getenv("IAM_POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("IAM_POSTGRES_DB"),
            "USER": os.getenv("IAM_POSTGRES_USER", "iam_app"),
            "PASSWORD": os.getenv("IAM_POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {
                # Ver backend/config/settings.py: `verify-full` precisa da CA em
                # DB_SSLROOTCERT para valer de fato.
                "sslmode": os.getenv("DB_SSLMODE", "prefer"),
                **(
                    {"sslrootcert": os.getenv("DB_SSLROOTCERT")}
                    if os.getenv("DB_SSLROOTCERT")
                    else {}
                ),
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "iam_dev.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Hash de senha forte (Argon2 preferencial; requer o pacote argon2-cffi).
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = os.getenv(
    "IAM_CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
).split(",")
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
# O refresh viaja em cookie HttpOnly → o browser precisa enviá-lo em requisições
# XHR (fetch/axios com credentials). Em produção tudo é mesma-origem (gateway),
# mas em dev (vite :5173) o CORS precisa permitir credenciais.
CORS_ALLOW_CREDENTIALS = True

# --- Ciclo de sessão: refresh token em cookie HttpOnly (Fase 10.6 / F1) ---
# O login põe o refresh num cookie HttpOnly (imune a XSS) com path /auth/ → só
# viaja para /auth/refresh e /auth/logout, nunca para /api. SameSite=Strict
# bloqueia envio cross-site (defesa de CSRF). Secure=1 sob HTTPS (produção).
REFRESH_COOKIE_NAME = os.getenv("IAM_REFRESH_COOKIE", "sgi_refresh")
REFRESH_COOKIE_PATH = "/auth/"
# SEGURO POR PADRÃO fora de DEBUG (mesmo princípio do S4). O default era "0" e nada
# no compose/.env o ligava: o staging — que roda HTTPS e se propõe idêntico a produção
# — emitia o refresh SEM `Secure`, ou seja, o cookie que É a sessão podia trafegar em
# HTTP puro. O endurecimento do bloco de produção só alcança os cookies do Django
# (SESSION/CSRF); este é setado à mão em cookies.py e ficava de fora.
REFRESH_COOKIE_SECURE = os.getenv("IAM_COOKIE_SECURE", "0" if DEBUG else "1") == "1"
REFRESH_COOKIE_SAMESITE = os.getenv("IAM_COOKIE_SAMESITE", "Strict")
# Duração da sessão (refresh): curta (sem "lembrar") vs longa deslizante (com),
# ambas limitadas por um teto absoluto desde o login.
# Sessão SEM "manter conectado": janela DESLIZANTE de inatividade + teto absoluto
# contado desde o início da sessão (`sst`). Antes a janela e o teto eram o MESMO
# valor, o que tornava a sessão FIXA desde o login: rotacionar não estendia nada e
# quem estava trabalhando caía no meio do expediente.
SESSION_IDLE = timedelta(hours=int(os.getenv("JWT_SESSION_IDLE_HOURS", "2")))
SESSION_IDLE_CAP = timedelta(hours=int(os.getenv("JWT_SESSION_IDLE_CAP_HOURS", "12")))
# Sessão COM "manter conectado" (equipamento pessoal): desliza 7d, teto absoluto 30d.
# O TETO é o que limita a persistência de uma sessão roubada: a detecção de reuso só
# pega o ladrão se o usuário legítimo usar o sistema em paralelo — um cookie copiado
# numa sexta à noite seria rotacionado sozinho o fim de semana todo sem disparar nada.
# Era 30d/90d: o mesmo malware que morre em ≤12h no caminho default (sem "manter
# conectado") sobrevivia até 3 meses aqui — 180× mais.
SESSION_REMEMBER = timedelta(days=int(os.getenv("JWT_SESSION_REMEMBER_DAYS", "7")))
SESSION_ABS_CAP = timedelta(days=int(os.getenv("JWT_SESSION_CAP_DAYS", "30")))
# Antecedência do aviso de queda (modal com contagem no front). Fica aqui para o
# servidor ser a fonte única — o front recebe o valor junto do `session_expires_at`.
SESSION_WARN_SECONDS = int(os.getenv("JWT_SESSION_WARN_MINUTES", "15")) * 60

# Tempo de vida do access token (min). Curto (5): reduz a janela de acesso
# residual do access stateless se a revogação imediata (abaixo) não estiver
# disponível. O usuário legítimo não reloga — o refresh silencioso renova.
JWT_ACCESS_MINUTES = int(os.getenv("JWT_ACCESS_MINUTES", "5"))

# --- Revogação imediata de sessão por "época" (Fase 10.7) ---------------------
# Fecha a janela residual do access token: ao trocar/resetar senha ou desativar
# um usuário, a IAM grava `revoked_after=<agora>` no Redis compartilhado; cada
# resource server rejeita, por requisição, access tokens com `iat` anterior. A
# chave é auto-limpante (TTL = ACCESS TTL + margem: um token emitido antes já
# terá expirado). Redis DB dedicado (2), separado de celery (0)/cache (1).
SESSION_REVOCATION_ENABLED = os.getenv("SESSION_REVOCATION_ENABLED", "True") == "True"
SESSION_REVOKE_REDIS_URL = os.getenv("SESSION_REVOKE_REDIS_URL", "redis://localhost:6379/2")
SESSION_REVOKE_PREFIX = "sess:revoked_after:"
SESSION_REVOKE_MARGIN_SECONDS = 120
SESSION_REVOKE_TTL_SECONDS = JWT_ACCESS_MINUTES * 60 + SESSION_REVOKE_MARGIN_SECONDS

# --- Token serviço→serviço (Fase 10.8) ----------------------------------------
# A IAM é a única que assina o JWT da plataforma (RS256 em produção). Um serviço
# (ex.: o backend, ao excluir obra/empreendimento) que precise chamar outro
# produto (drone) não pode forjar token — pede um à IAM via POST
# /auth/service-token/, autenticado por este segredo compartilhado (fail-fast em
# produção, sem fallback público — mesma disciplina do S7). TTL curto: o token
# só precisa sobreviver à chamada que o motivou.
SERVICE_TOKEN_SECRET = _config("SERVICE_TOKEN_SECRET", "service-token-dev-secret-NAO-USAR-EM-PROD")
SERVICE_TOKEN_TTL_SECONDS = int(os.getenv("SERVICE_TOKEN_TTL_SECONDS", "120"))

# --- E-mail (D11: recuperação de senha) ---------------------------------------
# A IAM passou a enviar e-mail por conta própria em vez de delegar ao backend: ela
# é a autoridade de identidade e o fluxo de recuperação não pode depender da saúde
# de outro serviço para destravar um usuário. Em dev/staging o destino é o Mailpit
# (perfil `mail` do compose), que captura tudo e não entrega para fora.
EMAIL_HOST = os.getenv("MAIL_HOST", "")
EMAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("MAIL_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("MAIL_PASS", "")
# Mailpit fala SMTP puro na 1025 (sem TLS, sem auth). Só ligamos TLS/SSL quando a
# porta indica um servidor real — senão o handshake falha contra o Mailpit.
EMAIL_USE_SSL = EMAIL_PORT == 465
EMAIL_USE_TLS = EMAIL_PORT not in (465, 1025)
EMAIL_TIMEOUT = int(os.getenv("MAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv("MAIL_FROM", "Sistema de Gestão <noreply@sistemagestao.com>")
# Sem MAIL_HOST o envio é no-op silencioso — aceitável em dev, inaceitável em
# produção: a recuperação responderia 200 sem nunca entregar o token, e o usuário
# ficaria travado achando que o e-mail vem. Fora de DEBUG, exigimos o host.
if not DEBUG and not EMAIL_HOST:
    raise ImproperlyConfigured(
        "MAIL_HOST é obrigatório em produção (IAM_DEBUG=False): sem ele a recuperação "
        "de senha aceita a solicitação e nunca entrega o token."
    )

# Base pública para montar o link do e-mail. É o domínio do gateway, não o da IAM
# (o usuário abre a tela do React, que então chama a API).
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:8090")

# --- Recuperação de senha (D11) -----------------------------------------------
# Janela curta: o token é uma credencial de takeover completo enquanto vive.
PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))
# Teto de solicitações por alvo/por IP na janela, para não virar oráculo de
# enumeração nem canal de spam contra a caixa da vítima.
PASSWORD_RESET_MAX_POR_HORA = int(os.getenv("PASSWORD_RESET_MAX_POR_HORA", "5"))
# Cooldown após troca de e-mail: fecha o caminho "admin troca o e-mail da vítima
# e pede recuperação para a própria caixa". Durante a carência nenhum token novo é
# emitido para a conta, dando tempo de o aviso chegar ao endereço ANTIGO.
PASSWORD_RESET_COOLDOWN_TROCA_EMAIL_HORAS = int(
    os.getenv("PASSWORD_RESET_COOLDOWN_TROCA_EMAIL_HORAS", "24")
)
# Validade do link de confirmação de troca de e-mail (enviado ao endereço ANTIGO).
EMAIL_CHANGE_TTL_HORAS = int(os.getenv("EMAIL_CHANGE_TTL_HORAS", "48"))

# Proxies CONFIÁVEIS entre o cliente e este serviço (hoje: só o gateway nginx).
# Setting de topo porque tem DOIS consumidores que precisam concordar: o throttle
# do DRF (via REST_FRAMEWORK abaixo) e o `_origem()` da trilha de segurança. Se
# divergissem, o teto contaria um endereço e a auditoria registraria outro.
NUM_PROXIES = int(os.getenv("NUM_PROXIES", "1"))

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",  # browser/admin session
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",  # interface web
    ],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # S8 — teto de requisições na IAM. O gateway já limita o /auth/login/, mas
    # o resto da superfície de identidade (refresh, troca de senha, listagem de
    # usuários, papéis) não tinha teto nenhum. O escopo `recuperacao` é o mais
    # apertado: é endpoint PÚBLICO e o teto por conta (5/h) não cobre quem
    # dispara pedidos contra contas diferentes em rajada.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("THROTTLE_ANON", "120/min"),
        "user": os.getenv("THROTTLE_USER", "1000/hour"),
        "recuperacao": os.getenv("THROTTLE_RECUPERACAO", "30/hour"),
    },
    # Quantos proxies CONFIÁVEIS existem entre o cliente e este serviço. Sem isto
    # o DRF usa a cadeia INTEIRA do X-Forwarded-For como identidade — e como o
    # gateway ACRESCENTA o IP real ao que o cliente mandou
    # (`$proxy_add_x_forwarded_for`), bastava enviar um XFF falso e trocá-lo a
    # cada requisição para ganhar um balde novo: o teto por IP era contornável
    # por qualquer um. Com o valor certo, o DRF ignora o que o cliente mandou e
    # usa o endereço que o proxy acrescentou.
    # AJUSTE se houver outra camada na frente (Cloudflare/ALB): o número tem de
    # bater com a quantidade real de proxies, senão volta a valer o IP errado.
    "NUM_PROXIES": NUM_PROXIES,
}

# Cache compartilhado — necessário para o throttle acima valer de verdade: com o
# LocMemCache padrão, cada worker do gunicorn teria a própria contagem e o teto
# real seria N vezes maior. Reusa o Redis da revogação de sessão (DB 3, separado
# do DB 2 das épocas). `IGNORE_EXCEPTIONS` mantém a IAM de pé se o Redis cair —
# throttle é proteção contra abuso, não deve derrubar o login (mesma escolha
# fail-open da revogação de sessão, ver acesso-e-permissoes.md §5.1).
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("IAM_CACHE_REDIS_URL", "redis://localhost:6379/3"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # Redis fora do ar => cache vira no-op (miss) em vez de exceção, e o
            # throttle deixa passar. Sem isto, uma queda do Redis derrubaria o
            # login inteiro — trocaríamos abuso por indisponibilidade total.
            "IGNORE_EXCEPTIONS": True,
        },
    }
}

# --- Testes: throttle desligado e cache isolada -----------------------------
# A contagem do throttle vive na cache, que é o Redis REAL e compartilhado. Sem
# isto os testes se contaminam entre si e entre execuções (o 6º teste que chama
# /auth/senha/esqueci/ toma 429 por causa do 5º, e o teto por hora nem zera
# entre runs) — foi exatamente o que aconteceu ao introduzir o S8.
# Quem exercita o throttle de propósito reativa a taxa com @override_settings.
TESTING = "test" in sys.argv
if TESTING:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
        chave: None for chave in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    }

# Segredo de assinatura COMPARTILHADO com os validadores (backend, funcoesODM, Node).
# Em produção, migrar para RS256/JWKS (docs/arquitetura.md, Fase 5).
# --- Assinatura do JWT (Fase 5: RS256 + JWKS) ---
# Se houver chave privada RSA, a IAM assina com RS256 (assimétrico): só ela
# detém a privada; os validadores (backend, drone) usam apenas a pública, servida
# em /.well-known/jwks.json. Sem a chave, cai para HS256 (segredo compartilhado).
def _read_key(path):
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    return ""

JWT_PRIVATE_KEY = _read_key(os.getenv("JWT_PRIVATE_KEY_PATH"))
JWT_PUBLIC_KEY = _read_key(os.getenv("JWT_PUBLIC_KEY_PATH"))

_JWT_COMMON = {
    # Access curto: a credencial de uso vive em memória no cliente e é renovada em
    # silêncio pelo refresh. Também define em quanto tempo uma revogação/mudança de
    # permissão passa a valer (o refresh recalcula claims).
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=JWT_ACCESS_MINUTES),
    # Valor INICIAL do refresh, sempre sobrescrito por `_aplicar_validade` com a
    # janela/teto da sessão (SESSION_IDLE* / SESSION_REMEMBER / SESSION_ABS_CAP).
    # NÃO há env var aqui de propósito: existia um `JWT_REFRESH_DAYS` que dava a
    # impressão de controlar a duração da sessão e nunca valeu nada, porque este
    # valor é descartado na emissão. Para mudar a sessão, use os knobs acima.
    "REFRESH_TOKEN_LIFETIME": SESSION_ABS_CAP,
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "ISSUER": os.getenv("JWT_ISSUER", "sgi-iam"),
    # S8 — `aud` passa a viajar no token para que os resource servers (backend,
    # drone) possam exigi-lo. Valor único da plataforma: hoje todos os produtos
    # aceitam o mesmo público; separar por produto exigiria um token por
    # audiência, que só faz sentido quando houver consumidor de terceiro.
    # ATENÇÃO: mudar isto obriga a mudar JWT_AUDIENCE nos validadores no mesmo
    # deploy — divergência derruba TODA autenticação.
    "AUDIENCE": os.getenv("JWT_AUDIENCE", "sgi"),
}

if JWT_PRIVATE_KEY:
    SIMPLE_JWT = {
        **_JWT_COMMON,
        "ALGORITHM": "RS256",
        "SIGNING_KEY": JWT_PRIVATE_KEY,
        "VERIFYING_KEY": JWT_PUBLIC_KEY,
    }
elif DEBUG:
    # Dev: sem a chave privada, assina em HS256 com o segredo compartilhado.
    SIMPLE_JWT = {
        **_JWT_COMMON,
        "ALGORITHM": "HS256",
        "SIGNING_KEY": os.getenv("JWT_SECRET", SECRET_KEY),
    }
else:
    # S3 — em produção a IAM só assina em RS256 (só ela detém a privada; os
    # validadores usam a pública e não conseguem forjar). HS256 compartilha o
    # segredo com quem valida → qualquer serviço poderia emitir tokens.
    raise ImproperlyConfigured(
        "Em produção a IAM deve assinar o JWT em RS256: defina JWT_PRIVATE_KEY_PATH "
        "apontando para a chave privada RSA. HS256 (segredo compartilhado, "
        "falsificável) só é permitido com IAM_DEBUG=True."
    )

# Observabilidade (Fase 10.1)
OBSERVABILITY_SERVICE_NAME = os.getenv("OBSERVABILITY_SERVICE_NAME", "iam")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json" if not DEBUG else "text")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Logs estruturados em JSON com `request_id` de correlação (ver
# identity.observability). `LOG_FORMAT=text` volta ao formato humano de dev.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {"()": "identity.observability.RequestContextFilter"},
    },
    "formatters": {
        "json": {"()": "identity.observability.JsonLogFormatter"},
        "text": {
            "format": "%(asctime)s %(levelname)s %(name)s [req=%(request_id)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": LOG_FORMAT,
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}
