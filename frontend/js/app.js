// API Configuration
const API_BASE = "http://localhost:8000/api";
let activeSessionId = null;
let activeSessionUrl = "";
let statusPollInterval = null;

// Auth State
let token = null;
let userRole = null;
let currentUserEmail = null;
let currentUsername = null;

// Safe localStorage access helper
try {
    token = localStorage.getItem("token") || null;
    userRole = localStorage.getItem("userRole") || null;
    currentUserEmail = localStorage.getItem("currentUserEmail") || null;
    currentUsername = localStorage.getItem("currentUsername") || null;
} catch (e) {
    console.warn("localStorage is not accessible (e.g. running on file:// protocol). Session state will not persist.", e);
}

function safeSetStorage(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch (e) {
        console.warn("localStorage write blocked:", e);
    }
}

function safeClearStorage() {
    try {
        localStorage.clear();
    } catch (e) {
        console.warn("localStorage clear blocked:", e);
    }
}

// DOM Elements
const appContainer = document.querySelector(".app-container");
const authOverlay = document.getElementById("auth-overlay");
const scrapeModal = document.getElementById("scrape-modal");
const openScrapeBtn = document.getElementById("open-scrape-modal");
const closeScrapeBtn = document.getElementById("close-scrape-modal");
const scrapeForm = document.getElementById("scrape-form");
const startScrapeBtn = document.getElementById("start-scrape-btn");
const crawlerTerminal = document.getElementById("crawler-terminal");
const terminalLogs = document.getElementById("terminal-logs");
const terminalStatus = document.getElementById("terminal-status");
const terminalLoader = document.getElementById("terminal-loader");
const emptyStateScrapeBtn = document.getElementById("empty-state-scrape-btn");

const sessionList = document.getElementById("session-list");
const activeSiteTitle = document.getElementById("active-site-title");
const activeSiteUrl = document.getElementById("active-site-url");
const headerAnalytics = document.getElementById("header-analytics");
const analyticPages = document.getElementById("analytic-pages");
const analyticWords = document.getElementById("analytic-words");

const chatWindow = document.getElementById("chat-window");
const chatEmptyState = document.getElementById("chat-empty-state");
const messagesContainer = document.getElementById("messages-container");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatSubmit = document.getElementById("chat-submit");

// New DOM Elements
const openFeedbackBtn = document.getElementById("open-feedback-modal");
const feedbackModal = document.getElementById("feedback-modal");
const closeFeedbackBtn = document.getElementById("close-feedback-modal");
const feedbackForm = document.getElementById("feedback-form");

const openAdminBtn = document.getElementById("open-admin-btn");
const adminOverlay = document.getElementById("admin-overlay");
const closeAdminBtn = document.getElementById("close-admin-btn");

// --- Auth Fetch Helper ---
async function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (token) {
        options.headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(url, options);
    if (response.status === 401) {
        logout();
    }
    return response;
}

// --- Check Authentication ---
function checkAuth() {
    if (token) {
        authOverlay.style.display = "none";
        appContainer.style.display = "grid";
        document.getElementById("user-profile-section").style.display = "flex";
        document.getElementById("user-display-name").innerText = currentUsername || "";
        document.getElementById("user-display-email").innerText = currentUserEmail || "";
        
        if (userRole === "admin") {
            openAdminBtn.style.display = "flex";
        } else {
            openAdminBtn.style.display = "none";
        }
        
        fetchSessions();
    } else {
        authOverlay.style.display = "flex";
        appContainer.style.display = "none";
    }
}

// --- Modal Control ---
function openModal() {
    scrapeModal.style.display = "flex";
    crawlerTerminal.style.display = "none";
    scrapeForm.style.display = "block";
    document.getElementById("scrape-url").value = "";
}

function closeModal() {
    scrapeModal.style.display = "none";
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
        statusPollInterval = null;
    }
}

openScrapeBtn.addEventListener("click", openModal);
emptyStateScrapeBtn.addEventListener("click", openModal);
closeScrapeBtn.addEventListener("click", closeModal);

// --- Session Handling ---
async function fetchSessions() {
    try {
        const response = await authFetch(`${API_BASE}/sessions`);
        const sessions = await response.json();
        renderSessions(sessions);
    } catch (e) {
        console.error("Error fetching sessions:", e);
    }
}

function renderSessions(sessions) {
    sessionList.innerHTML = "";
    if (!sessions || sessions.length === 0) {
        sessionList.innerHTML = `<div class="no-sessions">No sessions found. Ingest a website to begin!</div>`;
        return;
    }
    
    sessions.forEach(session => {
        const item = document.createElement("li");
        item.className = `session-item ${session.session_id === activeSessionId ? 'active' : ''}`;
        
        // Clean URL to hostname for display
        let displayUrl = session.url;
        try {
            displayUrl = new URL(session.url).hostname;
        } catch (_) {}
        
        const date = new Date(session.created_at).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
        
        item.innerHTML = `
            <span class="session-item-url" title="${session.url}">${displayUrl}</span>
            <span class="session-item-date">${date}</span>
            <button class="btn-delete-session" title="Delete Session">
                <i class="fa-solid fa-trash-can"></i>
            </button>
        `;
        
        item.addEventListener("click", () => selectSession(session.session_id, session.url));
        
        const deleteBtn = item.querySelector(".btn-delete-session");
        deleteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (confirm(`Are you sure you want to clear/delete the chat session for ${displayUrl}?`)) {
                deleteSession(session.session_id);
            }
        });
        
        sessionList.appendChild(item);
    });
}

async function deleteSession(sessionId) {
    try {
        const response = await authFetch(`${API_BASE}/sessions/${sessionId}`, {
            method: "DELETE"
        });
        if (response.ok) {
            if (activeSessionId === sessionId) {
                // Reset active session state
                activeSessionId = null;
                activeSessionUrl = "";
                
                // Reset UI
                activeSiteTitle.innerText = "Select or Ingest a Website";
                activeSiteUrl.innerText = "No URL selected";
                activeSiteUrl.removeAttribute("href");
                
                chatEmptyState.style.display = "flex";
                messagesContainer.style.display = "none";
                messagesContainer.innerHTML = "";
                
                chatInput.disabled = true;
                chatSubmit.disabled = true;
                chatInput.placeholder = "Ask a question about the scraped website...";
                
                openFeedbackBtn.style.display = "none";
                headerAnalytics.style.display = "none";
            }
            await fetchSessions();
        } else {
            const error = await response.json();
            alert(`Failed to delete session: ${error.detail || "Unknown error"}`);
        }
    } catch (e) {
        console.error("Error deleting session:", e);
        alert("Failed to delete session due to network error.");
    }
}


async function selectSession(sessionId, url) {
    activeSessionId = sessionId;
    activeSessionUrl = url;
    
    // Highlight selected in list
    document.querySelectorAll(".session-item").forEach(el => el.classList.remove("active"));
    const items = document.querySelectorAll(".session-item-url");
    items.forEach(item => {
        if (item.getAttribute("title") === url) {
            item.parentElement.classList.add("active");
        }
    });

    // Update active site header
    let displayTitle = url;
    try {
        displayTitle = new URL(url).hostname;
    } catch (_) {}
    
    activeSiteTitle.innerText = displayTitle;
    activeSiteUrl.innerText = url;
    activeSiteUrl.setAttribute("href", url);
    activeSiteUrl.setAttribute("target", "_blank");
    
    // Enable input fields
    chatInput.disabled = false;
    chatSubmit.disabled = false;
    chatInput.placeholder = "Ask a question about the scraped website...";
    
    // Show Feedback button
    openFeedbackBtn.style.display = "inline-flex";
    
    // Fetch and show history
    chatEmptyState.style.display = "none";
    messagesContainer.style.display = "flex";
    messagesContainer.innerHTML = "";
    
    try {
        const res = await authFetch(`${API_BASE}/sessions/${sessionId}/history`);
        const data = await res.json();
        
        // Load messages history
        data.messages.forEach(msg => {
            appendMessage(msg.role, msg.content);
        });
        scrollToBottom();
    } catch (e) {
        console.error("Error loading history:", e);
    }
}

// --- Scraping Form Submission & Progress Polling ---
scrapeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = document.getElementById("scrape-url").value;
    const maxDepth = parseInt(document.getElementById("max-depth").value);
    const maxPages = parseInt(document.getElementById("max-pages").value);
    
    startScrapeBtn.disabled = true;
    startScrapeBtn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Triggering Scraping...`;
    
    try {
        const response = await authFetch(`${API_BASE}/scrape`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, max_depth: maxDepth, max_pages: maxPages })
        });
        
        if (response.ok) {
            // Show Live terminal progression
            scrapeForm.style.display = "none";
            crawlerTerminal.style.display = "block";
            terminalLogs.innerHTML = "";
            terminalStatus.innerText = "Initializing scraping background task...";
            terminalLoader.style.display = "inline-block";
            
            // Poll for status
            startStatusPolling(url);
        } else {
            const error = await response.json();
            alert(`Error: ${error.detail || "Failed to trigger scraping."}`);
            startScrapeBtn.disabled = false;
            startScrapeBtn.innerHTML = `<i class="fa-solid fa-rocket"></i> Start Scraper & Indexer`;
        }
    } catch (err) {
        console.error("Error triggering scrape:", err);
        alert("Failed to connect to the backend server.");
        startScrapeBtn.disabled = false;
        startScrapeBtn.innerHTML = `<i class="fa-solid fa-rocket"></i> Start Scraper & Indexer`;
    }
});

function startStatusPolling(url) {
    if (statusPollInterval) clearInterval(statusPollInterval);
    
    statusPollInterval = setInterval(async () => {
        try {
            const res = await authFetch(`${API_BASE}/status`);
            const status = await res.json();
            
            // Render logs in terminal
            terminalLogs.innerHTML = "";
            status.logs.forEach(log => {
                const logLine = document.createElement("div");
                logLine.innerText = `> ${log}`;
                terminalLogs.appendChild(logLine);
            });
            terminalLogs.scrollTop = terminalLogs.scrollHeight; // Scroll terminal to bottom
            
            // Update terminal header status text
            if (status.state === "crawling") {
                terminalStatus.innerText = `Scraping: ${status.visited_count} / ${status.max_pages} pages processed...`;
            } else if (status.state === "completed") {
                terminalStatus.innerText = "Indexing successfully completed!";
                terminalLoader.style.display = "none";
                clearInterval(statusPollInterval);
                statusPollInterval = null;
                
                // Create new chat session for this newly crawled site!
                await createSessionAndStartChat(url, status.analytics);
            } else if (status.state === "error") {
                terminalStatus.innerText = "Scraping failed with errors.";
                terminalLoader.style.display = "none";
                clearInterval(statusPollInterval);
                statusPollInterval = null;
                startScrapeBtn.disabled = false;
                startScrapeBtn.innerHTML = `<i class="fa-solid fa-rocket"></i> Start Scraper & Indexer`;
            }
        } catch (e) {
            console.error("Error polling status:", e);
        }
    }, 1000); // Poll every second
}

async function createSessionAndStartChat(url, analytics) {
    try {
        const response = await authFetch(`${API_BASE}/sessions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url })
        });
        
        if (response.ok) {
            const session = await response.json();
            
            // Close modal with success animation
            terminalStatus.innerHTML = `<span style="color: #22c55e;"><i class="fa-solid fa-circle-check"></i> Session created! Opening workspace...</span>`;
            
            setTimeout(async () => {
                closeModal();
                await fetchSessions();
                await selectSession(session.session_id, session.url);
                
                // Render analytics headers
                headerAnalytics.style.display = "flex";
                analyticPages.innerText = analytics.total_pages_scraped || 0;
                analyticWords.innerText = (analytics.total_words_indexed || 0).toLocaleString();
                
                // Restore scraping button
                startScrapeBtn.disabled = false;
                startScrapeBtn.innerHTML = `<i class="fa-solid fa-rocket"></i> Start Scraper & Indexer`;
            }, 1500);
        }
    } catch (e) {
        console.error("Error creating session:", e);
    }
}

// --- Chat Messages Ingestion & Rendering ---
function appendMessage(role, text, citations = null) {
    const bubble = document.createElement("div");
    bubble.className = `message-bubble ${role}`;
    
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.innerHTML = role === "user" ? `<i class="fa-solid fa-user"></i>` : `<i class="fa-solid fa-robot"></i>`;
    
    const content = document.createElement("div");
    content.className = "message-content";
    
    // Parse Markdown text using marked library securely
    if (typeof marked !== 'undefined') {
        content.innerHTML = marked.parse(text);
    } else {
        content.innerText = text;
    }
    
    // Append Citations Accordion if present
    if (role === "assistant" && citations && citations.length > 0) {
        const citationsDiv = document.createElement("div");
        citationsDiv.className = "message-citations";
        
        const title = document.createElement("div");
        title.className = "citations-title";
        title.innerHTML = `<i class="fa-solid fa-chevron-right"></i> Source Citations (${citations.length})`;
        
        const list = document.createElement("div");
        list.className = "citations-list";
        list.style.display = "none"; // start collapsed
        
        citations.forEach(cit => {
            const displayTitle = cit.title.length > 20 ? cit.title.slice(0, 18) + "..." : cit.title;
            const scorePercent = Math.round(cit.score * 100);
            
            const chip = document.createElement("a");
            chip.className = "citation-chip";
            chip.setAttribute("href", cit.url);
            chip.setAttribute("target", "_blank");
            chip.setAttribute("title", `${cit.title}\nURL: ${cit.url}\nSimilarity: ${scorePercent}%`);
            chip.innerHTML = `<i class="fa-solid fa-link"></i> ${displayTitle} (${scorePercent}%)`;
            
            list.appendChild(chip);
        });
        
        // Expand/Collapse interactions
        title.addEventListener("click", () => {
            const isCollapsed = list.style.display === "none";
            list.style.display = isCollapsed ? "flex" : "none";
            title.classList.toggle("expanded", isCollapsed);
        });
        
        citationsDiv.appendChild(title);
        citationsDiv.appendChild(list);
        content.appendChild(citationsDiv);
    }
    
    bubble.appendChild(avatar);
    bubble.appendChild(content);
    messagesContainer.appendChild(bubble);
}

function scrollToBottom() {
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

// --- Dynamic Stream Fetch Chat Route ---
chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = chatInput.value.trim();
    if (!query || !activeSessionId) return;
    
    const selectedLanguage = document.getElementById("language-selector").value;
    
    // 1. Append User bubble
    appendMessage("user", query);
    chatInput.value = "";
    scrollToBottom();
    
    // 2. Disable input fields
    chatInput.disabled = true;
    chatSubmit.disabled = true;
    
    // 3. Append assistant typing mock bubble
    const assistantBubble = document.createElement("div");
    assistantBubble.className = "message-bubble assistant";
    
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.innerHTML = `<i class="fa-solid fa-robot"></i>`;
    
    const content = document.createElement("div");
    content.className = "message-content";
    content.innerHTML = `
        <div class="typing-loader" id="chat-typing-loader">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
        </div>
    `;
    
    assistantBubble.appendChild(avatar);
    assistantBubble.appendChild(content);
    messagesContainer.appendChild(assistantBubble);
    scrollToBottom();
    
    // 4. Fetch Response via SSE readable stream reader
    try {
        const response = await authFetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: activeSessionId, message: query, language: selectedLanguage })
        });
        
        if (!response.ok) {
            throw new Error("Failed to connect to assistant stream.");
        }
        
        // Remove typing loader
        content.innerHTML = "";
        
        // Set up SSE reader variables
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";
        let citations = [];
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunkStr = decoder.decode(value);
            
            // Split by lines in case multiple tokens arrived together
            const lines = chunkStr.split("\n");
            
            for (const line of lines) {
                if (line.startsWith("__CITATIONS__:")) {
                    // Extract Citations JSON
                    try {
                        const jsonStr = line.replace("__CITATIONS__:", "");
                        citations = JSON.parse(jsonStr);
                    } catch (err) {
                        console.error("Error parsing citations:", err);
                    }
                } else if (line) {
                    fullText += line;
                    
                    // Render streaming text using marked markdown parser
                    if (typeof marked !== 'undefined') {
                        content.innerHTML = marked.parse(fullText);
                    } else {
                        content.innerText = fullText;
                    }
                    scrollToBottom();
                }
            }
        }
        
        // Final render: Append Citations accordion to bubble once typing finishes
        if (citations && citations.length > 0) {
            const citationsDiv = document.createElement("div");
            citationsDiv.className = "message-citations";
            
            const title = document.createElement("div");
            title.className = "citations-title";
            title.innerHTML = `<i class="fa-solid fa-chevron-right"></i> Source Citations (${citations.length})`;
            
            const list = document.createElement("div");
            list.className = "citations-list";
            list.style.display = "none";
            
            citations.forEach(cit => {
                const displayTitle = cit.title.length > 20 ? cit.title.slice(0, 18) + "..." : cit.title;
                const scorePercent = Math.round(cit.score * 100);
                
                const chip = document.createElement("a");
                chip.className = "citation-chip";
                chip.setAttribute("href", cit.url);
                chip.setAttribute("target", "_blank");
                chip.setAttribute("title", `${cit.title}\nURL: ${cit.url}\nSimilarity: ${scorePercent}%`);
                chip.innerHTML = `<i class="fa-solid fa-link"></i> ${displayTitle} (${scorePercent}%)`;
                
                list.appendChild(chip);
            });
            
            title.addEventListener("click", () => {
                const isCollapsed = list.style.display === "none";
                list.style.display = isCollapsed ? "flex" : "none";
                title.classList.toggle("expanded", isCollapsed);
            });
            
            citationsDiv.appendChild(title);
            citationsDiv.appendChild(list);
            content.appendChild(citationsDiv);
            scrollToBottom();
        }
        
    } catch (err) {
        console.error("Chat streaming failed:", err);
        content.innerHTML = `<span style="color: #ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> Network error or backend server disconnected. Check your connection.</span>`;
    } finally {
        // Re-enable inputs
        chatInput.disabled = false;
        chatSubmit.disabled = false;
        chatInput.focus();
    }
});

// --- Auth Controls & Forms ---
document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;
    
    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        
        if (res.ok) {
            const data = await res.json();
            token = data.token;
            userRole = data.role;
            currentUserEmail = data.email;
            currentUsername = data.username;
            
            safeSetStorage("token", token);
            safeSetStorage("userRole", userRole);
            safeSetStorage("currentUserEmail", currentUserEmail);
            safeSetStorage("currentUsername", currentUsername);
            
            document.getElementById("login-email").value = "";
            document.getElementById("login-password").value = "";
            checkAuth();
        } else {
            const err = await res.json();
            alert(`Login failed: ${err.detail || "Invalid credentials"}`);
        }
    } catch (err) {
        console.error(err);
        alert("Error connecting to server.");
    }
});

document.getElementById("signup-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("signup-username").value;
    const email = document.getElementById("signup-email").value;
    const password = document.getElementById("signup-password").value;
    
    try {
        const res = await fetch(`${API_BASE}/auth/signup`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, username, password })
        });
        
        if (res.ok) {
            alert("Signup successful! Please sign in.");
            document.getElementById("signup-username").value = "";
            document.getElementById("signup-email").value = "";
            document.getElementById("signup-password").value = "";
            showCard("login");
        } else {
            const err = await res.json();
            alert(`Signup failed: ${err.detail || "Invalid details"}`);
        }
    } catch (err) {
        console.error(err);
        alert("Error connecting to server.");
    }
});

document.getElementById("go-to-signup").addEventListener("click", (e) => {
    e.preventDefault();
    showCard("signup");
});
document.getElementById("go-to-login").addEventListener("click", (e) => {
    e.preventDefault();
    showCard("login");
});

function showCard(cardType) {
    if (cardType === "login") {
        document.getElementById("login-card").style.display = "flex";
        document.getElementById("signup-card").style.display = "none";
    } else {
        document.getElementById("login-card").style.display = "none";
        document.getElementById("signup-card").style.display = "flex";
    }
}

document.getElementById("logout-btn").addEventListener("click", logout);
function logout() {
    token = null;
    userRole = null;
    currentUserEmail = null;
    currentUsername = null;
    safeClearStorage();
    activeSessionId = null;
    activeSessionUrl = "";
    
    // Hide feedback button & modal
    openFeedbackBtn.style.display = "none";
    feedbackModal.style.display = "none";
    adminOverlay.style.display = "none";
    
    checkAuth();
}

// --- Feedback Handlers ---
openFeedbackBtn.addEventListener("click", () => {
    feedbackModal.style.display = "flex";
});
closeFeedbackBtn.addEventListener("click", () => {
    feedbackModal.style.display = "none";
});

feedbackForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const ratingEl = document.querySelector('input[name="rating"]:checked');
    if (!ratingEl) {
        alert("Please select a rating!");
        return;
    }
    const rating = parseInt(ratingEl.value);
    const comments = document.getElementById("feedback-comments").value;
    
    try {
        const res = await authFetch(`${API_BASE}/feedback`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rating, comments })
        });
        
        if (res.ok) {
            alert("Thank you for your feedback!");
            feedbackModal.style.display = "none";
            feedbackForm.reset();
        } else {
            const err = await res.json();
            alert(`Failed to submit feedback: ${err.detail}`);
        }
    } catch (err) {
        console.error(err);
        alert("Error submitting feedback.");
    }
});

// --- Admin Panel Handlers ---
openAdminBtn.addEventListener("click", () => {
    adminOverlay.style.display = "flex";
    loadAdminDashboard();
});
closeAdminBtn.addEventListener("click", () => {
    adminOverlay.style.display = "none";
});

async function loadAdminDashboard() {
    try {
        // 1. Fetch Stats
        const statsRes = await authFetch(`${API_BASE}/admin/stats`);
        if (!statsRes.ok) return;
        const statsData = await statsRes.json();
        
        document.getElementById("kpi-users").innerText = statsData.general.total_users;
        document.getElementById("kpi-words").innerText = statsData.general.total_words.toLocaleString();
        document.getElementById("kpi-sessions").innerText = statsData.general.active_sessions;
        document.getElementById("kpi-locked").innerText = statsData.general.locked_accounts;
        
        renderAdminCharts(statsData.activity);
        renderAdminFeedbackTable(statsData.feedback || []);
        
        // 2. Fetch Users
        const usersRes = await authFetch(`${API_BASE}/admin/users`);
        if (usersRes.ok) {
            const users = await usersRes.json();
            renderAdminUsersTable(users);
        }
        
        // 3. Load Wordcloud via Object URL blob
        loadWordCloud();
        
    } catch (err) {
        console.error("Error loading dashboard data:", err);
    }
}

async function loadWordCloud() {
    try {
        const res = await authFetch(`${API_BASE}/admin/feedback/wordcloud`);
        if (res.ok) {
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            document.getElementById("admin-wordcloud").src = url;
        }
    } catch (e) {
        console.error("Error loading wordcloud:", e);
    }
}

function renderAdminCharts(activity) {
    // 1. Languages Pie
    const langData = activity.languages || {};
    const langLabels = Object.keys(langData);
    const langValues = Object.values(langData);
    
    const langPlotData = [{
        values: langValues.length ? langValues : [1],
        labels: langLabels.length ? langLabels : ['None'],
        type: 'pie',
        hole: 0.4,
        marker: {
            colors: ['#6366f1', '#a855f7', '#06b6d4', '#10b981', '#f59e0b', '#ef4444']
        },
        textinfo: 'percent',
        hoverinfo: 'label+value'
    }];
    
    const chartLayout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8', family: 'Inter, sans-serif' },
        showlegend: true,
        legend: { orientation: 'h', x: 0, y: -0.2 },
        margin: { t: 20, b: 20, l: 20, r: 20 },
        height: 230
    };
    
    Plotly.newPlot('chart-languages', langPlotData, chartLayout, { displayModeBar: false });
    
    // 2. Models Bar
    const modelData = activity.model_queries || {};
    const modelLabels = Object.keys(modelData);
    const modelValues = Object.values(modelData);
    
    const modelPlotData = [{
        x: modelLabels.length ? modelLabels : ['Qwen-1.5B'],
        y: modelValues.length ? modelValues : [0],
        type: 'bar',
        marker: { color: '#a855f7' }
    }];
    
    const barLayout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8', family: 'Inter, sans-serif' },
        margin: { t: 20, b: 40, l: 40, r: 20 },
        height: 230,
        xaxis: { gridcolor: 'rgba(255,255,255,0.05)' },
        yaxis: { gridcolor: 'rgba(255,255,255,0.05)' }
    };
    
    Plotly.newPlot('chart-models', modelPlotData, barLayout, { displayModeBar: false });
    
    // 3. Feature Hits Bar
    const featureData = activity.feature_hits || {};
    const featureLabels = Object.keys(featureData);
    const featureValues = Object.values(featureData);
    
    const featurePlotData = [{
        x: featureLabels.length ? featureLabels : ['Crawl', 'Chat', 'Feedback'],
        y: featureValues.length ? featureValues : [0, 0, 0],
        type: 'bar',
        marker: { color: '#06b6d4' }
    }];
    
    Plotly.newPlot('chart-features', featurePlotData, barLayout, { displayModeBar: false });
}

function renderAdminUsersTable(users) {
    const tbody = document.getElementById("admin-users-table");
    tbody.innerHTML = "";
    
    if (!users || users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;">No users found.</td></tr>`;
        return;
    }
    
    users.forEach(user => {
        const date = new Date(user.created_at).toLocaleDateString();
        const roleBadge = user.is_admin ? '<span class="badge badge-admin">Admin</span>' : '<span class="badge badge-user">User</span>';
        const statusBadge = user.is_locked ? '<span class="badge badge-status-locked">Locked</span>' : '<span class="badge badge-status-active">Active</span>';
        
        const isSelf = user.email === currentUserEmail;
        const disableAttr = isSelf ? 'disabled' : '';
        
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${user.username}</td>
            <td>${user.email}</td>
            <td>${date}</td>
            <td>${roleBadge}</td>
            <td>${statusBadge}</td>
            <td>
                <div class="table-actions">
                    <button class="btn btn-secondary promote-user-btn" data-email="${user.email}" ${disableAttr} style="padding: 4px 8px; font-size: 11px;">
                        ${user.is_admin ? 'Demote' : 'Promote'}
                    </button>
                    <button class="btn btn-secondary lock-user-btn" data-email="${user.email}" ${disableAttr} style="padding: 4px 8px; font-size: 11px;">
                        ${user.is_locked ? 'Unlock' : 'Lock'}
                    </button>
                    <button class="btn btn-danger delete-user-btn" data-email="${user.email}" ${disableAttr} style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); padding: 4px 8px; font-size: 11px;">
                        Delete
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
    
    // Bind actions
    document.querySelectorAll(".promote-user-btn").forEach(btn => {
        btn.addEventListener("click", () => handleUserAction(btn.dataset.email, "promote"));
    });
    document.querySelectorAll(".lock-user-btn").forEach(btn => {
        btn.addEventListener("click", () => handleUserAction(btn.dataset.email, "lock"));
    });
    document.querySelectorAll(".delete-user-btn").forEach(btn => {
        btn.addEventListener("click", () => handleUserAction(btn.dataset.email, "delete"));
    });
}

async function handleUserAction(email, action) {
    if (action === "delete" && !confirm(`Are you sure you want to delete user account ${email}?`)) {
        return;
    }
    
    try {
        const method = action === "delete" ? "DELETE" : "POST";
        const res = await authFetch(`${API_BASE}/admin/users/${email}/${action}`, { method });
        if (res.ok) {
            const data = await res.json();
            alert(data.message || "Action completed successfully");
            loadAdminDashboard();
        } else {
            const err = await res.json();
            alert(`Action failed: ${err.detail}`);
        }
    } catch (e) {
        console.error(e);
        alert("Network error.");
    }
}

function renderAdminFeedbackTable(feedbacks) {
    const tbody = document.getElementById("admin-feedback-table");
    tbody.innerHTML = "";
    
    if (feedbacks.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;">No feedback submitted yet.</td></tr>`;
        return;
    }
    
    feedbacks.forEach(f => {
        const date = new Date(f.created_at).toLocaleString();
        let stars = "";
        for (let i = 1; i <= 5; i++) {
            stars += i <= f.rating ? '<i class="fa-solid fa-star" style="color: #f59e0b; margin-right: 2px;"></i>' : '<i class="fa-regular fa-star" style="color: var(--text-dark); margin-right: 2px;"></i>';
        }
        
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${f.user_email}</td>
            <td>${stars}</td>
            <td>${f.comments || '<em style="color: var(--text-dark)">No comment</em>'}</td>
            <td>${date}</td>
        `;
        tbody.appendChild(row);
    });
}

// CSV Exports
document.getElementById("export-feedback-btn").addEventListener("click", () => handleCSVExport("feedback"));
document.getElementById("export-activity-btn").addEventListener("click", () => handleCSVExport("activity"));

async function handleCSVExport(type) {
    try {
        const res = await authFetch(`${API_BASE}/admin/export/${type}`);
        if (res.ok) {
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${type}_export_${Date.now()}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        } else {
            const err = await res.json();
            alert(`Export failed: ${err.detail}`);
        }
    } catch (e) {
        console.error(e);
        alert("Export failed due to network error.");
    }
}

// Initialize app on window load
window.addEventListener("DOMContentLoaded", () => {
    checkAuth();
});
