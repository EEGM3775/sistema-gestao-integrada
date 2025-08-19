const axios = require('axios');
const MockAdapter = require('axios-mock-adapter');
const { getFuncionarioByPhone } = require('../services/apiService');

// Mock a instância do axios criada em apiService
// É um pouco complexo porque a instância é interna ao módulo.
// Esta abordagem intercepta o 'axios.create' para nos dar acesso à instância.
jest.mock('axios', () => {
    const originalAxios = jest.requireActual('axios');
    originalAxios.create = jest.fn(() => originalAxios); // Mock create para retornar o axios original
    return originalAxios;
});

describe('apiService', () => {
  let mock;

  beforeEach(() => {
    // Resetamos o mock antes de cada teste
    mock = new MockAdapter(axios);
  });

  afterEach(() => {
    mock.restore();
  });

  describe('getFuncionarioByPhone', () => {
    it('deve retornar um funcionário quando a API encontra um usuário válido', async () => {
      const phoneNumber = '5571999998888';
      const mockFuncionario = {
        id: 1,
        nome_completo: 'João da Silva',
        usuario: { id: 10, username: 'joao.silva' },
        telefone_celular: phoneNumber,
      };

      // Configura o mock para responder a uma chamada GET específica
      mock.onGet(`/rh/funcionarios/?telefone_celular=${phoneNumber}`).reply(200, [mockFuncionario]);

      const result = await getFuncionarioByPhone(phoneNumber);

      expect(result.funcionario).toBeDefined();
      expect(result.funcionario.nome_completo).toBe('João da Silva');
      expect(result.error).toBeNull();
    });

    it('deve retornar um erro se o número não for encontrado', async () => {
      const phoneNumber = '5571900000000';
      
      // Configura o mock para responder com uma lista vazia
      mock.onGet(`/rh/funcionarios/?telefone_celular=${phoneNumber}`).reply(200, []);

      const result = await getFuncionarioByPhone(phoneNumber);

      expect(result.funcionario).toBeNull();
      expect(result.error).toBe('Seu número não está cadastrado como um funcionário no sistema.');
    });

    it('deve retornar um erro se o funcionário encontrado não tiver um usuário associado', async () => {
        const phoneNumber = '5571911112222';
        const mockFuncionarioSemUsuario = {
            id: 2,
            nome_completo: 'Maria Oliveira',
            usuario: null, // Sem usuário
            telefone_celular: phoneNumber,
        };

        mock.onGet(`/rh/funcionarios/?telefone_celular=${phoneNumber}`).reply(200, [mockFuncionarioSemUsuario]);

        const result = await getFuncionarioByPhone(phoneNumber);

        expect(result.funcionario).toBeNull();
        expect(result.error).toContain('não possui um usuário de sistema associado');
    });

    it('deve retornar um erro em caso de falha na API', async () => {
        const phoneNumber = '5571933334444';

        // Simula um erro de rede ou do servidor
        mock.onGet(`/rh/funcionarios/?telefone_celular=${phoneNumber}`).networkError();

        const result = await getFuncionarioByPhone(phoneNumber);

        expect(result.funcionario).toBeNull();
        expect(result.error).toContain('Ocorreu um erro ao verificar seu número.');
    });
  });
});
