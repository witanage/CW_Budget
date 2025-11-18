// Loading overlay functions
function showLoading() {
const overlay = document.getElementById('loadingOverlay');
if (overlay) {
overlay.classList.add('show');
}
}

function hideLoading() {
const overlay = document.getElementById('loadingOverlay');
if (overlay) {
overlay.classList.remove('show');
}
}

// Format currency
function formatCurrency(amount) {
if (amount == null || isNaN(amount)) return '0.00';
return parseFloat(amount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
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

// Global variables
let paymentMethods = [];
let selectedTransactionIdForPayment = null;

// Load payment methods
function loadPaymentMethods() {
console.log('Starting to load payment methods...');
fetch('/api/payment-methods')
.then(response => {
console.log('Payment methods response status:', response.status);
if (!response.ok) {
throw new Error(`HTTP error! status: ${response.status}`);
}
return response.json();
})
.then(data => {
paymentMethods = data || [];
console.log('Payment methods loaded successfully:', paymentMethods.length, 'methods');
console.log('Payment methods data:', paymentMethods);
})
.catch(error => {
console.error('Error loading payment methods:', error);
console.error('Error details:', error.message);
paymentMethods = [];
showToast('Failed to load payment methods: ' + error.message, 'danger');
});
}

// Show payment method modal
function showPaymentMethodModal(transactionId, isPaidClick = false) {
selectedTransactionIdForPayment = transactionId;

const listContainer = document.getElementById('paymentMethodList');

// Update modal title based on context
const modalTitle = document.querySelector('#paymentMethodModal .modal-title');
if (modalTitle) {
modalTitle.textContent = isPaidClick ? 'Select Payment Method' : 'Mark as Done - Select Payment Method';
}

// If payment methods are not loaded, reload them
if (!paymentMethods || paymentMethods.length === 0) {
console.log('Payment methods empty, reloading...');
listContainer.innerHTML = '<div class="text-center" style="color: #ccc; padding: 20px;"><i class="fas fa-spinner fa-spin fa-2x mb-3"></i><p>Loading payment methods...</p></div>';

// Reload payment methods
fetch('/api/payment-methods')
.then(response => {
console.log('Reload payment methods response status:', response.status);
if (!response.ok) {
throw new Error(`HTTP error! status: ${response.status}`);
}
return response.json();
})
.then(data => {
paymentMethods = data || [];
console.log('Payment methods reloaded:', paymentMethods.length, 'methods');
populatePaymentMethodsList(listContainer, isPaidClick);
})
.catch(error => {
console.error('Error reloading payment methods:', error);
listContainer.innerHTML = '<p style="color: #dc3545; padding: 20px;">Failed to load payment methods. Please check your connection and try again.</p>';
});
} else {
populatePaymentMethodsList(listContainer, isPaidClick);
}

const modal = new bootstrap.Modal(document.getElementById('paymentMethodModal'));
modal.show();
}

// Populate payment methods list
function populatePaymentMethodsList(listContainer, isPaidClick) {
listContainer.innerHTML = '';

if (!paymentMethods || paymentMethods.length === 0) {
listContainer.innerHTML = '<p style="color: #ffffff; padding: 20px;">No payment methods available. Please add one in settings.</p>';
} else {
paymentMethods.forEach(method => {
const item = document.createElement('div');
item.className = 'list-group-item payment-method-list-item';
item.innerHTML = `
<span class="payment-method-color-indicator" style="background-color: ${method.color}; width: 30px; height: 30px; display: inline-block; border-radius: 5px;"></span>
<span style="flex: 1;">${method.name}</span>
`;
item.onclick = () => {
if (isPaidClick) {
markTransactionAsPaid(selectedTransactionIdForPayment, method.id);
} else {
markTransactionWithPaymentMethod(selectedTransactionIdForPayment, method.id);
}
};
listContainer.appendChild(item);
});
}
}

// Show transaction info modal
function showTransactionInfo(transaction) {
// Populate modal with transaction details
const descElement = document.getElementById('infoDescription');
const notesElement = document.getElementById('infoNotes');
const paidAtElement = document.getElementById('infoPaidAt');

// Set description
if (descElement) {
descElement.textContent = transaction.description || '-';
}

// Set notes
if (notesElement) {
notesElement.textContent = transaction.notes || '-';
}

// Set paid at date
if (paidAtElement) {
if (transaction.paid_at) {
// Format the date nicely
const date = new Date(transaction.paid_at);
const formattedDate = date.toLocaleString('en-US', {
year: 'numeric',
month: 'short',
day: 'numeric',
hour: '2-digit',
minute: '2-digit'
});
paidAtElement.textContent = formattedDate;
} else {
paidAtElement.textContent = '-';
}
}

// Show the modal
const modal = new bootstrap.Modal(document.getElementById('transactionInfoModal'));
modal.show();
}

// Mark transaction with payment method (marks as done)
function markTransactionWithPaymentMethod(transactionId, paymentMethodId) {
showLoading();

fetch(`/api/transactions/${transactionId}/mark-done`, {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ payment_method_id: paymentMethodId })
})
.then(response => response.json())
.then(result => {
hideLoading();
if (result.error) {
showToast(result.error, 'danger');
} else {
showToast('Transaction marked as done', 'success');
// Close modal
const modal = bootstrap.Modal.getInstance(document.getElementById('paymentMethodModal'));
if (modal) modal.hide();
// Reload transactions
loadTransactions();
}
})
.catch(error => {
hideLoading();
console.error('Error marking transaction as done:', error);
showToast('Error marking transaction as done', 'danger');
});
}

// Mark transaction as paid
function markTransactionAsPaid(transactionId, paymentMethodId) {
showLoading();

fetch(`/api/transactions/${transactionId}/mark-paid`, {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ payment_method_id: paymentMethodId })
})
.then(response => response.json())
.then(result => {
hideLoading();
if (result.error) {
showToast(result.error, 'danger');
} else {
showToast('Transaction marked as paid', 'success');
// Close modal
const modal = bootstrap.Modal.getInstance(document.getElementById('paymentMethodModal'));
if (modal) modal.hide();
// Reload transactions
loadTransactions();
}
})
.catch(error => {
hideLoading();
console.error('Error marking transaction as paid:', error);
showToast('Error marking transaction as paid', 'danger');
});
}

// Mark transaction as unpaid
function markTransactionAsUnpaid(transactionId) {
showLoading();

fetch(`/api/transactions/${transactionId}/mark-unpaid`, {
method: 'POST'
})
.then(response => response.json())
.then(result => {
hideLoading();
if (result.error) {
showToast(result.error, 'danger');
} else {
showToast('Transaction marked as unpaid', 'success');
loadTransactions();
}
})
.catch(error => {
hideLoading();
console.error('Error marking transaction as unpaid:', error);
showToast('Error marking transaction as unpaid', 'danger');
});
}

// Load categories
function loadCategories() {
return fetch('/api/categories')
.then(response => response.json())
.then(data => {
const select = document.getElementById('transCategory');
select.innerHTML = '<option value="">Select Category</option>';
data.forEach(cat => {
select.innerHTML += `<option value="${cat.id}">${cat.name} (${cat.type})</option>`;
});
return data;
})
.catch(error => {
console.error('Error loading categories:', error);
throw error;
});
}

function toggleNewCategoryForm() {
const form = document.getElementById('newCategoryForm');
if (form) {
if (form.style.display === 'none') {
showNewCategoryForm();
} else {
hideNewCategoryForm();
}
}
}

function showNewCategoryForm() {
const form = document.getElementById('newCategoryForm');
const message = document.getElementById('newCategoryMessage');

if (form) {
form.style.display = 'block';
// Clear previous values
document.getElementById('newCategoryName').value = '';
document.getElementById('newCategoryType').value = '';
if (message) {
message.style.display = 'none';
}
// Focus on name input
document.getElementById('newCategoryName').focus();
}
}

function hideNewCategoryForm() {
const form = document.getElementById('newCategoryForm');
if (form) {
form.style.display = 'none';
// Clear form
document.getElementById('newCategoryName').value = '';
document.getElementById('newCategoryType').value = '';
const message = document.getElementById('newCategoryMessage');
if (message) {
message.style.display = 'none';
}
}
}

function saveNewCategory() {
const nameInput = document.getElementById('newCategoryName');
const typeInput = document.getElementById('newCategoryType');
const message = document.getElementById('newCategoryMessage');
const saveBtn = document.getElementById('saveNewCategoryBtn');

const name = nameInput.value.trim();
const type = typeInput.value;

// Validate inputs
if (!name) {
showCategoryMessage('Please enter a category name', 'danger');
return;
}

if (!type) {
showCategoryMessage('Please select a category type', 'danger');
return;
}

// Disable button during save
saveBtn.disabled = true;
saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Saving...';

// Send to API
fetch('/api/categories', {
method: 'POST',
headers: {
'Content-Type': 'application/json'
},
body: JSON.stringify({
name: name,
type: type
})
})
.then(response => {
if (!response.ok) {
return response.json().then(err => {
throw new Error(err.error || 'Failed to create category');
});
}
return response.json();
})
.then(newCategory => {
// Success!
showCategoryMessage('Category created successfully!', 'success');

// Reload categories to update all dropdowns, then select the new category
loadCategories().then(() => {
// Hide form after a brief delay to show success message
setTimeout(() => {
hideNewCategoryForm();
}, 800);

// Select the newly created category in the dropdown
const transCategorySelect = document.getElementById('transCategory');
if (transCategorySelect) {
transCategorySelect.value = newCategory.id;
}
}).catch(error => {
console.error('Error reloading categories:', error);
});
})
.catch(error => {
console.error('Error creating category:', error);
showCategoryMessage(error.message || 'Failed to create category', 'danger');
})
.finally(() => {
// Re-enable button
saveBtn.disabled = false;
saveBtn.innerHTML = '<i class="fas fa-check me-1"></i>Save';
});
}

function showCategoryMessage(text, type) {
const message = document.getElementById('newCategoryMessage');
if (message) {
message.className = `alert alert-${type} mb-0`;
message.style.fontSize = '0.875rem';
message.style.padding = '0.5rem';
message.textContent = text;
message.style.display = 'block';
}
}

// Current month and year
let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1;

// Month names
const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
'July', 'August', 'September', 'October', 'November', 'December'];

// Update month display
function updateMonthDisplay() {
const display = document.getElementById('monthDisplay');
display.textContent = `${monthNames[currentMonth - 1]} ${currentYear}`;
}

// Navigate to previous month
function navigateToPreviousMonth() {
currentMonth--;
if (currentMonth < 1) {
currentMonth = 12;
currentYear--;
}
updateMonthDisplay();
loadTransactions();
}

// Navigate to next month
function navigateToNextMonth() {
currentMonth++;
if (currentMonth > 12) {
currentMonth = 1;
currentYear++;
}
updateMonthDisplay();
loadTransactions();
}

// Load transactions
function loadTransactions() {
showLoading();
fetch(`/api/transactions?year=${currentYear}&month=${currentMonth}`)
.then(response => response.json())
.then(data => {
displayTransactions(data);
hideLoading();
})
.catch(error => {
console.error('Error loading transactions:', error);
hideLoading();
});
}

// Display transactions
function displayTransactions(transactions) {
const tbody = document.getElementById('transactionsList');

if (!transactions || transactions.length === 0) {
tbody.innerHTML = `
<tr>
<td colspan="4">
<div class="no-transactions">
<i class="fas fa-receipt fa-3x mb-3"></i>
<p>No transactions yet</p>
</div>
</td>
</tr>
`;
return;
}

// Sort transactions by ID (oldest first) to calculate balance correctly
const sortedTransactions = [...transactions].sort((a, b) => a.id - b.id);

// Calculate balance for each transaction
let runningBalance = 0;
sortedTransactions.forEach(t => {
const debit = parseFloat(t.debit) || 0;
const credit = parseFloat(t.credit) || 0;
runningBalance += debit - credit;
t.calculatedBalance = runningBalance;
});

// Display transactions in reverse order (newest first)
tbody.innerHTML = '';
sortedTransactions.reverse().forEach(t => {
const row = document.createElement('tr');
row.className = 'swipe-container';

// Check payment status
const hasPaymentMethod = t.payment_method_id && t.payment_method_id !== null;
const isPaid = t.is_paid === true || t.is_paid === 1;
const isDone = t.is_done === true || t.is_done === 1;

if (hasPaymentMethod && t.payment_method_color) {
row.classList.add('transaction-highlighted');
}

// Determine done/undone button
const doneBtnClass = isDone ? 'swipe-action-undone' : 'swipe-action-done';
const doneBtnIcon = isDone ? 'fa-times-circle' : 'fa-check-circle';
const doneBtnAction = isDone ? 'undone' : 'done';

// Build the row with swipe-to-reveal structure
row.innerHTML = `
<td colspan="4" style="padding: 0;">
<div class="swipe-wrapper">
<div class="swipe-info-actions">
<button class="swipe-action-btn swipe-action-info" data-action="info" data-id="${t.id}">
<i class="fas fa-info-circle"></i>
</button>
</div>
<div class="swipe-actions">
<button class="swipe-action-btn ${doneBtnClass}" data-action="${doneBtnAction}" data-id="${t.id}" data-is-done="${isDone}">
<i class="fas ${doneBtnIcon}"></i>
</button>
<button class="swipe-action-btn swipe-action-edit" data-action="edit" data-id="${t.id}">
<i class="fas fa-edit"></i>
</button>
<button class="swipe-action-btn swipe-action-delete" data-action="delete" data-id="${t.id}">
<i class="fas fa-trash"></i>
</button>
</div>
<table class="swipe-content" style="width: 100%; border-collapse: collapse;">
<tr>
<td class="col-desc" data-transaction-id="${t.id}">${t.description || ''}</td>
<td class="col-debit text-success">${t.debit ? formatCurrency(t.debit) : '-'}</td>
<td class="col-credit text-danger">${t.credit ? formatCurrency(t.credit) : '-'}</td>
<td class="col-balance fw-bold">${formatCurrency(t.calculatedBalance)}</td>
</tr>
</table>
</div>
</td>
`;

// Store transaction data
row.dataset.transaction = JSON.stringify(t);

// Apply background color (desktop behavior: description cell only gets color if is_paid)
if (isDone && t.payment_method_color) {
const swipeContent = row.querySelector('.swipe-content');
const cells = swipeContent.querySelectorAll('td');
cells.forEach((cell, index) => {
// Apply to all cells except description (index 0)
if (index !== 0) {
cell.style.backgroundColor = t.payment_method_color;
} else {
// Apply to description cell only if is_paid is true
if (isPaid) {
cell.style.backgroundColor = t.payment_method_color;
}
}
});
}

// Initialize swipe functionality
initializeSwipe(row);

// Add click handler to description cell (same as desktop behavior)
const descCell = row.querySelector('.col-desc');
if (descCell) {
descCell.style.cursor = 'pointer';

// Set description text color based on payment status
// White for unpaid (is_paid = 0), current color for paid (is_paid = 1)
if (!isPaid) {
descCell.style.color = '#ffffff';
}

descCell.addEventListener('click', function(e) {
// Prevent click during swipe
if (row.classList.contains('swiped')) return;

if (isPaid) {
// If already paid, mark as unpaid
showConfirmModal(
'Mark as Unpaid',
'Remove payment method from this transaction?',
function() {
markTransactionAsUnpaid(t.id);
},
'Mark Unpaid',
'btn-warning'
);
} else {
// If not paid, show payment method modal to mark as paid
// Pass true to indicate this is a "paid" click (sets is_paid=TRUE)
showPaymentMethodModal(t.id, true);
}
});
}

// Add action button handlers
const editBtn = row.querySelector('[data-action="edit"]');
const doneBtn = row.querySelector('[data-action="done"]');
const undoneBtn = row.querySelector('[data-action="undone"]');
const deleteBtn = row.querySelector('[data-action="delete"]');
const infoBtn = row.querySelector('[data-action="info"]');

if (editBtn) {
editBtn.addEventListener('click', function() {
editTransaction(t.id);
});
}

if (doneBtn) {
doneBtn.addEventListener('click', function() {
// Show payment method modal to mark as done (same as desktop checkbox behavior)
showPaymentMethodModal(t.id, false);
});
}

if (undoneBtn) {
undoneBtn.addEventListener('click', function() {
// Mark transaction as undone (same as desktop checkbox behavior)
markTransactionAsUndone(t.id);
});
}

if (deleteBtn) {
deleteBtn.addEventListener('click', function() {
deleteTransaction(t.id);
});
}

if (infoBtn) {
infoBtn.addEventListener('click', function() {
showTransactionInfo(t);
});
}

tbody.appendChild(row);
});

// Scroll to top after loading transactions
const mobileContent = document.querySelector('.mobile-content');
if (mobileContent) {
mobileContent.scrollTop = 0;
}
}

// Mark transaction as undone
function markTransactionAsUndone(transactionId) {
showLoading();

fetch(`/api/transactions/${transactionId}/mark-undone`, {
method: 'POST'
})
.then(response => response.json())
.then(result => {
hideLoading();
if (result.error) {
showToast(result.error, 'danger');
} else {
showToast('Transaction marked as undone', 'success');
loadTransactions();
}
})
.catch(error => {
hideLoading();
console.error('Error marking transaction as undone:', error);
showToast('Error marking transaction as undone', 'danger');
});
}

// ===== REVAMPED SWIPE MANAGER =====
// Modern, event-delegation-based swipe system
// Fixes: memory leaks, mouse support, touch conflicts, better architecture

const SwipeManager = {
// Configuration
config: {
buttonWidth: 70,
buttonCount: 3,
infoButtonWidth: 70,
snapThreshold: 60,
velocityThreshold: 0.3,
get maxSwipe() {
return this.buttonWidth * this.buttonCount;
},
get maxSwipeRight() {
return this.infoButtonWidth;
}
},

// State
state: {
startX: 0,
currentX: 0,
startY: 0,
currentY: 0,
isDragging: false,
startTime: 0,
activeRow: null,
isTouch: false,
scrollBlocked: false,
swipeDirection: null  // 'left' or 'right'
},

// Initialize the swipe manager (call once)
init: function() {
const tbody = document.getElementById('transactionsList');
if (!tbody) return;

// Use event delegation - single listener for all rows
// Touch events
tbody.addEventListener('touchstart', this.handleStart.bind(this), { passive: false });
tbody.addEventListener('touchmove', this.handleMove.bind(this), { passive: false });
tbody.addEventListener('touchend', this.handleEnd.bind(this), { passive: false });

// Mouse events for desktop testing
tbody.addEventListener('mousedown', this.handleStart.bind(this), { passive: false });
tbody.addEventListener('mousemove', this.handleMove.bind(this), { passive: false });
tbody.addEventListener('mouseup', this.handleEnd.bind(this), { passive: false });
tbody.addEventListener('mouseleave', this.handleEnd.bind(this), { passive: false });

// Close swipe when clicking outside
document.addEventListener('click', this.handleOutsideClick.bind(this));
},

// Get coordinates from touch or mouse event
getCoords: function(e) {
if (e.touches && e.touches.length > 0) {
return {
x: e.touches[0].clientX,
y: e.touches[0].clientY
};
}
return {
x: e.clientX,
y: e.clientY
};
},

// Find the swipe container row from event target
findSwipeRow: function(target) {
return target.closest('.swipe-container');
},

// Handle start of swipe (touch/mouse down)
handleStart: function(e) {
const row = this.findSwipeRow(e.target);
if (!row) return;

// Don't swipe if clicking on action buttons
if (e.target.closest('.swipe-action-btn')) return;

const coords = this.getCoords(e);
this.state.startX = coords.x;
this.state.currentX = coords.x;
this.state.startY = coords.y;
this.state.currentY = coords.y;
this.state.isDragging = true;
this.state.startTime = Date.now();
this.state.activeRow = row;
this.state.isTouch = e.type.startsWith('touch');
this.state.scrollBlocked = false;

row.classList.add('swiping');

// Close other open swipes
this.closeAllSwipes(row);
},

// Handle swipe movement
handleMove: function(e) {
if (!this.state.isDragging || !this.state.activeRow) return;

const coords = this.getCoords(e);
this.state.currentX = coords.x;
this.state.currentY = coords.y;

const diffX = this.state.startX - this.state.currentX;
const diffY = Math.abs(this.state.startY - this.state.currentY);

// Detect horizontal vs vertical scroll
if (!this.state.scrollBlocked && Math.abs(diffX) > 10) {
// Horizontal swipe detected - block vertical scroll
if (Math.abs(diffX) > diffY * 1.5) {
this.state.scrollBlocked = true;
e.preventDefault(); // Prevent page scroll
// Determine swipe direction
this.state.swipeDirection = diffX > 0 ? 'left' : 'right';
}
}

if (this.state.scrollBlocked) {
const swipeContent = this.state.activeRow.querySelector('.swipe-content');
if (swipeContent) {
if (diffX > 0) {
// Left swipe - reveal action buttons on right
const swipeAmount = Math.min(diffX, this.config.maxSwipe);
swipeContent.style.transform = `translateX(-${swipeAmount}px)`;
} else if (diffX < 0) {
// Right swipe - reveal info button on left
const swipeAmount = Math.min(Math.abs(diffX), this.config.maxSwipeRight);
swipeContent.style.transform = `translateX(${swipeAmount}px)`;
}
}
}
},

// Handle end of swipe (touch/mouse up)
handleEnd: function(e) {
if (!this.state.isDragging || !this.state.activeRow) return;

const diffX = this.state.startX - this.state.currentX;
const duration = Date.now() - this.state.startTime;
const velocity = duration > 0 ? Math.abs(diffX) / duration : 0;

const row = this.state.activeRow;
const swipeContent = row.querySelector('.swipe-content');

row.classList.remove('swiping');

if (diffX > 0) {
// Left swipe - reveal action buttons
const shouldOpen = diffX > this.config.snapThreshold ||
(velocity > this.config.velocityThreshold && diffX > 20);

if (shouldOpen && swipeContent) {
// Open swipe - show all buttons
swipeContent.style.transform = `translateX(-${this.config.maxSwipe}px)`;
row.classList.add('swiped');
row.dataset.swipeOpen = 'left';
} else if (swipeContent) {
// Close swipe
this.closeSwipe(row);
}
} else if (diffX < 0) {
// Right swipe - reveal info button
const shouldOpen = Math.abs(diffX) > this.config.snapThreshold ||
(velocity > this.config.velocityThreshold && Math.abs(diffX) > 20);

if (shouldOpen && swipeContent) {
// Open swipe - show info button
swipeContent.style.transform = `translateX(${this.config.maxSwipeRight}px)`;
row.classList.add('swiped');
row.dataset.swipeOpen = 'right';
} else if (swipeContent) {
// Close swipe
this.closeSwipe(row);
}
} else if (swipeContent) {
// No movement - close
this.closeSwipe(row);
}

// Reset state
this.state.isDragging = false;
this.state.activeRow = null;
this.state.scrollBlocked = false;
this.state.swipeDirection = null;
},

// Handle clicks outside swiped rows
handleOutsideClick: function(e) {
// Don't close if clicking on action buttons
if (e.target.closest('.swipe-action-btn')) return;

const clickedRow = this.findSwipeRow(e.target);
const allRows = document.querySelectorAll('.swipe-container[data-swipe-open]');

allRows.forEach(row => {
// Close if clicking different row or clicking on swiped row content
if (row !== clickedRow || (row === clickedRow && row.dataset.swipeOpen)) {
this.closeSwipe(row);
}
});
},

// Close a specific swipe
closeSwipe: function(row) {
const swipeContent = row.querySelector('.swipe-content');
if (swipeContent) {
swipeContent.style.transform = 'translateX(0)';
row.classList.remove('swiped');
delete row.dataset.swipeOpen;
}
},

// Close all swipes except specified row
closeAllSwipes: function(exceptRow) {
const allRows = document.querySelectorAll('.swipe-container');
allRows.forEach(row => {
if (row !== exceptRow && row.classList.contains('swiped')) {
this.closeSwipe(row);
}
});
}
};

// Legacy function for compatibility (now a no-op)
function initializeSwipe(row) {
// No longer needed - SwipeManager uses event delegation
// This function is kept for compatibility but does nothing
}

// Legacy function for compatibility
function closeAllSwipes(exceptRow) {
SwipeManager.closeAllSwipes(exceptRow);
}

// Refresh transactions
function refreshTransactions() {
loadTransactions();
}

// Save transaction
function saveTransaction() {
// Check if this is an edit
const editId = document.getElementById('transactionForm').dataset.editId;
const isEdit = editId && editId !== '';

const description = document.getElementById('transDescription').value;
if (!description || description.trim() === '') {
showToast('Description is required', 'warning');
return;
}

const debitValue = document.getElementById('transDebit').value;
const creditValue = document.getElementById('transCredit').value;

let debit = null;
let credit = null;

if (debitValue && debitValue.trim() !== '') {
debit = parseFloat(debitValue);
}

if (creditValue && creditValue.trim() !== '') {
credit = parseFloat(creditValue);
}

const data = {
description: description,
category_id: document.getElementById('transCategory').value || null,
debit: debit,
credit: credit,
transaction_date: document.getElementById('transDate').value,
notes: document.getElementById('transNotes').value,
year: parseInt(currentYear),
month: parseInt(currentMonth)
};

const url = isEdit ? `/api/transactions/${editId}` : '/api/transactions';
const method = isEdit ? 'PUT' : 'POST';

showLoading();

fetch(url, {
method: method,
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify(data)
})
.then(response => response.json())
.then(result => {
hideLoading();
if (result.error) {
showToast(result.error, 'danger');
} else {
showToast(isEdit ? 'Transaction updated successfully' : 'Transaction saved successfully', 'success');

// Close modal
const modal = bootstrap.Modal.getInstance(document.getElementById('transactionModal'));
const modalElement = document.getElementById('transactionModal');

// Wait for modal to fully close before reloading transactions
// This prevents the modal closing animation from interfering with scroll-to-top
modalElement.addEventListener('hidden.bs.modal', function onModalHidden() {
// Remove this listener after it fires once
modalElement.removeEventListener('hidden.bs.modal', onModalHidden);

// Now reload transactions after modal is fully closed
loadTransactions();
});

modal.hide();

// Reset form
document.getElementById('transactionForm').reset();
document.getElementById('transactionForm').dataset.editId = '';
document.querySelector('#transactionModal .modal-title').textContent = 'Add Transaction';
document.getElementById('transDate').value = new Date().toISOString().split('T')[0];
}
})
.catch(error => {
hideLoading();
console.error('Error saving transaction:', error);
showToast('Error saving transaction', 'danger');
});
}

// Edit transaction
function editTransaction(id) {
// Find the transaction in the table
const tbody = document.getElementById('transactionsList');
const row = tbody.querySelector(`tr[data-transaction*='"id":${id}']`);

if (!row) {
showToast('Transaction not found', 'danger');
return;
}

const transaction = JSON.parse(row.dataset.transaction);

// Populate form
document.getElementById('transDescription').value = transaction.description || '';
document.getElementById('transCategory').value = transaction.category_id || '';
document.getElementById('transDebit').value = transaction.debit || '';
document.getElementById('transCredit').value = transaction.credit || '';
document.getElementById('transDate').value = transaction.transaction_date ? transaction.transaction_date.split('T')[0] : '';
document.getElementById('transNotes').value = transaction.notes || '';

// Store edit ID
document.getElementById('transactionForm').dataset.editId = id;

// Update modal title
document.querySelector('#transactionModal .modal-title').textContent = 'Edit Transaction';

// Show modal
const modal = new bootstrap.Modal(document.getElementById('transactionModal'));
modal.show();
}

// Delete transaction
function deleteTransaction(id) {
showConfirmModal(
'Delete Transaction',
'Are you sure you want to delete this transaction? This action cannot be undone.',
function() {
showLoading();

fetch(`/api/transactions/${id}`, {
method: 'DELETE'
})
.then(response => response.json())
.then(result => {
hideLoading();
if (result.error) {
showToast(result.error, 'danger');
} else {
showToast('Transaction deleted successfully', 'success');
loadTransactions();
}
})
.catch(error => {
hideLoading();
console.error('Error deleting transaction:', error);
showToast('Error deleting transaction', 'danger');
});
},
'Delete',
'btn-danger'
);
}

// Load payment totals
function loadPaymentTotals() {
const container = document.getElementById('paymentTotalsContainer');
container.innerHTML = '<div class="text-center" style="color: #cccccc;"><i class="fas fa-spinner fa-spin fa-2x mb-3"></i><p>Loading...</p></div>';

fetch(`/api/payment-method-totals?year=${currentYear}&month=${currentMonth}`)
.then(response => response.json())
.then(data => {
if (!data || data.length === 0) {
container.innerHTML = '<div class="alert alert-warning" style="background: #2d2d2d; border-color: #444; color: #ffc107;">No payment methods found with transactions.</div>';
return;
}

let html = '<table class="payment-totals-table"><tbody>';
data.forEach(item => {
html += `
<tr>
<td>
<span class="payment-method-color-indicator" style="background-color: ${item.color}"></span>
<span class="payment-method-name">${item.name}</span>
</td>
<td class="payment-amount">${formatCurrency(item.net_amount || 0)}</td>
</tr>
`;
});
html += '</tbody></table>';
container.innerHTML = html;
})
.catch(error => {
console.error('Error loading payment totals:', error);
container.innerHTML = '<div class="alert alert-danger" style="background: #2d2d2d; border-color: #444; color: #dc3545;">Error loading payment totals</div>';
});
}

// Toast notification function - Android style
function showToast(message, type = 'info') {
// Create toast element
const toast = document.createElement('div');
toast.className = `android-toast toast-${type}`;
toast.textContent = message;
document.body.appendChild(toast);

// Fade out and remove after 2.5 seconds
setTimeout(() => {
toast.classList.add('toast-fade-out');
setTimeout(() => {
toast.remove();
}, 300); // Wait for fade-out animation to complete
}, 2500);
}

// Theme toggle functionality
function toggleTheme() {
const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

document.documentElement.setAttribute('data-theme', newTheme);
localStorage.setItem('theme', newTheme);

updateThemeButton(newTheme);
showToast(`Switched to ${newTheme} theme`, 'success');
}

function updateThemeButton(theme) {
const icon = document.getElementById('mobileThemeIcon');
const text = document.getElementById('mobileThemeText');

if (theme === 'dark') {
icon.className = 'fas fa-sun';
text.textContent = 'Light Theme';
} else {
icon.className = 'fas fa-moon';
text.textContent = 'Dark Theme';
}
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
// Set today's date
document.getElementById('transDate').value = new Date().toISOString().split('T')[0];

// Update month display
updateMonthDisplay();

// Initialize the new swipe manager
SwipeManager.init();

// Load data
loadCategories();
loadPaymentMethods();
loadTransactions();

// Save button
document.getElementById('saveTransactionBtn').addEventListener('click', saveTransaction);

// New category inline creation
const toggleNewCategoryBtn = document.getElementById('toggleNewCategoryBtn');
if (toggleNewCategoryBtn) {
toggleNewCategoryBtn.addEventListener('click', toggleNewCategoryForm);
}

const saveNewCategoryBtn = document.getElementById('saveNewCategoryBtn');
if (saveNewCategoryBtn) {
saveNewCategoryBtn.addEventListener('click', saveNewCategory);
}

const cancelNewCategoryBtn = document.getElementById('cancelNewCategoryBtn');
if (cancelNewCategoryBtn) {
cancelNewCategoryBtn.addEventListener('click', hideNewCategoryForm);
}

// Allow pressing Enter to save new category
const newCategoryName = document.getElementById('newCategoryName');
if (newCategoryName) {
newCategoryName.addEventListener('keypress', function(e) {
if (e.key === 'Enter') {
e.preventDefault();
saveNewCategory();
}
});
}

// Load payment totals when modal is shown
const paymentTotalsModal = document.getElementById('paymentTotalsModal');
if (paymentTotalsModal) {
paymentTotalsModal.addEventListener('show.bs.modal', loadPaymentTotals);
}

// User dropdown toggle
const userBtn = document.getElementById('mobileUserBtn');
const userDropdown = document.getElementById('mobileUserDropdown');

if (userBtn && userDropdown) {
userBtn.addEventListener('click', function(e) {
e.stopPropagation();
userDropdown.classList.toggle('show');
});

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
if (!userDropdown.contains(e.target) && !userBtn.contains(e.target)) {
userDropdown.classList.remove('show');
}
});

// Close dropdown when clicking a link
userDropdown.querySelectorAll('.mobile-dropdown-item').forEach(item => {
item.addEventListener('click', function() {
userDropdown.classList.remove('show');
});
});
}

// Theme toggle button
const themeToggle = document.getElementById('mobileThemeToggle');
if (themeToggle) {
themeToggle.addEventListener('click', function(e) {
e.preventDefault();
toggleTheme();
});
}

// Initialize theme
const savedTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);
updateThemeButton(savedTheme);

// Reset form when modal is closed
const transactionModal = document.getElementById('transactionModal');
if (transactionModal) {
transactionModal.addEventListener('hidden.bs.modal', function() {
document.getElementById('transactionForm').reset();
document.getElementById('transactionForm').dataset.editId = '';
document.querySelector('#transactionModal .modal-title').textContent = 'Add Transaction';
document.getElementById('transDate').value = new Date().toISOString().split('T')[0];
});
}

// Change password functionality
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

// Send request
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
const modal = bootstrap.Modal.getInstance(document.getElementById('changePasswordModal'));
modal.hide();
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
});
