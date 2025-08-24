<?php
require_once(__DIR__ . '/NotaFiscalManager.php');
use FuncoesNF\PHPSupport\NotaFiscalManager;

$invoiceId = $argv[1] ?? '';
$filename = $argv[2] ?? null;

if (empty($invoiceId)) {
    echo json_encode(['success' => false, 'error' => 'Invoice ID é obrigatório']);
    exit(1);
}

$nfManager = new NotaFiscalManager();
$resultado = $nfManager->baixarPDF($invoiceId, $filename);
echo json_encode($resultado);
?>