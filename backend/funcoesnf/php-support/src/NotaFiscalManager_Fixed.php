<?php
/**
 * Classe principal para gerenciar Notas Fiscais de Serviço
 * usando a API do NFE.io
 */

namespace FuncoesNF\PHPSupport;

require_once(__DIR__ . '/../vendor/autoload.php');
require_once('Config.php');

class NotaFiscalManager
{
    private $apiKey;
    private $companyId;
    private $logger;
    
    public function __construct()
    {
        $this->apiKey = Config::getApiKey();
        $this->companyId = Config::getCompanyId();
        $this->logger = new \stdClass(); // Logger simples
        $this->logger->info = function($msg) { error_log("[INFO] " . $msg); };
        $this->logger->error = function($msg) { error_log("[ERROR] " . $msg); };
        
        // Configurar API Key para NFE.io
        \NFe_Base::setApiKey($this->apiKey);
    }
    
    /**
     * Emitir uma Nota Fiscal de Serviço
     */
    public function emitirNFS(array $dados): array
    {
        try {
            ($this->logger->info)('Iniciando emissão de NFS');
            
            $this->validarDadosEmissao($dados);
            
            $invoice = new \NFe_ServiceInvoice();
            
            // Dados básicos
            $invoice->cityServiceCode = $dados['cityServiceCode'];
            $invoice->description = $dados['description'] ?? 'Serviços prestados';
            $invoice->servicesAmount = $dados['servicesAmount'];
            
            // Dados do tomador
            if (isset($dados['borrower'])) {
                $invoice->borrower = $dados['borrower'];
            }
            
            // Criar a invoice
            $createdInvoice = $invoice->create($this->companyId);
            
            ($this->logger->info)('NFS emitida com sucesso: ' . $createdInvoice->id);
            
            return [
                'success' => true,
                'invoice_id' => $createdInvoice->id,
                'status' => $createdInvoice->status ?? 'PROCESSING',
                'data' => $createdInvoice,
                'message' => 'Nota fiscal emitida com sucesso'
            ];
            
        } catch (\Exception $e) {
            ($this->logger->error)('Erro ao emitir NFS: ' . $e->getMessage());
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'message' => 'Erro ao emitir nota fiscal'
            ];
        }
    }
    
    /**
     * Consultar uma Nota Fiscal específica
     */
    public function consultarNFS(string $invoiceId): array
    {
        try {
            ($this->logger->info)('Consultando NFS: ' . $invoiceId);
            
            $invoice = \NFe_ServiceInvoice::fetch($invoiceId, $this->companyId);
            
            ($this->logger->info)('NFS consultada com sucesso: ' . $invoiceId);
            
            return [
                'id' => $invoice->id,
                'status' => $invoice->status,
                'number' => $invoice->number ?? null,
                'accessKey' => $invoice->accessKey ?? null,
                'issueDate' => $invoice->issueDate ?? null,
                'amount' => $invoice->servicesAmount ?? null,
                'cityServiceCode' => $invoice->cityServiceCode ?? null,
                'description' => $invoice->description ?? null,
                'fullResponse' => $invoice
            ];
            
        } catch (\Exception $e) {
            ($this->logger->error)('Erro ao consultar NFS: ' . $e->getMessage());
            throw $e;
        }
    }
    
    /**
     * Baixar PDF de uma Nota Fiscal
     */
    public function baixarPDF(string $invoiceId, ?string $filename = null): array
    {
        try {
            ($this->logger->info)('Baixando PDF da NFS: ' . $invoiceId);
            
            $invoice = \NFe_ServiceInvoice::fetch($invoiceId, $this->companyId);
            $pdfContent = $invoice->pdf();
            
            if ($filename) {
                $savedPath = __DIR__ . '/../downloads/' . $filename;
                if (!is_dir(dirname($savedPath))) {
                    mkdir(dirname($savedPath), 0755, true);
                }
                file_put_contents($savedPath, $pdfContent);
                
                return [
                    'success' => true,
                    'filename' => $filename,
                    'path' => $savedPath,
                    'size' => strlen($pdfContent),
                    'message' => 'PDF salvo com sucesso'
                ];
            }
            
            return [
                'success' => true,
                'content' => base64_encode($pdfContent),
                'size' => strlen($pdfContent),
                'message' => 'PDF obtido com sucesso'
            ];
            
        } catch (\Exception $e) {
            ($this->logger->error)('Erro ao baixar PDF: ' . $e->getMessage());
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'message' => 'Erro ao baixar PDF'
            ];
        }
    }
    
    /**
     * Cancelar uma Nota Fiscal
     */
    public function cancelarNFS(string $invoiceId, string $reason): array
    {
        try {
            ($this->logger->info)('Cancelando NFS: ' . $invoiceId);
            
            $invoice = \NFe_ServiceInvoice::fetch($invoiceId, $this->companyId);
            $result = $invoice->cancel(['reason' => $reason]);
            
            ($this->logger->info)('NFS cancelada com sucesso: ' . $invoiceId);
            
            return [
                'success' => true,
                'invoice_id' => $invoiceId,
                'status' => 'CANCELLED',
                'reason' => $reason,
                'data' => $result,
                'message' => 'Nota fiscal cancelada com sucesso'
            ];
            
        } catch (\Exception $e) {
            ($this->logger->error)('Erro ao cancelar NFS: ' . $e->getMessage());
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'message' => 'Erro ao cancelar nota fiscal'
            ];
        }
    }
    
    /**
     * Listar todas as notas fiscais da empresa
     * 
     * @param array $filtros Filtros para a consulta
     * @return array Lista de notas fiscais
     */
    public function listarNFS(array $filtros = []): array
    {
        try {
            // A biblioteca NFE.io PHP não possui método 'all()' para listar notas
            // Implementar usando cURL para chamar a API REST diretamente
            return $this->listarNFSViaAPI($filtros);
            
        } catch (\Exception $e) {
            ($this->logger->error)('Erro ao listar NFS: ' . $e->getMessage());
            throw $e;
        }
    }
    
    /**
     * Listar NFS via API REST
     */
    private function listarNFSViaAPI(array $filtros = []): array
    {
        $url = "https://api.nfe.io/v1/companies/{$this->companyId}/serviceinvoices";
        
        // Aplicar filtros na URL
        $queryParams = [];
        if (isset($filtros['pageSize'])) {
            $queryParams['pageSize'] = min($filtros['pageSize'], 50); // Máximo 50
        } else {
            $queryParams['pageSize'] = 10; // Padrão
        }
        
        if (isset($filtros['page'])) {
            $queryParams['page'] = $filtros['page'];
        }
        
        if (!empty($queryParams)) {
            $url .= '?' . http_build_query($queryParams);
        }
        
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'Authorization: ' . $this->apiKey,
            'Content-Type: application/json'
        ]);
        curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
        curl_setopt($ch, CURLOPT_TIMEOUT, 30);
        
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error = curl_error($ch);
        curl_close($ch);
        
        if ($error) {
            throw new \Exception("Erro cURL: " . $error);
        }
        
        if ($httpCode !== 200) {
            throw new \Exception("API retornou código: " . $httpCode . " - Resposta: " . substr($response, 0, 200));
        }
        
        $data = json_decode($response, true);
        if (json_last_error() !== JSON_ERROR_NONE) {
            throw new \Exception("Erro ao decodificar JSON: " . json_last_error_msg());
        }
        
        return $data;
    }
    
    /**
     * Validar dados obrigatórios para emissão
     */
    private function validarDadosEmissao(array $dados): void
    {
        $required = ['cityServiceCode', 'servicesAmount'];
        
        foreach ($required as $field) {
            if (!isset($dados[$field]) || empty($dados[$field])) {
                throw new \Exception("Campo obrigatório ausente: {$field}");
            }
        }
        
        if (!is_numeric($dados['servicesAmount']) || $dados['servicesAmount'] <= 0) {
            throw new \Exception("Valor dos serviços deve ser numérico e maior que zero");
        }
        
        if (!is_string($dados['cityServiceCode'])) {
            throw new \Exception("Código do serviço municipal deve ser uma string");
        }
    }
}
