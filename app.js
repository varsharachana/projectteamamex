const STORAGE_KEY = 'credit-card-expense-agent-demo';
const CATEGORY_ORDER = ['Groceries', 'Dining', 'Shopping', 'Transport', 'Utilities', 'Travel', 'Healthcare', 'Entertainment', 'Other', 'Needs Review'];
const CATEGORY_COLORS = {
  Groceries: '#20b7b4',
  Dining: '#0d2449',
  Shopping: '#4c8df6',
  Transport: '#ffb74d',
  Utilities: '#27ae60',
  Travel: '#7c7ad9',
  Healthcare: '#f1608a',
  Entertainment: '#4ab4dc',
  Other: '#a8b4c6',
  'Needs Review': '#e35a5a'
};

const bankConfig = {
  HDFC: {
    accent: '#0d2449',
    merchants: ['Fresh Basket', 'Metro Mart', 'FuelPoint', 'City Cafe', 'TravelPlus', 'Aster Labs', 'HomeFlow', 'Skyline Cinema'],
    short: 'HDFC'
  },
  SBI: {
    accent: '#0f9d9d',
    merchants: ['GreenCart', 'QuickBites', 'Metro Rail', 'EnerGo', 'Lakshmi Pharmacy', 'Bharat Bazaar', 'Namma Cinema', 'Weekend Mall'],
    short: 'SBI'
  },
  ICICI: {
    accent: '#12315e',
    merchants: ['Savory Table', 'SmartMart', 'RideNow', 'Luxe Avenue', 'City Transit', 'WellCare', 'Blue Horizon', 'Playhouse'],
    short: 'ICICI'
  }
};

const appState = {
  currentScreen: 'auth',
  authMode: 'login',
  currentUser: null,
  users: [],
  connectedCards: [],
  selectedBank: null,
  activeCard: null,
  statement: null,
  dashboardFilters: {
    search: '',
    category: 'All'
  }
};

const mockServices = {
  auth: {
    signup(fullName, email, password) {
      if (!fullName || !email || !password) {
        return { ok: false, message: 'Please fill in all signup fields.' };
      }

      const normalizedEmail = normalizeEmail(email);
      const existing = appState.users.find((user) => user.email === normalizedEmail);

      if (existing) {
        appState.currentUser = { name: existing.name, email: existing.email };
        return { ok: true, user: appState.currentUser, message: 'Welcome back. Your signed-in session has been restored.' };
      }

      const newUser = { name: fullName.trim(), email: normalizedEmail };
      appState.users.push(newUser);
      appState.currentUser = { name: newUser.name, email: newUser.email };
      persistState();
      return { ok: true, user: appState.currentUser, message: 'Account created successfully.' };
    },
    login(email, password) {
      if (!email || !password) {
        return { ok: false, message: 'Please enter your email and password.' };
      }

      const normalizedEmail = normalizeEmail(email);
      const existing = appState.users.find((user) => user.email === normalizedEmail);

      if (!existing) {
        return { ok: false, message: 'No account found for this email. Please sign up first.' };
      }

      appState.currentUser = { name: existing.name, email: existing.email };
      persistState();
      return { ok: true, user: appState.currentUser, message: 'Login successful.' };
    }
  },
  cards: {
    connect(bankName, formData) {
      const masked = maskCardNumber(formData.cardNumber);
      const card = {
        id: crypto.randomUUID(),
        bankName,
        cardholderName: formData.cardholderName.trim(),
        cardNumberMasked: masked,
        cardNumberLast4: masked.slice(-4),
        mobile: formData.mobile.trim(),
        connectedAt: new Date().toISOString(),
        consent: formData.consent
      };

      const existing = appState.connectedCards.find((item) => item.bankName === bankName && item.cardNumberLast4 === card.cardNumberLast4);
      if (existing) {
        appState.activeCard = existing;
      } else {
        appState.connectedCards.push(card);
        appState.activeCard = card;
      }

      appState.selectedBank = bankName;
      persistState();
      return { ok: true, card };
    },
    fetchStatement({ bankName, statementMonth, customStart, customEnd }) {
      if (!bankName || !appState.activeCard) {
        return { ok: false, message: 'Please connect a card before fetching a statement.' };
      }

      const range = statementMonth ? getMonthRange(statementMonth) : getRange(customStart, customEnd);
      const transactions = generateSyntheticTransactions(bankName, range.start, range.end, appState.activeCard.cardNumberLast4);
      appState.statement = {
        bankName,
        cardNumberMasked: appState.activeCard.cardNumberMasked,
        periodLabel: range.label,
        startDate: range.start,
        endDate: range.end,
        transactions,
        generatedAt: new Date().toISOString()
      };
      persistState();
      return { ok: true, statement: appState.statement };
    }
  }
};

document.addEventListener('DOMContentLoaded', init);

function init() {
  hydrateState();
  bindEvents();
  render();
}

function bindEvents() {
  document.getElementById('auth-toggle-login').addEventListener('click', () => setAuthMode('login'));
  document.getElementById('auth-toggle-signup').addEventListener('click', () => setAuthMode('signup'));

  document.getElementById('login-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    const result = mockServices.auth.login(email, password);
    renderAuthStatus(result, 'login');
    if (result.ok) {
      showScreen('profile');
    }
  });

  document.getElementById('signup-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const fullName = document.getElementById('signup-name').value;
    const email = document.getElementById('signup-email').value;
    const password = document.getElementById('signup-password').value;
    const confirmPassword = document.getElementById('signup-confirm-password').value;

    if (password !== confirmPassword) {
      renderAuthStatus({ ok: false, message: 'Passwords do not match.' }, 'signup');
      return;
    }

    const result = mockServices.auth.signup(fullName, email, password);
    renderAuthStatus(result, 'signup');
    if (result.ok) {
      showScreen('profile');
    }
  });

  const newConnectionBtn = document.getElementById('new-connection-btn');
  if (newConnectionBtn) newConnectionBtn.addEventListener('click', () => showScreen('bank'));

  const goToProfile = document.getElementById('go-to-profile');
  if (goToProfile) goToProfile.addEventListener('click', () => showScreen('profile'));

  const backToBank = document.getElementById('back-to-bank');
  if (backToBank) backToBank.addEventListener('click', () => showScreen('bank'));

  const backToStatement = document.getElementById('back-to-statement');
  if (backToStatement) backToStatement.addEventListener('click', () => showScreen('statement'));

  document.getElementById('logout-btn').addEventListener('click', logout);

  document.querySelectorAll('[data-bank]').forEach((button) => {
    button.addEventListener('click', () => {
      const bankName = button.dataset.bank;
      appState.selectedBank = bankName;
      persistState();
      renderBankSelection();
      showScreen('connect');
    });
  });

  document.getElementById('connect-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = {
      cardholderName: form.cardholderName.value,
      cardNumber: form.cardNumber.value,
      mobile: form.mobile.value,
      consent: form.consent.checked
    };

    if (!formData.cardholderName || !formData.cardNumber || !formData.mobile) {
      showInlineError('Please complete all connection fields.');
      return;
    }

    if (formData.cardNumber.replace(/\s/g, '').length < 16) {
      showInlineError('Card number must contain at least 16 digits.');
      return;
    }

    if (!formData.consent) {
      showInlineError('Please consent to statement retrieval and analysis before continuing.');
      return;
    }

    const otpCode = document.getElementById('otp-code').value.trim();
    const demoOtp = document.getElementById('demo-otp').dataset.otp || '483271';
    if (!otpCode) {
      showInlineError('Enter the simulated OTP received on the registered mobile number.');
      return;
    }

    if (otpCode !== demoOtp) {
      showInlineError('That OTP does not match the demo code. Use the displayed OTP for verification.');
      return;
    }

    const result = mockServices.cards.connect(appState.selectedBank, formData);
    if (!result.ok) {
      showInlineError(result.message || 'Unable to connect card.');
      return;
    }

    showInlineError('', true);
    showScreen('statement');
    renderStatementScreen();
  });

  document.getElementById('card-number').addEventListener('input', (event) => {
    const value = formatCardInput(event.target.value);
    event.target.value = value;
    const masked = maskCardNumber(value);
    document.getElementById('masked-preview').textContent = masked || '•••• •••• •••• ••••';
  });

  document.getElementById('verify-otp-btn').addEventListener('click', () => {
    const demoOtp = generateDemoOtp();
    document.getElementById('demo-otp').textContent = `Demo OTP: ${demoOtp}`;
    document.getElementById('demo-otp').dataset.otp = demoOtp;
    document.getElementById('otp-box').classList.add('visible');
    document.getElementById('otp-code').focus();
  });

  document.getElementById('statement-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const month = document.getElementById('statement-month').value;
    const customStart = document.getElementById('date-start').value;
    const customEnd = document.getElementById('date-end').value;
    const loading = document.getElementById('loading-wrap');
    const info = document.getElementById('fetch-status');

    if (!month && (!customStart || !customEnd)) {
      showInlineError('Select a statement month or a custom date range.');
      return;
    }

    if (customStart && customEnd && customStart > customEnd) {
      showInlineError('The start date must be earlier than the end date.');
      return;
    }

    showInlineError('', true);
    loading.classList.add('visible');
    info.textContent = 'Preparing demo statement...';

    let progress = 0;
    const timer = setInterval(() => {
      progress += 16;
      document.getElementById('progress-bar').style.width = `${Math.min(progress, 100)}%`;
      if (progress >= 100) {
        clearInterval(timer);
        setTimeout(() => {
          const result = mockServices.cards.fetchStatement({
            bankName: appState.selectedBank,
            statementMonth: month,
            customStart,
            customEnd
          });

          if (!result.ok) {
            loading.classList.remove('visible');
            showInlineError(result.message);
            return;
          }

          loading.classList.remove('visible');
          info.textContent = 'Demo statement retrieved successfully.';
          showScreen('dashboard');
          renderDashboard();
        }, 350);
      }
    }, 180);
  });

  const searchInput = document.getElementById('search-transactions');
  if (searchInput) {
    searchInput.addEventListener('input', (event) => {
      appState.dashboardFilters.search = event.target.value.trim().toLowerCase();
      renderDashboard();
    });
  }

  const categoryFilter = document.getElementById('category-filter');
  if (categoryFilter) {
    categoryFilter.addEventListener('change', (event) => {
      appState.dashboardFilters.category = event.target.value;
      renderDashboard();
    });
  }

  const exportCsvButton = document.getElementById('export-csv');
  if (exportCsvButton) exportCsvButton.addEventListener('click', exportCsv);

  const exportPdfButton = document.getElementById('export-pdf');
  if (exportPdfButton) exportPdfButton.addEventListener('click', exportPdf);
}

function hydrateState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return;

  try {
    const parsed = JSON.parse(raw);
    appState.currentUser = parsed.currentUser || null;
    appState.users = Array.isArray(parsed.users) ? parsed.users : [];
    appState.connectedCards = Array.isArray(parsed.connectedCards) ? parsed.connectedCards : [];
    appState.selectedBank = parsed.selectedBank || null;
    appState.activeCard = parsed.activeCard || null;
    appState.statement = parsed.statement || null;
    appState.currentScreen = parsed.currentScreen || 'auth';
  } catch (error) {
    console.warn('Unable to restore saved demo state.', error);
  }
}

function persistState() {
  const payload = {
    currentScreen: appState.currentScreen,
    currentUser: appState.currentUser,
    users: appState.users,
    connectedCards: appState.connectedCards,
    selectedBank: appState.selectedBank,
    activeCard: appState.activeCard,
    statement: appState.statement
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

function render() {
  renderAuthMode();
  renderProfile();
  renderBankSelection();
  renderStatementScreen();
  renderDashboard();
  renderHeader();
  showScreen(appState.currentScreen);
}

function renderHeader() {
  const userName = appState.currentUser ? appState.currentUser.name.split(' ')[0] : 'Guest';
  const headerUser = document.getElementById('header-user');
  const logoutBtn = document.getElementById('logout-btn');

  if (appState.currentUser) {
    headerUser.textContent = userName;
    headerUser.parentElement.style.display = 'inline-flex';
    logoutBtn.style.display = 'inline-flex';
  } else {
    headerUser.textContent = 'Guest';
    headerUser.parentElement.style.display = 'none';
    logoutBtn.style.display = 'none';
  }
}

function renderAuthMode() {
  const loginMode = appState.authMode === 'login';
  document.getElementById('auth-toggle-login').classList.toggle('active', loginMode);
  document.getElementById('auth-toggle-signup').classList.toggle('active', !loginMode);
  document.getElementById('login-form').style.display = loginMode ? 'grid' : 'none';
  document.getElementById('signup-form').style.display = loginMode ? 'none' : 'grid';
}

function setAuthMode(mode) {
  appState.authMode = mode;
  renderAuthMode();
  clearAuthStatus();
}

function renderAuthStatus(result, formType) {
  const status = document.getElementById(`${formType}-status`);
  if (!status) return;

  status.textContent = result.message || '';
  status.classList.remove('error', 'success');
  status.classList.add(result.ok ? 'success' : 'error');
}

function clearAuthStatus() {
  const loginStatus = document.getElementById('login-status');
  const signupStatus = document.getElementById('signup-status');
  loginStatus.textContent = '';
  signupStatus.textContent = '';
  loginStatus.classList.remove('error', 'success');
  signupStatus.classList.remove('error', 'success');
}

function showScreen(screenName) {
  const validScreens = ['auth', 'profile', 'bank', 'connect', 'statement', 'dashboard'];
  if (!validScreens.includes(screenName)) return;

  appState.currentScreen = screenName;
  persistState();

  document.querySelectorAll('.screen').forEach((screen) => {
    const isVisible = screen.id === `${screenName}-screen`;
    screen.classList.toggle('active', isVisible);
  });

  if (screenName === 'auth' && !appState.currentUser) {
    document.getElementById('auth-screen').classList.add('active');
  }

  const selectedBankField = document.getElementById('bank-name');
  if (selectedBankField) {
    selectedBankField.value = appState.selectedBank || 'HDFC';
  }

  renderHeader();
  renderProfile();
  renderBankSelection();
  renderStatementScreen();
  renderDashboard();
}

function logout() {
  appState.currentUser = null;
  appState.currentScreen = 'auth';
  appState.activeCard = null;
  persistState();
  showScreen('auth');
}

function renderProfile() {
  const profileScreen = document.getElementById('profile-screen');
  if (!profileScreen) return;

  const profileName = appState.currentUser ? appState.currentUser.name : 'Your Profile';
  const profileEmail = appState.currentUser ? appState.currentUser.email : 'Sign in to continue';

  document.getElementById('profile-name').textContent = profileName;
  document.getElementById('profile-email').textContent = profileEmail;
  document.getElementById('profile-avatar').textContent = getInitials(profileName);

  const cardList = document.getElementById('connected-card-list');
  if (!appState.connectedCards.length) {
    cardList.innerHTML = '<div class="empty-state">No cards connected yet. Add a credit card to begin categorizing expenses.</div>';
    return;
  }

  const cards = appState.connectedCards.map((card) => `
    <div class="card-mini">
      <div class="card-label">${card.bankName}</div>
      <div class="card-number">${card.cardNumberMasked}</div>
      <div class="card-meta">
        <span>${card.cardholderName}</span>
        <span>••${card.cardNumberLast4}</span>
      </div>
    </div>
  `).join('');

  cardList.innerHTML = cards;
}

function renderBankSelection() {
  const banks = Object.entries(bankConfig);
  const options = banks.map(([bankName, config]) => {
    const activeClass = appState.selectedBank === bankName ? 'active' : '';
    return `
      <button type="button" class="bank-option ${activeClass}" data-bank="${bankName}">
        <div class="bank-logo" style="background:${config.accent};">${bankName.substring(0, 2)}</div>
        <div>
          <h3>${bankName}</h3>
          <p>Credit card linking and demo statement processing</p>
        </div>
      </button>
    `;
  }).join('');

  document.getElementById('bank-options').innerHTML = options;
  document.querySelectorAll('[data-bank]').forEach((button) => {
    button.addEventListener('click', () => {
      const bankName = button.dataset.bank;
      appState.selectedBank = bankName;
      persistState();
      renderBankSelection();
      showScreen('connect');
    });
  });
}

function renderStatementScreen() {
  const form = document.getElementById('statement-form');
  const activeBank = appState.selectedBank || 'HDFC';
  const bank = bankConfig[activeBank] || bankConfig.HDFC;
  const selectedCard = appState.activeCard || ({ cardNumberMasked: '•••• •••• •••• 4242', cardholderName: 'Demo Cardholder' });

  document.getElementById('statement-bank-name').textContent = activeBank;
  document.getElementById('statement-card').textContent = selectedCard.cardNumberMasked;
  document.getElementById('statement-period-label').textContent = appState.statement ? appState.statement.periodLabel : 'Select period';
  document.getElementById('statement-bank-accent').style.background = bank.accent;
  document.getElementById('statement-bank').textContent = activeBank;
  document.getElementById('statement-month').value = '';
}

function renderDashboard() {
  const dashboardSummary = document.getElementById('dashboard-summary');
  if (!dashboardSummary) return;

  if (!appState.statement) {
    dashboardSummary.innerHTML = '<div class="empty-state">No statement retrieved yet. Choose a bank and fetch a statement to analyze spending.</div>';
    return;
  }

  const statement = appState.statement;
  const filteredTransactions = getFilteredTransactions();
  const totals = calculateTotals(filteredTransactions);
  const categoryTotals = getCategoryTotals(filteredTransactions);
  const topCategory = categoryTotals.length ? categoryTotals[0].category : 'Other';
  const donutGradient = buildDonutGradient(categoryTotals);
  const maxBar = categoryTotals.reduce((max, item) => Math.max(max, item.total), 1);

  dashboardSummary.innerHTML = `
    <div class="metric-grid">
      <div class="metric-card panel">
        <span>Total spending</span>
        <strong>${formatCurrency(totals.total)}</strong>
      </div>
      <div class="metric-card panel">
        <span>Transactions</span>
        <strong>${totals.count}</strong>
      </div>
      <div class="metric-card panel">
        <span>Needs review</span>
        <strong>${totals.needsReview}</strong>
      </div>
      <div class="metric-card panel">
        <span>Selected period</span>
        <strong>${statement.periodLabel}</strong>
      </div>
    </div>

    <div class="chart-grid">
      <div class="chart-card panel">
        <h3>Spending mix</h3>
        <div class="donut-wrap">
          <div id="donut-chart" class="donut" style="background:${donutGradient};"></div>
        </div>
        <div id="legend-items" class="chart-legend">
          ${categoryTotals.slice(0, 5).map((item) => `
            <div class="legend-item">
              <div class="legend-label">
                <span class="legend-dot" style="background:${CATEGORY_COLORS[item.category] || '#a8b4c6'}"></span>
                ${item.category}
              </div>
              <strong>${formatCurrency(item.total)}</strong>
            </div>
          `).join('')}
        </div>
      </div>

      <div class="summary-card panel">
        <h3>Spending summary</h3>
        <p id="summary-highlight" class="muted">${topCategory} is the largest spending bucket this period.</p>
        <ul id="summary-list" class="summary-list">
          ${categoryTotals.slice(0, 4).map((item) => `
            <li class="summary-item">
              <span>${item.category}</span>
              <strong>${formatCurrency(item.total)}</strong>
            </li>
          `).join('')}
        </ul>

        <h3 style="margin-top:20px;">Category trend</h3>
        <div id="bar-chart" class="bar-chart">
          ${categoryTotals.slice(0, 6).map((item) => {
            const height = Math.max((item.total / maxBar) * 100, 10);
            return `
              <div class="bar-group">
                <div class="bar" style="height:${height}%; background: linear-gradient(180deg, ${CATEGORY_COLORS[item.category] || '#20b7b4'}, #0d2449);"></div>
                <div class="bar-label">${item.category.slice(0, 4)}</div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    </div>

    <div class="table-card panel">
      <div class="table-top">
        <h3>Transactions</h3>
        <div class="filter-bar">
          <input id="search-transactions" type="search" value="${appState.dashboardFilters.search || ''}" placeholder="Search merchant or category" />
          <select id="category-filter">
            <option value="All" ${appState.dashboardFilters.category === 'All' ? 'selected' : ''}>All categories</option>
            ${CATEGORY_ORDER.map((category) => `<option value="${category}" ${appState.dashboardFilters.category === category ? 'selected' : ''}>${category}</option>`).join('')}
          </select>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Merchant</th>
              <th>Amount</th>
              <th>Category</th>
              <th>Confidence</th>
              <th>Explanation</th>
            </tr>
          </thead>
          <tbody id="dashboard-tbody">
            ${filteredTransactions.length ? filteredTransactions.map((txn) => `
              <tr>
                <td>${formatDate(txn.date)}</td>
                <td>${txn.merchant}</td>
                <td class="amount negative">${formatCurrency(txn.amount)}</td>
                <td>
                  <select class="category-select" data-category-id="${txn.id}">
                    ${CATEGORY_ORDER.map((category) => `<option value="${category}" ${txn.category === category ? 'selected' : ''}>${category}</option>`).join('')}
                  </select>
                </td>
                <td><span class="badge ${getConfidenceBadge(txn.confidence)}">${txn.confidence}</span></td>
                <td class="explainer">${txn.explanation}</td>
              </tr>
            `).join('') : '<tr><td colspan="6"><div class="empty-state">No transactions match the active search or category filter.</div></td></tr>'}
          </tbody>
        </table>
      </div>
    </div>
  `;

  const searchInput = document.getElementById('search-transactions');
  if (searchInput) {
    searchInput.addEventListener('input', (event) => {
      appState.dashboardFilters.search = event.target.value.trim().toLowerCase();
      renderDashboard();
    });
  }

  const categoryFilter = document.getElementById('category-filter');
  if (categoryFilter) {
    categoryFilter.addEventListener('change', (event) => {
      appState.dashboardFilters.category = event.target.value;
      renderDashboard();
    });
  }

  const tableBody = document.getElementById('dashboard-tbody');
  if (tableBody) {
    tableBody.querySelectorAll('.category-select').forEach((select) => {
      select.addEventListener('change', (event) => {
        const id = event.target.dataset.categoryId;
        const nextCategory = event.target.value;
        const target = appState.statement.transactions.find((txn) => txn.id === id);
        if (target) {
          target.category = nextCategory;
          target.confidence = nextCategory === 'Needs Review' ? 'Low' : nextCategory === 'Groceries' || nextCategory === 'Dining' ? 'High' : 'Medium';
          target.explanation = nextCategory === 'Needs Review'
            ? 'Flagged for manual review because the merchant pattern is ambiguous.'
            : 'Simulated classification based on merchant pattern and historical spending behavior.';
          persistState();
          renderDashboard();
        }
      });
    });
  }
}

function getFilteredTransactions() {
  if (!appState.statement) return [];
  const search = appState.dashboardFilters.search;
  const selectedCategory = appState.dashboardFilters.category;

  return appState.statement.transactions.filter((transaction) => {
    const matchesSearch = !search || transaction.merchant.toLowerCase().includes(search) || transaction.category.toLowerCase().includes(search);
    const matchesCategory = selectedCategory === 'All' || transaction.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });
}

function calculateTotals(transactions) {
  const total = transactions.reduce((sum, tx) => sum + tx.amount, 0);
  const needsReview = transactions.filter((tx) => tx.category === 'Needs Review').length;
  return { total, count: transactions.length, needsReview };
}

function getCategoryTotals(transactions) {
  const totals = {};
  for (const category of CATEGORY_ORDER) totals[category] = 0;

  for (const transaction of transactions) {
    totals[transaction.category] = (totals[transaction.category] || 0) + transaction.amount;
  }

  return Object.entries(totals)
    .filter(([, total]) => total > 0)
    .map(([category, total]) => ({ category, total }))
    .sort((a, b) => b.total - a.total);
}

function buildDonutGradient(categoryTotals) {
  const total = categoryTotals.reduce((sum, item) => sum + item.total, 0) || 1;
  let current = 0;
  const stops = categoryTotals.map((item) => {
    const start = current;
    current += (item.total / total) * 100;
    return `${CATEGORY_COLORS[item.category] || '#a8b4c6'} ${start}% ${current}%`;
  });
  return `conic-gradient(${stops.join(', ')})`;
}

function getConfidenceBadge(confidence) {
  if (confidence === 'High') return 'high';
  if (confidence === 'Medium') return 'medium';
  return 'low';
}

function generateSyntheticTransactions(bankName, startDate, endDate, last4) {
  const bank = bankConfig[bankName] || bankConfig.HDFC;
  const start = new Date(startDate);
  const end = new Date(endDate);
  const count = 14;
  const transactions = [];

  for (let index = 0; index < count; index += 1) {
    const randomDate = new Date(start.getTime() + Math.random() * (end.getTime() - start.getTime()));
    const category = pickCategory(index);
    const merchant = pickMerchant(bank.merchants, category);
    const amount = Math.round((Math.random() * 780 + 45) * 100) / 100;

    transactions.push({
      id: `${last4}-${index}-${Date.now()}`,
      date: formatISODate(randomDate),
      merchant,
      amount,
      category,
      confidence: category === 'Needs Review' ? 'Low' : category === 'Groceries' || category === 'Dining' ? 'High' : 'Medium',
      explanation: category === 'Needs Review'
        ? 'Merchant pattern is ambiguous and requires a manual check.'
        : `Simulated classification based on merchant behavior and spending history for ${bankName}.`,
      bankName
    });
  }

  return transactions.sort((a, b) => new Date(b.date) - new Date(a.date));
}

function pickCategory(index) {
  const categories = [...CATEGORY_ORDER];
  if (index % 5 === 0) return 'Needs Review';
  return categories[Math.floor(Math.random() * (categories.length - 1))];
}

function pickMerchant(merchants, category) {
  const categoryMerchants = {
    Groceries: ['Fresh Basket', 'GreenCart', 'Metro Mart', 'Daily Essentials'],
    Dining: ['Savory Table', 'City Cafe', 'QuickBites', 'Night Noodles'],
    Shopping: ['Luxe Avenue', 'Weekend Mall', 'Urban Style', 'SmartMart'],
    Transport: ['Metro Rail', 'RideNow', 'FuelPoint', 'City Transit'],
    Utilities: ['PowerGrid', 'HomeFlow', 'EnerGo', 'Water Works'],
    Travel: ['TravelPlus', 'Skyline Air', 'RailFast', 'Hotel Bay'],
    Healthcare: ['Aster Labs', 'WellCare', 'Clinic Care', 'Care Pharmacy'],
    Entertainment: ['Skyline Cinema', 'Playhouse', 'Live Arena', 'Cinema Luxe'],
    Other: ['Global Services', 'Office Mart', 'QuickPay', 'Digital Plus']
  };

  const source = categoryMerchants[category] || merchants;
  return source[Math.floor(Math.random() * source.length)];
}

function formatCardInput(value) {
  const digits = value.replace(/\D/g, '').slice(0, 16);
  return digits.replace(/(.{4})/g, '$1 ').trim();
}

function maskCardNumber(value) {
  const digits = value.replace(/\D/g, '').slice(-16);
  if (!digits) return '•••• •••• •••• ••••';
  const lastFour = digits.slice(-4);
  return `•••• •••• •••• ${lastFour}`;
}

function normalizeEmail(value) {
  return value.trim().toLowerCase();
}

function getInitials(name) {
  return (name || 'U').split(' ').filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
}

function formatCurrency(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0
  }).format(value);
}

function formatDate(dateString) {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(date);
}

function formatISODate(date) {
  return new Date(date).toISOString().split('T')[0];
}

function getMonthRange(monthValue) {
  if (!monthValue) {
    const toDay = new Date();
    const start = new Date(toDay.getFullYear(), toDay.getMonth(), 1);
    const end = new Date(toDay.getFullYear(), toDay.getMonth() + 1, 0);
    return {
      start: formatISODate(start),
      end: formatISODate(end),
      label: `${start.toLocaleString('en-IN', { month: 'long' })} ${start.getFullYear()}`
    };
  }

  const [year, month] = monthValue.split('-').map(Number);
  const start = new Date(year, month - 1, 1);
  const end = new Date(year, month, 0);
  return {
    start: formatISODate(start),
    end: formatISODate(end),
    label: `${start.toLocaleString('en-IN', { month: 'long' })} ${start.getFullYear()}`
  };
}

function getRange(customStart, customEnd) {
  const start = new Date(customStart);
  const end = new Date(customEnd);
  return {
    start: formatISODate(start),
    end: formatISODate(end),
    label: `${formatDate(customStart)} to ${formatDate(customEnd)}`
  };
}

function showInlineError(message, clear = false) {
  const el = document.getElementById('connect-error') || document.getElementById('statement-error');
  if (!el) return;

  if (clear) {
    el.textContent = '';
    el.classList.remove('visible');
    return;
  }

  el.textContent = message;
  el.classList.add('visible');
}

function generateDemoOtp() {
  return String(Math.floor(100000 + Math.random() * 900000));
}

function exportCsv() {
  if (!appState.statement) return;

  const headers = ['Date', 'Merchant', 'Amount', 'Category', 'Confidence', 'Explanation'];
  const rows = appState.statement.transactions.map((tx) => [
    tx.date,
    tx.merchant,
    tx.amount,
    tx.category,
    tx.confidence,
    tx.explanation
  ]);

  const csv = [headers, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `credit-card-expense-summary-${appState.statement.bankName}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function exportPdf() {
  if (!appState.statement) return;
  window.print();
}

window.addEventListener('load', () => {
  if (!appState.currentUser) {
    showScreen('auth');
  } else {
    showScreen('profile');
  }
});
