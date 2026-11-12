/*
 * Planner page: category budgets, recurring transactions, bills, savings goals
 * and notification settings. The markup is templates/partials/dashboard_planner.html
 * (lazy loaded by dashboard.js); loadPlanner() is called each time the page opens.
 */
(function () {
    'use strict';

    const state = {
        tab: 'budgets',
        categories: [],
        methods: [],
        rules: [],
        goals: [],
        openGoals: new Set(),
        refsLoaded: false
    };

    const $ = (id) => document.getElementById(id);
    const root = () => $('plannerPage');

    function esc(value) {
        const d = document.createElement('div');
        d.textContent = value == null ? '' : String(value);
        return d.innerHTML;
    }

    function money(n) {
        return typeof formatCurrency === 'function' ? formatCurrency(n) : Number(n || 0).toFixed(2);
    }

    function todayISO() {
        const d = new Date();
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    }

    function toast(message, type) {
        if (typeof showToast === 'function') showToast(message, type || 'info');
    }

    async function api(method, url, body) {
        const resp = await fetch(url, {
            method,
            headers: body ? { 'Content-Type': 'application/json' } : {},
            body: body ? JSON.stringify(body) : undefined,
            credentials: 'same-origin'
        });
        let data = null;
        try { data = await resp.json(); } catch (e) { /* non-JSON */ }
        if (!resp.ok) throw new Error((data && data.error) || 'Request failed (' + resp.status + ')');
        if (data === null) throw new Error('Session expired. Please log in again.');
        return data;
    }

    function fail(error) {
        toast(error.message || 'Something went wrong', 'danger');
    }

    function refreshTransactionViews() {
        if (typeof loadTransactions === 'function') loadTransactions();
        if (typeof loadSidebarWidgets === 'function') loadSidebarWidgets();
    }

    function setList(id, html) {
        const el = $(id);
        if (el) el.innerHTML = html;
    }

    const empty = (text) => '<div class="planner-empty">' + esc(text) + '</div>';

    // ------------------------------------------------------------------ tabs

    function showTab(name) {
        state.tab = name;
        root().querySelectorAll('[data-planner-tab]').forEach((a) =>
            a.classList.toggle('active', a.getAttribute('data-planner-tab') === name));
        root().querySelectorAll('[data-planner-pane]').forEach((pane) =>
            pane.classList.toggle('d-none', pane.getAttribute('data-planner-pane') !== name));
        loadTab(name);
    }

    function loadTab(name) {
        switch (name) {
            case 'budgets': return loadBudgets();
            case 'recurring': return loadRecurring();
            case 'bills': return loadBills();
            case 'goals': return loadGoals();
            case 'alerts': return loadSettings();
        }
    }

    async function loadRefs() {
        if (state.refsLoaded) return;
        try {
            const [cats, methods] = await Promise.all([api('GET', '/api/categories'), api('GET', '/api/payment-methods')]);
            state.categories = Array.isArray(cats) ? cats : [];
            state.methods = Array.isArray(methods) ? methods : [];
            state.refsLoaded = true;
        } catch (e) {
            fail(e);
        }
    }

    function options(items, selected, blankLabel) {
        const blank = blankLabel ? '<option value="">' + esc(blankLabel) + '</option>' : '';
        return blank + items.map((i) =>
            '<option value="' + esc(i.id) + '"' + (String(i.id) === String(selected) ? ' selected' : '') + '>' + esc(i.name) + '</option>'
        ).join('');
    }

    function hideForm(id) {
        const form = $(id);
        if (form) { form.classList.add('d-none'); form.reset(); }
    }

    // --------------------------------------------------------------- budgets

    function budgetMonth() {
        const input = $('plannerBudgetMonth');
        if (input && !input.value) input.value = todayISO().slice(0, 7);
        const [year, month] = (input.value || todayISO().slice(0, 7)).split('-').map(Number);
        return { year, month };
    }

    function shiftBudgetMonth(delta) {
        const { year, month } = budgetMonth();
        const d = new Date(year, month - 1 + delta, 1);
        $('plannerBudgetMonth').value = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
        loadBudgets();
    }

    async function loadBudgets() {
        const { year, month } = budgetMonth();
        setList('plannerBudgetList', empty('Loading…'));
        try {
            const data = await api('GET', '/api/planner/budgets?year=' + year + '&month=' + month);
            const c = data.combined;
            const color = c.status === 'over' ? 'danger' : c.status === 'warning' ? 'warning' : 'success';
            const left = c.remaining >= 0 ? money(c.remaining) + ' left' : money(-c.remaining) + ' over';
            const combinedHtml = '<div class="planner-row">' +
                '<div class="d-flex justify-content-between flex-wrap gap-2">' +
                '<strong>Other (uncategorised + categories without a budget)</strong>' +
                '<span>' + money(c.spent) + ' / ' + money(c.monthly_limit) +
                ' <span class="badge bg-' + color + ' badge-soft">' + c.percent + '%</span></span></div>' +
                '<div class="progress my-1"><div class="progress-bar bg-' + color + '" style="width:' + Math.min(c.percent, 100) + '%"></div></div>' +
                '<div class="d-flex justify-content-between align-items-center flex-wrap gap-2 planner-sub"><span>' + esc(left) + ' · limit = total debit this month</span>' +
                '<span class="planner-actions d-flex align-items-center gap-1"><label class="mb-0" for="plannerCombinedAlert">Warn me at (%)</label>' +
                '<input type="number" id="plannerCombinedAlert" class="form-control form-control-sm" style="width:80px" min="50" max="99" value="' + c.alert_percent + '"> ' +
                '<button class="btn btn-sm btn-success" data-action="combined-save">Save</button>' +
                '</span></div></div>';
            setList('plannerBudgetList', combinedHtml + data.budgets.map((b) => {
                const color = b.status === 'over' ? 'danger' : b.status === 'warning' ? 'warning' : 'success';
                const left = b.remaining >= 0
                    ? money(b.remaining) + ' left'
                    : money(-b.remaining) + ' over';
                return '<div class="planner-row">' +
                    '<div class="d-flex justify-content-between flex-wrap gap-2">' +
                    '<strong>' + esc(b.category_name) + '</strong>' +
                    '<span>' + money(b.spent) + ' / ' + money(b.monthly_limit) +
                    ' <span class="badge bg-' + color + ' badge-soft">' + b.percent + '%</span></span></div>' +
                    '<div class="progress my-1"><div class="progress-bar bg-' + color + '" style="width:' + Math.min(b.percent, 100) + '%"></div></div>' +
                    '<div class="d-flex justify-content-between planner-sub"><span>' + esc(left) + ' · warns at ' + b.alert_percent + '%</span>' +
                    '<span class="planner-actions">' +
                    '<button class="btn btn-sm btn-outline-secondary" data-action="budget-edit" data-id="' + b.category_id + '" data-limit="' + b.monthly_limit + '" data-alert="' + b.alert_percent + '">Edit</button> ' +
                    '<button class="btn btn-sm btn-outline-danger" data-action="budget-delete" data-id="' + b.category_id + '" data-name="' + esc(b.category_name) + '">Remove</button>' +
                    '</span></div></div>';
            }).join(''));
        } catch (e) {
            setList('plannerBudgetList', '<div class="text-danger">' + esc(e.message) + '</div>');
        }
    }

    function openBudgetForm(categoryId, limit, alertPercent) {
        const expense = state.categories.filter((c) => c.type === 'expense');
        $('plannerBudgetCategory').innerHTML = options(expense, categoryId, expense.length ? '' : 'No expense categories');
        $('plannerBudgetLimit').value = limit || '';
        $('plannerBudgetAlert').value = alertPercent || 80;
        $('plannerBudgetForm').classList.remove('d-none');
        $('plannerBudgetLimit').focus();
    }

    async function saveCombinedBudget() {
        try {
            await api('PUT', '/api/planner/budgets/combined', {
                alert_percent: $('plannerCombinedAlert').value
            });
            toast('Combined budget saved', 'success');
            loadBudgets();
        } catch (e) { fail(e); }
    }

    async function saveBudget() {
        const categoryId = $('plannerBudgetCategory').value;
        if (!categoryId) return toast('Choose a category', 'warning');
        try {
            await api('PUT', '/api/planner/budgets/' + categoryId, {
                monthly_limit: $('plannerBudgetLimit').value,
                alert_percent: $('plannerBudgetAlert').value
            });
            hideForm('plannerBudgetForm');
            toast('Budget saved', 'success');
            loadBudgets();
        } catch (e) { fail(e); }
    }

    // ------------------------------------------------------------- recurring

    function scheduleText(r) {
        const n = r.interval_count;
        let text;
        if (r.frequency === 'weekly') text = n === 1 ? 'Weekly' : 'Every ' + n + ' weeks';
        else if (r.frequency === 'yearly') text = n === 1 ? 'Yearly' : 'Every ' + n + ' years';
        else text = (n === 1 ? 'Monthly' : 'Every ' + n + ' months') + ' on day ' + r.anchor_day;
        return text + (r.end_date ? ' until ' + r.end_date : '');
    }

    function fillRecCategories(selected) {
        const kind = $('plannerRecKind').value;
        const items = state.categories.filter((c) => c.type === kind);
        $('plannerRecCategory').innerHTML = options(items, selected, 'None');
        $('plannerRecDueWrap').classList.toggle('d-none', kind !== 'expense');
    }

    function openRecurringForm(rule) {
        $('plannerRecId').value = rule ? rule.id : '';
        $('plannerRecDescription').value = rule ? rule.description : '';
        $('plannerRecKind').value = rule ? rule.kind : 'expense';
        $('plannerRecAmount').value = rule ? rule.amount : '';
        fillRecCategories(rule ? rule.category_id : '');
        $('plannerRecPayment').innerHTML = options(state.methods, rule ? rule.payment_method_id : '', 'None');
        $('plannerRecFrequency').value = rule ? rule.frequency : 'monthly';
        $('plannerRecInterval').value = rule ? rule.interval_count : 1;
        $('plannerRecStart').value = rule ? rule.start_date : todayISO();
        $('plannerRecEnd').value = rule && rule.end_date ? rule.end_date : '';
        $('plannerRecDueOffset').value = rule && rule.due_offset_days != null ? rule.due_offset_days : '';
        $('plannerRecNotes').value = rule && rule.notes ? rule.notes : '';
        $('plannerRecurringForm').classList.remove('d-none');
        $('plannerRecDescription').focus();
    }

    async function loadRecurring() {
        setList('plannerRecurringList', empty('Loading…'));
        try {
            state.rules = await api('GET', '/api/planner/recurring');
            if (!state.rules.length) {
                setList('plannerRecurringList', empty('No recurring transactions yet.'));
                return;
            }
            setList('plannerRecurringList', state.rules.map((r) => {
                const sign = r.kind === 'income' ? '+' : '−';
                const color = r.kind === 'income' ? 'text-success' : '';
                const status = r.is_active
                    ? '<span class="badge bg-success badge-soft">Active</span>'
                    : '<span class="badge bg-secondary badge-soft">Paused</span>';
                return '<div class="planner-row">' +
                    '<div class="d-flex justify-content-between flex-wrap gap-2">' +
                    '<strong>' + esc(r.description) + '</strong>' +
                    '<span class="' + color + '">' + sign + ' ' + money(r.amount) + ' ' + status + '</span></div>' +
                    '<div class="d-flex justify-content-between flex-wrap gap-2 planner-sub">' +
                    '<span>' + esc(scheduleText(r)) + (r.is_active ? ' · next ' + esc(r.next_run) : '') +
                    (r.category_name ? ' · ' + esc(r.category_name) : '') +
                    (r.due_offset_days != null ? ' · due ' + r.due_offset_days + 'd after' : '') + '</span>' +
                    '<span class="planner-actions">' +
                    '<button class="btn btn-sm btn-outline-secondary" data-action="recurring-toggle" data-id="' + r.id + '" data-active="' + (r.is_active ? 1 : 0) + '">' + (r.is_active ? 'Pause' : 'Resume') + '</button> ' +
                    '<button class="btn btn-sm btn-outline-secondary" data-action="recurring-edit" data-id="' + r.id + '">Edit</button> ' +
                    '<button class="btn btn-sm btn-outline-danger" data-action="recurring-delete" data-id="' + r.id + '" data-name="' + esc(r.description) + '">Delete</button>' +
                    '</span></div></div>';
            }).join(''));
        } catch (e) {
            setList('plannerRecurringList', '<div class="text-danger">' + esc(e.message) + '</div>');
        }
    }

    async function saveRecurring() {
        const id = $('plannerRecId').value;
        const existing = state.rules.find((r) => String(r.id) === id);
        const payload = {
            description: $('plannerRecDescription').value,
            kind: $('plannerRecKind').value,
            amount: $('plannerRecAmount').value,
            category_id: $('plannerRecCategory').value || null,
            payment_method_id: $('plannerRecPayment').value || null,
            frequency: $('plannerRecFrequency').value,
            interval_count: $('plannerRecInterval').value,
            start_date: $('plannerRecStart').value,
            end_date: $('plannerRecEnd').value || null,
            due_offset_days: $('plannerRecKind').value === 'expense' ? $('plannerRecDueOffset').value : '',
            notes: $('plannerRecNotes').value,
            is_active: existing ? !!existing.is_active : true
        };
        try {
            const result = id
                ? await api('PUT', '/api/planner/recurring/' + id, payload)
                : await api('POST', '/api/planner/recurring', payload);
            hideForm('plannerRecurringForm');
            const n = result.created_now || 0;
            toast(n ? 'Saved. ' + n + ' transaction' + (n === 1 ? '' : 's') + ' created.' : 'Recurring transaction saved', 'success');
            if (n) refreshTransactionViews();
            loadRecurring();
        } catch (e) { fail(e); }
    }

    // ----------------------------------------------------------------- bills

    const BILL_STYLE = {
        overdue: ['danger', 'Overdue'],
        today: ['warning', 'Due today'],
        soon: ['warning', 'Due soon'],
        upcoming: ['secondary', 'Upcoming']
    };

    function daysText(days) {
        if (days < 0) return Math.abs(days) + ' day' + (days === -1 ? '' : 's') + ' overdue';
        if (days === 0) return 'today';
        if (days === 1) return 'tomorrow';
        return 'in ' + days + ' days';
    }

    function setBillsBadge(bills) {
        const badge = $('plannerBillsBadge');
        if (!badge) return;
        const urgent = bills.filter((b) => b.state !== 'upcoming').length;
        badge.textContent = urgent;
        badge.classList.toggle('d-none', urgent === 0);
    }

    async function loadBills(silent) {
        if (!silent) setList('plannerBillList', empty('Loading…'));
        try {
            const bills = await api('GET', '/api/planner/bills');
            setBillsBadge(bills);
            if (silent) return;
            if (!bills.length) {
                setList('plannerBillList', empty('No unpaid bills with a due date.'));
                return;
            }
            setList('plannerBillList', bills.map((b) => {
                const [color, label] = BILL_STYLE[b.state] || BILL_STYLE.upcoming;
                return '<div class="planner-row">' +
                    '<div class="d-flex justify-content-between flex-wrap gap-2">' +
                    '<strong>' + esc(b.description) + '</strong>' +
                    '<span>' + money(b.amount) + ' <span class="badge bg-' + color + ' badge-soft">' + label + '</span></span></div>' +
                    '<div class="d-flex justify-content-between flex-wrap gap-2 planner-sub">' +
                    '<span>Due ' + esc(b.due_date) + ' (' + esc(daysText(b.days_left)) + ')' +
                    (b.category_name ? ' · ' + esc(b.category_name) : '') +
                    (b.payment_method_name ? ' · ' + esc(b.payment_method_name) : '') + '</span>' +
                    '<span class="planner-actions">' +
                    '<button class="btn btn-sm btn-outline-success" data-action="bill-paid" data-id="' + b.transaction_id + '" data-method="' + (b.payment_method_id || '') + '">Mark paid</button> ' +
                    '<button class="btn btn-sm btn-outline-secondary" data-action="bill-clear" data-id="' + b.transaction_id + '">Remove reminder</button>' +
                    '</span></div></div>';
            }).join(''));
        } catch (e) {
            if (!silent) setList('plannerBillList', '<div class="text-danger">' + esc(e.message) + '</div>');
        }
    }

    // ----------------------------------------------------------------- goals

    function goalCard(g) {
        const color = g.completed ? 'success' : g.overdue ? 'danger' : 'primary';
        let hint = '';
        if (g.completed) hint = 'Goal reached 🎉';
        else if (g.overdue) hint = 'Past the target date · ' + money(g.remaining) + ' still to go';
        else if (g.monthly_needed != null) hint = 'Save ' + money(g.monthly_needed) + ' / month for ' + g.months_left + ' month' + (g.months_left === 1 ? '' : 's');
        else hint = money(g.remaining) + ' to go';

        const history = g.contributions.length
            ? g.contributions.map((c) =>
                '<div class="d-flex justify-content-between planner-sub"><span>' + esc(c.contributed_on) + (c.note ? ' · ' + esc(c.note) : '') + '</span>' +
                '<span>' + (c.amount < 0 ? '−' : '+') + money(Math.abs(c.amount)) +
                ' <a href="#" class="text-danger ms-2" data-action="contribution-delete" data-goal="' + g.id + '" data-id="' + c.id + '" title="Delete">×</a></span></div>').join('')
            : '<div class="planner-sub">No contributions yet.</div>';

        return '<div class="planner-row">' +
            '<div class="d-flex justify-content-between flex-wrap gap-2">' +
            '<strong>' + esc(g.name) + (g.archived ? ' <span class="badge bg-secondary badge-soft">Archived</span>' : '') + '</strong>' +
            '<span>' + money(g.saved) + ' / ' + money(g.target_amount) + ' <span class="badge bg-' + color + ' badge-soft">' + g.percent + '%</span></span></div>' +
            '<div class="progress my-1"><div class="progress-bar bg-' + color + '" style="width:' + g.percent + '%"></div></div>' +
            '<div class="planner-sub">' + esc(hint) + (g.target_date ? ' · target ' + esc(g.target_date) : '') + '</div>' +
            (g.archived ? '' :
                '<form class="d-flex flex-wrap gap-1 mt-2" data-goal-contribute="' + g.id + '">' +
                '<input type="number" step="0.01" class="form-control form-control-sm" style="max-width:160px" placeholder="Amount" title="Use a negative amount to withdraw" required>' +
                '<input type="text" class="form-control form-control-sm" style="max-width:200px" maxlength="255" placeholder="Note (optional)">' +
                '<button class="btn btn-sm btn-outline-success" type="submit">Add</button></form>') +
            '<div class="planner-actions mt-2">' +
            '<button class="btn btn-sm btn-outline-secondary" data-action="goal-history" data-id="' + g.id + '">History (' + g.contributions.length + ')</button> ' +
            '<button class="btn btn-sm btn-outline-secondary" data-action="goal-edit" data-id="' + g.id + '">Edit</button> ' +
            '<button class="btn btn-sm btn-outline-secondary" data-action="goal-archive" data-id="' + g.id + '" data-archived="' + (g.archived ? 1 : 0) + '">' + (g.archived ? 'Restore' : 'Archive') + '</button> ' +
            '<button class="btn btn-sm btn-outline-danger" data-action="goal-delete" data-id="' + g.id + '" data-name="' + esc(g.name) + '">Delete</button></div>' +
            '<div class="mt-2' + (state.openGoals.has(g.id) ? '' : ' d-none') + '" data-goal-history="' + g.id + '">' + history + '</div>' +
            '</div>';
    }

    async function loadGoals() {
        setList('plannerGoalList', empty('Loading…'));
        const archived = $('plannerGoalArchived') && $('plannerGoalArchived').checked;
        try {
            state.goals = await api('GET', '/api/planner/goals' + (archived ? '?archived=1' : ''));
            setList('plannerGoalList', state.goals.length
                ? state.goals.map(goalCard).join('')
                : empty('No savings goals yet. Create one to see how much to put aside each month.'));
        } catch (e) {
            setList('plannerGoalList', '<div class="text-danger">' + esc(e.message) + '</div>');
        }
    }

    function openGoalForm(goal) {
        $('plannerGoalId').value = goal ? goal.id : '';
        $('plannerGoalName').value = goal ? goal.name : '';
        $('plannerGoalTarget').value = goal ? goal.target_amount : '';
        $('plannerGoalDate').value = goal && goal.target_date ? goal.target_date : '';
        $('plannerGoalForm').classList.remove('d-none');
        $('plannerGoalName').focus();
    }

    async function saveGoal() {
        const id = $('plannerGoalId').value;
        const payload = {
            name: $('plannerGoalName').value,
            target_amount: $('plannerGoalTarget').value,
            target_date: $('plannerGoalDate').value || null
        };
        try {
            if (id) await api('PUT', '/api/planner/goals/' + id, payload);
            else await api('POST', '/api/planner/goals', payload);
            hideForm('plannerGoalForm');
            toast('Goal saved', 'success');
            loadGoals();
        } catch (e) { fail(e); }
    }

    async function addContribution(form) {
        const goalId = form.getAttribute('data-goal-contribute');
        const inputs = form.querySelectorAll('input');
        try {
            await api('POST', '/api/planner/goals/' + goalId + '/contributions', {
                amount: inputs[0].value,
                note: inputs[1].value,
                contributed_on: todayISO()
            });
            toast('Saved', 'success');
            loadGoals();
        } catch (e) { fail(e); }
    }

    // -------------------------------------------------------------- settings

    async function loadSettings() {
        try {
            const data = await api('GET', '/api/planner/settings');
            $('plannerTopic').value = data.ntfy_topic || '';
        } catch (e) { fail(e); }
    }

    async function saveSettings() {
        try {
            await api('PUT', '/api/planner/settings', { ntfy_topic: $('plannerTopic').value });
            toast('Notification topic saved', 'success');
        } catch (e) { fail(e); }
    }

    async function testNotification() {
        try {
            await saveSettingsQuiet();
            const result = await api('POST', '/api/planner/settings/test');
            toast(result.message || 'Test sent', 'success');
        } catch (e) { fail(e); }
    }

    async function saveSettingsQuiet() {
        await api('PUT', '/api/planner/settings', { ntfy_topic: $('plannerTopic').value });
    }

    // --------------------------------------------------------------- actions

    function confirmThen(title, message, action) {
        if (typeof showConfirmModal === 'function') showConfirmModal(title, message, action);
        else if (window.confirm(message)) action();
    }

    async function run(promise, successMessage, reload) {
        try {
            await promise;
            if (successMessage) toast(successMessage, 'success');
            if (reload) reload();
        } catch (e) { fail(e); }
    }

    function handleClick(event) {
        const tab = event.target.closest('[data-planner-tab]');
        if (tab) {
            event.preventDefault();
            showTab(tab.getAttribute('data-planner-tab'));
            return;
        }
        const el = event.target.closest('[data-action]');
        if (!el) return;
        event.preventDefault();
        const id = el.getAttribute('data-id');

        switch (el.getAttribute('data-action')) {
            case 'form-cancel': hideForm(el.getAttribute('data-target')); break;

            case 'budget-month-prev': shiftBudgetMonth(-1); break;
            case 'budget-month-next': shiftBudgetMonth(1); break;
            case 'combined-save': saveCombinedBudget(); break;
            case 'budget-new': openBudgetForm('', '', 80); break;
            case 'budget-edit':
                openBudgetForm(id, el.getAttribute('data-limit'), el.getAttribute('data-alert'));
                break;
            case 'budget-delete':
                confirmThen('Remove budget', 'Remove the budget for ' + el.getAttribute('data-name') + '?',
                    () => run(api('DELETE', '/api/planner/budgets/' + id), 'Budget removed', loadBudgets));
                break;

            case 'recurring-new': openRecurringForm(null); break;
            case 'recurring-edit': openRecurringForm(state.rules.find((r) => String(r.id) === id)); break;
            case 'recurring-toggle':
                run(api('PUT', '/api/planner/recurring/' + id + '/active', { is_active: el.getAttribute('data-active') !== '1' }),
                    null, loadRecurring);
                break;
            case 'recurring-delete':
                confirmThen('Delete recurring transaction',
                    'Delete "' + el.getAttribute('data-name') + '"? Transactions it already created are kept.',
                    () => run(api('DELETE', '/api/planner/recurring/' + id), 'Deleted', loadRecurring));
                break;

            case 'bill-paid':
                run(api('POST', '/api/transactions/' + id + '/mark-paid', { payment_method_id: el.getAttribute('data-method') || null }),
                    'Marked as paid', () => { loadBills(); refreshTransactionViews(); });
                break;
            case 'bill-clear':
                run(api('DELETE', '/api/planner/bills/' + id), 'Reminder removed', () => { loadBills(); refreshTransactionViews(); });
                break;

            case 'goal-new': openGoalForm(null); break;
            case 'goal-edit': openGoalForm(state.goals.find((g) => String(g.id) === id)); break;
            case 'goal-history': {
                const gid = Number(id);
                if (state.openGoals.has(gid)) state.openGoals.delete(gid); else state.openGoals.add(gid);
                const box = root().querySelector('[data-goal-history="' + id + '"]');
                if (box) box.classList.toggle('d-none');
                break;
            }
            case 'goal-archive':
                run(api('PUT', '/api/planner/goals/' + id, { archived: el.getAttribute('data-archived') !== '1' }), null, loadGoals);
                break;
            case 'goal-delete':
                confirmThen('Delete goal', 'Delete "' + el.getAttribute('data-name') + '" and its history?',
                    () => run(api('DELETE', '/api/planner/goals/' + id), 'Goal deleted', loadGoals));
                break;
            case 'contribution-delete':
                run(api('DELETE', '/api/planner/goals/' + el.getAttribute('data-goal') + '/contributions/' + id), null, loadGoals);
                break;

            case 'settings-test': testNotification(); break;
        }
    }

    function handleSubmit(event) {
        const form = event.target;
        event.preventDefault();
        if (form.id === 'plannerBudgetForm') saveBudget();
        else if (form.id === 'plannerRecurringForm') saveRecurring();
        else if (form.id === 'plannerGoalForm') saveGoal();
        else if (form.id === 'plannerSettingsForm') saveSettings();
        else if (form.hasAttribute('data-goal-contribute')) addContribution(form);
    }

    function handleChange(event) {
        const id = event.target.id;
        if (id === 'plannerBudgetMonth') loadBudgets();
        else if (id === 'plannerGoalArchived') loadGoals();
        else if (id === 'plannerRecKind') fillRecCategories('');
    }

    function bindOnce() {
        const el = root();
        if (!el || el.dataset.plannerBound) return;
        el.dataset.plannerBound = '1';
        el.addEventListener('click', handleClick);
        el.addEventListener('submit', handleSubmit);
        el.addEventListener('change', handleChange);
    }

    // Called by dashboard.js whenever the Planner page is shown
    window.loadPlanner = async function () {
        if (!root() || !$('plannerPills')) return;
        bindOnce();
        await loadRefs();
        showTab(state.tab);
        loadBills(true);              // keeps the badge on the Bills tab current
    };
})();
