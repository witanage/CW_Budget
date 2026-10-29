// Show loading spinner
function showLoading() {
document.querySelector('.loading-spinner').classList.add('active');
}

// Hide loading spinner
function hideLoading() {
document.querySelector('.loading-spinner').classList.remove('active');
}

// Show toast notification
function showToast(message, type = 'info') {
const toastHtml = `
<div class="toast align-items-center text-white bg-${type} border-0" role="alert">
<div class="d-flex">
<div class="toast-body">
${message}
</div>
<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
</div>
</div>
`;

const toastContainer = document.querySelector('.toast-container');
toastContainer.insertAdjacentHTML('beforeend', toastHtml);

const toastElement = toastContainer.lastElementChild;
const toast = new bootstrap.Toast(toastElement, { autohide: true, delay: 3000 });
toast.show();

toastElement.addEventListener('hidden.bs.toast', () => {
toastElement.remove();
});
}

// Format currency (Sri Lankan Rupees)
function formatCurrency(amount) {
if (amount == null || isNaN(amount)) return 'රු 0.00';
return 'රු ' + parseFloat(amount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
}

// Format date
function formatDate(dateString) {
    if (!dateString) return '';
    
    // MySQL datetime format: "2026-04-23 21:05:30"
    // Parse as local time by replacing space with 'T'
    const isoString = dateString.replace(' ', 'T');
    const date = new Date(isoString);
    
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}

// Show confirmation modal (replacement for confirm())
function showConfirmModal(title, message, onConfirm, confirmBtnText = 'Confirm', confirmBtnClass = 'btn-danger') {
const modal = document.getElementById('confirmModal');
const modalTitle = document.getElementById('confirmModalTitle');
const modalMessage = document.getElementById('confirmModalMessage');
const confirmBtn = document.getElementById('confirmModalBtn');

// Set content
modalTitle.textContent = title;
modalMessage.innerHTML = message;  // Use innerHTML to support HTML content
confirmBtn.textContent = confirmBtnText;

// Set button class
confirmBtn.className = `btn ${confirmBtnClass}`;

// Remove previous event listeners
const newConfirmBtn = confirmBtn.cloneNode(true);
confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

// Add new event listener
document.getElementById('confirmModalBtn').addEventListener('click', function() {
const bootstrapModal = bootstrap.Modal.getInstance(modal);
bootstrapModal.hide();
if (onConfirm) onConfirm();
});

// Show modal
const bootstrapModal = new bootstrap.Modal(modal);
bootstrapModal.show();
}

// Theme Toggle Functions
var THEME_SVG_ATTRS = 'viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
var THEME_MOON = `<svg ${THEME_SVG_ATTRS}><path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10Z"></path></svg>`;
var THEME_SUN = `<svg ${THEME_SVG_ATTRS}><circle cx="12" cy="12" r="4"></circle><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"></path></svg>`;

function applyTheme(theme) {
document.documentElement.setAttribute('data-theme', theme);
localStorage.setItem('theme', theme);
updateThemeButton(theme);
document.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
}

function toggleTheme(event) {
const newTheme = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const btn = event && event.currentTarget;

if (!document.startViewTransition || reduce || !btn) {
applyTheme(newTheme);
return;
}

const rect = btn.getBoundingClientRect();
const x = rect.left + rect.width / 2;
const y = rect.top + rect.height / 2;
const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
const transition = document.startViewTransition(() => applyTheme(newTheme));
transition.ready.then(() => {
document.documentElement.animate(
{ clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
{ duration: 600, easing: 'ease-in-out', pseudoElement: '::view-transition-new(root)' }
);
});
}

function updateThemeButton(theme) {
const label = theme === 'light' ? 'Switch to dark' : 'Switch to light';
document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
btn.innerHTML = theme === 'light' ? THEME_MOON : THEME_SUN;
btn.setAttribute('aria-label', label);
btn.setAttribute('title', label);
});
}

if (!window.__themeToggleBound) {
window.__themeToggleBound = true;
document.addEventListener('click', function(e) {
const btn = e.target.closest('[data-theme-toggle]');
if (btn) toggleTheme({ currentTarget: btn });
});
}

// Change Password functionality
const savePasswordBtn = document.getElementById('savePasswordBtn');
if (savePasswordBtn) {
savePasswordBtn.addEventListener('click', function() {
const currentPassword = document.getElementById('currentPassword').value;
const newPassword = document.getElementById('newPassword').value;
const confirmPassword = document.getElementById('confirmPassword').value;

// Validation
if (!currentPassword || !newPassword || !confirmPassword) {
showToast('All fields are required', 'warning');
return;
}

if (newPassword.length < 6) {
showToast('New password must be at least 6 characters long', 'warning');
return;
}

if (newPassword !== confirmPassword) {
showToast('New passwords do not match', 'warning');
return;
}

// Send request to change password
showLoading();
fetch('/api/change-password', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({
current_password: currentPassword,
new_password: newPassword
})
})
.then(response => response.json())
.then(data => {
hideLoading();
if (data.error) {
showToast(data.error, 'danger');
} else {
showToast(data.message, 'success');
// Close modal
const modal = bootstrap.Modal.getInstance(document.getElementById('changePasswordModal'));
modal.hide();
// Reset form
document.getElementById('changePasswordForm').reset();
}
})
.catch(error => {
hideLoading();
showToast('Error changing password', 'danger');
console.error('Error:', error);
});
});
}

// Default Page Preference functionality
const saveDefaultPageBtn = document.getElementById('saveDefaultPageBtn');
const defaultPageModal = document.getElementById('defaultPageModal');
const defaultPageSelect = document.getElementById('defaultPageSelect');
const defaultCurrencySelect = document.getElementById('defaultCurrencySelect');

if (saveDefaultPageBtn && defaultPageSelect && defaultCurrencySelect) {
    // Load current preference when modal is shown
    if (defaultPageModal) {
        defaultPageModal.addEventListener('show.bs.modal', async function() {
            try {
                const response = await fetch('/api/user-preferences');
                if (response.ok) {
                    const data = await response.json();
                    defaultPageSelect.value = data.default_page || 'transactions';
                    defaultCurrencySelect.value = data.default_currency || 'USD';
                }
            } catch (error) {
                console.error('Error loading preferences:', error);
            }
        });
    }

    // Save preference
    saveDefaultPageBtn.addEventListener('click', async function() {
        const defaultPage = defaultPageSelect.value;
        const defaultCurrency = defaultCurrencySelect.value;

        if (!defaultPage || !defaultCurrency) {
            showToast('Please select both default page and currency', 'warning');
            return;
        }

        showLoading();
        try {
            const response = await fetch('/api/user-preferences', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    default_page: defaultPage,
                    default_currency: defaultCurrency
                })
            });

            const data = await response.json();
            hideLoading();

            if (response.ok) {
                showToast(data.message, 'success');
                // Store currency preference in localStorage for immediate use
                localStorage.setItem('defaultCurrency', defaultCurrency);

                // Reload sidebar widgets if on dashboard to update exchange rate widget
                if (typeof loadSidebarWidgets === 'function') {
                    loadSidebarWidgets();
                }

                // Close modal
                const modal = bootstrap.Modal.getInstance(defaultPageModal);
                modal.hide();
            } else {
                showToast(data.error || 'Failed to update preference', 'danger');
            }
        } catch (error) {
            hideLoading();
            showToast('Error updating preference', 'danger');
            console.error('Error:', error);
        }
    });
}

// ========================================
// MFA Settings Management
// ========================================

// Load MFA status when modal is shown
const mfaSettingsModal = document.getElementById('mfaSettingsModal');
if (mfaSettingsModal) {
    mfaSettingsModal.addEventListener('show.bs.modal', async function() {
        await loadMfaStatus();
    });
}

async function loadMfaStatus() {
    const statusContainer = document.getElementById('mfaStatusContainer');
    const disabledState = document.getElementById('mfaDisabledState');
    const enabledState = document.getElementById('mfaEnabledState');

    try {
        const response = await fetch('/api/mfa/status');
        const data = await response.json();

        statusContainer.classList.add('d-none');

        if (data.mfa_enabled) {
            disabledState.classList.add('d-none');
            enabledState.classList.remove('d-none');

            if (data.mfa_enabled_at) {
                const enabledDate = new Date(data.mfa_enabled_at);
                document.getElementById('mfaEnabledDate').textContent = enabledDate.toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                });
            }
        } else {
            enabledState.classList.add('d-none');
            disabledState.classList.remove('d-none');
        }
    } catch (error) {
        console.error('Error loading MFA status:', error);
        statusContainer.innerHTML = '<div class="alert alert-danger">Failed to load MFA status</div>';
    }
}

// Disable MFA
const confirmDisableMfaBtn = document.getElementById('confirmDisableMfaBtn');
if (confirmDisableMfaBtn) {
    confirmDisableMfaBtn.addEventListener('click', async function() {
        const password = document.getElementById('disableMfaPassword').value;
        const spinner = document.getElementById('disableMfaSpinner');

        if (!password) {
            showToast('Password is required', 'warning');
            return;
        }

        this.disabled = true;
        spinner.classList.remove('d-none');

        try {
            const response = await fetch('/api/mfa/disable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: password })
            });

            const data = await response.json();

            if (response.ok) {
                showToast('MFA has been disabled', 'success');

                // Close both modals
                const disableModal = bootstrap.Modal.getInstance(document.getElementById('disableMfaModal'));
                const settingsModal = bootstrap.Modal.getInstance(document.getElementById('mfaSettingsModal'));

                disableModal.hide();
                document.getElementById('disableMfaForm').reset();

                // Reload MFA status
                await loadMfaStatus();
            } else {
                showToast(data.error || 'Failed to disable MFA', 'danger');
            }
        } catch (error) {
            console.error('Error disabling MFA:', error);
            showToast('Error disabling MFA', 'danger');
        } finally {
            this.disabled = false;
            spinner.classList.add('d-none');
        }
    });
}

// Regenerate backup codes
const confirmRegenerateBtn = document.getElementById('confirmRegenerateBtn');
if (confirmRegenerateBtn) {
    confirmRegenerateBtn.addEventListener('click', async function() {
        const password = document.getElementById('regeneratePassword').value;
        const spinner = document.getElementById('regenerateSpinner');
        const formContainer = document.getElementById('regenerateFormContainer');
        const codesContainer = document.getElementById('newBackupCodesContainer');

        if (!password) {
            showToast('Password is required', 'warning');
            return;
        }

        this.disabled = true;
        spinner.classList.remove('d-none');

        try {
            const response = await fetch('/api/mfa/regenerate-backup-codes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: password })
            });

            const data = await response.json();

            if (response.ok) {
                showToast('Backup codes regenerated successfully', 'success');

                // Display new codes
                const codesList = document.getElementById('newBackupCodesList');
                let html = '<div class="row g-2">';
                data.backup_codes.forEach((code, index) => {
                    html += `
                        <div class="col-6">
                            <div class="alert alert-secondary mb-0 py-2">
                                <strong>${index + 1}.</strong> <code>${code}</code>
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
                codesList.innerHTML = html;

                // Show codes, hide form
                formContainer.classList.add('d-none');
                codesContainer.classList.remove('d-none');
                this.classList.add('d-none');

                // Store codes for copying
                window.currentBackupCodes = data.backup_codes;
            } else {
                showToast(data.error || 'Failed to regenerate backup codes', 'danger');
            }
        } catch (error) {
            console.error('Error regenerating backup codes:', error);
            showToast('Error regenerating backup codes', 'danger');
        } finally {
            this.disabled = false;
            spinner.classList.add('d-none');
        }
    });
}

// Copy new backup codes
const copyNewBackupCodesBtn = document.getElementById('copyNewBackupCodesBtn');
if (copyNewBackupCodesBtn) {
    copyNewBackupCodesBtn.addEventListener('click', function() {
        if (!window.currentBackupCodes) {
            showToast('No codes to copy', 'warning');
            return;
        }

        const codesText = window.currentBackupCodes.join('\n');

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(codesText)
                .then(() => {
                    showToast('Backup codes copied to clipboard', 'success');
                    this.innerHTML = '<i class="fas fa-check me-2"></i>Copied!';
                    setTimeout(() => {
                        this.innerHTML = '<i class="fas fa-copy me-2"></i>Copy Backup Codes';
                    }, 2000);
                })
                .catch(err => {
                    console.error('Failed to copy:', err);
                    showToast('Failed to copy codes', 'danger');
                });
        } else {
            // Fallback
            const textarea = document.createElement('textarea');
            textarea.value = codesText;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                showToast('Backup codes copied to clipboard', 'success');
            } catch (err) {
                showToast('Failed to copy codes', 'danger');
            }
            document.body.removeChild(textarea);
        }
    });
}

// Reset regenerate backup codes modal when hidden
const regenerateBackupCodesModal = document.getElementById('regenerateBackupCodesModal');
if (regenerateBackupCodesModal) {
    regenerateBackupCodesModal.addEventListener('hidden.bs.modal', function() {
        document.getElementById('regenerateFormContainer').classList.remove('d-none');
        document.getElementById('newBackupCodesContainer').classList.add('d-none');
        document.getElementById('regenerateBackupCodesForm').reset();
        document.getElementById('confirmRegenerateBtn').classList.remove('d-none');
        window.currentBackupCodes = null;
    });
}

// Reset disable MFA modal when hidden
const disableMfaModal = document.getElementById('disableMfaModal');
if (disableMfaModal) {
    disableMfaModal.addEventListener('hidden.bs.modal', function() {
        document.getElementById('disableMfaForm').reset();
    });
}

// Initialize theme on page load
(function initTheme() {
    // Check for saved theme preference or default to 'dark'
    const savedTheme = localStorage.getItem('theme') || 'dark';

    // Set the theme
    document.documentElement.setAttribute('data-theme', savedTheme);

    updateThemeButton(savedTheme);
})();

// Initialize Bootstrap dropdowns properly
document.addEventListener('DOMContentLoaded', function() {
// Let Bootstrap handle dropdowns automatically via data-bs-toggle
// No manual intervention needed - Bootstrap 5 handles it
});
