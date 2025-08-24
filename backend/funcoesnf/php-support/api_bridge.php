<?php
/**
 * API Bridge - Ponte entre Node.js e PHP para NFE.io
 * 
 * Este script serve como uma ponte entre o microserviço Node.js
 * e a biblioteca PHP do NFE.io para funcionalidades avançadas
 */

require_once(__DIR__ . '/../src/NotaFiscalManager.php');

use FuncoesNF\PHPSupport\NotaFiscalManager;

// Configurar headers para API REST
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Tratar OPTIONS request (CORS preflight)
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

// Função para enviar resposta JSON
function sendResponse(bool $success, $data = null, string $message = '', int $httpCode = 200): void
{
    http_response_code($httpCode);
    echo json_encode([
        'success' => $success,
        'data' => $data,
        'message' => $message,
        'timestamp' => date('Y-m-d H:i:s')
    ]);
    exit();
}

// Função para registrar log
function logAction(string $action, array $data = [], string $result = ''): void
{
    $logEntry = [
        'timestamp' => date('Y-m-d H:i:s'),
        'action' => $action,
        'data' => $data,
        'result' => $result
    ];
    
    $logFile = __DIR__ . '/../logs/php_bridge.log';
    $logDir = dirname($logFile);
    
    if (!is_dir($logDir)) {
        mkdir($logDir, 0755, true);
    }
    
    file_put_contents($logFile, json_encode($logEntry) . "\n", FILE_APPEND | LOCK_EX);
}

try {
    // Instanciar o gerenciador
    $nfManager = new NotaFiscalManager();
    
    // Obter dados da requisição
    $method = $_SERVER['REQUEST_METHOD'];
    $pathInfo = $_SERVER['PATH_INFO'] ?? '';
    $inputData = json_decode(file_get_contents('php://input'), true) ?? [];
    
    // Remover barra inicial se existir
    $pathInfo = ltrim($pathInfo, '/');
    
    // Roteamento das requisições
    switch ($method) {
        case 'POST':
            switch ($pathInfo) {
                case 'emitir':
                    logAction('emitir_nfs', $inputData);
                    
                    // Validar dados obrigatórios
                    if (!isset($inputData['cityServiceCode']) || !isset($inputData['description']) || !isset($inputData['servicesAmount'])) {
                        sendResponse(false, null, 'Dados obrigatórios ausentes', 400);
                    }
                    
                    $resultado = $nfManager->emitirNFS($inputData);
                    logAction('emitir_nfs_result', [], $resultado['success'] ? 'success' : 'error');
                    
                    sendResponse(
                        $resultado['success'],
                        $resultado['data'] ?? null,
                        $resultado['message'],
                        $resultado['success'] ? 201 : 400
                    );
                    break;
                    
                case 'cancelar':
                    logAction('cancelar_nfs', $inputData);
                    
                    if (!isset($inputData['invoiceId'])) {
                        sendResponse(false, null, 'ID da nota fiscal é obrigatório', 400);
                    }
                    
                    $resultado = $nfManager->cancelarNFS(
                        $inputData['invoiceId'],
                        $inputData['reason'] ?? 'Cancelamento solicitado via API'
                    );
                    logAction('cancelar_nfs_result', [], $resultado['success'] ? 'success' : 'error');
                    
                    sendResponse(
                        $resultado['success'],
                        $resultado['data'] ?? null,
                        $resultado['message'],
                        $resultado['success'] ? 200 : 400
                    );
                    break;
                    
                case 'baixar-pdf':
                    logAction('baixar_pdf', $inputData);
                    
                    if (!isset($inputData['invoiceId'])) {
                        sendResponse(false, null, 'ID da nota fiscal é obrigatório', 400);
                    }
                    
                    $resultado = $nfManager->baixarPDF(
                        $inputData['invoiceId'],
                        $inputData['filename'] ?? null
                    );
                    logAction('baixar_pdf_result', [], $resultado['success'] ? 'success' : 'error');
                    
                    sendResponse(
                        $resultado['success'],
                        $resultado['data'] ?? null,
                        $resultado['message'],
                        $resultado['success'] ? 200 : 400
                    );
                    break;
                    
                default:
                    sendResponse(false, null, 'Endpoint não encontrado', 404);
            }
            break;
            
        case 'GET':
            switch ($pathInfo) {
                case 'consultar':
                    $invoiceId = $_GET['id'] ?? '';
                    
                    if (empty($invoiceId)) {
                        sendResponse(false, null, 'ID da nota fiscal é obrigatório', 400);
                    }
                    
                    logAction('consultar_nfs', ['invoiceId' => $invoiceId]);
                    
                    $resultado = $nfManager->consultarNFS($invoiceId);
                    logAction('consultar_nfs_result', [], $resultado['success'] ? 'success' : 'error');
                    
                    sendResponse(
                        $resultado['success'],
                        $resultado['data'] ?? null,
                        $resultado['message'],
                        $resultado['success'] ? 200 : 400
                    );
                    break;
                    
                case 'listar':
                    logAction('listar_nfs', []);
                    
                    $resultado = $nfManager->listarNFS();
                    logAction('listar_nfs_result', [], $resultado['success'] ? 'success' : 'error');
                    
                    sendResponse(
                        $resultado['success'],
                        $resultado['data'] ?? null,
                        $resultado['message']
                    );
                    break;
                    
                case 'status':
                    // Endpoint para verificar se o serviço está ativo
                    sendResponse(true, [
                        'service' => 'NFE.io PHP Bridge',
                        'status' => 'active',
                        'version' => '1.0.0'
                    ], 'Serviço ativo');
                    break;
                    
                default:
                    sendResponse(false, null, 'Endpoint não encontrado', 404);
            }
            break;
            
        default:
            sendResponse(false, null, 'Método não permitido', 405);
    }
    
} catch (\Exception $e) {
    logAction('error', [], $e->getMessage());
    sendResponse(false, null, 'Erro interno: ' . $e->getMessage(), 500);
}
?>
