module.exports = {
  testEnvironment: 'node',
  clearMocks: true,
  coverageProvider: 'v8',
  // Executa este arquivo para configurar o ambiente de teste antes dos testes.
  setupFilesAfterEnv: ['./__tests__/setup.js'],
  // Define explicitamente quais arquivos são considerados testes
  testMatch: [
    '**/__tests__/**/*.test.js',
    '**/__tests__/**/*.spec.js',
  ],
};
