<?php
require_once(__DIR__ . '/NotaFiscalManager.php');
use FuncoesNF\PHPSupport\NotaFiscalManager;

$filtrosJson = $argv[1] ?? '[]';
$filtros = json_decode($filtrosJson, true);

if (json_last_error() !== JSON_ERROR_NONE) {
    echo json_encode(['success' => false, 'error' => 'Filtros JSON inválidos']);
    exit(1);
}

$nfManager = new NotaFiscalManager();
$resultado = $nfManager->listarNFS($filtros);
echo json_encode($resultado);
?>