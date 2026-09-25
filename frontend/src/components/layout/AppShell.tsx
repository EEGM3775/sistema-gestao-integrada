import React from 'react'
import { Outlet } from 'react-router-dom'
import AppSidebar from './AppSidebar'
import AppTopbar from './AppTopbar'
import Assistente, { AssistenteProvider } from '../assistente/Assistente'

/** O assistente envolve o shell inteiro, e não uma tela.
 *
 *  Duas razões. A chave que o liga mora na **barra de cima**, que é do shell, e
 *  a tela que publica a ajuda está dentro do `<Outlet>` — os dois precisam do
 *  mesmo contexto. E a promessa é de plataforma, não de módulo: qualquer tela
 *  que publique a ajuda dela passa a ter assistente sem tocar em nada daqui.
 */
const AppShell: React.FC = () => {
  return (
    <AssistenteProvider>
      <div className="flex h-screen overflow-hidden" style={{ background: 'var(--color-bg-alt)' }}>
        {/* Sidebar */}
        <AppSidebar />

        {/* Coluna direita */}
        <div className="flex flex-col flex-1 min-w-0">
          <AppTopbar />
          <main className="flex-1 overflow-y-auto">
            <Outlet />
          </main>
        </div>
      </div>
      {/* Fora da coluna: o cartão flutua sobre a tela e o painel do `?` é modal. */}
      <Assistente />
    </AssistenteProvider>
  )
}

export default AppShell
