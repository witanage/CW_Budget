let currentDeleteUserId = null;

// Load users on page load
document.addEventListener('DOMContentLoaded', function() {
loadUsers();
loadAuditLogs();
});

// Load all users
async function loadUsers() {
try {
const response = await fetch('/api/admin/users');
const users = await response.json();

if (!response.ok) {
throw new Error(users.error || 'Failed to load users');
}

const tbody = document.getElementById('usersTableBody');
tbody.innerHTML = '';

users.forEach(user => {
const row = document.createElement('tr');
row.style.background = 'var(--table-bg)';

const statusBadge = user.is_active
? '<span class="badge bg-success">Active</span>'
: '<span class="badge bg-danger">Inactive</span>';

const roleBadge = user.is_admin
? '<span class="badge bg-primary">Admin</span>'
: '<span class="badge bg-secondary">User</span>';

const lastLogin = user.last_login
? new Date(user.last_login).toLocaleString()
: '<span class="text-muted">Never</span>';

const created = user.created_at
? new Date(user.created_at).toLocaleString()
: '<span class="text-muted">N/A</span>';

row.innerHTML = `
<td>${user.id}</td>
<td><strong>${user.username}</strong></td>
<td>${user.email}</td>
<td>${statusBadge}</td>
<td>${roleBadge}</td>
<td>${lastLogin}</td>
<td>${created}</td>
<td>${user.monthly_records_count || 0}</td>
<td>${user.transactions_count || 0}</td>
<td>
<div class="btn-group btn-group-sm" role="group">
<button class="btn ${user.is_active ? 'btn-warning' : 'btn-success'}"
onclick="toggleUserActive(${user.id}, '${user.username}')"
title="${user.is_active ? 'Deactivate' : 'Activate'} user">
<i class="fas fa-${user.is_active ? 'ban' : 'check'}"></i>
</button>
<button class="btn ${user.is_admin ? 'btn-secondary' : 'btn-primary'}"
onclick="toggleUserAdmin(${user.id}, '${user.username}')"
title="${user.is_admin ? 'Revoke' : 'Grant'} admin">
<i class="fas fa-user-shield"></i>
</button>
<button class="btn btn-danger"
onclick="showDeleteModal(${user.id}, '${user.username}')"
title="Delete user">
<i class="fas fa-trash"></i>
</button>
</div>
</td>
`;
tbody.appendChild(row);
});

} catch (error) {
console.error('Error loading users:', error);
showAlert('Error loading users: ' + error.message, 'danger');
}
}

// Toggle user active status
async function toggleUserActive(userId, username) {
if (!confirm(`Are you sure you want to ${username}'s account status?`)) {
return;
}

try {
const response = await fetch(`/api/admin/users/${userId}/toggle-active`, {
method: 'POST',
headers: {
'Content-Type': 'application/json'
}
});

const data = await response.json();

if (!response.ok) {
throw new Error(data.error || 'Failed to update user');
}

showAlert(data.message, 'success');
loadUsers();
loadAuditLogs();

} catch (error) {
console.error('Error toggling user active status:', error);
showAlert('Error: ' + error.message, 'danger');
}
}

// Toggle user admin status
async function toggleUserAdmin(userId, username) {
if (!confirm(`Are you sure you want to modify ${username}'s admin privileges?`)) {
return;
}

try {
const response = await fetch(`/api/admin/users/${userId}/toggle-admin`, {
method: 'POST',
headers: {
'Content-Type': 'application/json'
}
});

const data = await response.json();

if (!response.ok) {
throw new Error(data.error || 'Failed to update user');
}

showAlert(data.message, 'success');
loadUsers();
loadAuditLogs();

} catch (error) {
console.error('Error toggling user admin status:', error);
showAlert('Error: ' + error.message, 'danger');
}
}

// Show delete confirmation modal
function showDeleteModal(userId, username) {
currentDeleteUserId = userId;
document.getElementById('deleteUsername').textContent = username;
const modal = new bootstrap.Modal(document.getElementById('confirmDeleteModal'));
modal.show();
}

// Confirm delete user
document.getElementById('confirmDeleteBtn').addEventListener('click', async function() {
if (!currentDeleteUserId) return;

try {
const response = await fetch(`/api/admin/users/${currentDeleteUserId}`, {
method: 'DELETE'
});

const data = await response.json();

if (!response.ok) {
throw new Error(data.error || 'Failed to delete user');
}

showAlert(data.message, 'success');

// Close modal
const modal = bootstrap.Modal.getInstance(document.getElementById('confirmDeleteModal'));
modal.hide();

// Reload data
loadUsers();
loadAuditLogs();

currentDeleteUserId = null;

} catch (error) {
console.error('Error deleting user:', error);
showAlert('Error: ' + error.message, 'danger');
}
});

// Load audit logs
async function loadAuditLogs() {
try {
const response = await fetch('/api/admin/audit-logs?limit=50');
const logs = await response.json();

if (!response.ok) {
throw new Error(logs.error || 'Failed to load audit logs');
}

const tbody = document.getElementById('auditLogsTableBody');
tbody.innerHTML = '';

if (logs.length === 0) {
tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No audit logs found</td></tr>';
return;
}

logs.forEach(log => {
const row = document.createElement('tr');
row.style.background = 'var(--table-bg)';

const timestamp = new Date(log.created_at).toLocaleString();

row.innerHTML = `
<td>${timestamp}</td>
<td><strong>${log.admin_username}</strong></td>
<td><span class="badge bg-info">${log.action}</span></td>
<td>${log.target_username || '<span class="text-muted">N/A</span>'}</td>
<td>${log.details || ''}</td>
`;
tbody.appendChild(row);
});

} catch (error) {
console.error('Error loading audit logs:', error);
showAlert('Error loading audit logs: ' + error.message, 'danger');
}
}

// Show alert
function showAlert(message, type = 'info') {
const alertDiv = document.createElement('div');
alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3`;
alertDiv.style.zIndex = '9999';
alertDiv.innerHTML = `
${message}
<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
`;
document.body.appendChild(alertDiv);

setTimeout(() => {
alertDiv.remove();
}, 5000);
}
