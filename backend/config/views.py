from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

def home(request):
    """
    View para a página inicial do sistema
    """
    html_content = """
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
            .modules-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .module-card {
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 10px;
                padding: 25px;
                text-align: center;
                transition: all 0.3s ease;
                cursor: pointer;
            }
            .module-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.1);
                border-color: #667eea;
            }
            .module-card h3 {
                color: #667eea;
                margin: 0 0 15px 0;
                font-size: 1.4em;
            }
            .module-card p {
                color: #666;
                margin: 0;
                line-height: 1.5;
            }
            .module-links {
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #e9ecef;
            }
            .module-links a {
                display: block;
                color: #667eea;
                text-decoration: none;
                font-weight: 500;
                margin: 5px 0;
                padding: 5px 0;
                transition: color 0.3s ease;
            }
            .module-links a:hover {
                color: #5a6fd8;
                text-decoration: underline;
            }
            .admin-link {
                display: inline-block;
                background: #667eea;
                color: white;
                text-decoration: none;
                padding: 15px 30px;
                border-radius: 25px;
                font-weight: 500;
                margin: 20px 0;
                transition: all 0.3s ease;
            }
            .admin-link:hover {
                background: #5a6fd8;
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .info-section {
                background: #f8f9fa;
                border-left: 4px solid #667eea;
                padding: 20px;
                margin: 30px 0;
                border-radius: 0 10px 10px 0;
            }
            .status-indicator {
                display: inline-block;
                width: 12px;
                height: 12px;
                background: #28a745;
                border-radius: 50%;
                margin-right: 8px;
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0% { box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.7); }
                70% { box-shadow: 0 0 0 10px rgba(40, 167, 69, 0); }
                100% { box-shadow: 0 0 0 0 rgba(40, 167, 69, 0); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏢 Sistema de Gestão Integrada</h1>
                <p>Plataforma completa para gestão empresarial</p>
                <p><span class="status-indicator"></span>Sistema Operacional</p>
            </div>
            
            <div class="info-section">
                <h3>✅ Sistema Configurado com Sucesso!</h3>
                <p>Todos os módulos estão funcionando e o banco de dados foi criado. Use o painel administrativo para gerenciar os dados do sistema.</p>
            </div>
            
            <div style="text-align: center;">
                <a href="/admin/" class="admin-link">🔧 Acessar Painel Administrativo</a>
            </div>
            
            <div class="modules-grid">
                <div class="module-card">
                    <h3>👥 Clientes</h3>
                    <p>Gestão completa de clientes, contratos, documentos e relacionamentos com empreendimentos.</p>
                    <div class="module-links">
                        <a href="/admin/clientes/cliente/" target="_blank">📝 Gerenciar Clientes</a>
                        <a href="/admin/clientes/contratocliente/" target="_blank">📋 Contratos</a>
                        <a href="/admin/clientes/clienteempreendimento/" target="_blank">🏠 Aquisições</a>
                        <a href="/admin/clientes/dadobancariocliente/" target="_blank">🏦 Dados Bancários</a>
                        <a href="/api/clientes/" target="_blank">🔗 API Clientes</a>
                    </div>
                </div>
                
                <div class="module-card">
                    <h3>🏗️ Empreendimentos</h3>
                    <p>Controle de projetos, custos e contas bancárias específicas para cada empreendimento.</p>
                    <div class="module-links">
                        <a href="/admin/empreendimentos/empreendimento/" target="_blank">🏢 Gerenciar Empreendimentos</a>
                        <a href="/admin/empreendimentos/custoempreendimento/" target="_blank">💸 Custos</a>
                        <a href="/admin/empreendimentos/contabancariaempreendimento/" target="_blank">🏦 Contas Bancárias</a>
                    </div>
                </div>
                
                <div class="module-card">
                    <h3>💰 Financeiro</h3>
                    <p>Contas a pagar e receber, cobranças, notas fiscais e controle financeiro completo.</p>
                    <div class="module-links">
                        <a href="/admin/financeiro/contareceber/" target="_blank">💵 Contas a Receber</a>
                        <a href="/admin/financeiro/contapagar/" target="_blank">💳 Contas a Pagar</a>
                        <a href="/admin/financeiro/notafiscal/" target="_blank">🧾 Notas Fiscais</a>
                        <a href="/admin/financeiro/cobrancacliente/" target="_blank">📞 Cobranças</a>
                    </div>
                </div>
                
                <div class="module-card">
                    <h3>🏪 Fornecedores</h3>
                    <p>Cadastro e gestão de fornecedores com todas as informações necessárias.</p>
                    <div class="module-links">
                        <a href="/admin/fornecedores/fornecedor/" target="_blank">🏪 Gerenciar Fornecedores</a>
                        <a href="/admin/fornecedores/produtoservicofornecedor/" target="_blank">📦 Produtos/Serviços</a>
                        <a href="/admin/fornecedores/dadobancariofornecedor/" target="_blank">🏦 Dados Bancários</a>
                    </div>
                </div>
                
                <div class="module-card">
                    <h3>🔧 Obras</h3>
                    <p>Controle de obras, etapas de execução e documentos relacionados aos projetos.</p>
                    <div class="module-links">
                        <a href="/admin/obras/obra/" target="_blank">🏗️ Gerenciar Obras</a>
                        <a href="/admin/obras/etapaobra/" target="_blank">📊 Etapas</a>
                        <a href="/admin/obras/documentoobra/" target="_blank">📄 Documentos</a>
                    </div>
                </div>
                
                <div class="module-card">
                    <h3>👨‍💼 Recursos Humanos</h3>
                    <p>Gestão de funcionários, folha de pagamento, documentos e dados médicos.</p>
                    <div class="module-links">
                        <a href="/admin/rh/funcionario/" target="_blank">👤 Funcionários</a>
                        <a href="/admin/rh/folhapagamento/" target="_blank">💰 Folha de Pagamento</a>
                        <a href="/admin/rh/cargo/" target="_blank">🎯 Cargos</a>
                        <a href="/admin/rh/dadomedicofuncionario/" target="_blank">� Dados Médicos</a>
                    </div>
                </div>
                
                <div class="module-card">
                    <h3>⚙️ Núcleo</h3>
                    <p>Usuários do sistema, perfis de acesso, permissões e logs de atividades.</p>
                    <div class="module-links">
                        <a href="/admin/nucleo/usuario/" target="_blank">👥 Usuários</a>
                        <a href="/admin/nucleo/perfil/" target="_blank">🔐 Perfis</a>
                        <a href="/admin/nucleo/permissao/" target="_blank">� Permissões</a>
                        <a href="/admin/nucleo/logacividadeusuario/" target="_blank">📊 Logs</a>
                    </div>
                </div>
            </div>
            
            <div class="info-section">
                <h3>� Acessos Rápidos à API</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
                    <a href="/api/" target="_blank" style="color: #667eea; text-decoration: none; padding: 10px; background: #f8f9fa; border-radius: 5px; border: 1px solid #e9ecef;">🔗 API Principal</a>
                    <a href="/api/clientes/" target="_blank" style="color: #667eea; text-decoration: none; padding: 10px; background: #f8f9fa; border-radius: 5px; border: 1px solid #e9ecef;">👥 API Clientes</a>
                    <a href="/api/contratos-clientes/" target="_blank" style="color: #667eea; text-decoration: none; padding: 10px; background: #f8f9fa; border-radius: 5px; border: 1px solid #e9ecef;">📋 API Contratos</a>
                    <a href="/api/clientes-empreendimentos/" target="_blank" style="color: #667eea; text-decoration: none; padding: 10px; background: #f8f9fa; border-radius: 5px; border: 1px solid #e9ecef;">🏠 API Aquisições</a>
                </div>
            </div>
            
            <div class="info-section">
                <h3>�📋 Funcionalidades Principais</h3>
                <ul style="margin: 15px 0; padding-left: 20px;">
                    <li>Interface administrativa completa com Django Admin</li>
                    <li>Sistema de autenticação e autorização</li>
                    <li>Relacionamentos entre módulos</li>
                    <li>Upload e gestão de documentos</li>
                    <li>Controle financeiro integrado</li>
                    <li>Gestão de obras e empreendimentos</li>
                    <li>Sistema de RH completo</li>
                    <li>API REST com Django REST Framework</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html_content)

def api_info(request):
    """
    View para informações da API
    """
    return HttpResponse("""
    <h1>API do Sistema de Gestão Integrada</h1>
    <p>Endpoints da API serão implementados aqui.</p>
    <p><a href="/">← Voltar para página inicial</a></p>
    <p><a href="/admin/">Acessar Admin</a></p>
    """)
