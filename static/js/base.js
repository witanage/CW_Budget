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
if (amount == null || isNaN(amount)) return 'LKR 0.00';
return 'LKR ' + parseFloat(amount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
}

// Format date
function formatDate(dateString) {
const options = { year: 'numeric', month: 'short', day: 'numeric' };
return new Date(dateString).toLocaleDateString('en-US', options);
}

// Show confirmation modal (replacement for confirm())
function showConfirmModal(title, message, onConfirm, confirmBtnText = 'Confirm', confirmBtnClass = 'btn-danger') {
const modal = document.getElementById('confirmModal');
const modalTitle = document.getElementById('confirmModalTitle');
const modalMessage = document.getElementById('confirmModalMessage');
const confirmBtn = document.getElementById('confirmModalBtn');

// Set content
modalTitle.textContent = title;
modalMessage.textContent = message;
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
function toggleTheme() {
const currentTheme = document.documentElement.getAttribute('data-theme');
const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

// Set theme
document.documentElement.setAttribute('data-theme', newTheme);

// Save to localStorage
localStorage.setItem('theme', newTheme);

// Update button
updateThemeButton(newTheme);

// Show toast
showToast(`Switched to ${newTheme} theme`, 'success');
}

function updateThemeButton(theme) {
const themeIcon = document.getElementById('themeIcon');
const themeText = document.getElementById('themeText');

if (theme === 'dark') {
themeIcon.className = 'fas fa-sun me-2 theme-toggle-icon';
themeText.textContent = 'Light Theme';
} else {
themeIcon.className = 'fas fa-moon me-2 theme-toggle-icon';
themeText.textContent = 'Dark Theme';
}
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

// Initialize theme on page load
(function initTheme() {
// Check for saved theme preference or default to 'dark'
const savedTheme = localStorage.getItem('theme') || 'dark';

// Set the theme
document.documentElement.setAttribute('data-theme', savedTheme);

// Update button if it exists
if (document.getElementById('themeIcon')) {
updateThemeButton(savedTheme);
}
})();

// Fix dropdown menu behavior - prevent immediate closing
document.addEventListener('DOMContentLoaded', function() {
const userDropdown = document.getElementById('userDropdown');
if (userDropdown) {
// Prevent click event from bubbling and closing dropdown immediately
userDropdown.addEventListener('click', function(e) {
e.stopPropagation();
});

// Ensure dropdown menu items are clickable
const dropdownMenu = userDropdown.nextElementSibling;
if (dropdownMenu && dropdownMenu.classList.contains('dropdown-menu')) {
dropdownMenu.addEventListener('click', function(e) {
// Allow clicks on dropdown items (links) to work
// Only stop propagation for the menu container itself
if (e.target === this) {
e.stopPropagation();
}
});
}
}
});
