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
        populateDateSelectors();

        // 4. Initialize charts
        initCharts();

        // 5. Load dashboard data
        loadDashboardStats();

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
        case 'recurring':
            loadRecurring();
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

    // Recurring form
    const saveRecBtn = document.getElementById('saveRecurringBtn');
    if (saveRecBtn) {
        saveRecBtn.addEventListener('click', saveRecurring);
    }

    const applyRecBtn = document.getElementById('applyRecurringBtn');
    if (applyRecBtn) {
        applyRecBtn.addEventListener('click', applyRecurring);
    }

    // Set today's date in transaction form
    const transDate = document.getElementById('transDate');
    if (transDate) {
        transDate.value = new Date().toISOString().split('T')[0];
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
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">No transactions for this period</td></tr>';
        return;
    }

    transactions.forEach(t => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${t.id}</td>
            <td>${t.description}</td>
            <td><span class="badge bg-secondary">${t.category_name || 'Uncategorized'}</span></td>
            <td class="text-success">${t.debit ? formatCurrency(t.debit) : '-'}</td>
            <td class="text-danger">${t.credit ? formatCurrency(t.credit) : '-'}</td>
            <td class="fw-bold">${t.balance ? formatCurrency(t.balance) : '-'}</td>
            <td>${t.notes || '-'}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="deleteTransaction(${t.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function saveTransaction() {
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

    fetch('/api/transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.error) {
            showToast(result.error, 'danger');
        } else {
            showToast('Transaction saved successfully', 'success');
            closeModal('transactionModal');
            document.getElementById('transactionForm')?.reset();
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
// RECURRING PAGE
// ================================

function loadRecurring() {
    showLoading();

    fetch('/api/recurring-transactions')
        .then(response => response.json())
        .then(data => {
            displayRecurring(data);
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading recurring:', error);
            hideLoading();
        });
}

function displayRecurring(items) {
    const tbody = document.querySelector('#recurringTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!items || items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">No recurring transactions</td></tr>';
        return;
    }

    items.forEach(r => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${r.description}</td>
            <td><span class="badge bg-secondary">${r.category_name || 'Uncategorized'}</span></td>
            <td><span class="badge ${r.type === 'debit' ? 'bg-success' : 'bg-danger'}">${r.type}</span></td>
            <td>${formatCurrency(r.amount)}</td>
            <td>${r.day_of_month || 'Any'}</td>
            <td>${r.start_date ? formatDate(r.start_date) : '-'}</td>
            <td>${r.end_date ? formatDate(r.end_date) : '-'}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="deleteRecurring(${r.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function saveRecurring() {
    const data = {
        description: document.getElementById('recDescription')?.value,
        category_id: document.getElementById('recCategory')?.value || null,
        type: document.getElementById('recType')?.value,
        amount: parseFloat(document.getElementById('recAmount')?.value),
        day_of_month: parseInt(document.getElementById('recDay')?.value) || null,
        start_date: document.getElementById('recStart')?.value || null,
        end_date: document.getElementById('recEnd')?.value || null
    };

    fetch('/api/recurring-transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.error) {
            showToast(result.error, 'danger');
        } else {
            showToast('Recurring transaction saved', 'success');
            closeModal('recurringModal');
            document.getElementById('recurringForm')?.reset();
            loadRecurring();
        }
    })
    .catch(error => {
        console.error('Error saving recurring:', error);
        showToast('Error saving recurring transaction', 'danger');
    });
}

function deleteRecurring(id) {
    if (!confirm('Delete this recurring transaction?')) return;

    fetch(`/api/recurring-transactions/${id}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(result => {
            showToast('Recurring transaction deleted', 'success');
            loadRecurring();
        })
        .catch(error => {
            console.error('Error deleting recurring:', error);
            showToast('Error deleting recurring transaction', 'danger');
        });
}

function applyRecurring() {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth() + 1;

    if (!confirm(`Apply recurring transactions for ${month}/${year}?`)) return;

    showLoading();

    fetch(`/api/apply-recurring/${year}/${month}`)
        .then(response => response.json())
        .then(result => {
            showToast(result.message, 'success');
            loadDashboardStats();
            hideLoading();
        })
        .catch(error => {
            console.error('Error applying recurring:', error);
            showToast('Error applying recurring transactions', 'danger');
            hideLoading();
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

// Note: formatCurrency, formatDate, showLoading, hideLoading, showToast
// are defined in base.html and available globally
