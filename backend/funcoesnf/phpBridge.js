/**
 * Integração PHP Support - Extensão para o microserviço Node.js
 * 
 * Este módulo adiciona funcionalidades avançadas usando a biblioteca PHP do NFE.io
 */

const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const logger = require('./logger');

class PHPBridge {
    constructor() {
        this.phpSupportPath = path.join(__dirname, 'php-support');
        this.bridgeScript = path.join(this.phpSupportPath, 'api_bridge.php');
        this.isAvailable = this.checkPHPSupport();
    }

    /**
     * Verificar se o suporte PHP está disponível
     */
    checkPHPSupport() {
        try {
            if (!fs.existsSync(this.phpSupportPath)) {
                logger.warn('PHP Support não encontrado. Execute a instalação primeiro.');
                return false;
            }

            if (!fs.existsSync(this.bridgeScript)) {
                logger.warn('API Bridge PHP não encontrada.');
                return false;
            }

            logger.info('PHP Support detectado e disponível');
            return true;
        } catch (error) {
            logger.error('Erro ao verificar PHP Support:', error);
            return false;
        }
    }

    /**
     * Executar comando PHP e retornar resultado
     */
    async executePHP(script, args = []) {
        return new Promise((resolve, reject) => {
            const phpPath = 'php'; // Assumindo que PHP está no PATH
            const fullArgs = [script, ...args];

            const process = spawn(phpPath, fullArgs, {
                cwd: this.phpSupportPath,
                stdio: 'pipe'
            });

            let stdout = '';
            let stderr = '';

            process.stdout.on('data', (data) => {
                stdout += data.toString();
            });

            process.stderr.on('data', (data) => {
                stderr += data.toString();
            });

            process.on('close', (code) => {
                if (code === 0) {
                    try {
                        const result = stdout.trim() ? JSON.parse(stdout.trim()) : null;
                        resolve(result);
                    } catch (parseError) {
                        resolve({ output: stdout.trim(), error: parseError.message });
                    }
                } else {
                    reject(new Error(stderr || `Processo PHP terminou com código: ${code}`));
                }
            });

            process.on('error', (error) => {
                reject(error);
            });
        });
    }

    /**
     * Consultar nota fiscal usando PHP (mais confiável que Node.js)
     */
    async consultarNotaFiscal(invoiceId) {
        if (!this.isAvailable) {
            throw new Error('PHP Support não está disponível');
        }

        try {
            logger.info(`Consultando NF via PHP: ${invoiceId}`);

            const consultScript = path.join(this.phpSupportPath, 'src', 'consultar_bridge.php');
            
            // Criar script temporário se não existir
            if (!fs.existsSync(consultScript)) {
                await this.createTempConsultScript(consultScript);
            }

            const result = await this.executePHP(consultScript, [invoiceId]);
            
            logger.info(`Consulta PHP concluída para NF: ${invoiceId}`);
            return result;

        } catch (error) {
            logger.error(`Erro na consulta PHP para NF ${invoiceId}:`, error);
            throw error;
        }
    }

    /**
     * Baixar PDF da nota fiscal
     */
    async baixarPDF(invoiceId, filename = null) {
        if (!this.isAvailable) {
            throw new Error('PHP Support não está disponível');
        }

        try {
            logger.info(`Baixando PDF via PHP: ${invoiceId}`);

            const pdfScript = path.join(this.phpSupportPath, 'src', 'pdf_bridge.php');
            
            // Criar script temporário se não existir
            if (!fs.existsSync(pdfScript)) {
                await this.createTempPDFScript(pdfScript);
            }

            const args = filename ? [invoiceId, filename] : [invoiceId];
            const result = await this.executePHP(pdfScript, args);
            
            logger.info(`Download PDF PHP concluído para NF: ${invoiceId}`);
            return result;

        } catch (error) {
            logger.error(`Erro no download PDF via PHP para NF ${invoiceId}:`, error);
            throw error;
        }
    }

    /**
     * Cancelar uma nota fiscal
     */
    async cancelarNFS(invoiceId, reason) {
        if (!this.isAvailable) {
            throw new Error('PHP Support não está disponível');
        }

        try {
            logger.info(`Cancelando NFS via PHP: ${invoiceId} - Motivo: ${reason}`);

            const cancelScript = path.join(this.phpSupportPath, 'src', 'cancelar_bridge.php');
            
            // Criar script temporário se não existir
            if (!fs.existsSync(cancelScript)) {
                await this.createTempCancelScript(cancelScript);
            }

            const result = await this.executePHP(cancelScript, [invoiceId, reason]);
            
            logger.info(`Cancelamento via PHP concluído para NF: ${invoiceId}`);
            return result;

        } catch (error) {
            logger.error(`Erro no cancelamento via PHP para NF ${invoiceId}:`, error);
            throw error;
        }
    }

    /**
     * Listar notas fiscais da empresa.
     */
    async listarNotasFiscais(filtros = {}) {
        if (!this.isAvailable) {
            throw new Error('PHP Support não está disponível');
        }

        try {
            logger.info('Listando NFs via PHP com filtros:', filtros);

            const listScript = path.join(this.phpSupportPath, 'src', 'listar_bridge.php');

            if (!fs.existsSync(listScript)) {
                await this.createTempListScript(listScript);
            }

            const filtrosJson = JSON.stringify(filtros);
            const result = await this.executePHP(listScript, [filtrosJson]);

            logger.info('Listagem de NFs via PHP concluída.');
            return result;

        } catch (error) {
            logger.error('Erro ao listar NFs via PHP:', error);
            throw error;
        }
    }

    /**
     * Criar script temporário de consulta
     */
    async createTempConsultScript(scriptPath) {
        const scriptContent = `<?php
require_once(__DIR__ . '/NotaFiscalManager.php');
use FuncoesNF\\PHPSupport\\NotaFiscalManager;

$invoiceId = $argv[1] ?? '';
if (empty($invoiceId)) {
    echo json_encode(['success' => false, 'error' => 'Invoice ID é obrigatório']);
    exit(1);
}

$nfManager = new NotaFiscalManager();
$resultado = $nfManager->consultarNFS($invoiceId);
echo json_encode($resultado);
?>`;

        fs.writeFileSync(scriptPath, scriptContent);
    }

    /**
     * Criar script temporário de PDF
     */
    async createTempPDFScript(scriptPath) {
        const scriptContent = `<?php
require_once(__DIR__ . '/NotaFiscalManager.php');
use FuncoesNF\\PHPSupport\\NotaFiscalManager;

$invoiceId = $argv[1] ?? '';
$filename = $argv[2] ?? null;

if (empty($invoiceId)) {
    echo json_encode(['success' => false, 'error' => 'Invoice ID é obrigatório']);
    exit(1);
}

$nfManager = new NotaFiscalManager();
$resultado = $nfManager->baixarPDF($invoiceId, $filename);
echo json_encode($resultado);
?>`;

        fs.writeFileSync(scriptPath, scriptContent);
    }

    /**
     * Criar script temporário de cancelamento
     */
    async createTempCancelScript(scriptPath) {
        const scriptContent = `<?php
require_once(__DIR__ . '/NotaFiscalManager.php');
use FuncoesNF\\PHPSupport\\NotaFiscalManager;

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
?>`;

        fs.writeFileSync(scriptPath, scriptContent);
    }

    /**
     * Criar script temporário de listagem
     */
    async createTempListScript(scriptPath) {
        const scriptContent = `<?php
require_once(__DIR__ . '/NotaFiscalManager.php');
use FuncoesNF\\PHPSupport\\NotaFiscalManager;

$filtrosJson = $argv[1] ?? '[]';
$filtros = json_decode($filtrosJson, true);

if (json_last_error() !== JSON_ERROR_NONE) {
    echo json_encode(['success' => false, 'error' => 'Filtros JSON inválidos']);
    exit(1);
}

$nfManager = new NotaFiscalManager();
$resultado = $nfManager->listarNFS($filtros);
echo json_encode($resultado);
?>`;

        fs.writeFileSync(scriptPath, scriptContent);
    }

    /**
     * Instalar PHP Support
     */
    async instalarPHPSupport() {
        try {
            logger.info('Iniciando instalação do PHP Support...');

            const installScript = path.join(this.phpSupportPath, 'install.sh');
            
            if (!fs.existsSync(installScript)) {
                throw new Error('Script de instalação não encontrado');
            }

            return new Promise((resolve, reject) => {
                exec(`bash ${installScript}`, { cwd: this.phpSupportPath }, (error, stdout, stderr) => {
                    if (error) {
                        logger.error('Erro na instalação PHP Support:', error);
                        reject(error);
                        return;
                    }

                    logger.info('PHP Support instalado com sucesso');
                    logger.info('Saída da instalação:', stdout);
                    
                    if (stderr) {
                        logger.warn('Avisos durante instalação:', stderr);
                    }

                    this.isAvailable = this.checkPHPSupport();
                    resolve({ success: true, output: stdout });
                });
            });

        } catch (error) {
            logger.error('Erro ao instalar PHP Support:', error);
            throw error;
        }
    }

    /**
     * Obter status do PHP Support
     */
    getStatus() {
        return {
            available: this.isAvailable,
            path: this.phpSupportPath,
            bridge: this.bridgeScript,
            features: {
                consultarNF: this.isAvailable,
                baixarPDF: this.isAvailable,
                cancelarNF: this.isAvailable,
                listarNF: this.isAvailable
            }
        };
    }
}

// Exportar instância única
const phpBridge = new PHPBridge();

module.exports = {
    PHPBridge,
    phpBridge
};
