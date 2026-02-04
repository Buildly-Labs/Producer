/**
 * ProducerForge UI Interactions
 * Vanilla JS module for theme toggle, dropdowns, modals, and toasts
 */

(function() {
  'use strict';

  // ============================================================================
  // THEME TOGGLE
  // ============================================================================

  const ThemeManager = {
    STORAGE_KEY: 'producerforge-theme',
    
    init() {
      // Apply saved theme on load
      const savedTheme = localStorage.getItem(this.STORAGE_KEY) || 'dark';
      this.setTheme(savedTheme);
      
      // Bind toggle buttons (both data-attribute and ID-based)
      document.querySelectorAll('[data-theme-toggle], #theme-toggle').forEach(btn => {
        btn.addEventListener('click', () => this.toggle());
      });
    },
    
    setTheme(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem(this.STORAGE_KEY, theme);
    },
    
    toggle() {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      this.setTheme(next);
    },
    
    get current() {
      return document.documentElement.getAttribute('data-theme') || 'dark';
    }
  };

  // ============================================================================
  // DROPDOWN
  // ============================================================================

  const DropdownManager = {
    init() {
      // Toggle dropdown on trigger click
      document.querySelectorAll('[data-dropdown-trigger]').forEach(trigger => {
        trigger.addEventListener('click', (e) => {
          e.stopPropagation();
          const dropdown = trigger.closest('.dropdown');
          this.toggle(dropdown);
        });
      });
      
      // Close on click outside
      document.addEventListener('click', (e) => {
        if (!e.target.closest('.dropdown')) {
          this.closeAll();
        }
      });
      
      // Close on Escape
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          this.closeAll();
        }
      });
    },
    
    toggle(dropdown) {
      const isOpen = dropdown.classList.contains('open');
      this.closeAll();
      if (!isOpen) {
        dropdown.classList.add('open');
        // Focus first menu item for accessibility
        const firstItem = dropdown.querySelector('.dropdown-item');
        if (firstItem) firstItem.focus();
      }
    },
    
    closeAll() {
      document.querySelectorAll('.dropdown.open').forEach(d => {
        d.classList.remove('open');
      });
    }
  };

  // ============================================================================
  // MODAL
  // ============================================================================

  const ModalManager = {
    init() {
      // Open modal triggers
      document.querySelectorAll('[data-modal-open]').forEach(trigger => {
        trigger.addEventListener('click', () => {
          const modalId = trigger.getAttribute('data-modal-open');
          this.open(modalId);
        });
      });
      
      // Close modal triggers
      document.querySelectorAll('[data-modal-close]').forEach(trigger => {
        trigger.addEventListener('click', () => {
          const modal = trigger.closest('.modal-backdrop');
          if (modal) this.close(modal.id);
        });
      });
      
      // Close on backdrop click
      document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
        backdrop.addEventListener('click', (e) => {
          if (e.target === backdrop) {
            this.close(backdrop.id);
          }
        });
      });
      
      // Close on Escape
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          const openModal = document.querySelector('.modal-backdrop.open');
          if (openModal) this.close(openModal.id);
        }
      });
    },
    
    open(modalId) {
      const modal = document.getElementById(modalId);
      if (!modal) return;
      
      modal.classList.add('open');
      document.body.style.overflow = 'hidden';
      
      // Focus first focusable element
      const focusable = modal.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (focusable) focusable.focus();
      
      // Trap focus within modal
      this.trapFocus(modal);
    },
    
    close(modalId) {
      const modal = document.getElementById(modalId);
      if (!modal) return;
      
      modal.classList.remove('open');
      document.body.style.overflow = '';
    },
    
    trapFocus(modal) {
      const focusableElements = modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      
      modal.addEventListener('keydown', (e) => {
        if (e.key !== 'Tab') return;
        
        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            lastElement.focus();
            e.preventDefault();
          }
        } else {
          if (document.activeElement === lastElement) {
            firstElement.focus();
            e.preventDefault();
          }
        }
      });
    }
  };

  // ============================================================================
  // TOAST NOTIFICATIONS
  // ============================================================================

  const ToastManager = {
    container: null,
    
    init() {
      // Create container if it doesn't exist
      if (!document.querySelector('.toast-container')) {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        this.container.setAttribute('aria-live', 'polite');
        this.container.setAttribute('aria-atomic', 'true');
        document.body.appendChild(this.container);
      } else {
        this.container = document.querySelector('.toast-container');
      }
    },
    
    show(options = {}) {
      const {
        type = 'info',
        title = '',
        message = '',
        duration = 5000
      } = options;
      
      const toast = document.createElement('div');
      toast.className = `toast ${type}`;
      toast.innerHTML = `
        <span class="toast-icon">
          ${this.getIcon(type)}
        </span>
        <div class="toast-content">
          ${title ? `<div class="toast-title">${title}</div>` : ''}
          <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close" aria-label="Dismiss">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      `;
      
      // Close button handler
      toast.querySelector('.toast-close').addEventListener('click', () => {
        this.dismiss(toast);
      });
      
      this.container.appendChild(toast);
      
      // Auto dismiss
      if (duration > 0) {
        setTimeout(() => this.dismiss(toast), duration);
      }
      
      return toast;
    },
    
    dismiss(toast) {
      toast.classList.add('removing');
      setTimeout(() => toast.remove(), 200);
    },
    
    getIcon(type) {
      const icons = {
        success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
      };
      return icons[type] || icons.info;
    },
    
    success(message, title = 'Success') {
      return this.show({ type: 'success', title, message });
    },
    
    error(message, title = 'Error') {
      return this.show({ type: 'error', title, message });
    },
    
    warning(message, title = 'Warning') {
      return this.show({ type: 'warning', title, message });
    },
    
    info(message, title = '') {
      return this.show({ type: 'info', title, message });
    }
  };

  // ============================================================================
  // SIDEBAR
  // ============================================================================

  const SidebarManager = {
    init() {
      const sidebar = document.querySelector('.app-sidebar');
      const overlay = document.querySelector('.sidebar-overlay');
      const toggleBtns = document.querySelectorAll('[data-sidebar-toggle]');
      
      if (!sidebar) return;
      
      toggleBtns.forEach(btn => {
        btn.addEventListener('click', () => this.toggle());
      });
      
      if (overlay) {
        overlay.addEventListener('click', () => this.close());
      }
      
      // Close on Escape (mobile)
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar.classList.contains('open')) {
          this.close();
        }
      });
    },
    
    toggle() {
      const sidebar = document.querySelector('.app-sidebar');
      const overlay = document.querySelector('.sidebar-overlay');
      
      sidebar.classList.toggle('open');
      if (overlay) overlay.classList.toggle('open');
    },
    
    close() {
      const sidebar = document.querySelector('.app-sidebar');
      const overlay = document.querySelector('.sidebar-overlay');
      
      sidebar.classList.remove('open');
      if (overlay) overlay.classList.remove('open');
    }
  };

  // ============================================================================
  // INITIALIZE
  // ============================================================================

  function init() {
    ThemeManager.init();
    DropdownManager.init();
    ModalManager.init();
    ToastManager.init();
    SidebarManager.init();
    
    // Expose to global scope for manual usage
    window.ProducerForge = {
      theme: ThemeManager,
      dropdown: DropdownManager,
      modal: ModalManager,
      toast: ToastManager,
      sidebar: SidebarManager
    };
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
