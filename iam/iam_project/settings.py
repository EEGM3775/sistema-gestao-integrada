"""
Configuração do serviço IAM (Identity & Access Management).

Serviço separado, autoridade única de identidade da plataforma: dono de
tenants, usuários, papéis/permissões e entitlements de módulo. Emite e
assina os JWTs consumidos por todos os produtos (ERP, funcoesODM, Node).
Ver docs/arquitetura.md (Fase 0.2).
"""
from datetime import timedelta
from pathlib import Path
import os

from dotenv import load_dotenv

# Carrega o .env da raiz do repositório (um nível acima de iam/)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

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
            "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "prefer")},
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
REFRESH_COOKIE_SECURE = os.getenv("IAM_COOKIE_SECURE", "0") == "1"
REFRESH_COOKIE_SAMESITE = os.getenv("IAM_COOKIE_SAMESITE", "Strict")
# Duração da sessão (refresh): curta (sem "lembrar") vs longa deslizante (com),
# ambas limitadas por um teto absoluto desde o login.
SESSION_SHORT = timedelta(hours=int(os.getenv("JWT_SESSION_SHORT_HOURS", "12")))
SESSION_REMEMBER = timedelta(days=int(os.getenv("JWT_SESSION_REMEMBER_DAYS", "30")))
SESSION_ABS_CAP = timedelta(days=int(os.getenv("JWT_SESSION_CAP_DAYS", "90")))

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
}

# Segredo de assinatura COMPARTILHADO com os validadores (ERP, funcoesODM, Node).
# Em produção, migrar para RS256/JWKS (docs/arquitetura.md, Fase 5).
# --- Assinatura do JWT (Fase 5: RS256 + JWKS) ---
# Se houver chave privada RSA, a IAM assina com RS256 (assimétrico): só ela
# detém a privada; os validadores (ERP, drone) usam apenas a pública, servida
# em /.well-known/jwks.json. Sem a chave, cai para HS256 (segredo compartilhado).
def _read_key(path):
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    return ""

JWT_PRIVATE_KEY = _read_key(os.getenv("JWT_PRIVATE_KEY_PATH"))
JWT_PUBLIC_KEY = _read_key(os.getenv("JWT_PUBLIC_KEY_PATH"))

_JWT_COMMON = {
    # Access curto (15 min): a credencial de uso vive em memória no cliente e é
    # renovada em silêncio pelo refresh. Também define em quanto tempo uma
    # revogação/mudança de permissão passa a valer (o refresh recalcula claims).
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "15"))),
    # Teto do refresh no SimpleJWT; a validade REAL por sessão é setada no login
    # (12h sem "lembrar" · 30d com "lembrar"), respeitando o cap absoluto abaixo.
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "30"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "ISSUER": os.getenv("JWT_ISSUER", "sgi-iam"),
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

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
