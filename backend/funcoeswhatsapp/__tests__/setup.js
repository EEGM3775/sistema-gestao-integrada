// __tests__/setup.js

// Define variáveis de ambiente falsas para o ambiente de teste.
// Isso evita que a validação de configuração falhe durante os testes.
process.env.META_ACCESS_TOKEN = 'test_meta_access_token';
process.env.META_VERIFY_TOKEN = 'test_meta_verify_token';
process.env.META_APP_SECRET = 'test_meta_app_secret';
process.env.META_PHONE_NUMBER_ID = '123456789';
process.env.META_API_VERSION = 'v19.0';
process.env.DJANGO_API_URL = 'http://test-django-api.com/api';
process.env.DJANGO_API_TOKEN = 'test_django_api_token';
process.env.REDIS_URL = 'redis://test-redis:6379';
