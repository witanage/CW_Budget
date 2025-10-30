// Dashboard JavaScript
let trendChart, categoryChart, monthlyReportChart, categoryReportChart, yearlyReportChart;
let currentCategories = [];

document.addEventListener('DOMContentLoaded', function() {
    initializeDashboard();
    loadCategories();
    setupEventListeners();
    loadDashboardStats();
    initializeCharts();
    populateDateSelectors();
});

function initializeDashboard() {
    // Set current date
    const today = new Date();
    document.getElementById('transDate').value = today.toISOString().split('T')[0];
}

function setupEventListeners() {
    // Sidebar navigation
    document.querySelectorAll('.sidebar .nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const page = this.dataset.page;
            switchPage(page);
        });
    });
    
    // Refresh button
    document.getElementById('refreshBtn').addEventListener('click', loadDashboardStats);
    
    // Transaction form
    document.getElementById('saveTransactionBtn').addEventListener('click', saveTransaction);
    document.getElementById('loadTransactionsBtn').addEventListener('click', loadTransactions);
    
    // Budget form
    document.getElementById('saveBudgetBtn').addEventListener('click', saveBudget);
    document.getElementById('loadBudgetBtn').addEventListener('click', loadBudget);
    
    // Recurring form
    document.getElementById('saveRecurringBtn').addEventListener('click', saveRecurring);
    document.getElementById('applyRecurringBtn').addEventListener('click', applyRecurring);
    
    // Import form
    document.getElementById('importForm').addEventListener('submit', importExcel);
}

function switchPage(page) {
    // Hide all pages
    document.querySelectorAll('.page-content').forEach(p => {
        p.style.display = 'none';
    });
    
    // Remove active class from all nav links
    document.querySelectorAll('.sidebar .nav-link').forEach(link => {
        link.classList.remove('active');
    });
    
    // Show selected page
    document.getElementById(page + 'Page').style.display = 'block';
    
    // Add active class to selected nav link
    document.querySelector(`.sidebar .nav-link[data-page="${page}"]`).classList.add('active');
    
    // Load page-specific data
    switch(page) {
        case 'transactions':
            loadTransactions();
            break;
        case 'budget':
            loadBudget();
            break;
        case 'recurring':
            loadRecurringTransactions();
            break;
        case 'reports':
            loadReports();
            break;
    }
}

function loadCategories() {
    fetch('/api/categories')
        .then(response => response.json())
        .then(categories => {
            currentCategories = categories;
            
            // Populate category dropdowns
            const selects = ['transCategory', 'budgetCategory', 'recCategory'];
            selects.forEach(selectId => {
                const select = document.getElementById(selectId);
                if (select) {
                    select.innerHTML = '<option value="">Select Category</option>';
                    categories.forEach(cat => {
                        select.innerHTML += `<option value="${cat.id}">${cat.name} (${cat.type})</option>`;
                    });
                }
            });
        })
        .catch(error => {
            console.error('Error loading categories:', error);
            showToast('Error loading categories', 'danger');
        });
}

function loadDashboardStats() {
    showLoading();
    fetch('/api/dashboard-stats')
        .then(response => response.json())
        .then(data => {
            // Update stat cards
            if (data.current_stats) {
                document.getElementById('currentBalance').textContent = 
                    formatCurrency(data.current_stats.current_balance || 0);
                document.getElementById('monthlyIncome').textContent = 
                    formatCurrency(data.current_stats.total_income || 0);
                document.getElementById('monthlyExpenses').textContent = 
                    formatCurrency(data.current_stats.total_expenses || 0);
                
                const savingsRate = data.current_stats.total_income > 0 ? 
                    ((data.current_stats.total_income - data.current_stats.total_expenses) / 
                     data.current_stats.total_income * 100).toFixed(1) : 0;
                document.getElementById('savingsRate').textContent = savingsRate + '%';
            }
            
            // Update recent transactions table
            if (data.recent_transactions) {
                updateRecentTransactionsTable(data.recent_transactions);
            }
            
            // Update charts
            if (data.monthly_trend) {
                updateTrendChart(data.monthly_trend);
            }
            
            hideLoading();
        })
        .catch(error => {
            hideLoading();
            console.error('Error loading dashboard stats:', error);
            showToast('Error loading dashboard statistics', 'danger');
        });
}

function updateRecentTransactionsTable(transactions) {
    const tbody = document.querySelector('#recentTransactionsTable tbody');
    tbody.innerHTML = '';
    
    transactions.forEach(trans => {
        const row = tbody.insertRow();
        row.innerHTML = `
            <td>${trans.transaction_date ? formatDate(trans.transaction_date) : '-'}</td>
            <td>${trans.description}</td>
            <td><span class="badge bg-secondary">${trans.category || 'Uncategorized'}</span></td>
            <td class="text-success">${trans.debit ? formatCurrency(trans.debit) : '-'}</td>
            <td class="text-danger">${trans.credit ? formatCurrency(trans.credit) : '-'}</td>
            <td class="fw-bold">${trans.balance ? formatCurrency(trans.balance) : '-'}</td>
        `;
    });
    
    if (transactions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">No transactions found</td></tr>';
    }
}

function initializeCharts() {
    // Trend Chart
    const trendCtx = document.getElementById('trendChart');
    if (trendCtx) {
        trendChart = new Chart(trendCtx, {
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
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
    }
    
    // Category Chart
    const categoryCtx = document.getElementById('categoryChart');
    if (categoryCtx) {
        categoryChart = new Chart(categoryCtx, {
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
                    legend: {
                        position: 'bottom',
                    }
                }
            }
        });
    }
}

function updateTrendChart(monthlyData) {
    if (!trendChart) return;
    
    const labels = [];
    const incomeData = [];
    const expenseData = [];
    
    // Reverse to show oldest to newest
    monthlyData.reverse().forEach(item => {
        labels.push(`${item.month_name} ${item.year}`);
        incomeData.push(item.income || 0);
        expenseData.push(item.expenses || 0);
    });
    
    trendChart.data.labels = labels;
    trendChart.data.datasets[0].data = incomeData;
    trendChart.data.datasets[1].data = expenseData;
    trendChart.update();
}

function updateCategoryChart(categoryData) {
    if (!categoryChart) return;
    
    const labels = [];
    const data = [];
    
    categoryData.forEach(item => {
        if (item.type === 'expense' && item.amount > 0) {
            labels.push(item.category);
            data.push(item.amount);
        }
    });
    
    categoryChart.data.labels = labels;
    categoryChart.data.datasets[0].data = data;
    categoryChart.update();
}

function saveTransaction() {
    const year = document.getElementById('yearSelect').value || new Date().getFullYear();
    const month = document.getElementById('monthSelect').value || new Date().getMonth() + 1;
    
    const transactionData = {
        description: document.getElementById('transDescription').value,
        category_id: document.getElementById('transCategory').value || null,
        debit: parseFloat(document.getElementById('transDebit').value) || null,
        credit: parseFloat(document.getElementById('transCredit').value) || null,
        transaction_date: document.getElementById('transDate').value,
        notes: document.getElementById('transNotes').value,
        year: parseInt(year),
        month: parseInt(month)
    };
    
    fetch('/api/transactions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(transactionData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Transaction saved successfully', 'success');
            document.getElementById('transactionForm').reset();
            bootstrap.Modal.getInstance(document.getElementById('transactionModal')).hide();
            loadTransactions();
            loadDashboardStats();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error saving transaction', 'danger');
    });
}

function loadTransactions() {
    const year = document.getElementById('yearSelect').value || new Date().getFullYear();
    const month = document.getElementById('monthSelect').value || new Date().getMonth() + 1;
    
    showLoading();
    fetch(`/api/transactions?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(transactions => {
            hideLoading();
            updateTransactionsTable(transactions);
        })
        .catch(error => {
            hideLoading();
            console.error('Error loading transactions:', error);
            showToast('Error loading transactions', 'danger');
        });
}

function updateTransactionsTable(transactions) {
    const tbody = document.querySelector('#transactionsTable tbody');
    tbody.innerHTML = '';
    
    transactions.forEach(trans => {
        const row = tbody.insertRow();
        row.innerHTML = `
            <td>${trans.id}</td>
            <td>${trans.description}</td>
            <td><span class="badge bg-secondary">${trans.category_name || 'Uncategorized'}</span></td>
            <td class="text-success">${trans.debit ? formatCurrency(trans.debit) : '-'}</td>
            <td class="text-danger">${trans.credit ? formatCurrency(trans.credit) : '-'}</td>
            <td class="fw-bold">${trans.balance ? formatCurrency(trans.balance) : '-'}</td>
            <td>${trans.notes || '-'}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="deleteTransaction(${trans.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
    });
    
    if (transactions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">No transactions found for this period</td></tr>';
    }
}

function deleteTransaction(id) {
    if (confirm('Are you sure you want to delete this transaction?')) {
        fetch(`/api/transactions/${id}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            showToast('Transaction deleted successfully', 'success');
            loadTransactions();
            loadDashboardStats();
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Error deleting transaction', 'danger');
        });
    }
}

function loadRecurringTransactions() {
    showLoading();
    fetch('/api/recurring-transactions')
        .then(response => response.json())
        .then(recurring => {
            hideLoading();
            updateRecurringTable(recurring);
        })
        .catch(error => {
            hideLoading();
            console.error('Error loading recurring transactions:', error);
            showToast('Error loading recurring transactions', 'danger');
        });
}

function updateRecurringTable(recurring) {
    const tbody = document.querySelector('#recurringTable tbody');
    tbody.innerHTML = '';
    
    recurring.forEach(rec => {
        const row = tbody.insertRow();
        row.innerHTML = `
            <td>${rec.description}</td>
            <td><span class="badge bg-secondary">${rec.category_name || 'Uncategorized'}</span></td>
            <td><span class="badge ${rec.type === 'debit' ? 'bg-success' : 'bg-danger'}">${rec.type}</span></td>
            <td>${formatCurrency(rec.amount)}</td>
            <td>${rec.day_of_month || 'Any'}</td>
            <td>${rec.start_date ? formatDate(rec.start_date) : '-'}</td>
            <td>${rec.end_date ? formatDate(rec.end_date) : '-'}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="deleteRecurring(${rec.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
    });
    
    if (recurring.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center">No recurring transactions found</td></tr>';
    }
}

function saveRecurring() {
    const recurringData = {
        description: document.getElementById('recDescription').value,
        category_id: document.getElementById('recCategory').value || null,
        type: document.getElementById('recType').value,
        amount: parseFloat(document.getElementById('recAmount').value),
        day_of_month: parseInt(document.getElementById('recDay').value) || null,
        start_date: document.getElementById('recStart').value || null,
        end_date: document.getElementById('recEnd').value || null
    };
    
    fetch('/api/recurring-transactions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(recurringData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Recurring transaction saved successfully', 'success');
            document.getElementById('recurringForm').reset();
            bootstrap.Modal.getInstance(document.getElementById('recurringModal')).hide();
            loadRecurringTransactions();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error saving recurring transaction', 'danger');
    });
}

function applyRecurring() {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth() + 1;
    
    if (confirm(`Apply recurring transactions for ${month}/${year}?`)) {
        showLoading();
        fetch(`/api/apply-recurring/${year}/${month}`)
            .then(response => response.json())
            .then(data => {
                hideLoading();
                showToast(data.message, 'success');
                loadDashboardStats();
            })
            .catch(error => {
                hideLoading();
                console.error('Error:', error);
                showToast('Error applying recurring transactions', 'danger');
            });
    }
}

function loadBudget() {
    const year = document.getElementById('budgetYear').value || new Date().getFullYear();
    const month = document.getElementById('budgetMonth').value || new Date().getMonth() + 1;
    
    showLoading();
    fetch(`/api/budget?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(budgets => {
            hideLoading();
            updateBudgetDisplay(budgets);
            
            // Also load category breakdown for comparison
            fetch(`/api/reports/category-breakdown?year=${year}&month=${month}`)
                .then(response => response.json())
                .then(categoryData => {
                    updateCategoryChart(categoryData);
                });
        })
        .catch(error => {
            hideLoading();
            console.error('Error loading budget:', error);
            showToast('Error loading budget', 'danger');
        });
}

function updateBudgetDisplay(budgets) {
    const budgetList = document.getElementById('budgetList');
    budgetList.innerHTML = '';
    
    budgets.forEach(budget => {
        const percentage = budget.planned_amount > 0 ? 
            (budget.actual_amount / budget.planned_amount * 100).toFixed(1) : 0;
        
        const progressColor = percentage > 100 ? 'danger' : 
                             percentage > 80 ? 'warning' : 'success';
        
        const budgetCard = `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="row align-items-center">
                        <div class="col-md-3">
                            <h6 class="mb-0">${budget.category_name}</h6>
                            <small class="text-muted">${budget.category_type}</small>
                        </div>
                        <div class="col-md-3">
                            <small class="text-muted">Planned</small>
                            <h6 class="mb-0">${formatCurrency(budget.planned_amount)}</h6>
                        </div>
                        <div class="col-md-3">
                            <small class="text-muted">Actual</small>
                            <h6 class="mb-0">${formatCurrency(budget.actual_amount)}</h6>
                        </div>
                        <div class="col-md-3">
                            <div class="progress">
                                <div class="progress-bar bg-${progressColor}" 
                                     role="progressbar" 
                                     style="width: ${Math.min(percentage, 100)}%">
                                    ${percentage}%
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        budgetList.innerHTML += budgetCard;
    });
    
    if (budgets.length === 0) {
        budgetList.innerHTML = '<div class="alert alert-info">No budget items found for this period</div>';
    }
}

function saveBudget() {
    const year = document.getElementById('budgetYear').value || new Date().getFullYear();
    const month = document.getElementById('budgetMonth').value || new Date().getMonth() + 1;
    
    const budgetData = {
        category_id: document.getElementById('budgetCategory').value,
        planned_amount: parseFloat(document.getElementById('budgetAmount').value),
        year: parseInt(year),
        month: parseInt(month)
    };
    
    fetch('/api/budget', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(budgetData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Budget saved successfully', 'success');
            document.getElementById('budgetForm').reset();
            bootstrap.Modal.getInstance(document.getElementById('budgetModal')).hide();
            loadBudget();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error saving budget', 'danger');
    });
}

function loadReports() {
    const year = new Date().getFullYear();
    
    // Load monthly summary
    fetch(`/api/reports/monthly-summary?year=${year}`)
        .then(response => response.json())
        .then(data => {
            updateMonthlyReportChart(data);
        });
    
    // Load category breakdown
    fetch(`/api/reports/category-breakdown?year=${year}`)
        .then(response => response.json())
        .then(data => {
            updateCategoryReportChart(data);
        });
}

function updateMonthlyReportChart(data) {
    const ctx = document.getElementById('monthlyReportChart');
    if (!ctx) return;
    
    if (monthlyReportChart) {
        monthlyReportChart.destroy();
    }
    
    const labels = data.map(item => `${item.month_name} ${item.year}`);
    const income = data.map(item => item.total_income || 0);
    const expenses = data.map(item => item.total_expenses || 0);
    const savings = data.map(item => item.net_savings || 0);
    
    monthlyReportChart = new Chart(ctx, {
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
                        callback: function(value) {
                            return '$' + value.toLocaleString();
                        }
                    }
                }
            }
        }
    });
}

function updateCategoryReportChart(data) {
    const ctx = document.getElementById('categoryReportChart');
    if (!ctx) return;
    
    if (categoryReportChart) {
        categoryReportChart.destroy();
    }
    
    const expenseData = data.filter(item => item.type === 'expense');
    const labels = expenseData.map(item => item.category);
    const amounts = expenseData.map(item => item.amount);
    
    categoryReportChart = new Chart(ctx, {
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
                legend: {
                    position: 'right',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = '$' + context.parsed.toLocaleString();
                            return label + ': ' + value;
                        }
                    }
                }
            }
        }
    });
}

function importExcel(e) {
    e.preventDefault();
    
    const formData = new FormData();
    const fileInput = document.getElementById('excelFile');
    formData.append('file', fileInput.files[0]);
    
    showLoading();
    fetch('/api/import-excel', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        
        const importResults = document.getElementById('importResults');
        const importMessage = document.getElementById('importMessage');
        
        if (data.error) {
            importMessage.innerHTML = `<strong>Error:</strong> ${data.error}`;
            importResults.classList.remove('alert-info');
            importResults.classList.add('alert-danger');
        } else {
            importMessage.innerHTML = `
                <strong>Success!</strong> ${data.message}<br>
                Imported months: ${data.imported_months.join(', ')}
            `;
            importResults.classList.remove('alert-danger');
            importResults.classList.add('alert-success');
            
            // Clear the form
            document.getElementById('importForm').reset();
            
            // Reload dashboard stats
            loadDashboardStats();
        }
        
        importResults.style.display = 'block';
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showToast('Error importing Excel file', 'danger');
    });
}

function populateDateSelectors() {
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;
    
    // Populate month selectors
    const monthSelects = ['monthSelect', 'budgetMonth'];
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                       'July', 'August', 'September', 'October', 'November', 'December'];
    
    monthSelects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (select) {
            monthNames.forEach((month, index) => {
                const option = new Option(month, index + 1);
                if (index + 1 === currentMonth) {
                    option.selected = true;
                }
                select.add(option);
            });
        }
    });
    
    // Populate year selectors
    const yearSelects = ['yearSelect', 'budgetYear'];
    yearSelects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (select) {
            for (let year = currentYear - 2; year <= currentYear + 1; year++) {
                const option = new Option(year, year);
                if (year === currentYear) {
                    option.selected = true;
                }
                select.add(option);
            });
        }
    });
}
