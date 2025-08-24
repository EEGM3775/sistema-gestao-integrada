<?php
require_once(__DIR__ . '/vendor/autoload.php');
require_once(__DIR__ . '/src/NotaFiscalManager.php');

use FuncoesNF\PHPSupport\NotaFiscalManager;

try {
    $filtrosJson = $argv[1] ?? '{}';
    $filtros = json_decode($filtrosJson, true);
    
    if (json_last_error() !== JSON_ERROR_NONE) {
        echo json_encode([
            'success' => false, 
            'error' => 'Filtros JSON inválidos: ' . json_last_error_msg()
        ]);
        exit(1);
    }

    $nfManager = new NotaFiscalManager();
    $resultado = $nfManager->listarNFS($filtros);
    
    echo json_encode([
        'success' => true,
        'data' => $resultado
    ]);
    
} catch (Exception $e) {
    echo json_encode([
        'success' => false,
        'error' => $e->getMessage()
    ]);
    exit(1);
}
?>