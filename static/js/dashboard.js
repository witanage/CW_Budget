// Personal Finance Manager - Dashboard JavaScript
// Clean, simple, and working version

// Global variables
let charts = {
    trend: null,
    category: null,
    monthlyReport: null,
    categoryReport: null,
    yearlyReport: null,
    cashFlowReport: null,
    topSpendingReport: null,
    forecastReport: null
};
let currentCategories = [];
let paymentMethods = [];
let currentTransactionId = null;

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
        case 'notifications':
            loadNotifications();
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

function loadTransactions() {
    const year = document.getElementById('yearSelect')?.value || new Date().getFullYear();
    const month = document.getElementById('monthSelect')?.value || (new Date().getMonth() + 1);

    showLoading();

    fetch(`/api/transactions?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            console.log('Transactions received:', data);
            displayTransactions(data);
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

    // Add event listeners
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
}

function loadAllReports(year, month, rangeType) {
    showLoading();

    Promise.all([
        fetch(`/api/reports/monthly-summary?year=${year}`)
            .then(response => response.json())
            .then(data => updateMonthlyReportChart(data)),

        fetch(`/api/reports/category-breakdown?year=${year}&month=${month}`)
            .then(response => response.json())
            .then(data => updateCategoryReportChart(data)),

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

function updateCategoryReportChart(data) {
    const ctx = document.getElementById('categoryReportChart');
    if (!ctx || !data) return;

    if (charts.categoryReport) {
        charts.categoryReport.destroy();
    }

    const expenseData = data.filter(d => d.type === 'expense');
    const labels = expenseData.map(d => d.category);
    const amounts = expenseData.map(d => d.amount);

    charts.categoryReport = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: amounts,
                backgroundColor: [
                    'rgba(255, 99, 132, 0.8)',
                    'rgba(54, 162, 235, 0.8)',
                    'rgba(255, 206, 86, 0.8)',
                    'rgba(75, 192, 192, 0.8)',
                    'rgba(153, 102, 255, 0.8)',
                    'rgba(255, 159, 64, 0.8)',
                    'rgba(201, 203, 207, 0.8)',
                    'rgba(255, 99, 71, 0.8)',
                    'rgba(144, 238, 144, 0.8)',
                    'rgba(135, 206, 250, 0.8)'
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'right' },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            return ctx.label + ': LKR ' + ctx.parsed.toLocaleString();
                        }
                    }
                }
            }
        }
    });
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

    fetch(`/api/transactions/${transactionId}/mark-done`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method_id: paymentMethodId })
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

    fetch(`/api/transactions/${transactionId}/mark-paid`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method_id: paymentMethodId })
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

    // Check for new notifications every 5 minutes
    setInterval(checkForNewNotifications, 5 * 60 * 1000);

    // Update notification badge initially
    setTimeout(updateNotificationBadge, 1000);

    // Check for notifications on first load
    setTimeout(checkForNewNotifications, 3000);

    // Notification buttons
    const markAllReadBtn = document.getElementById('markAllReadBtn');
    if (markAllReadBtn) {
        markAllReadBtn.addEventListener('click', () => {
            fetch('/api/notifications/mark-all-read', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadNotifications();
                    showToast('All notifications marked as read', 'success');
                }
            });
        });
    }

    const refreshNotificationsBtn = document.getElementById('refreshNotificationsBtn');
    if (refreshNotificationsBtn) {
        refreshNotificationsBtn.addEventListener('click', () => {
            checkForNewNotifications();
            setTimeout(() => loadNotifications(), 500);
        });
    }

    const savePreferencesBtn = document.getElementById('savePreferencesBtn');
    if (savePreferencesBtn) {
        savePreferencesBtn.addEventListener('click', savePreferences);
    }

    // Load preferences when modal is opened
    const preferencesModal = document.getElementById('preferencesModal');
    if (preferencesModal) {
        preferencesModal.addEventListener('show.bs.modal', loadPreferences);
    }
});

// ================================
// NOTIFICATIONS FUNCTIONS
// ================================

function loadNotifications() {
    showLoading();

    Promise.all([
        fetch('/api/notifications?limit=50')
            .then(response => response.json()),
        fetch('/api/preferences')
            .then(response => response.json())
    ])
    .then(([notifications, preferences]) => {
        displayNotifications(notifications);
        hideLoading();
        updateNotificationBadge();
    })
    .catch(error => {
        hideLoading();
        console.error('Error loading notifications:', error);
        showToast('Error loading notifications', 'danger');
    });
}

function displayNotifications(notifications) {
    const notificationsList = document.getElementById('notificationsList');

    if (!notifications || notifications.length === 0) {
        notificationsList.innerHTML = `
            <div class="text-center py-5 text-muted">
                <i class="fas fa-bell-slash fa-3x mb-3"></i>
                <p>No notifications yet</p>
                <small>We'll notify you about upcoming bills, budget limits, and unusual spending</small>
            </div>
        `;
        return;
    }

    notificationsList.innerHTML = notifications.map(notif => {
        const severityColors = {
            'info': 'primary',
            'warning': 'warning',
            'success': 'success',
            'danger': 'danger'
        };

        const typeIcons = {
            'bill_reminder': 'fa-file-invoice-dollar',
            'budget_alert': 'fa-exclamation-triangle',
            'unusual_spending': 'fa-chart-line',
            'goal_milestone': 'fa-trophy',
            'system': 'fa-info-circle'
        };

        const color = severityColors[notif.severity] || 'secondary';
        const icon = typeIcons[notif.type] || 'fa-bell';
        const isRead = notif.is_read;
        const readClass = isRead ? 'opacity-75' : '';

        return `
            <div class="list-group-item ${readClass}" data-notification-id="${notif.id}">
                <div class="d-flex w-100 justify-content-between">
                    <h6 class="mb-1">
                        <i class="fas ${icon} text-${color} me-2"></i>
                        ${notif.title}
                        ${!isRead ? '<span class="badge bg-primary ms-2">New</span>' : ''}
                    </h6>
                    <small class="text-muted">${timeAgo(notif.created_at)}</small>
                </div>
                <p class="mb-1">${notif.message}</p>
                <div class="d-flex justify-content-end gap-2">
                    ${!isRead ? `
                        <button class="btn btn-sm btn-outline-primary mark-read-btn" data-id="${notif.id}">
                            <i class="fas fa-check"></i> Mark Read
                        </button>
                    ` : ''}
                    <button class="btn btn-sm btn-outline-danger delete-notif-btn" data-id="${notif.id}">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            </div>
        `;
    }).join('');

    // Attach event listeners
    document.querySelectorAll('.mark-read-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            markNotificationRead(this.dataset.id);
        });
    });

    document.querySelectorAll('.delete-notif-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            deleteNotification(this.dataset.id);
        });
    });
}

function markNotificationRead(notificationId) {
    fetch(`/api/notifications/${notificationId}/read`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            loadNotifications();
        }
    })
    .catch(error => {
        console.error('Error marking notification as read:', error);
        showToast('Error updating notification', 'danger');
    });
}

function deleteNotification(notificationId) {
    if (!confirm('Delete this notification?')) return;

    fetch(`/api/notifications/${notificationId}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            loadNotifications();
            showToast('Notification deleted', 'success');
        }
    })
    .catch(error => {
        console.error('Error deleting notification:', error);
        showToast('Error deleting notification', 'danger');
    });
}

function updateNotificationBadge() {
    fetch('/api/notifications?unread_only=true')
        .then(response => response.json())
        .then(notifications => {
            const badge = document.getElementById('notificationBadge');
            if (notifications && notifications.length > 0) {
                badge.textContent = notifications.length;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Error updating notification badge:', error);
        });
}

function checkForNewNotifications() {
    fetch('/api/notifications/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.new_notifications > 0) {
            updateNotificationBadge();
            showToast(`${data.new_notifications} new notification(s)`, 'info');
        }
    })
    .catch(error => {
        console.error('Error checking notifications:', error);
    });
}

function loadPreferences() {
    fetch('/api/preferences')
        .then(response => response.json())
        .then(prefs => {
            document.getElementById('enableBillReminders').checked = prefs.enable_bill_reminders;
            document.getElementById('billReminderDays').value = prefs.bill_reminder_days_before || 3;
            document.getElementById('enableBudgetAlerts').checked = prefs.enable_budget_alerts;
            document.getElementById('monthlyBudgetLimit').value = prefs.monthly_budget_limit || '';
            document.getElementById('enableUnusualSpending').checked = prefs.enable_unusual_spending_detection;
            document.getElementById('unusualSpendingThreshold').value = prefs.unusual_spending_threshold_percentage || 150;
        })
        .catch(error => {
            console.error('Error loading preferences:', error);
        });
}

function savePreferences() {
    const prefs = {
        enable_bill_reminders: document.getElementById('enableBillReminders').checked,
        bill_reminder_days_before: parseInt(document.getElementById('billReminderDays').value),
        enable_budget_alerts: document.getElementById('enableBudgetAlerts').checked,
        monthly_budget_limit: document.getElementById('monthlyBudgetLimit').value ? parseFloat(document.getElementById('monthlyBudgetLimit').value) : null,
        enable_unusual_spending_detection: document.getElementById('enableUnusualSpending').checked,
        unusual_spending_threshold_percentage: parseInt(document.getElementById('unusualSpendingThreshold').value)
    };

    fetch('/api/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(prefs)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Preferences saved successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('preferencesModal')).hide();
        }
    })
    .catch(error => {
        console.error('Error saving preferences:', error);
        showToast('Error saving preferences', 'danger');
    });
}

function timeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)} days ago`;
    return date.toLocaleDateString();
}

// Note: formatCurrency, formatDate, showLoading, hideLoading, showToast
// are defined in base.html and available globally
