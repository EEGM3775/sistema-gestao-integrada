import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { ChunkService } from '../../projects/services/chunk.service';

@Component({
    selector: 'app-dashboard-layout',
    imports: [CommonModule, RouterOutlet],
    template: `
    <div class="app-layout">

      <!-- Main Content -->
      <div class="main-container">
        <!-- Header -->
        <header class="header">
          <div class="header-left">
            <div class="search-container">
              <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/>
                <line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <input type="text" placeholder="Buscar projetos, mapas, relatórios..." class="search-input"/>
              <span class="search-shortcut">⌘K</span>
            </div>
          </div>

          <div class="header-right">
            <button class="header-btn" title="Notificações">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
              </svg>
              @if (chunkService.failedChunksCount() > 0) {
                <span class="notification-badge">{{ chunkService.failedChunksCount() }}</span>
              }
            </button>

            <button class="header-btn" title="Upload">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </button>

            <div class="user-menu" (click)="toggleUserMenu()">
              <div class="user-avatar">
                {{ getUserInitials() }}
              </div>
              <div class="user-info">
                <span class="user-name">{{ authService.currentUser()?.username || 'Usuário' }}</span>
                <span class="user-role">Administrador</span>
              </div>
              <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>

              <div class="user-dropdown" *ngIf="userMenuOpen()">
                <a class="dropdown-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                  </svg>
                  Meu Perfil
                </a>
                <a class="dropdown-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                  </svg>
                  Configurações
                </a>
                <div class="dropdown-divider"></div>
                <a class="dropdown-item text-danger" (click)="logout()">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                    <polyline points="16 17 21 12 16 7"/>
                    <line x1="21" y1="12" x2="9" y2="12"/>
                  </svg>
                  Sair
                </a>
              </div>
            </div>
          </div>
        </header>

        <!-- Content Area -->
        <main class="main-content">
          <router-outlet></router-outlet>
        </main>
      </div>
    </div>
  `,
    styles: [`
    .app-layout {
      display: flex;
      min-height: 100vh;
      background: var(--color-bg);
    }

    /* Main Container */
    .main-container {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }

    /* Header */
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: var(--spacing-sm) var(--spacing-lg);
      background: var(--color-bg-white);
      border-bottom: 1px solid var(--color-border);
      position: sticky;
      top: 0;
      z-index: var(--z-sticky);
      height: var(--header-height);
    }

    .header-left {
      flex: 1;
      max-width: 600px;
    }

    .search-container {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
      padding: var(--spacing-sm) var(--spacing-md);
      background: var(--color-bg);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-full);
      transition: all var(--transition-fast);
    }

    .search-container:focus-within {
      border-color: var(--color-primary);
      box-shadow: 0 0 0 3px var(--color-primary-bg);
    }

    .search-icon {
      width: 18px;
      height: 18px;
      color: var(--color-text-muted);
      flex-shrink: 0;
    }

    .search-input {
      flex: 1;
      border: none;
      background: transparent;
      font-size: var(--font-size-sm);
      color: var(--color-text);
      outline: none;
    }

    .search-input::placeholder {
      color: var(--color-text-muted);
    }

    .search-shortcut {
      padding: 2px 6px;
      background: var(--color-bg-white);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-sm);
      font-size: var(--font-size-xs);
      color: var(--color-text-muted);
    }

    .header-right {
      display: flex;
      align-items: center;
      gap: var(--spacing-md);
    }

    .header-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 40px;
      height: 40px;
      background: transparent;
      border: none;
      border-radius: var(--radius-md);
      color: var(--color-text-secondary);
      cursor: pointer;
      position: relative;
      transition: all var(--transition-fast);
    }

    .header-btn:hover {
      background: var(--color-bg-hover);
      color: var(--color-text);
    }

    .header-btn svg {
      width: 20px;
      height: 20px;
    }

    .notification-badge {
      position: absolute;
      top: 6px;
      right: 6px;
      width: 16px;
      height: 16px;
      background: var(--color-danger);
      color: white;
      font-size: 10px;
      font-weight: 600;
      border-radius: var(--radius-full);
      display: flex;
      align-items: center;
      justify-content: center;
    }

    /* User Menu */
    .user-menu {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
      padding: var(--spacing-xs) var(--spacing-sm);
      border-radius: var(--radius-md);
      cursor: pointer;
      position: relative;
      transition: all var(--transition-fast);
    }

    .user-menu:hover {
      background: var(--color-bg-hover);
    }

    .user-avatar {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
      color: white;
      border-radius: var(--radius-full);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 600;
      font-size: var(--font-size-sm);
    }

    .user-info {
      display: flex;
      flex-direction: column;
    }

    .user-name {
      font-size: var(--font-size-sm);
      font-weight: 500;
      color: var(--color-text);
    }

    .user-role {
      font-size: var(--font-size-xs);
      color: var(--color-text-muted);
    }

    .chevron {
      width: 16px;
      height: 16px;
      color: var(--color-text-muted);
    }

    .user-dropdown {
      position: absolute;
      top: 100%;
      right: 0;
      margin-top: var(--spacing-xs);
      min-width: 200px;
      background: var(--color-bg-white);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      box-shadow: var(--shadow-lg);
      padding: var(--spacing-xs) 0;
      z-index: var(--z-dropdown);
      animation: slideDown var(--transition-fast);
    }

    .dropdown-item {
      display: flex;
      align-items: center;
      gap: var(--spacing-sm);
      padding: var(--spacing-sm) var(--spacing-md);
      font-size: var(--font-size-sm);
      color: var(--color-text);
      cursor: pointer;
      transition: background var(--transition-fast);
    }

    .dropdown-item:hover {
      background: var(--color-bg-hover);
    }

    .dropdown-item svg {
      width: 16px;
      height: 16px;
    }

    .dropdown-item.text-danger {
      color: var(--color-danger);
    }

    .dropdown-divider {
      height: 1px;
      margin: var(--spacing-xs) 0;
      background: var(--color-border);
    }

    /* Main Content */
    .main-content {
      flex: 1;
      padding: var(--spacing-lg);
      overflow-y: auto;
    }

    /* Responsive */
    @media (max-width: 768px) {
      .sidebar {
        transform: translateX(-100%);
      }

      .sidebar.open {
        transform: translateX(0);
      }

      .main-container {
        margin-left: 0;
      }

      .search-shortcut {
        display: none;
      }

      .user-info {
        display: none;
      }
    }
  `]
})
export class DashboardLayoutComponent {
  userMenuOpen = signal(false);
  readonly chunkService = inject(ChunkService);

  constructor(public authService: AuthService) {}

  toggleUserMenu(): void {
    this.userMenuOpen.update(v => !v);
  }

  getUserInitials(): string {
    const username = this.authService.currentUser()?.username || 'U';
    return username.substring(0, 2).toUpperCase();
  }

  logout(): void {
    this.authService.logout();
  }
}
