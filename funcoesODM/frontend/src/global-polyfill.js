/**
 * Polyfill para compatibilidade com bibliotecas Node.js no navegador.
 * Algumas bibliotecas (como sockjs-client, buffer, etc.) dependem do objeto
 * 'global' que existe apenas no Node.js.
 * 
 * IMPORTANTE: Este arquivo DEVE ser carregado ANTES de zone.js e qualquer outro código.
 */

// Definir 'global' imediatamente no escopo global
// Isso é necessário porque algumas bibliotecas acessam 'global' antes que qualquer código execute
var global = global || (typeof globalThis !== 'undefined' ? globalThis : (typeof window !== 'undefined' ? window : (typeof self !== 'undefined' ? self : {})));

// Atribuir ao window/globalThis para garantir disponibilidade
if (typeof globalThis !== 'undefined') {
  globalThis.global = global;
}
if (typeof window !== 'undefined') {
  window.global = global;
}
if (typeof self !== 'undefined') {
  self.global = global;
}

// Polyfill para 'process' (algumas bibliotecas também precisam)
if (typeof process === 'undefined') {
  var process = {
    env: {},
    browser: true,
    version: '',
    versions: {},
    platform: 'browser',
    nextTick: function(fn) { setTimeout(fn, 0); }
  };
  if (typeof globalThis !== 'undefined') globalThis.process = process;
  if (typeof window !== 'undefined') window.process = process;
  if (typeof self !== 'undefined') self.process = process;
}

// Polyfill para 'Buffer' (caso necessário)
if (typeof Buffer === 'undefined') {
  var Buffer = {
    isBuffer: function() { return false; },
    from: function() { return []; },
    alloc: function() { return []; }
  };
  if (typeof globalThis !== 'undefined') globalThis.Buffer = Buffer;
  if (typeof window !== 'undefined') window.Buffer = Buffer;
  if (typeof self !== 'undefined') self.Buffer = Buffer;
}
