<?php
require_once(__DIR__ . '/NotaFiscalManager.php');
use FuncoesNF\PHPSupport\NotaFiscalManager;

$invoiceId = $argv[1] ?? '';
$reason = $argv[2] ?? '';

if (empty($invoiceId)) {
    echo json_encode(['success' => false, 'error' => 'Invoice ID é obrigatório']);
    exit(1);
}

if (empty($reason)) {
    echo json_encode(['success' => false, 'error' => 'Motivo do cancelamento é obrigatório']);
    exit(1);
}

$nfManager = new NotaFiscalManager();
$resultado = $nfManager->cancelarNFS($invoiceId, $reason);
echo json_encode($resultado);
?>