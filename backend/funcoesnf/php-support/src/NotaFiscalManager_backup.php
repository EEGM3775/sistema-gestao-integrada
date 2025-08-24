<?php
/**
 * Classe principal para gerenciar Notas Fiscais de Serviço
 * usando a API do NFE.io
 */

namespace FuncoesNF\PHPSupport;

require_once(__DIR__ . '/../vendor/autoload.php');
require_once('Config.php');

class NotaFiscalManager{
    private $apiKey;
    private $companyId;
    
    public function __construct()
    {
        $this->apiKey = Config::getApiKey();
        $this->companyId = Config::getCompanyId();
        
        // Configurar a chave da API
        \NFe_io::setApiKey($this->apiKey);
    }
    
    /**
     * Emitir uma Nota Fiscal de Serviço
     * 
     * @param array $dadosNF Dados da nota fiscal
     * @return array Resultado da emissão
     */
    public function emitirNFS(array $dadosNF): array
    {
        try {
            // Validar dados obrigatórios
            $this->validarDadosEmissao($dadosNF);
            
            // Preparar dados para a API
            $dadosAPI = $this->prepararDadosEmissao($dadosNF);
            
            // Criar a nota fiscal
            $invoiceCreated = \NFe_ServiceInvoice::create($this->companyId, $dadosAPI);
            
            return [
                'success' => true,
                'data' => [
                    'id' => $invoiceCreated->id,
                    'status' => $invoiceCreated->status ?? 'Processing',
                    'rpsNumber' => $invoiceCreated->rpsNumber ?? null,
                    'rpsSerial' => $invoiceCreated->rpsSerial ?? null,
                    'number' => $invoiceCreated->number ?? null,
                    'checkCode' => $invoiceCreated->checkCode ?? null,
                    'cityServiceCode' => $dadosNF['cityServiceCode'] ?? null,
                    'servicesAmount' => $dadosNF['servicesAmount'] ?? null
                ],
                'message' => 'Nota fiscal enviada para processamento com sucesso'
            ];
            
        } catch (\Exception $e) {
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'message' => 'Erro ao emitir nota fiscal'
            ];
        }
    }
    
    /**
     * Consultar uma Nota Fiscal de Serviço
     * 
     * @param string $invoiceId ID da nota fiscal no NFE.io
     * @return array Dados da nota fiscal
     */
    public function consultarNFS(string $invoiceId): array
    {
        try {
            $invoice = \NFe_ServiceInvoice::fetch($this->companyId, $invoiceId);
            
            return [
                'success' => true,
                'data' => [
                    'id' => $invoice->id,
                    'status' => $invoice->status,
                    'statusDescription' => Config::NF_STATUS[$invoice->status] ?? $invoice->status,
                    'rpsNumber' => $invoice->rpsNumber ?? null,
                    'rpsSerial' => $invoice->rpsSerial ?? null,
                    'number' => $invoice->number ?? null,
                    'checkCode' => $invoice->checkCode ?? null,
                    'cityServiceCode' => $invoice->cityServiceCode ?? null,
                    'servicesAmount' => $invoice->servicesAmount ?? null,
                    'issueDate' => $invoice->issueDate ?? null,
                    'borrower' => $invoice->borrower ?? null,
                    'flowStatus' => $invoice->flowStatus ?? null,
                    'pdfUrl' => $invoice->pdfUrl ?? null,
                    'xmlUrl' => $invoice->xmlUrl ?? null
                ],
                'message' => 'Consulta realizada com sucesso'
            ];
            
        } catch (\Exception $e) {
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'message' => 'Erro ao consultar nota fiscal'
            ];
        }
    }
    
    /**
     * Cancelar uma Nota Fiscal de Serviço
     * 
     * @param string $invoiceId ID da nota fiscal no NFE.io
     * @param string $reason Motivo do cancelamento
     * @return array Resultado do cancelamento
     */
    public function cancelarNFS(string $invoiceId, string $reason = 'Cancelamento solicitado'): array
    {
        try {
            $invoice = \NFe_ServiceInvoice::fetch($this->companyId, $invoiceId);
            
            // Verificar se a nota pode ser cancelada
            if ($invoice->status !== 'Issued') {
                return [
                    'success' => false,
                    'error' => 'Apenas notas com status "Issued" podem ser canceladas',
                    'current_status' => $invoice->status,
                    'message' => 'Nota fiscal não pode ser cancelada no status atual'
                ];
            }
            
            // Cancelar a nota fiscal
            $invoice->cancel();
            
            return [
                'success' => true,
                'data' => [
                    'id' => $invoice->id,
                    'status' => 'Cancelled',
                    'reason' => $reason
                ],
                'message' => 'Nota fiscal cancelada com sucesso'
            ];
            
        } catch (\Exception $e) {
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'message' => 'Erro ao cancelar nota fiscal'
            ];
        }
    }
    
    /**
     * Baixar PDF da Nota Fiscal
     * 
     * @param string $invoiceId ID da nota fiscal no NFE.io
     * @param string|null $filename Nome do arquivo (opcional)
     * @return array Resultado do download
     */
    public function baixarPDF(string $invoiceId, ?string $filename = null): array
    {
        try {
            // Obter URL do PDF
            $pdfUrl = \NFe_ServiceInvoice::pdf($this->companyId, $invoiceId);
            
            // Definir nome do arquivo se não fornecido
            if (!$filename) {
                $filename = "nfs_" . $invoiceId . "_" . date('Y-m-d_H-i-s') . '.pdf';
            }
            
            // Caminho completo para salvar o arquivo
            $storagePath = Config::getPdfStoragePath();
            $fullPath = $storagePath . $filename;
            
            // Baixar e salvar o arquivo
            $pdfContent = file_get_contents($pdfUrl);
            
            if ($pdfContent === false) {
                throw new \Exception('Falha ao baixar o PDF da URL fornecida');
            }
            
            $saved = file_put_contents($fullPath, $pdfContent);
            
            if ($saved === false) {
                throw new \Exception('Falha ao salvar o arquivo PDF');
            }
            
            return [
                'success' => true,
                'data' => [
                    'filename' => $filename,
                    'fullPath' => $fullPath,
                    'size' => $saved,
                    'url' => $pdfUrl
                ],
                'message' => 'PDF baixado com sucesso'
            ];
            
        } catch (\Exception $e) {
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'message' => 'Erro ao baixar PDF'
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
            $this->logger->error('Erro ao listar NFS: ' . $e->getMessage());
            throw $e;
        }
    }
    
    /**
     * Listar NFS via API REST
     */
    private function listarNFSViaAPI(array $filtros = []): array
    {
        try {
            $url = "https://api.nfe.io/v1/companies/{$this->companyId}/serviceinvoices";
            
            // Aplicar filtros na URL
            $queryParams = [];
            if (isset($filtros['pageSize'])) {
                $queryParams['pageSize'] = $filtros['pageSize'];
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
            
            $response = curl_exec($ch);
            $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
            $error = curl_error($ch);
            curl_close($ch);
            
            if ($error) {
                throw new \Exception("Erro cURL: " . $error);
            }
            
            if ($httpCode !== 200) {
                throw new \Exception("API retornou código: " . $httpCode . " - " . $response);
            }
            
            $data = json_decode($response, true);
            if (json_last_error() !== JSON_ERROR_NONE) {
                throw new \Exception("Erro ao decodificar JSON: " . json_last_error_msg());
            }
            
            return [
                'success' => true,
                'data' => $data,
                'message' => 'Lista de notas fiscais obtida com sucesso'
            ];
        } catch (\Exception $e) {
            return [
                'success' => false,
                'error' => $e->getMessage(),
                'message' => 'Erro ao listar notas fiscais'
            ];
        }
    }
    /**
     * Validar dados obrigatórios para emissão
     */
    private function validarDadosEmissao(array $dados): void
    {
        $camposObrigatorios = ['cityServiceCode', 'description', 'servicesAmount'];
        
        foreach ($camposObrigatorios as $campo) {
            if (!isset($dados[$campo]) || empty($dados[$campo])) {
                throw new \Exception("Campo obrigatório ausente: {$campo}");
            }
        }
        
        // Validar valor
        if (!is_numeric($dados['servicesAmount']) || floatval($dados['servicesAmount']) <= 0) {
            throw new \Exception("Valor dos serviços deve ser um número positivo");
        }
    }
    
    /**
     * Preparar dados para envio à API
     */
    private function prepararDadosEmissao(array $dados): array
    {
        $dadosAPI = [
            'cityServiceCode' => $dados['cityServiceCode'],
            'description' => $dados['description'],
            'servicesAmount' => floatval($dados['servicesAmount'])
        ];
        
        // Adicionar dados do tomador se fornecidos
        if (isset($dados['borrower']) && is_array($dados['borrower'])) {
            $dadosAPI['borrower'] = $this->prepararDadosTomador($dados['borrower']);
        }
        
        return $dadosAPI;
    }
    
    /**
     * Preparar dados do tomador de serviços
     */
    private function prepararDadosTomador(array $tomador): array
    {
        $dadosTomador = [];
        
        // Campos básicos
        if (isset($tomador['federalTaxNumber'])) {
            $dadosTomador['federalTaxNumber'] = $tomador['federalTaxNumber'];
        }
        
        if (isset($tomador['name'])) {
            $dadosTomador['name'] = $tomador['name'];
        }
        
        if (isset($tomador['email'])) {
            $dadosTomador['email'] = $tomador['email'];
        }
        
        // Endereço
        if (isset($tomador['address']) && is_array($tomador['address'])) {
            $dadosTomador['address'] = $tomador['address'];
        }
        
        return $dadosTomador;
    }
}
