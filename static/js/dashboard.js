// Personal Finance Manager - Dashboard JavaScript
// Clean, simple, and working version

// Global variables
let charts = {
    trend: null,
    category: null,
    monthlyReport: null,
    categoryReport: null,
    categoryIncome: null,
    categoryExpense: null,
    yearlyReport: null,
    cashFlowReport: null,
    topSpendingReport: null,
    forecastReport: null
};
let currentCategories = [];
let paymentMethods = [];
let currentTransactionId = null;
let allTransactions = [];
let activeFilters = {
    description: '',
    categories: [],
    paymentMethods: [],
    types: [],
    statuses: [],
    minAmount: null,
    maxAmount: null,
    startDate: null,
    endDate: null,
    notes: ''
};

// Geolocation helper function
function getGeolocation() {
    return new Promise((resolve) => {
        // Check if geolocation is supported
        if (!navigator.geolocation) {
            console.log('Geolocation is not supported by this browser');
            resolve(null);
            return;
        }

        // Get current position with timeout
        navigator.geolocation.getCurrentPosition(
            (position) => {
                // Success callback
                const location = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy
                };
                console.log('Geolocation captured:', location);
                resolve(location);
            },
            (error) => {
                // Error callback - don't block the transaction
                console.log('Geolocation error:', error.message);
                resolve(null);
            },
            {
                // Options
                enableHighAccuracy: true,
                timeout: 5000, // 5 seconds timeout
                maximumAge: 0 // Don't use cached position
            }
        );
    });
}

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('=== Dashboard Loading ===');
    initApp();
});

// Main initialization function
function initApp() {
    try {
        // 1. Setup navigation
        setupNavigation();

        // 2. Setup form buttons
        setupFormButtons();

        // 3. Load initial data
        loadCategories();
        loadPaymentMethods();
        populateDateSelectors();

        // 4. Initialize charts
        initCharts();

        // 5. Load default page (transactions)
        navigateToPage('transactions');

        console.log('✓ Dashboard loaded successfully');
    } catch (error) {
        console.error('✗ Dashboard initialization failed:', error);
    }
}

// ================================
// NAVIGATION
// ================================

function setupNavigation() {
    const navLinks = document.querySelectorAll('.sidebar .nav-link');
    console.log('Setting up navigation for', navLinks.length, 'links');

    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const pageName = this.getAttribute('data-page');
            navigateToPage(pageName);
        });
    });

    // Setup refresh button - recalculate balances and reload
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', recalculateAndRefresh);
    }
}

function navigateToPage(pageName) {
    console.log('→ Navigating to:', pageName);

    // Hide all pages
    const allPages = document.querySelectorAll('.page-content');
    allPages.forEach(page => page.style.display = 'none');

    // Remove active from all nav links
    const allLinks = document.querySelectorAll('.sidebar .nav-link');
    allLinks.forEach(link => link.classList.remove('active'));

    // Show target page
    const targetPage = document.getElementById(pageName + 'Page');
    if (targetPage) {
        targetPage.style.display = 'block';
        console.log('✓ Showing:', pageName + 'Page');
    } else {
        console.error('✗ Page not found:', pageName + 'Page');
        return;
    }

    // Set active nav link
    const activeLink = document.querySelector(`[data-page="${pageName}"]`);
    if (activeLink) {
        activeLink.classList.add('active');
    }

    // Load page-specific data
    loadPageData(pageName);
}

function loadPageData(pageName) {
    switch(pageName) {
        case 'transactions':
            loadTransactions();
            break;
        case 'reports':
            loadReports();
            break;
        case 'overview':
            loadDashboardStats();
            break;
    }
}

// ================================
// FORM BUTTONS
// ================================

function setupFormButtons() {
    // Transaction form - prevent default form submission
    const transForm = document.getElementById('transactionForm');
    if (transForm) {
        transForm.addEventListener('submit', function(e) {
            e.preventDefault();
            saveTransaction();
        });
    }

    // Transaction form
    const saveTransBtn = document.getElementById('saveTransactionBtn');
    if (saveTransBtn) {
        saveTransBtn.addEventListener('click', function(e) {
            e.preventDefault();
            saveTransaction();
        });
    }

    // Month navigation buttons
    const prevMonthBtn = document.getElementById('prevMonthBtn');
    if (prevMonthBtn) {
        prevMonthBtn.addEventListener('click', navigateToPreviousMonth);
    }

    const nextMonthBtn = document.getElementById('nextMonthBtn');
    if (nextMonthBtn) {
        nextMonthBtn.addEventListener('click', navigateToNextMonth);
    }

    // Auto-load transactions when month or year changes
    const monthSelect = document.getElementById('monthSelect');
    if (monthSelect) {
        monthSelect.addEventListener('change', loadTransactions);
    }

    const yearSelect = document.getElementById('yearSelect');
    if (yearSelect) {
        yearSelect.addEventListener('change', loadTransactions);
    }

    const viewPaymentTotalsBtn = document.getElementById('viewPaymentTotalsBtn');
    if (viewPaymentTotalsBtn) {
        viewPaymentTotalsBtn.addEventListener('click', loadPaymentTotals);
    }

    // Set today's date in transaction form
    const transDate = document.getElementById('transDate');
    if (transDate) {
        transDate.value = new Date().toISOString().split('T')[0];
    }

    // Credit card management
    const addCardBtn = document.getElementById('addCreditCardBtn');
    if (addCardBtn) {
        addCardBtn.addEventListener('click', showAddCreditCardForm);
    }

    const cancelAddCardBtn = document.getElementById('cancelAddCardBtn');
    if (cancelAddCardBtn) {
        cancelAddCardBtn.addEventListener('click', hideAddCreditCardForm);
    }

    const creditCardForm = document.getElementById('creditCardForm');
    if (creditCardForm) {
        creditCardForm.addEventListener('submit', saveCreditCard);
    }

    // Filter buttons
    const applyFiltersBtn = document.getElementById('applyFiltersBtn');
    if (applyFiltersBtn) {
        applyFiltersBtn.addEventListener('click', applyFilters);
    }

    const clearFiltersBtn = document.getElementById('clearFiltersBtn');
    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', clearFilters);
    }

    // Setup filter modal to populate dropdowns when shown
    const filterModal = document.getElementById('filterModal');
    if (filterModal) {
        filterModal.addEventListener('shown.bs.modal', populateFilterDropdowns);
    }

    // Prevent dropdown from closing when clicking on dropdown items (for checkboxes)
    document.addEventListener('click', function(e) {
        if (e.target.closest('.dropdown-item')) {
            e.stopPropagation();
        }
    });
}

// ================================
// CATEGORIES
// ================================

function loadCategories() {
    fetch('/api/categories')
        .then(response => response.json())
        .then(data => {
            currentCategories = data;
            populateCategoryDropdowns(data);
        })
        .catch(error => {
            console.error('Error loading categories:', error);
        });
}

function populateCategoryDropdowns(categories) {
    const dropdowns = ['transCategory', 'recCategory'];

    dropdowns.forEach(dropdownId => {
        const dropdown = document.getElementById(dropdownId);
        if (dropdown) {
            dropdown.innerHTML = '<option value="">Select Category</option>';
            categories.forEach(cat => {
                dropdown.innerHTML += `<option value="${cat.id}">${cat.name} (${cat.type})</option>`;
            });
        }
    });

    // Also populate filter dropdown
    const filterDropdown = document.getElementById('filterCategory');
    if (filterDropdown) {
        filterDropdown.innerHTML = '<option value="">All Categories</option>';
        categories.forEach(cat => {
            filterDropdown.innerHTML += `<option value="${cat.id}">${cat.name} (${cat.type})</option>`;
        });
    }
}

// ================================
// DASHBOARD / OVERVIEW
// ================================

function loadDashboardStats() {
    showLoading();

    fetch('/api/dashboard-stats')
        .then(response => response.json())
        .then(data => {
            updateStatsCards(data.current_stats);
            updateRecentTransactions(data.recent_transactions);
            updateTrendChart(data.monthly_trend);
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading dashboard stats:', error);
            hideLoading();
        });
}

function updateStatsCards(stats) {
    if (!stats) return;

    // Current Balance
    const balanceEl = document.getElementById('currentBalance');
    if (balanceEl) {
        balanceEl.textContent = formatCurrency(stats.current_balance || 0);
    }

    // Monthly Income
    const incomeEl = document.getElementById('monthlyIncome');
    if (incomeEl) {
        incomeEl.textContent = formatCurrency(stats.total_income || 0);
    }

    // Monthly Expenses
    const expensesEl = document.getElementById('monthlyExpenses');
    if (expensesEl) {
        expensesEl.textContent = formatCurrency(stats.total_expenses || 0);
    }

    // Savings Rate
    const savingsEl = document.getElementById('savingsRate');
    if (savingsEl && stats.total_income > 0) {
        const rate = ((stats.total_income - stats.total_expenses) / stats.total_income * 100).toFixed(1);
        savingsEl.textContent = rate + '%';
    }
}

function updateRecentTransactions(transactions) {
    const tbody = document.querySelector('#recentTransactionsTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">No transactions found</td></tr>';
        return;
    }

    // Calculate running balance for recent transactions
    // Note: transactions come sorted by created_at DESC, so we need to reverse to calculate
    const sortedTransactions = [...transactions].reverse();
    let runningBalance = 0;
    sortedTransactions.forEach(t => {
        const debit = parseFloat(t.debit) || 0;
        const credit = parseFloat(t.credit) || 0;
        runningBalance += debit - credit;
        t.calculatedBalance = runningBalance;
    });

    // Display in original order (newest first)
    sortedTransactions.reverse().forEach(t => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${t.transaction_date ? formatDate(t.transaction_date) : '-'}</td>
            <td>${t.description}</td>
            <td><span class="badge bg-secondary">${t.category || 'Uncategorized'}</span></td>
            <td class="text-success">${t.debit ? formatCurrency(t.debit) : '-'}</td>
            <td class="text-danger">${t.credit ? formatCurrency(t.credit) : '-'}</td>
            <td class="fw-bold">${formatCurrency(t.calculatedBalance)}</td>
        `;
        tbody.appendChild(row);
    });
}

// ================================
// TRANSACTIONS PAGE
// ================================

function loadTransactions(applyActiveFilters = false) {
    const year = document.getElementById('yearSelect')?.value || new Date().getFullYear();
    const month = document.getElementById('monthSelect')?.value || (new Date().getMonth() + 1);

    showLoading();

    // Build query parameters
    let queryParams = `year=${year}&month=${month}`;

    // Add filter parameters if requested
    if (applyActiveFilters) {
        if (activeFilters.description) {
            queryParams += `&description=${encodeURIComponent(activeFilters.description)}`;
        }
        if (activeFilters.notes) {
            queryParams += `&notes=${encodeURIComponent(activeFilters.notes)}`;
        }
        if (activeFilters.categories.length > 0) {
            queryParams += `&categories=${activeFilters.categories.join(',')}`;
        }
        if (activeFilters.paymentMethods.length > 0) {
            queryParams += `&paymentMethods=${activeFilters.paymentMethods.join(',')}`;
        }
        if (activeFilters.types.length > 0) {
            queryParams += `&types=${activeFilters.types.join(',')}`;
        }
        if (activeFilters.statuses.length > 0) {
            queryParams += `&statuses=${activeFilters.statuses.join(',')}`;
        }
        if (activeFilters.minAmount !== null) {
            queryParams += `&minAmount=${activeFilters.minAmount}`;
        }
        if (activeFilters.maxAmount !== null) {
            queryParams += `&maxAmount=${activeFilters.maxAmount}`;
        }
        if (activeFilters.startDate) {
            queryParams += `&startDate=${activeFilters.startDate}`;
        }
        if (activeFilters.endDate) {
            queryParams += `&endDate=${activeFilters.endDate}`;
        }
    }

    fetch(`/api/transactions?${queryParams}`)
        .then(response => response.json())
        .then(data => {
            console.log('Transactions received:', data);
            allTransactions = data; // Store all transactions globally
            displayTransactions(data); // Display transactions directly
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading transactions:', error);
            hideLoading();
        });
}

function navigateToPreviousMonth() {
    const monthSelect = document.getElementById('monthSelect');
    const yearSelect = document.getElementById('yearSelect');

    if (!monthSelect || !yearSelect) return;

    let currentMonth = parseInt(monthSelect.value);
    let currentYear = parseInt(yearSelect.value);

    // Go to previous month
    currentMonth--;

    // If month goes below 1, go to December of previous year
    if (currentMonth < 1) {
        currentMonth = 12;
        currentYear--;
    }

    // Update selectors
    monthSelect.value = currentMonth;
    yearSelect.value = currentYear;

    // Load transactions for the new month
    loadTransactions();
}

function navigateToNextMonth() {
    const monthSelect = document.getElementById('monthSelect');
    const yearSelect = document.getElementById('yearSelect');

    if (!monthSelect || !yearSelect) return;

    let currentMonth = parseInt(monthSelect.value);
    let currentYear = parseInt(yearSelect.value);

    // Go to next month
    currentMonth++;

    // If month goes above 12, go to January of next year
    if (currentMonth > 12) {
        currentMonth = 1;
        currentYear++;
    }

    // Update selectors
    monthSelect.value = currentMonth;
    yearSelect.value = currentYear;

    // Load transactions for the new month
    loadTransactions();
}

function recalculateAndRefresh() {
    const year = document.getElementById('yearSelect')?.value || new Date().getFullYear();
    const month = document.getElementById('monthSelect')?.value || (new Date().getMonth() + 1);

    showLoading();

    // Call recalculate balances API
    fetch('/api/recalculate-balances', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            year: parseInt(year),
            month: parseInt(month)
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            console.error('Recalculation error:', data.error);
            showToast('Error recalculating balances: ' + data.error, 'danger');
            hideLoading();
        } else {
            console.log('Balances recalculated:', data.message);
            showToast(data.message, 'success');
            // Reload transactions to show updated balances
            loadTransactions();
        }
    })
    .catch(error => {
        console.error('Error recalculating balances:', error);
        showToast('Error recalculating balances', 'danger');
        hideLoading();
    });
}

function displayTransactions(transactions) {
    const tbody = document.querySelector('#transactionsTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center">No transactions for this period</td></tr>';
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
    sortedTransactions.reverse().forEach(t => {
        const row = document.createElement('tr');

        // Checkbox for marking done/undone (handle both boolean and numeric values)
        const isDone = t.is_done === true || t.is_done === 1;
        const checkboxHtml = isDone
            ? `<input type="checkbox" class="form-check-input" checked onchange="unmarkTransaction(${t.id})" title="${t.payment_method_name || 'Done'}">`
            : `<input type="checkbox" class="form-check-input" onchange="showPaymentMethodModal(${t.id})">`;

        // Store transaction data
        row.dataset.transaction = JSON.stringify(t);

        // Apply highlighting class if done
        let rowClass = '';
        if (isDone && t.payment_method_color) {
            rowClass = `class="transaction-highlighted"`;
            row.dataset.paymentColor = t.payment_method_color;
        }

        // Format paid_at date if exists
        const paidAtDisplay = t.paid_at ? formatDate(t.paid_at) : '-';

        row.innerHTML = `
            <td class="text-center">${checkboxHtml}</td>
            <td class="description-cell" style="cursor: pointer;" data-transaction-id="${t.id}">${t.description}</td>
            <td><span class="badge bg-secondary">${t.category_name || 'Uncategorized'}</span></td>
            <td class="text-success">${t.debit ? formatCurrency(t.debit) : '-'}</td>
            <td class="text-danger">${t.credit ? formatCurrency(t.credit) : '-'}</td>
            <td class="fw-bold">${formatCurrency(t.calculatedBalance)}</td>
            <td class="text-muted small">${paidAtDisplay}</td>
            <td>${t.notes || '-'}</td>
            <td>
                <button class="btn btn-sm btn-primary me-1" onclick="editTransaction(${t.id})">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm btn-danger" onclick="deleteTransaction(${t.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;

        // Get the description cell
        const descCell = row.querySelector('.description-cell');

        // Check if transaction is paid (handle both boolean and numeric values)
        const isPaid = t.is_paid === true || t.is_paid === 1;

        // Apply background color to all cells for proper highlighting
        if (isDone && t.payment_method_color) {
            console.log(`Highlighting transaction ${t.id} with color ${t.payment_method_color}`);
            row.classList.add('transaction-highlighted');
            const cells = row.querySelectorAll('td');
            cells.forEach((cell, index) => {
                // Apply to all cells except description (index 1)
                if (index !== 1) {
                    cell.style.backgroundColor = t.payment_method_color;
                } else {
                    // Apply to description cell only if is_paid is true
                    if (isPaid) {
                        cell.style.backgroundColor = t.payment_method_color;
                    }
                }
            });
        }

        // Add click handler to description cell
        if (descCell) {
            // Store isPaid status in the cell
            descCell.dataset.isPaid = isPaid ? '1' : '0';

            descCell.addEventListener('click', function() {
                const transId = parseInt(this.dataset.transactionId);
                const cellIsPaid = this.dataset.isPaid === '1';

                // If already paid, unpay it. Otherwise, show payment modal
                if (cellIsPaid) {
                    markTransactionAsUnpaid(transId);
                } else {
                    showPaymentMethodModal(transId, true); // true = isPaidClick
                }
            });
        }

        tbody.appendChild(row);
    });
}

function loadPaymentTotals() {
    const year = document.getElementById('yearSelect')?.value || new Date().getFullYear();
    const month = document.getElementById('monthSelect')?.value || (new Date().getMonth() + 1);

    showLoading();

    fetch(`/api/payment-method-totals?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            displayPaymentTotals(data);
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading payment totals:', error);
            showToast('Error loading payment totals', 'danger');
            hideLoading();
        });
}

function displayPaymentTotals(totals) {
    const container = document.getElementById('paymentTotalsContent');
    if (!container) return;

    container.innerHTML = '';

    if (!totals || totals.length === 0) {
        container.innerHTML = '<div class="alert alert-warning">No payment methods found with transactions.</div>';
        return;
    }

    let totalDebit = 0;
    let totalCredit = 0;

    const html = `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Payment Method</th>
                        <th>Type</th>
                        <th>Transactions</th>
                        <th class="text-end">Total Debit</th>
                        <th class="text-end">Total Credit</th>
                        <th class="text-end">Net Amount</th>
                    </tr>
                </thead>
                <tbody>
                    ${totals.map(t => {
                        const debit = t.total_debit || 0;
                        const credit = t.total_credit || 0;
                        const net = t.net_amount || 0;
                        totalDebit += debit;
                        totalCredit += credit;

                        return `
                            <tr>
                                <td>
                                    <span class="payment-method-color-indicator" style="background-color: ${t.color}"></span>
                                    <strong>${t.name}</strong>
                                </td>
                                <td>
                                    <span class="badge ${t.type === 'cash' ? 'bg-success' : 'bg-info'}">
                                        ${t.type === 'cash' ? 'Cash' : 'Credit Card'}
                                    </span>
                                </td>
                                <td>${t.transaction_count || 0}</td>
                                <td class="text-end text-success">${formatCurrency(debit)}</td>
                                <td class="text-end text-danger">${formatCurrency(credit)}</td>
                                <td class="text-end fw-bold ${net >= 0 ? 'text-success' : 'text-danger'}">
                                    ${formatCurrency(net)}
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
                <tfoot>
                    <tr class="table-active fw-bold">
                        <td colspan="3">TOTAL</td>
                        <td class="text-end text-success">${formatCurrency(totalDebit)}</td>
                        <td class="text-end text-danger">${formatCurrency(totalCredit)}</td>
                        <td class="text-end ${(totalDebit - totalCredit) >= 0 ? 'text-success' : 'text-danger'}">
                            ${formatCurrency(totalDebit - totalCredit)}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    `;

    container.innerHTML = html;
}

function editTransaction(id) {
    // Find the transaction in the table
    const tbody = document.querySelector('#transactionsTable tbody');
    const row = tbody.querySelector(`tr[data-transaction*='"id":${id}']`);

    if (!row) return;

    const transaction = JSON.parse(row.dataset.transaction);

    // Populate form
    document.getElementById('editTransactionId').value = transaction.id;
    document.getElementById('transDescription').value = transaction.description || '';
    document.getElementById('transCategory').value = transaction.category_id || '';
    document.getElementById('transDebit').value = transaction.debit || '';
    document.getElementById('transCredit').value = transaction.credit || '';
    document.getElementById('transDate').value = transaction.transaction_date ? transaction.transaction_date.split('T')[0] : '';
    document.getElementById('transNotes').value = transaction.notes || '';

    // Update modal title
    document.querySelector('#transactionModal .modal-title').textContent = 'Edit Transaction';

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('transactionModal'));
    modal.show();
}

function saveTransaction() {
    const editId = document.getElementById('editTransactionId')?.value;
    const isEdit = editId && editId !== '';

    const year = document.getElementById('yearSelect')?.value || new Date().getFullYear();
    const month = document.getElementById('monthSelect')?.value || (new Date().getMonth() + 1);

    // Validate description
    const description = document.getElementById('transDescription')?.value;
    if (!description || description.trim() === '') {
        showToast('Description is required', 'danger');
        return;
    }

    // Get raw values
    const debitValue = document.getElementById('transDebit')?.value;
    const creditValue = document.getElementById('transCredit')?.value;

    // Parse and validate values - handle empty strings properly
    let debit = null;
    let credit = null;

    if (debitValue && debitValue.trim() !== '') {
        debit = parseFloat(debitValue);
        if (isNaN(debit) || debit < 0) {
            showToast('Debit must be a valid positive number', 'danger');
            return;
        }
    }

    if (creditValue && creditValue.trim() !== '') {
        credit = parseFloat(creditValue);
        if (isNaN(credit) || credit < 0) {
            showToast('Credit must be a valid positive number', 'danger');
            return;
        }
    }

    const data = {
        description: description,
        category_id: document.getElementById('transCategory')?.value || null,
        debit: debit,
        credit: credit,
        transaction_date: document.getElementById('transDate')?.value,
        notes: document.getElementById('transNotes')?.value,
        year: parseInt(year),
        month: parseInt(month)
    };

    console.log('Saving transaction with data:', data);
    console.log('Debit value:', debitValue, 'Parsed:', debit);
    console.log('Credit value:', creditValue, 'Parsed:', credit);

    const url = isEdit ? `/api/transactions/${editId}` : '/api/transactions';
    const method = isEdit ? 'PUT' : 'POST';

    showLoading();

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => {
        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);
        console.log('Response headers:', response.headers.get('content-type'));

        // Get response as text first
        return response.text().then(text => {
            console.log('Response text (first 500 chars):', text.substring(0, 500));

            // Try to parse as JSON
            try {
                const result = JSON.parse(text);
                return { status: response.status, ok: response.ok, result };
            } catch (e) {
                console.error('Failed to parse JSON:', e);
                console.error('Full response text:', text);
                return { status: response.status, ok: false, result: { error: 'Server returned non-JSON response' } };
            }
        });
    })
    .then(({ status, ok, result }) => {
        console.log('Parsed result:', result);
        hideLoading();
        if (!ok || result.error) {
            const errorMsg = result.error || `Server error (${status})`;
            console.error('Save failed:', errorMsg);
            showToast(errorMsg, 'danger');
        } else {
            showToast(isEdit ? 'Transaction updated successfully' : 'Transaction saved successfully', 'success');
            closeModal('transactionModal');
            document.getElementById('transactionForm')?.reset();
            document.getElementById('editTransactionId').value = '';
            document.querySelector('#transactionModal .modal-title').textContent = 'Add Transaction';

            // Reset date to today after form reset
            const transDate = document.getElementById('transDate');
            if (transDate) {
                transDate.value = new Date().toISOString().split('T')[0];
            }

            loadTransactions();
            loadDashboardStats();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error saving transaction:', error);
        showToast('Error saving transaction: ' + error.message, 'danger');
    });
}

function deleteTransaction(id) {
    showConfirmModal(
        'Delete Transaction',
        'Are you sure you want to delete this transaction? This action cannot be undone.',
        function() {
            showLoading();
            fetch(`/api/transactions/${id}`, { method: 'DELETE' })
                .then(response => response.json())
                .then(result => {
                    hideLoading();
                    showToast('Transaction deleted successfully', 'success');
                    loadTransactions();
                    loadDashboardStats();
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

// ================================
// TRANSACTION FILTERS
// ================================

function populateFilterDropdowns() {
    // Populate categories
    const categoryMenu = document.getElementById('filterCategoryMenu');
    if (categoryMenu) {
        categoryMenu.innerHTML = '';
        currentCategories.forEach(cat => {
            const li = document.createElement('li');
            li.innerHTML = `
                <div class="dropdown-item">
                    <div class="form-check">
                        <input class="form-check-input filter-category-checkbox" type="checkbox" value="${cat.id}" id="filterCat${cat.id}">
                        <label class="form-check-label" for="filterCat${cat.id}">${cat.name} (${cat.type})</label>
                    </div>
                </div>
            `;
            categoryMenu.appendChild(li);
        });

        // Add event listeners to update label
        categoryMenu.querySelectorAll('.filter-category-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', updateCategoryLabel);
        });
    }

    // Populate payment methods
    const paymentMenu = document.getElementById('filterPaymentMethodMenu');
    if (paymentMenu && Array.isArray(paymentMethods)) {
        paymentMenu.innerHTML = '';
        paymentMethods.forEach(method => {
            const li = document.createElement('li');
            li.innerHTML = `
                <div class="dropdown-item">
                    <div class="form-check">
                        <input class="form-check-input filter-payment-checkbox" type="checkbox" value="${method.id}" id="filterPay${method.id}">
                        <label class="form-check-label" for="filterPay${method.id}">${method.name} (${method.type === 'cash' ? 'Cash' : 'Credit Card'})</label>
                    </div>
                </div>
            `;
            paymentMenu.appendChild(li);
        });

        // Add event listeners to update label
        paymentMenu.querySelectorAll('.filter-payment-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', updatePaymentMethodLabel);
        });
    }

    // Add event listeners for type and status checkboxes
    document.querySelectorAll('.filter-type-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', updateTypeLabel);
    });

    document.querySelectorAll('.filter-status-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', updateStatusLabel);
    });
}

// Update label functions
function updateCategoryLabel() {
    const checkboxes = document.querySelectorAll('.filter-category-checkbox:checked');
    const label = document.getElementById('filterCategoryLabel');
    if (checkboxes.length === 0) {
        label.textContent = 'All Categories';
    } else if (checkboxes.length === 1) {
        const catId = checkboxes[0].value;
        const cat = currentCategories.find(c => c.id == catId);
        label.textContent = cat ? cat.name : 'Selected';
    } else {
        label.textContent = `${checkboxes.length} selected`;
    }
}

function updatePaymentMethodLabel() {
    const checkboxes = document.querySelectorAll('.filter-payment-checkbox:checked');
    const label = document.getElementById('filterPaymentMethodLabel');
    if (checkboxes.length === 0) {
        label.textContent = 'All Methods';
    } else if (checkboxes.length === 1) {
        const methodId = checkboxes[0].value;
        const method = paymentMethods.find(m => m.id == methodId);
        label.textContent = method ? method.name : 'Selected';
    } else {
        label.textContent = `${checkboxes.length} selected`;
    }
}

function updateTypeLabel() {
    const checkboxes = document.querySelectorAll('.filter-type-checkbox:checked');
    const label = document.getElementById('filterTypeLabel');
    if (checkboxes.length === 0) {
        label.textContent = 'All Types';
    } else if (checkboxes.length === 1) {
        label.textContent = checkboxes[0].value === 'income' ? 'Income' : 'Expense';
    } else {
        label.textContent = `${checkboxes.length} selected`;
    }
}

function updateStatusLabel() {
    const checkboxes = document.querySelectorAll('.filter-status-checkbox:checked');
    const label = document.getElementById('filterStatusLabel');
    if (checkboxes.length === 0) {
        label.textContent = 'All Statuses';
    } else if (checkboxes.length === 1) {
        const status = checkboxes[0].value;
        if (status === 'done') label.textContent = 'Done';
        else if (status === 'not_done') label.textContent = 'Not Done';
        else if (status === 'paid') label.textContent = 'Paid';
        else if (status === 'unpaid') label.textContent = 'Unpaid';
    } else {
        label.textContent = `${checkboxes.length} selected`;
    }
}

function applyFilters() {
    // Get filter values
    activeFilters.description = document.getElementById('filterDescription')?.value.trim() || '';
    activeFilters.notes = document.getElementById('filterNotes')?.value.trim() || '';

    // Get selected categories (from checkboxes)
    activeFilters.categories = [];
    document.querySelectorAll('.filter-category-checkbox:checked').forEach(checkbox => {
        activeFilters.categories.push(checkbox.value);
    });

    // Get selected payment methods (from checkboxes)
    activeFilters.paymentMethods = [];
    document.querySelectorAll('.filter-payment-checkbox:checked').forEach(checkbox => {
        activeFilters.paymentMethods.push(checkbox.value);
    });

    // Get selected types (from checkboxes)
    activeFilters.types = [];
    document.querySelectorAll('.filter-type-checkbox:checked').forEach(checkbox => {
        activeFilters.types.push(checkbox.value);
    });

    // Get selected statuses (from checkboxes)
    activeFilters.statuses = [];
    document.querySelectorAll('.filter-status-checkbox:checked').forEach(checkbox => {
        activeFilters.statuses.push(checkbox.value);
    });

    // Get amount range
    const minAmount = document.getElementById('filterMinAmount')?.value;
    const maxAmount = document.getElementById('filterMaxAmount')?.value;
    activeFilters.minAmount = minAmount ? parseFloat(minAmount) : null;
    activeFilters.maxAmount = maxAmount ? parseFloat(maxAmount) : null;

    // Get date range
    activeFilters.startDate = document.getElementById('filterStartDate')?.value || null;
    activeFilters.endDate = document.getElementById('filterEndDate')?.value || null;

    console.log('Active filters:', activeFilters);

    // Update active filters display
    displayActiveFilters();

    // Close modal
    closeModal('filterModal');

    // Load transactions from backend with filters
    loadTransactions(true);

    showToast('Filters applied successfully', 'success');
}

function clearFilters() {
    // Reset filter values
    activeFilters = {
        description: '',
        categories: [],
        paymentMethods: [],
        types: [],
        statuses: [],
        minAmount: null,
        maxAmount: null,
        startDate: null,
        endDate: null,
        notes: ''
    };

    // Clear form inputs
    document.getElementById('filterDescription').value = '';
    document.getElementById('filterNotes').value = '';
    document.getElementById('filterMinAmount').value = '';
    document.getElementById('filterMaxAmount').value = '';
    document.getElementById('filterStartDate').value = '';
    document.getElementById('filterEndDate').value = '';

    // Uncheck all filter checkboxes
    document.querySelectorAll('.filter-category-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    document.querySelectorAll('.filter-payment-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    document.querySelectorAll('.filter-type-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    document.querySelectorAll('.filter-status-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });

    // Reset dropdown labels
    updateCategoryLabel();
    updatePaymentMethodLabel();
    updateTypeLabel();
    updateStatusLabel();

    // Update active filters display and badge
    displayActiveFilters();

    // Reload transactions from backend without filters
    loadTransactions(false);

    showToast('All filters cleared', 'info');
}

function displayActiveFilters() {
    const container = document.getElementById('activeFiltersDisplay');
    const listEl = document.getElementById('activeFiltersList');

    if (!container || !listEl) return;

    listEl.innerHTML = '';
    let hasActiveFilters = false;

    // Description filter
    if (activeFilters.description) {
        hasActiveFilters = true;
        listEl.innerHTML += `<span class="badge bg-primary">Description: "${activeFilters.description}"</span>`;
    }

    // Notes filter
    if (activeFilters.notes) {
        hasActiveFilters = true;
        listEl.innerHTML += `<span class="badge bg-primary">Notes: "${activeFilters.notes}"</span>`;
    }

    // Category filter (multiple)
    if (activeFilters.categories.length > 0) {
        hasActiveFilters = true;
        const categoryNames = activeFilters.categories.map(catId => {
            const cat = currentCategories.find(c => c.id == catId);
            return cat ? cat.name : catId;
        }).join(', ');
        listEl.innerHTML += `<span class="badge bg-info">Categories: ${categoryNames}</span>`;
    }

    // Payment method filter (multiple)
    if (activeFilters.paymentMethods.length > 0) {
        hasActiveFilters = true;
        const methodNames = activeFilters.paymentMethods.map(methodId => {
            const method = paymentMethods.find(m => m.id == methodId);
            return method ? method.name : methodId;
        }).join(', ');
        listEl.innerHTML += `<span class="badge bg-info">Payment Methods: ${methodNames}</span>`;
    }

    // Type filter (multiple)
    if (activeFilters.types.length > 0) {
        hasActiveFilters = true;
        const typeLabels = activeFilters.types.map(type => type === 'income' ? 'Income' : 'Expense').join(', ');
        listEl.innerHTML += `<span class="badge bg-success">Types: ${typeLabels}</span>`;
    }

    // Status filter (multiple)
    if (activeFilters.statuses.length > 0) {
        hasActiveFilters = true;
        const statusLabels = activeFilters.statuses.map(status => {
            if (status === 'done') return 'Done';
            if (status === 'not_done') return 'Not Done';
            if (status === 'paid') return 'Paid';
            if (status === 'unpaid') return 'Unpaid';
            return status;
        }).join(', ');
        listEl.innerHTML += `<span class="badge bg-warning">Statuses: ${statusLabels}</span>`;
    }

    // Amount range
    if (activeFilters.minAmount !== null || activeFilters.maxAmount !== null) {
        hasActiveFilters = true;
        let amountText = 'Amount: ';
        if (activeFilters.minAmount !== null && activeFilters.maxAmount !== null) {
            amountText += `${formatCurrency(activeFilters.minAmount)} - ${formatCurrency(activeFilters.maxAmount)}`;
        } else if (activeFilters.minAmount !== null) {
            amountText += `≥ ${formatCurrency(activeFilters.minAmount)}`;
        } else {
            amountText += `≤ ${formatCurrency(activeFilters.maxAmount)}`;
        }
        listEl.innerHTML += `<span class="badge bg-secondary">${amountText}</span>`;
    }

    // Date range
    if (activeFilters.startDate || activeFilters.endDate) {
        hasActiveFilters = true;
        let dateText = 'Date: ';
        if (activeFilters.startDate && activeFilters.endDate) {
            dateText += `${activeFilters.startDate} to ${activeFilters.endDate}`;
        } else if (activeFilters.startDate) {
            dateText += `From ${activeFilters.startDate}`;
        } else {
            dateText += `Until ${activeFilters.endDate}`;
        }
        listEl.innerHTML += `<span class="badge bg-secondary">${dateText}</span>`;
    }

    // Show/hide container
    container.style.display = hasActiveFilters ? 'block' : 'none';

    // Update filter button badge
    const filterBadge = document.getElementById('filterBadge');
    if (filterBadge) {
        if (hasActiveFilters) {
            // Count active filters
            let filterCount = 0;
            if (activeFilters.description) filterCount++;
            if (activeFilters.notes) filterCount++;
            if (activeFilters.categories.length > 0) filterCount++;
            if (activeFilters.paymentMethods.length > 0) filterCount++;
            if (activeFilters.types.length > 0) filterCount++;
            if (activeFilters.statuses.length > 0) filterCount++;
            if (activeFilters.minAmount !== null || activeFilters.maxAmount !== null) filterCount++;
            if (activeFilters.startDate || activeFilters.endDate) filterCount++;

            filterBadge.textContent = filterCount;
            filterBadge.style.display = 'inline-block';
        } else {
            filterBadge.style.display = 'none';
        }
    }
}

function executeCloneMonth() {
    const fromMonth = document.getElementById('cloneFromMonth')?.value;
    const fromYear = document.getElementById('cloneFromYear')?.value;
    const toMonth = document.getElementById('cloneToMonth')?.value;
    const toYear = document.getElementById('cloneToYear')?.value;
    const includePayments = document.getElementById('cloneWithPayments')?.checked || false;

    // Validation
    if (!fromMonth || !fromYear || !toMonth || !toYear) {
        showToast('Please select all date fields', 'danger');
        return;
    }

    if (fromYear === toYear && fromMonth === toMonth) {
        showToast('Source and target months cannot be the same', 'danger');
        return;
    }

    // Confirm action
    const fromMonthName = document.getElementById('cloneFromMonth')?.options[document.getElementById('cloneFromMonth')?.selectedIndex]?.text;
    const toMonthName = document.getElementById('cloneToMonth')?.options[document.getElementById('cloneToMonth')?.selectedIndex]?.text;

    showConfirmModal(
        'Clone Month Transactions',
        `Clone all transactions from ${fromMonthName} ${fromYear} to ${toMonthName} ${toYear}?`,
        function() {
            showLoading();

            fetch('/api/clone-month-transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            from_year: parseInt(fromYear),
            from_month: parseInt(fromMonth),
            to_year: parseInt(toYear),
            to_month: parseInt(toMonth),
            include_payments: includePayments
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast(data.message, 'success');
            closeModal('cloneMonthModal');

            // Reload transactions if viewing the target month
            const currentMonth = document.getElementById('monthSelect')?.value;
            const currentYear = document.getElementById('yearSelect')?.value;
            if (currentMonth == toMonth && currentYear == toYear) {
                loadTransactions();
            }
        }
    })
            .catch(error => {
                hideLoading();
                console.error('Error cloning transactions:', error);
                showToast('Error cloning transactions', 'danger');
            });
        },
        'Clone',
        'btn-primary'
    );
}

// ================================
// REPORTS PAGE
// ================================

function loadReports() {
    const year = new Date().getFullYear();
    const month = new Date().getMonth() + 1;

    // Initialize year and month selectors
    initializeReportFilters(year, month);

    showLoading();

    // Load all reports
    loadAllReports(year, month, 'monthly');
}

function initializeReportFilters(year, month) {
    const yearSelect = document.getElementById('reportYear');
    const monthSelect = document.getElementById('reportMonth');
    const rangeSelect = document.getElementById('reportRangeType');

    // Populate years (from 2020 to current year + 1)
    yearSelect.innerHTML = '';
    for (let y = year + 1; y >= 2020; y--) {
        const option = document.createElement('option');
        option.value = y;
        option.textContent = y;
        if (y === year) option.selected = true;
        yearSelect.appendChild(option);
    }

    // Set current month
    monthSelect.value = month;

    // Add event listeners only once
    if (!reportFiltersInitialized) {
        yearSelect.addEventListener('change', () => {
            const selectedYear = yearSelect.value;
            const selectedMonth = monthSelect.value;
            const selectedRange = rangeSelect.value;
            loadAllReports(selectedYear, selectedMonth, selectedRange);
        });

        monthSelect.addEventListener('change', () => {
            const selectedYear = yearSelect.value;
            const selectedMonth = monthSelect.value;
            const selectedRange = rangeSelect.value;
            loadAllReports(selectedYear, selectedMonth, selectedRange);
        });

        rangeSelect.addEventListener('change', () => {
            const selectedYear = yearSelect.value;
            const selectedMonth = monthSelect.value;
            const selectedRange = rangeSelect.value;

            // Show/hide month selector based on range type
            const monthContainer = document.getElementById('reportMonthContainer');
            if (selectedRange === 'yearly') {
                monthContainer.style.display = 'none';
            } else {
                monthContainer.style.display = 'block';
            }

            loadAllReports(selectedYear, selectedMonth, selectedRange);
        });

        reportFiltersInitialized = true;
    }
}

function loadAllReports(year, month, rangeType) {
    showLoading();

    Promise.all([
        fetch(`/api/reports/monthly-summary?year=${year}`)
            .then(response => response.json())
            .then(data => updateMonthlyReportChart(data)),

        fetch(`/api/reports/category-breakdown?range=${rangeType}&year=${year}&month=${month}`)
            .then(response => response.json())
            .then(data => updateCategoryReportChart(data, rangeType)),

        fetch(`/api/reports/cash-flow?range=${rangeType}&year=${year}&month=${month}`)
            .then(response => response.json())
            .then(data => updateCashFlowChart(data, rangeType)),

        fetch(`/api/reports/top-spending?range=${rangeType}&year=${year}&month=${month}&limit=10`)
            .then(response => response.json())
            .then(data => updateTopSpendingChart(data)),

        fetch(`/api/reports/forecast?months=6`)
            .then(response => response.json())
            .then(data => updateForecastChart(data))
    ])
    .then(() => {
        hideLoading();
    })
    .catch(error => {
        hideLoading();
        console.error('Error loading reports:', error);
        showToast('Error loading reports', 'danger');
    });
}

// ================================
// CHARTS
// ================================

function initCharts() {
    // Trend Chart
    const trendCtx = document.getElementById('trendChart');
    if (trendCtx) {
        charts.trend = new Chart(trendCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Income',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.1
                }, {
                    label: 'Expenses',
                    data: [],
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: value => 'LKR ' + value.toLocaleString()
                        }
                    }
                }
            }
        });
    }

    // Category Chart
    const categoryCtx = document.getElementById('categoryChart');
    if (categoryCtx) {
        charts.category = new Chart(categoryCtx, {
            type: 'doughnut',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.8)',
                        'rgba(54, 162, 235, 0.8)',
                        'rgba(255, 206, 86, 0.8)',
                        'rgba(75, 192, 192, 0.8)',
                        'rgba(153, 102, 255, 0.8)',
                        'rgba(255, 159, 64, 0.8)'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    }
}

function updateTrendChart(data) {
    if (!charts.trend || !data) return;

    const labels = [];
    const income = [];
    const expenses = [];

    data.slice().reverse().forEach(item => {
        labels.push(`${item.month_name} ${item.year}`);
        income.push(item.income || 0);
        expenses.push(item.expenses || 0);
    });

    charts.trend.data.labels = labels;
    charts.trend.data.datasets[0].data = income;
    charts.trend.data.datasets[1].data = expenses;
    charts.trend.update();
}

function updateMonthlyReportChart(data) {
    const ctx = document.getElementById('monthlyReportChart');
    if (!ctx || !data) return;

    if (charts.monthlyReport) {
        charts.monthlyReport.destroy();
    }

    const labels = data.map(d => `${d.month_name} ${d.year}`);
    const income = data.map(d => d.total_income || 0);
    const expenses = data.map(d => d.total_expenses || 0);
    const savings = data.map(d => d.net_savings || 0);

    charts.monthlyReport = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Income',
                data: income,
                backgroundColor: 'rgba(75, 192, 192, 0.8)'
            }, {
                label: 'Expenses',
                data: expenses,
                backgroundColor: 'rgba(255, 99, 132, 0.8)'
            }, {
                label: 'Net Savings',
                data: savings,
                backgroundColor: 'rgba(54, 162, 235, 0.8)'
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'LKR ' + value.toLocaleString()
                    }
                }
            }
        }
    });
}

function updateCategoryReportChart(data, rangeType) {
    if (!data) return;

    // Destroy old charts if they exist
    if (charts.categoryIncome) {
        charts.categoryIncome.destroy();
    }
    if (charts.categoryExpense) {
        charts.categoryExpense.destroy();
    }

    // Aggregate data by category across all time periods
    const categoryTotals = {};
    data.forEach(item => {
        if (!categoryTotals[item.category]) {
            categoryTotals[item.category] = {
                type: item.type,
                income: 0,
                expense: 0
            };
        }
        categoryTotals[item.category].income += parseFloat(item.income || 0);
        categoryTotals[item.category].expense += parseFloat(item.expense || 0);
    });

    // Separate income and expense categories
    const incomeCategories = [];
    const incomeAmounts = [];
    const expenseCategories = [];
    const expenseAmounts = [];
    let totalIncome = 0;
    let totalExpense = 0;

    Object.entries(categoryTotals).forEach(([category, data]) => {
        if (data.type === 'income' && data.income > 0) {
            incomeCategories.push(category);
            incomeAmounts.push(data.income);
            totalIncome += data.income;
        } else if (data.type === 'expense' && data.expense > 0) {
            expenseCategories.push(category);
            expenseAmounts.push(data.expense);
            totalExpense += data.expense;
        }
    });

    // Create Income Chart (Horizontal Bar Chart)
    const incomeCtx = document.getElementById('categoryIncomeChart');
    if (incomeCtx && incomeCategories.length > 0) {
        charts.categoryIncome = new Chart(incomeCtx, {
            type: 'doughnut',
            data: {
                labels: incomeCategories,
                datasets: [{
                    data: incomeAmounts,
                    backgroundColor: [
                        'rgba(75, 192, 192, 0.8)',
                        'rgba(54, 162, 235, 0.8)',
                        'rgba(153, 102, 255, 0.8)',
                        'rgba(144, 238, 144, 0.8)',
                        'rgba(135, 206, 250, 0.8)',
                        'rgba(176, 224, 230, 0.8)'
                    ],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const percentage = ((ctx.parsed / totalIncome) * 100).toFixed(1);
                                return ctx.label + ': LKR ' + ctx.parsed.toLocaleString() + ' (' + percentage + '%)';
                            }
                        }
                    }
                }
            }
        });
    }

    // Create Expense Chart (Horizontal Bar Chart)
    const expenseCtx = document.getElementById('categoryExpenseChart');
    if (expenseCtx && expenseCategories.length > 0) {
        charts.categoryExpense = new Chart(expenseCtx, {
            type: 'doughnut',
            data: {
                labels: expenseCategories,
                datasets: [{
                    data: expenseAmounts,
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.8)',
                        'rgba(255, 159, 64, 0.8)',
                        'rgba(255, 206, 86, 0.8)',
                        'rgba(255, 99, 71, 0.8)',
                        'rgba(201, 203, 207, 0.8)',
                        'rgba(240, 230, 140, 0.8)',
                        'rgba(189, 183, 107, 0.8)',
                        'rgba(255, 182, 193, 0.8)',
                        'rgba(221, 160, 221, 0.8)',
                        'rgba(255, 228, 181, 0.8)'
                    ],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const percentage = ((ctx.parsed / totalExpense) * 100).toFixed(1);
                                return ctx.label + ': LKR ' + ctx.parsed.toLocaleString() + ' (' + percentage + '%)';
                            }
                        }
                    }
                }
            }
        });
    }

    // Update summary tables
    updateCategorySummaryTables(categoryTotals, totalIncome, totalExpense);

    // Update net savings
    updateNetSavings(totalIncome, totalExpense);
}

// Helper function to get consistent colors for categories
function getColorForIndex(index) {
    const colors = [
        'rgba(255, 99, 132, 0.8)',
        'rgba(54, 162, 235, 0.8)',
        'rgba(255, 206, 86, 0.8)',
        'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)',
        'rgba(255, 159, 64, 0.8)',
        'rgba(201, 203, 207, 0.8)',
        'rgba(255, 99, 71, 0.8)',
        'rgba(144, 238, 144, 0.8)',
        'rgba(135, 206, 250, 0.8)',
        'rgba(255, 182, 193, 0.8)',
        'rgba(176, 224, 230, 0.8)',
        'rgba(221, 160, 221, 0.8)',
        'rgba(240, 230, 140, 0.8)',
        'rgba(189, 183, 107, 0.8)'
    ];
    return colors[index % colors.length];
}

// Update category summary tables (separate income and expense)
function updateCategorySummaryTables(categoryTotals, totalIncome, totalExpense) {
    const incomeTableBody = document.getElementById('incomeTableBody');
    const expenseTableBody = document.getElementById('expenseTableBody');
    const totalIncomeElement = document.getElementById('totalIncome');
    const totalExpensesElement = document.getElementById('totalExpenses');

    if (!incomeTableBody || !expenseTableBody) return;

    // Prepare income rows
    const incomeRows = [];
    const expenseRows = [];

    Object.entries(categoryTotals).forEach(([category, data]) => {
        if (data.type === 'income' && data.income > 0) {
            incomeRows.push({ category, amount: data.income });
        } else if (data.type === 'expense' && data.expense > 0) {
            expenseRows.push({ category, amount: data.expense });
        }
    });

    // Sort by amount descending
    incomeRows.sort((a, b) => b.amount - a.amount);
    expenseRows.sort((a, b) => b.amount - a.amount);

    // Build income table HTML
    incomeTableBody.innerHTML = incomeRows.map(row => {
        const percentage = totalIncome > 0 ? ((row.amount / totalIncome) * 100).toFixed(1) : 0;
        return `
            <tr>
                <td>${row.category}</td>
                <td class="text-end">LKR ${row.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td class="text-end">${percentage}%</td>
            </tr>
        `;
    }).join('');

    // Build expense table HTML
    expenseTableBody.innerHTML = expenseRows.map(row => {
        const percentage = totalExpense > 0 ? ((row.amount / totalExpense) * 100).toFixed(1) : 0;
        return `
            <tr>
                <td>${row.category}</td>
                <td class="text-end">LKR ${row.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td class="text-end">${percentage}%</td>
            </tr>
        `;
    }).join('');

    // Update totals
    totalIncomeElement.textContent = `LKR ${totalIncome.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    totalExpensesElement.textContent = `LKR ${totalExpense.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

// Update net savings display
function updateNetSavings(totalIncome, totalExpense) {
    const netSavingsElement = document.getElementById('netSavings');
    const savingsPercentageElement = document.getElementById('savingsPercentage');
    const netSavingsCard = document.getElementById('netSavingsCard');

    if (!netSavingsElement || !savingsPercentageElement || !netSavingsCard) return;

    const netSavings = totalIncome - totalExpense;
    const savingsRate = totalIncome > 0 ? ((netSavings / totalIncome) * 100).toFixed(1) : 0;

    // Update text
    netSavingsElement.textContent = `LKR ${netSavings.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    savingsPercentageElement.textContent = `${savingsRate}% savings rate`;

    // Update card styling based on savings
    netSavingsCard.className = 'card';
    if (netSavings > 0) {
        netSavingsCard.classList.add('border-success');
        netSavingsElement.classList.add('text-success');
    } else if (netSavings < 0) {
        netSavingsCard.classList.add('border-danger');
        netSavingsElement.classList.add('text-danger');
    } else {
        netSavingsCard.classList.add('border-secondary');
        netSavingsElement.classList.add('text-secondary');
    }
}

function updateCashFlowChart(data, rangeType) {
    const ctx = document.getElementById('cashFlowReportChart');
    if (!ctx || !data) return;

    if (charts.cashFlowReport) {
        charts.cashFlowReport.destroy();
    }

    let labels, cashIn, cashOut, netFlow;

    if (rangeType === 'weekly') {
        labels = data.map(d => `Week ${d.week_num}: ${d.week_start} to ${d.week_end}`);
        cashIn = data.map(d => d.cash_in || 0);
        cashOut = data.map(d => d.cash_out || 0);
        netFlow = data.map(d => d.net_flow || 0);
    } else if (rangeType === 'yearly') {
        labels = data.map(d => `${d.year}`);
        cashIn = data.map(d => d.cash_in || 0);
        cashOut = data.map(d => d.cash_out || 0);
        netFlow = data.map(d => d.net_flow || 0);
    } else {
        labels = data.map(d => `${d.month_name} ${d.year}`);
        cashIn = data.map(d => d.cash_in || 0);
        cashOut = data.map(d => d.cash_out || 0);
        netFlow = data.map(d => d.net_flow || 0);
    }

    charts.cashFlowReport = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Cash In',
                data: cashIn,
                borderColor: 'rgba(75, 192, 192, 1)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                fill: true,
                tension: 0.4
            }, {
                label: 'Cash Out',
                data: cashOut,
                borderColor: 'rgba(255, 99, 132, 1)',
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                fill: true,
                tension: 0.4
            }, {
                label: 'Net Flow',
                data: netFlow,
                borderColor: 'rgba(54, 162, 235, 1)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'LKR ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': LKR ' + ctx.parsed.y.toLocaleString()
                    }
                }
            }
        }
    });
}

function updateTopSpendingChart(data) {
    const ctx = document.getElementById('topSpendingReportChart');
    if (!ctx || !data) return;

    if (charts.topSpendingReport) {
        charts.topSpendingReport.destroy();
    }

    const labels = data.map(d => d.category || 'Uncategorized');
    const amounts = data.map(d => d.total_spent || 0);
    const counts = data.map(d => d.transaction_count || 0);

    charts.topSpendingReport = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Total Spent',
                data: amounts,
                backgroundColor: 'rgba(255, 99, 132, 0.8)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'LKR ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const index = ctx.dataIndex;
                            return [
                                'Total: LKR ' + ctx.parsed.x.toLocaleString(),
                                'Transactions: ' + counts[index],
                                'Average: LKR ' + (amounts[index] / counts[index]).toLocaleString()
                            ];
                        }
                    }
                }
            }
        }
    });
}

function updateForecastChart(data) {
    const ctx = document.getElementById('forecastReportChart');
    if (!ctx || !data) return;

    if (charts.forecastReport) {
        charts.forecastReport.destroy();
    }

    const forecast = data.next_month_forecast;
    const historical = data.historical_average;

    // Update forecast summary
    const summaryDiv = document.getElementById('forecastSummary');
    if (summaryDiv) {
        const confidenceText = forecast.confidence === 'medium' ? 'Medium' :
                               forecast.confidence === 'low' ? 'Low' : 'No Data';
        const trendText = forecast.expense_trend > 0 ?
            `trending up by ${forecast.expense_trend.toFixed(1)}%` :
            forecast.expense_trend < 0 ?
            `trending down by ${Math.abs(forecast.expense_trend).toFixed(1)}%` :
            'stable';

        summaryDiv.innerHTML = `
            <h5>Next Month Forecast (Confidence: ${confidenceText})</h5>
            <p><strong>Predicted Income:</strong> LKR ${forecast.predicted_income.toLocaleString()}</p>
            <p><strong>Predicted Expenses:</strong> LKR ${forecast.predicted_expenses.toLocaleString()}
               <span class="badge ${forecast.expense_trend > 0 ? 'bg-danger' : 'bg-success'}">${trendText}</span>
            </p>
            <p><strong>Predicted Savings:</strong> LKR ${forecast.predicted_savings.toLocaleString()}</p>
            <p class="text-muted">Based on ${data.based_on_months} months of historical data</p>
        `;
    }

    // Create comparison chart
    charts.forecastReport = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Historical Average', 'Next Month Forecast'],
            datasets: [{
                label: 'Income',
                data: [historical.avg_income, forecast.predicted_income],
                backgroundColor: 'rgba(75, 192, 192, 0.8)'
            }, {
                label: 'Expenses',
                data: [historical.avg_expenses, forecast.predicted_expenses],
                backgroundColor: 'rgba(255, 99, 132, 0.8)'
            }, {
                label: 'Savings',
                data: [historical.avg_savings, forecast.predicted_savings],
                backgroundColor: 'rgba(54, 162, 235, 0.8)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'LKR ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': LKR ' + ctx.parsed.y.toLocaleString()
                    }
                }
            }
        }
    });

    // Update category forecast table
    const tbody = document.getElementById('forecastTableBody');
    if (tbody && data.category_forecast) {
        tbody.innerHTML = data.category_forecast.map(d => `
            <tr>
                <td>${d.category || 'Uncategorized'}</td>
                <td>LKR ${(d.avg_monthly_spending || 0).toLocaleString()}</td>
                <td>LKR ${(d.min_spending || 0).toLocaleString()}</td>
                <td>LKR ${(d.max_spending || 0).toLocaleString()}</td>
                <td>LKR ${(d.std_deviation || 0).toLocaleString()}</td>
            </tr>
        `).join('');
    }
}

// ================================
// UTILITIES
// ================================

function populateDateSelectors() {
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;

    // Month selectors
    const monthSelects = ['monthSelect', 'cloneFromMonth', 'cloneToMonth'];
    const months = ['January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'];

    monthSelects.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.innerHTML = '';
            months.forEach((month, index) => {
                const option = document.createElement('option');
                option.value = index + 1;
                option.textContent = month;
                if (index + 1 === currentMonth) option.selected = true;
                select.appendChild(option);
            });
        }
    });

    // Year selectors
    const yearSelects = ['yearSelect', 'cloneFromYear', 'cloneToYear'];
    yearSelects.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.innerHTML = '';
            for (let year = currentYear - 2; year <= currentYear + 1; year++) {
                const option = document.createElement('option');
                option.value = year;
                option.textContent = year;
                if (year === currentYear) option.selected = true;
                select.appendChild(option);
            }
        }
    });

    // Add event listener for clone execute button
    const executeCloneBtn = document.getElementById('executeCloneBtn');
    if (executeCloneBtn) {
        executeCloneBtn.addEventListener('click', executeCloneMonth);
    }
}

function closeModal(modalId) {
    const modalEl = document.getElementById(modalId);
    if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) {
            modal.hide();
        }
    }
}

// ================================
// PAYMENT METHODS
// ================================

function loadPaymentMethods() {
    fetch('/api/payment-methods')
        .then(response => response.json())
        .then(methods => {
            // Ensure we always have an array
            paymentMethods = Array.isArray(methods) ? methods : [];
            console.log('✓ Loaded', paymentMethods.length, 'payment methods');

            // Populate filter dropdown
            const filterDropdown = document.getElementById('filterPaymentMethod');
            if (filterDropdown) {
                filterDropdown.innerHTML = '<option value="">All Payment Methods</option>';
                paymentMethods.forEach(method => {
                    filterDropdown.innerHTML += `<option value="${method.id}">${method.name}</option>`;
                });
            }
        })
        .catch(error => {
            console.error('✗ Error loading payment methods:', error);
            paymentMethods = []; // Ensure it stays an array on error
            showToast('Error loading payment methods', 'danger');
        });
}

function showPaymentMethodModal(transactionId, isPaidClick = false) {
    currentTransactionId = transactionId;
    const modalEl = document.getElementById('paymentMethodModal');
    const listEl = document.getElementById('paymentMethodList');

    // Clear and populate payment methods
    listEl.innerHTML = '';

    // Check if paymentMethods is an array
    if (!Array.isArray(paymentMethods) || paymentMethods.length === 0) {
        listEl.innerHTML = '<div class="alert alert-warning">No payment methods available. Please add a payment method first.</div>';
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
        return;
    }

    paymentMethods.forEach(method => {
        const item = document.createElement('a');
        item.href = '#';
        item.className = 'list-group-item list-group-item-action payment-method-list-item';
        item.innerHTML = `
            <span class="payment-method-color-indicator" style="background-color: ${method.color}"></span>
            <strong>${method.name}</strong>
            <span class="badge bg-secondary float-end">${method.type === 'cash' ? 'Cash' : 'Credit Card'}</span>
        `;
        item.onclick = (e) => {
            e.preventDefault();
            if (isPaidClick) {
                markTransactionAsPaid(transactionId, method.id);
            } else {
                markTransactionWithPaymentMethod(transactionId, method.id);
            }
        };
        listEl.appendChild(item);
    });

    const modal = new bootstrap.Modal(modalEl);
    modal.show();
}

function markTransactionWithPaymentMethod(transactionId, paymentMethodId) {
    showLoading();

    // Get geolocation if available
    getGeolocation().then(location => {
        const requestBody = { payment_method_id: paymentMethodId };

        // Add location data if available
        if (location) {
            requestBody.latitude = location.latitude;
            requestBody.longitude = location.longitude;
            requestBody.accuracy = location.accuracy;
        }

        fetch(`/api/transactions/${transactionId}/mark-done`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            if (data.error) {
                showToast(data.error, 'danger');
            } else {
                showToast('Transaction marked as done', 'success');
                closeModal('paymentMethodModal');
                loadTransactions();
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Error:', error);
            showToast('Error marking transaction', 'danger');
        });
    });
}

function unmarkTransaction(transactionId) {
    showLoading();

    fetch(`/api/transactions/${transactionId}/mark-undone`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        showToast('Transaction unmarked', 'success');
        loadTransactions();
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showToast('Error unmarking transaction', 'danger');
    });
}

function markTransactionAsPaid(transactionId, paymentMethodId) {
    showLoading();

    // Get geolocation if available
    getGeolocation().then(location => {
        const requestBody = { payment_method_id: paymentMethodId };

        // Add location data if available
        if (location) {
            requestBody.latitude = location.latitude;
            requestBody.longitude = location.longitude;
            requestBody.accuracy = location.accuracy;
        }

        fetch(`/api/transactions/${transactionId}/mark-paid`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            if (data.error) {
                showToast(data.error, 'danger');
            } else {
                showToast('Transaction marked as paid', 'success');
                closeModal('paymentMethodModal');
                loadTransactions();
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Error:', error);
            showToast('Error marking transaction as paid', 'danger');
        });
    });
}

function markTransactionAsUnpaid(transactionId) {
    showLoading();

    fetch(`/api/transactions/${transactionId}/mark-unpaid`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Transaction marked as unpaid', 'success');
            loadTransactions();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showToast('Error unmarking transaction as paid', 'danger');
    });
}

function showAddCreditCardForm() {
    document.getElementById('addCreditCardForm').style.display = 'block';
}

function hideAddCreditCardForm() {
    document.getElementById('addCreditCardForm').style.display = 'none';
    document.getElementById('creditCardForm').reset();
}

function saveCreditCard(e) {
    e.preventDefault();

    const cardData = {
        name: document.getElementById('cardName').value,
        type: 'credit_card',
        color: document.getElementById('cardColor').value
    };

    showLoading();

    fetch('/api/payment-methods', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cardData)
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Credit card added successfully', 'success');
            hideAddCreditCardForm();
            loadPaymentMethods();
            loadCreditCardsList();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showToast('Error adding credit card', 'danger');
    });
}

function loadCreditCardsList() {
    const listEl = document.getElementById('creditCardsList');
    listEl.innerHTML = '';

    // Check if paymentMethods is an array
    if (!Array.isArray(paymentMethods)) {
        listEl.innerHTML = '<p class="text-muted">No credit cards added yet.</p>';
        return;
    }

    const creditCards = paymentMethods.filter(m => m.type === 'credit_card');

    if (creditCards.length === 0) {
        listEl.innerHTML = '<p class="text-muted">No credit cards added yet.</p>';
        return;
    }

    creditCards.forEach(card => {
        const item = document.createElement('div');
        item.className = 'credit-card-item';
        item.innerHTML = `
            <div class="credit-card-color" style="background-color: ${card.color}"></div>
            <div class="flex-grow-1">
                <strong>${card.name}</strong>
            </div>
            <button class="btn btn-sm btn-danger" onclick="deleteCreditCard(${card.id})">
                <i class="fas fa-trash"></i>
            </button>
        `;
        listEl.appendChild(item);
    });
}

function deleteCreditCard(cardId) {
    showConfirmModal(
        'Delete Credit Card',
        'Are you sure you want to delete this credit card? This action cannot be undone.',
        function() {
            showLoading();
            fetch(`/api/payment-methods/${cardId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                hideLoading();
                showToast('Credit card deleted successfully', 'success');
                loadPaymentMethods();
                loadCreditCardsList();
            })
            .catch(error => {
                hideLoading();
                console.error('Error:', error);
                showToast('Error deleting credit card', 'danger');
            });
        },
        'Delete',
        'btn-danger'
    );
}

// Load credit cards when the manage modal is shown
document.addEventListener('DOMContentLoaded', function() {
    const manageCCModal = document.getElementById('manageCreditCardsModal');
    if (manageCCModal) {
        manageCCModal.addEventListener('shown.bs.modal', loadCreditCardsList);
    }
});

// Note: formatCurrency, formatDate, showLoading, hideLoading, showToast
// are defined in base.html and available globally
