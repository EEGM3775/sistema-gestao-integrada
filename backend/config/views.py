from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings
import os

def home(request):
    """Página inicial que serve o frontend"""
    try:
        # Caminho para o arquivo frontend
        frontend_path = os.path.join(settings.BASE_DIR, '../frontend/index.html')
        
        with open(frontend_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return HttpResponse(content, content_type='text/html')
    except FileNotFoundError:
        # Fallback se o arquivo não existir
        return HttpResponse(get_fallback_home_content())

def serve_frontend_file(request, file_name):
    """Serve arquivos estáticos do frontend"""
    try:
        # Caminho para o arquivo frontend
        frontend_path = os.path.join(settings.BASE_DIR, '../frontend', file_name)
        
        # Verificar se o arquivo existe
        if not os.path.exists(frontend_path):
            raise Http404("Arquivo não encontrado")
        
        # Determinar o content type baseado na extensão
        if file_name.endswith('.html'):
            content_type = 'text/html'
        elif file_name.endswith('.css'):
            content_type = 'text/css'
        elif file_name.endswith('.js'):
            content_type = 'application/javascript'
        else:
            content_type = 'text/plain'
        
        with open(frontend_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return HttpResponse(content, content_type=content_type)
    
    except Exception:
        raise Http404("Arquivo não encontrado")

def get_fallback_home_content():
    """Retorna conteúdo HTML de fallback caso o frontend não esteja disponível"""
    return """
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sistema de Gestão Integrada</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
                min-height: 100vh;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }
            .header {
                text-align: center;
                margin-bottom: 40px;
                border-bottom: 3px solid #667eea;
                padding-bottom: 20px;
            }
            .header h1 {
                color: #667eea;
                margin: 0;
                font-size: 2.5em;
                font-weight: 300;
            }
            .header p {
                color: #666;
                margin: 10px 0 0 0;
                font-size: 1.2em;
            }
            .info-section {
                background: #f8f9fa;
                border-left: 4px solid #667eea;
                padding: 20px;
                margin: 30px 0;
                border-radius: 0 10px 10px 0;
            }
            .warning-section {
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 20px;
                margin: 30px 0;
                border-radius: 0 10px 10px 0;
            }
            .admin-link {
                display: inline-block;
                background: #667eea;
                color: white;
                text-decoration: none;
                padding: 15px 30px;
                border-radius: 25px;
                font-weight: 500;
                margin: 20px 10px;
                transition: all 0.3s ease;
            }
            .admin-link:hover {
                background: #5a6fd8;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .features {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .feature-card {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                border: 1px solid #e9ecef;
            }
            .feature-icon {
                font-size: 2rem;
                margin-bottom: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏢 Sistema de Gestão Integrada</h1>
                <p>Plataforma completa para gestão empresarial</p>
            </div>
            
            <div class="warning-section">
                <h3>⚠️ Frontend em modo de fallback</h3>
                <p>O frontend completo não foi encontrado. Esta é uma versão simplificada.</p>
                <p><strong>Localização esperada:</strong> ../frontend/index.html</p>
            </div>
            
            <div class="info-section">
                <h3>✅ Sistema Online!</h3>
                <p>O backend está funcionando corretamente. Principais funcionalidades disponíveis:</p>
            </div>

            <div class="features">
                <div class="feature-card">
                    <div class="feature-icon">📄</div>
                    <h4>Emissão de NF</h4>
                    <p>Microserviço Node.js integrado com NFE.io</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">👥</div>
                    <h4>Gestão de Clientes</h4>
                    <p>Cadastro completo de clientes e fornecedores</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🏗️</div>
                    <h4>Módulos Ativos</h4>
                    <p>17+ módulos integrados (CRM, ERP, RH, etc.)</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">💬</div>
                    <h4>WhatsApp</h4>
                    <p>Integração com WhatsApp Business</p>
                </div>
            </div>
            
            <div style="text-align: center;">
                <a href="/admin/" class="admin-link">🔧 Painel Administrativo</a>
                <a href="/nfse/" class="admin-link">📄 Sistema NFS-e</a>
                <a href="/api/" class="admin-link">🔗 APIs do Sistema</a>
            </div>
        </div>
    </body>
    </html>
    """

def api_info(request):
    """
    View para informações da API
    """
    return HttpResponse("""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>API - Sistema de Gestão Integrada</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
                min-height: 100vh;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                border-bottom: 3px solid #667eea;
                padding-bottom: 20px;
            }
            .api-endpoint {
                background: #f8f9fa;
                padding: 15px;
                margin: 15px 0;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }
            .link {
                display: inline-block;
                background: #667eea;
                color: white;
                text-decoration: none;
                padding: 10px 20px;
                border-radius: 20px;
                margin: 10px;
                transition: all 0.3s ease;
            }
            .link:hover {
                background: #5a6fd8;
                transform: translateY(-2px);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔗 API do Sistema de Gestão Integrada</h1>
                <p>Endpoints e informações da API</p>
            </div>
            
            <div class="api-endpoint">
                <h3>📄 Microserviço de Notas Fiscais</h3>
                <p><strong>Porta:</strong> 3002</p>
                <p><strong>Status:</strong> Ativo e integrado com NFE.io</p>
                <p><strong>Funcionalidades:</strong> Emissão de NFS-e, consulta e cancelamento</p>
            </div>
            
            <div class="api-endpoint">
                <h3>🏢 API Principal Django</h3>
                <p><strong>Base URL:</strong> /api/</p>
                <p><strong>Módulos disponíveis:</strong> Clientes, Fornecedores, Empreendimentos, RH, CRM, ERP e mais</p>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="/" class="link">← Voltar para página inicial</a>
                <a href="/nfse/" class="link">📄 Sistema NFS-e</a>
                <a href="/admin/" class="link">Acessar Admin</a>
            </div>
        </div>
    </body>
    </html>
    """)

def nfse_frontend(request):
    """Serve o frontend específico para emissão de NFS-e"""
    try:
        # Caminho para o arquivo frontend NFS-e
        frontend_path = os.path.join(settings.BASE_DIR, '../frontend/nfse.html')
        
        with open(frontend_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return HttpResponse(content, content_type='text/html')
    except FileNotFoundError:
        # Fallback se o arquivo não existir
        return HttpResponse(get_nfse_fallback_content())

def get_nfse_fallback_content():
    """Retorna conteúdo HTML de fallback para NFS-e"""
    return """
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NFS-e - Sistema de Gestão</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0; padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333; min-height: 100vh;
            }
            .container {
                max-width: 800px; margin: 0 auto; background: white;
                border-radius: 15px; padding: 40px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }
            .error { background: #fff3cd; padding: 20px; border-radius: 10px;
                border-left: 4px solid #ffc107; margin: 20px 0; }
            .link { display: inline-block; background: #667eea; color: white;
                text-decoration: none; padding: 15px 30px; border-radius: 25px;
                margin: 10px; transition: all 0.3s ease; }
            .link:hover { background: #5a6fd8; transform: translateY(-2px); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📄 Sistema de Emissão NFS-e</h1>
            <div class="error">
                <h3>⚠️ Frontend não encontrado</h3>
                <p>O arquivo /frontend/nfse.html não foi encontrado.</p>
                <p><strong>As APIs estão funcionando!</strong> Você pode acessar diretamente:</p>
                <ul>
                    <li><strong>Faturas:</strong> /api/erp/faturas/</li>
                    <li><strong>Emissão NFS-e:</strong> POST /api/erp/faturas/{id}/emitir-nfse/</li>
                </ul>
            </div>
            <div style="text-align: center;">
                <a href="/" class="link">← Página Inicial</a>
                <a href="/api/erp/faturas/" class="link">Ver Faturas (JSON)</a>
                <a href="/admin/" class="link">Admin</a>
            </div>
        </div>
    </body>
    </html>
    """

# Remover função duplicada - mantendo apenas uma versão
# def api_info(request):
#     """
#     View para informações da API
#     """
#     return HttpResponse("""
#     <h1>API do Sistema de Gestão Integrada</h1>
#     <p>Endpoints da API serão implementados aqui.</p>
#     <p><a href="/">← Voltar para página inicial</a></p>
#     <p><a href="/admin/">Acessar Admin</a></p>
#     """)
