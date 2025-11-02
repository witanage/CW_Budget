// Personal Finance Manager - Dashboard JavaScript
// Clean, simple, and working version

// Global variables
let charts = {
    trend: null,
    category: null,
    monthlyReport: null,
    categoryReport: null,
    yearlyReport: null
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
        switchPage('transactions');

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

    // Setup refresh button
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => loadDashboardStats());
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
        case 'budget':
            loadBudget();
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
    // Transaction form
    const saveTransBtn = document.getElementById('saveTransactionBtn');
    if (saveTransBtn) {
        saveTransBtn.addEventListener('click', saveTransaction);
    }

    const loadTransBtn = document.getElementById('loadTransactionsBtn');
    if (loadTransBtn) {
        loadTransBtn.addEventListener('click', loadTransactions);
    }

    // Budget form
    const saveBudgetBtn = document.getElementById('saveBudgetBtn');
    if (saveBudgetBtn) {
        saveBudgetBtn.addEventListener('click', saveBudget);
    }

    const loadBudgetBtn = document.getElementById('loadBudgetBtn');
    if (loadBudgetBtn) {
        loadBudgetBtn.addEventListener('click', loadBudget);
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
    const dropdowns = ['transCategory', 'budgetCategory', 'recCategory'];

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

    transactions.forEach(t => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${t.transaction_date ? formatDate(t.transaction_date) : '-'}</td>
            <td>${t.description}</td>
            <td><span class="badge bg-secondary">${t.category || 'Uncategorized'}</span></td>
            <td class="text-success">${t.debit ? formatCurrency(t.debit) : '-'}</td>
            <td class="text-danger">${t.credit ? formatCurrency(t.credit) : '-'}</td>
            <td class="fw-bold">${t.balance ? formatCurrency(t.balance) : '-'}</td>
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

function displayTransactions(transactions) {
    const tbody = document.querySelector('#transactionsTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center">No transactions for this period</td></tr>';
        return;
    }

    transactions.forEach(t => {
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

        row.innerHTML = `
            <td class="text-center">${checkboxHtml}</td>
            <td>${t.id}</td>
            <td>${t.description}</td>
            <td><span class="badge bg-secondary">${t.category_name || 'Uncategorized'}</span></td>
            <td class="text-success">${t.debit ? formatCurrency(t.debit) : '-'}</td>
            <td class="text-danger">${t.credit ? formatCurrency(t.credit) : '-'}</td>
            <td class="fw-bold">${t.balance ? formatCurrency(t.balance) : '-'}</td>
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

        // Apply background color to all cells for proper highlighting
        if (isDone && t.payment_method_color) {
            console.log(`Highlighting transaction ${t.id} with color ${t.payment_method_color}`);
            row.classList.add('transaction-highlighted');
            const cells = row.querySelectorAll('td');
            cells.forEach(cell => {
                cell.style.backgroundColor = t.payment_method_color;
            });
        }

        tbody.appendChild(row);
    });
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

    const data = {
        description: document.getElementById('transDescription')?.value,
        category_id: document.getElementById('transCategory')?.value || null,
        debit: parseFloat(document.getElementById('transDebit')?.value) || null,
        credit: parseFloat(document.getElementById('transCredit')?.value) || null,
        transaction_date: document.getElementById('transDate')?.value,
        notes: document.getElementById('transNotes')?.value,
        year: parseInt(year),
        month: parseInt(month)
    };

    const url = isEdit ? `/api/transactions/${editId}` : '/api/transactions';
    const method = isEdit ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.error) {
            showToast(result.error, 'danger');
        } else {
            showToast(isEdit ? 'Transaction updated successfully' : 'Transaction saved successfully', 'success');
            closeModal('transactionModal');
            document.getElementById('transactionForm')?.reset();
            document.getElementById('editTransactionId').value = '';
            document.querySelector('#transactionModal .modal-title').textContent = 'Add Transaction';
            loadTransactions();
            loadDashboardStats();
        }
    })
    .catch(error => {
        console.error('Error saving transaction:', error);
        showToast('Error saving transaction', 'danger');
    });
}

function deleteTransaction(id) {
    if (!confirm('Delete this transaction?')) return;

    fetch(`/api/transactions/${id}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
            showToast('Transaction deleted', 'success');
            loadTransactions();
            loadDashboardStats();
        })
        .catch(error => {
            console.error('Error deleting transaction:', error);
            showToast('Error deleting transaction', 'danger');
        });
}

// ================================
// BUDGET PAGE
// ================================

function loadBudget() {
    const year = document.getElementById('budgetYear')?.value || new Date().getFullYear();
    const month = document.getElementById('budgetMonth')?.value || (new Date().getMonth() + 1);

    showLoading();

    fetch(`/api/budget?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            displayBudgets(data);
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading budget:', error);
            hideLoading();
        });
}

function displayBudgets(budgets) {
    const container = document.getElementById('budgetList');
    if (!container) return;

    container.innerHTML = '';

    if (!budgets || budgets.length === 0) {
        container.innerHTML = '<div class="alert alert-info">No budget items for this period</div>';
        return;
    }

    budgets.forEach(b => {
        const percent = b.planned_amount > 0 ? (b.actual_amount / b.planned_amount * 100).toFixed(1) : 0;
        const color = percent > 100 ? 'danger' : percent > 80 ? 'warning' : 'success';

        const card = document.createElement('div');
        card.className = 'card mb-3';
        card.innerHTML = `
            <div class="card-body">
                <div class="row align-items-center">
                    <div class="col-md-3">
                        <h6 class="mb-0">${b.category_name}</h6>
                        <small class="text-muted">${b.category_type}</small>
                    </div>
                    <div class="col-md-3">
                        <small class="text-muted">Planned</small>
                        <h6 class="mb-0">${formatCurrency(b.planned_amount)}</h6>
                    </div>
                    <div class="col-md-3">
                        <small class="text-muted">Actual</small>
                        <h6 class="mb-0">${formatCurrency(b.actual_amount)}</h6>
                    </div>
                    <div class="col-md-3">
                        <div class="progress">
                            <div class="progress-bar bg-${color}" style="width: ${Math.min(percent, 100)}%">
                                ${percent}%
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function saveBudget() {
    const year = document.getElementById('budgetYear')?.value || new Date().getFullYear();
    const month = document.getElementById('budgetMonth')?.value || (new Date().getMonth() + 1);

    const data = {
        category_id: document.getElementById('budgetCategory')?.value,
        planned_amount: parseFloat(document.getElementById('budgetAmount')?.value),
        year: parseInt(year),
        month: parseInt(month)
    };

    fetch('/api/budget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.error) {
            showToast(result.error, 'danger');
        } else {
            showToast('Budget saved successfully', 'success');
            closeModal('budgetModal');
            document.getElementById('budgetForm')?.reset();
            loadBudget();
        }
    })
    .catch(error => {
        console.error('Error saving budget:', error);
        showToast('Error saving budget', 'danger');
    });
}

// ================================
// REPORTS PAGE
// ================================

function loadReports() {
    const year = new Date().getFullYear();

    fetch(`/api/reports/monthly-summary?year=${year}`)
        .then(response => response.json())
        .then(data => {
            updateMonthlyReportChart(data);
        })
        .catch(error => console.error('Error loading monthly report:', error));

    fetch(`/api/reports/category-breakdown?year=${year}`)
        .then(response => response.json())
        .then(data => {
            updateCategoryReportChart(data);
        })
        .catch(error => console.error('Error loading category report:', error));
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

// ================================
// UTILITIES
// ================================

function populateDateSelectors() {
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;

    // Month selectors
    const monthSelects = ['monthSelect', 'budgetMonth'];
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
    const yearSelects = ['yearSelect', 'budgetYear'];
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
            paymentMethods = methods;
            console.log('✓ Loaded', methods.length, 'payment methods');
        })
        .catch(error => {
            console.error('✗ Error loading payment methods:', error);
            showToast('Error loading payment methods', 'danger');
        });
}

function showPaymentMethodModal(transactionId) {
    currentTransactionId = transactionId;
    const modalEl = document.getElementById('paymentMethodModal');
    const listEl = document.getElementById('paymentMethodList');

    // Clear and populate payment methods
    listEl.innerHTML = '';
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
            markTransactionWithPaymentMethod(transactionId, method.id);
        };
        listEl.appendChild(item);
    });

    const modal = new bootstrap.Modal(modalEl);
    modal.show();
}

function markTransactionWithPaymentMethod(transactionId, paymentMethodId) {
    fetch(`/api/transactions/${transactionId}/mark-done`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method_id: paymentMethodId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Transaction marked as done', 'success');
            closeModal('paymentMethodModal');
            loadTransactions();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error marking transaction', 'danger');
    });
}

function unmarkTransaction(transactionId) {
    fetch(`/api/transactions/${transactionId}/mark-undone`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        showToast('Transaction unmarked', 'success');
        loadTransactions();
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error unmarking transaction', 'danger');
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

    fetch('/api/payment-methods', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cardData)
    })
    .then(response => response.json())
    .then(data => {
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
        console.error('Error:', error);
        showToast('Error adding credit card', 'danger');
    });
}

function loadCreditCardsList() {
    const listEl = document.getElementById('creditCardsList');
    listEl.innerHTML = '';

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
    if (!confirm('Are you sure you want to delete this credit card?')) return;

    fetch(`/api/payment-methods/${cardId}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        showToast('Credit card deleted successfully', 'success');
        loadPaymentMethods();
        loadCreditCardsList();
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error deleting credit card', 'danger');
    });
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
