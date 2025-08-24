<?php
/**
 * Configurações para integração com NFE.io
 * 
 * Este arquivo centraliza todas as configurações necessárias
 * para a integração com a API do NFE.io
 */

namespace FuncoesNF\PHPSupport;

class Config
{
    /**
     * Chave da API NFE.io
     * Esta chave deve ser obtida no painel: https://app.nfe.io/account/apikeys
     */
    const NFE_API_KEY = 'uquNvR3QCRbf5FA3MyXQmp3Phd6qq6nMzzlKUvOhv2V66Oouz5SpeuAj5Fm3JpFer2q'; // Substitua pela sua chave real
    
    /**
     * ID da empresa no NFE.io
     * Este ID deve ser copiado exatamente como aparece no painel
     */
    const COMPANY_ID = '68a63350f2f80c159c51526c'; // Substitua pelo seu ID real
    
    /**
     * Configurações de ambiente
     */
    const ENVIRONMENT = 'development'; // 'development' ou 'production'
    
    /**
     * URLs base da API
     */
    const API_BASE_URL = 'https://api.nfe.io/v1/';
    
    /**
     * Timeout para requisições HTTP (em segundos)
     */
    const HTTP_TIMEOUT = 30;
    
    /**
     * Diretório para salvar PDFs das notas fiscais
     */
    const PDF_STORAGE_PATH = '../../../media/nf_pdfs/';
    
    /**
     * Diretório para salvar XMLs das notas fiscais
     */
    const XML_STORAGE_PATH = '../../../media/nf_xmls/';
    
    /**
     * Email padrão para testes
     * Você pode visualizar os emails em: https://www.mailinator.com/
     */
    const TEST_EMAIL = 'nfe@mailinator.com';
    
    /**
     * Códigos de serviço mais utilizados
     */
    const SERVICE_CODES = [
        '010701' => 'Serviços de consultoria',
        '1401'   => 'Serviços de tecnologia da informação',
        '2690'   => 'Outros serviços',
        '1701'   => 'Serviços de engenharia',
        '1101'   => 'Serviços advocatícios',
        '1301'   => 'Serviços de contabilidade'
    ];
    
    /**
     * Status das notas fiscais
     */
    const NF_STATUS = [
        'WaitingCalculateTaxes' => 'Aguardando cálculo de impostos',
        'WaitingDefineRpsNumber' => 'Aguardando definição do número RPS',
        'WaitingSend' => 'Aguardando envio',
        'Processing' => 'Processando',
        'Issued' => 'Emitida',
        'Cancelled' => 'Cancelada',
        'Error' => 'Erro'
    ];
    
    /**
     * Obter a chave da API a partir das variáveis de ambiente ou constante
     */
    public static function getApiKey(): string
    {
        return $_ENV['NFE_API_KEY'] ?? self::NFE_API_KEY;
    }
    
    /**
     * Obter o ID da empresa a partir das variáveis de ambiente ou constante
     */
    public static function getCompanyId(): string
    {
        return $_ENV['NFE_COMPANY_ID'] ?? self::COMPANY_ID;
    }
    
    /**
     * Verificar se está em modo de desenvolvimento
     */
    public static function isDevelopment(): bool
    {
        return self::ENVIRONMENT === 'development';
    }
    
    /**
     * Obter o caminho completo para armazenamento de PDFs
     */
    public static function getPdfStoragePath(): string
    {
        $path = __DIR__ . '/' . self::PDF_STORAGE_PATH;
        
        // Criar diretório se não existir
        if (!is_dir($path)) {
            mkdir($path, 0755, true);
        }
        
        return $path;
    }
    
    /**
     * Obter o caminho completo para armazenamento de XMLs
     */
    public static function getXmlStoragePath(): string
    {
        $path = __DIR__ . '/' . self::XML_STORAGE_PATH;
        
        // Criar diretório se não existir
        if (!is_dir($path)) {
            mkdir($path, 0755, true);
        }
        
        return $path;
    }
}
