// ==========================================================================
// ProsArtisan Chat Application JS Logic
// State Management, Real JWT & Google OAuth, SSE Streaming, Premium UX.
// ==========================================================================

// Global state variables
let state = {
    isLoggedIn: false,
    user: null, // { email, id, nom, avatar_url, type_abonnement }
    currentConversationId: null,
    conversations: [],
    selectedImage: null, // base64 string or file URL
};

// Dom Elements
const sidebar = document.getElementById('sidebar');
const conversationsList = document.getElementById('conversations-list');
const historyEmpty = document.getElementById('history-empty');
const ctaSidebarLogin = document.getElementById('cta-sidebar-login');
const userProfileFooter = document.getElementById('user-profile-footer');
const userEmailLbl = document.getElementById('user-email-lbl');
const authButtonsHeader = document.getElementById('auth-buttons-header');
const userAvatarHeader = document.getElementById('user-avatar-header');
const landingContainer = document.getElementById('landing-container');
const messagesStream = document.getElementById('messages-stream');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const imagePreviewBox = document.getElementById('image-preview-box');
const previewImgName = document.getElementById('preview-img-name');
const loginModal = document.getElementById('login-modal');

// Initialize App on DOM Loaded
document.addEventListener('DOMContentLoaded', () => {
    // 1. Theme recovery
    const savedTheme = localStorage.getItem('prosartisan_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    const sunIcon = document.querySelector('.sun-icon');
    const moonIcon = document.querySelector('.moon-icon');
    if (savedTheme === 'light') {
        sunIcon?.classList.add('hidden');
        moonIcon?.classList.remove('hidden');
    }

    // 2. Check local storage for existing session
    const storedUser = localStorage.getItem('prosartisan_user');
    const storedToken = localStorage.getItem('prosartisan_token');
    
    if (storedUser && storedToken) {
        try {
            state.user = JSON.parse(storedUser);
            state.isLoggedIn = true;
            updateAuthUI();
            loadConversations();
            updateQuotaUI();
        } catch (e) {
            console.error("Failed to parse stored session:", e);
            logout();
        }
    } else {
        updateAuthUI();
        updateQuotaUI();
    }

    // Auto-expand textarea input
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight - 4) + 'px';
    });

    // Enter / Shift+Enter key listeners
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Google Identity Services setup
    setTimeout(() => {
        if (window.google && window.google.accounts) {
            try {
                google.accounts.id.initialize({
                    client_id: "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com",
                    callback: handleGoogleCredentialResponse
                });
                google.accounts.id.renderButton(
                    document.getElementById("google-signin-btn"),
                    { theme: "outline", size: "large", width: 240 }
                );
            } catch (err) {
                console.warn("Failed to initialize native Google Sign-in button:", err);
            }
        }
    }, 1000);
});

// Theme switcher
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('prosartisan_theme', newTheme);
    
    const sunIcon = document.querySelector('.sun-icon');
    const moonIcon = document.querySelector('.moon-icon');
    if (newTheme === 'light') {
        sunIcon?.classList.add('hidden');
        moonIcon?.classList.remove('hidden');
    } else {
        sunIcon?.classList.remove('hidden');
        moonIcon?.classList.add('hidden');
    }
}

// Update Quota display inside Sidebar
async function updateQuotaUI() {
    const quotaText = document.getElementById('quota-text-lbl');
    const progressBar = document.getElementById('quota-progress-bar');
    if (!quotaText || !progressBar) return;
    
    try {
        const headers = {};
        if (state.isLoggedIn) {
            const token = localStorage.getItem('prosartisan_token');
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch('/api/quota', { headers });
        if (response.ok) {
            const data = await response.json();
            if (data.statut === 'premium') {
                quotaText.textContent = "PRO ∞";
                progressBar.style.width = "100%";
                progressBar.style.backgroundColor = "var(--primary)";
                
                const planBadge = document.getElementById('user-plan-badge');
                if (planBadge) planBadge.textContent = "Artisan Pro";
            } else {
                const rest = data.restantes;
                const total = 5; // Default questions count
                quotaText.textContent = `${rest} / ${total}`;
                
                const percent = (rest / total) * 100;
                progressBar.style.width = `${percent}%`;
                
                if (rest <= 1) {
                    progressBar.style.backgroundColor = "#EF5350"; // alert red
                } else if (rest <= 3) {
                    progressBar.style.backgroundColor = "#FFA726"; // warning orange
                } else {
                    progressBar.style.backgroundColor = "var(--primary)"; // theme amber
                }
                
                const planBadge = document.getElementById('user-plan-badge');
                if (planBadge) planBadge.textContent = "Gratuit";
            }
        }
    } catch (e) {
        console.warn("Failed to update quota UI:", e);
    }
}

// Update UI based on connection state
function updateAuthUI() {
    if (state.isLoggedIn) {
        // Logged-in view
        ctaSidebarLogin.classList.add('hidden');
        userProfileFooter.classList.remove('hidden');
        userEmailLbl.textContent = state.user.nom || state.user.email;
        
        // Header profile
        authButtonsHeader.classList.add('hidden');
        userAvatarHeader.classList.remove('hidden');
        
        const avatarLetter = (state.user.nom || state.user.email || 'U').charAt(0).toUpperCase();
        document.querySelector('.header-avatar').textContent = avatarLetter;
        document.getElementById('user-avatar-lbl').textContent = avatarLetter;
        historyEmpty.classList.add('hidden');
        
        const searchBar = document.getElementById('sidebar-search-container');
        if (searchBar) searchBar.classList.remove('hidden');
    } else {
        // Disconnected view
        ctaSidebarLogin.classList.remove('hidden');
        userProfileFooter.classList.add('hidden');
        
        // Header buttons
        authButtonsHeader.classList.remove('hidden');
        userAvatarHeader.classList.add('hidden');
        historyEmpty.classList.remove('hidden');
        
        // Clear list
        conversationsList.innerHTML = '';
        state.conversations = [];
        
        const searchBar = document.getElementById('sidebar-search-container');
        if (searchBar) searchBar.classList.add('hidden');
    }
}

// Fetch Conversations list for connected user
async function loadConversations(q = null) {
    if (!state.isLoggedIn) return;

    try {
        const token = localStorage.getItem('prosartisan_token');
        let url = `/api/conversations`;
        if (q) {
            url += `?q=${encodeURIComponent(q)}`;
        }
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (response.ok) {
            state.conversations = await response.json();
            renderConversationsList();
        } else if (response.status === 401) {
            logout();
        } else {
            showToast("Impossible de charger l'historique.");
        }
    } catch (e) {
        console.error("Failed to fetch conversations:", e);
        showToast("Erreur de connexion avec le serveur.");
    }
}

// Handle search field input
function handleSidebarSearch() {
    const input = document.getElementById('sidebar-search-input');
    if (input) {
        loadConversations(input.value.trim());
    }
}

// Render historical list in sidebar
function renderConversationsList() {
    conversationsList.innerHTML = '';
    
    if (state.conversations.length === 0) {
        historyEmpty.textContent = "Aucun chat récent.";
        historyEmpty.classList.remove('hidden');
        return;
    }
    historyEmpty.classList.add('hidden');

    state.conversations.forEach(conv => {
        const li = document.createElement('li');
        const activeClass = state.currentConversationId === conv.id ? 'active' : '';
        
        li.innerHTML = `
            <button class="conv-item ${activeClass}" onclick="selectConversation('${conv.id}')" id="conv-btn-${conv.id}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px; flex-shrink: 0;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                <span class="conv-title-text" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%; display: block;">${conv.title || "Discussions"}</span>
            </button>
            <button class="edit-conv-btn" onclick="startRenameConversation('${conv.id}', event)" title="Renommer">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            </button>
            <button class="delete-conv-btn" onclick="deleteConversation('${conv.id}', event)" title="Supprimer la discussion">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
        `;
        conversationsList.appendChild(li);
    });
}

// Rename conversation helper
function startRenameConversation(id, event) {
    event.stopPropagation();
    const btn = document.getElementById(`conv-btn-${id}`);
    if (!btn) return;
    const titleSpan = btn.querySelector('.conv-title-text');
    if (!titleSpan) return;
    const oldTitle = titleSpan.textContent;
    
    const input = document.createElement('input');
    input.type = 'text';
    input.value = oldTitle;
    input.style.width = '80%';
    input.style.background = 'rgba(255,255,255,0.15)';
    input.style.border = '1px solid var(--primary)';
    input.style.color = '#fff';
    input.style.borderRadius = '4px';
    input.style.padding = '2px 6px';
    input.style.fontSize = '12px';
    input.style.outline = 'none';
    
    titleSpan.replaceWith(input);
    input.focus();
    input.select();
    
    const commitRename = async () => {
        const newTitle = input.value.trim();
        if (!newTitle || newTitle === oldTitle) {
            input.replaceWith(titleSpan);
            return;
        }
        
        try {
            const token = localStorage.getItem('prosartisan_token');
            const response = await fetch(`/api/conversations/${id}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ title: newTitle })
            });
            
            if (response.ok) {
                titleSpan.textContent = newTitle;
                input.replaceWith(titleSpan);
                showToast("Discussion renommée.");
                loadConversations();
            } else {
                showToast("Échec du renommage.");
                input.replaceWith(titleSpan);
            }
        } catch (e) {
            showToast("Erreur de connexion.");
            input.replaceWith(titleSpan);
        }
    };
    
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            commitRename();
        } else if (e.key === 'Escape') {
            input.replaceWith(titleSpan);
        }
    });
    
    input.addEventListener('blur', () => {
        setTimeout(commitRename, 200);
    });
}

// Select and load a conversation
async function selectConversation(id) {
    state.currentConversationId = id;
    renderConversationsList(); // Update active highlights

    try {
        const token = localStorage.getItem('prosartisan_token');
        const response = await fetch(`/api/conversations/${id}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (response.ok) {
            const data = await response.json();
            
            // Show messages
            landingContainer.classList.add('hidden');
            messagesStream.classList.remove('hidden');
            messagesStream.innerHTML = '';

            data.messages.forEach(msg => {
                appendMessageBubble(msg.role, msg.content, msg.image_url);
            });

            scrollToBottom();
        } else {
            showToast("Erreur lors de la récupération du chat.");
        }
    } catch (e) {
        console.error("Load conversation error:", e);
        showToast("Erreur serveur.");
    }
}

// Delete conversation
async function deleteConversation(id, event) {
    event.stopPropagation(); // Avoid selecting the item

    if (!confirm("Voulez-vous supprimer cette discussion ?")) return;

    try {
        const token = localStorage.getItem('prosartisan_token');
        const response = await fetch(`/api/conversations/${id}`, { 
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (response.ok) {
            showToast("Discussion supprimée.");
            if (state.currentConversationId === id) {
                startNewChat();
            }
            loadConversations();
        } else {
            showToast("Échec de la suppression.");
        }
    } catch (e) {
        console.error("Delete conversation error:", e);
        showToast("Erreur réseau.");
    }
}

// Reset chat view to New Chat
function startNewChat() {
    state.currentConversationId = null;
    landingContainer.classList.remove('hidden');
    messagesStream.classList.add('hidden');
    messagesStream.innerHTML = '';
    chatInput.value = '';
    chatInput.style.height = 'auto';
    clearSelectedImage();
    renderConversationsList();
}

// Toggle Sidebar on mobile
function toggleSidebar() {
    sidebar.classList.toggle('open');
}

// Trigger input files
function triggerImageUpload() {
    document.getElementById('image-upload').click();
}

// Handle Image Selection
function handleImageSelection() {
    const file = document.getElementById('image-upload').files[0];
    if (!file) return;

    // Convert file to Base64
    const reader = new FileReader();
    reader.onload = function(e) {
        state.selectedImage = e.target.result;
        previewImgName.textContent = file.name;
        imagePreviewBox.classList.remove('hidden');
        sendBtn.classList.remove('disabled');
    };
    reader.readAsDataURL(file);
}

// Clear selected image
function clearSelectedImage() {
    state.selectedImage = null;
    document.getElementById('image-upload').value = '';
    imagePreviewBox.classList.add('hidden');
    handleInputKeyPress();
}

// Auto enable/disable send button
function handleInputKeyPress() {
    const text = chatInput.value.trim();
    if (text.length > 0 || state.selectedImage !== null) {
        sendBtn.classList.remove('disabled');
    } else {
        sendBtn.classList.add('disabled');
    }
}

// Fill input from suggestion chips
function fillInput(text) {
    chatInput.value = text;
    chatInput.style.height = 'auto';
    chatInput.style.height = (chatInput.scrollHeight - 4) + 'px';
    sendBtn.classList.remove('disabled');
    chatInput.focus();
}

// Real speech recognition utilizing Web Speech API
function startSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        showToast("🎤 Entrée vocale non supportée sur ce navigateur.");
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'fr-FR';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    showToast("🎤 Écoute en cours... Parlez maintenant.");
    recognition.start();

    recognition.onresult = function(event) {
        const text = event.results[0][0].transcript;
        fillInput(text);
        showToast("🎤 Transcription complétée.");
    };

    recognition.onerror = function() {
        showToast("🎤 Échec de la reconnaissance vocale.");
    };
}

// Show helper constructions toast
function showUnderConstruction(feature) {
    showToast(`🛠️ Module ${feature} en cours de développement.`);
}

// Send Message
async function sendMessage() {
    const text = chatInput.value.trim();
    const image = state.selectedImage;

    if (text.length === 0 && image === null) return;

    // Clear input bar
    chatInput.value = '';
    chatInput.style.height = 'auto';
    sendBtn.classList.add('disabled');
    clearSelectedImage();

    // Show Chat Stream
    landingContainer.classList.add('hidden');
    messagesStream.classList.remove('hidden');

    // 1. Add User bubble
    appendMessageBubble('user', text, image);
    scrollToBottom();

    // 2. Add empty Assistant bubble with a typing cursor indicator
    const assistantBubbleId = 'assistant_' + Date.now();
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble assistant';
    bubble.id = assistantBubbleId;
    bubble.innerHTML = `
        <div class="msg-avatar">A</div>
        <div class="msg-content">
            <div class="streaming-text"><span class="cursor">▌</span></div>
        </div>
    `;
    messagesStream.appendChild(bubble);
    scrollToBottom();

    // 3. Prepare payload
    const payload = {
        question: text,
        metier_id: 1, // Default Batiment
        image_url: image
    };

    if (state.isLoggedIn && state.currentConversationId) {
        payload.conversation_id = state.currentConversationId;
    }

    try {
        const headers = { 'Content-Type': 'application/json' };
        if (state.isLoggedIn) {
            const token = localStorage.getItem('prosartisan_token');
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            bubble.querySelector('.streaming-text').innerHTML = "⚠️ Désolé chef, une erreur s'est produite lors de la connexion à l'assistant. Veuillez réessayer.";
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let fullResponseText = "";
        let buffer = "";
        let sources = [];

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            
            // Keep the last partial line in the buffer
            buffer = lines.pop();

            for (const line of lines) {
                const cleanLine = line.trim();
                if (!cleanLine) continue;

                if (cleanLine.startsWith("event: info")) {
                    // event info contains meta like conversation ID and sources list
                } else if (cleanLine.startsWith("event: chunk")) {
                    // chunk identifier
                } else if (cleanLine.startsWith("data:")) {
                    const dataStr = cleanLine.substring(5).trim();
                    try {
                        const parsed = JSON.parse(dataStr);
                        if (parsed && typeof parsed === 'object') {
                            if (parsed.conversation_id) {
                                if (state.isLoggedIn && !state.currentConversationId) {
                                    state.currentConversationId = parsed.conversation_id;
                                    loadConversations();
                                }
                            }
                            if (parsed.sources) {
                                sources = parsed.sources;
                            }
                        } else if (typeof parsed === 'string') {
                            fullResponseText += parsed;
                            // Update assistant bubble content
                            bubble.querySelector('.streaming-text').innerHTML = formatMarkdownText(fullResponseText) + '<span class="cursor">▌</span>';
                            scrollToBottom();
                        }
                    } catch (e) {
                        // skip errors on [DONE] signal
                    }
                }
            }
        }

        // Remove cursor when finished
        bubble.querySelector('.streaming-text').innerHTML = formatMarkdownText(fullResponseText);
        
        // Append sources block if any
        let sourcesHtml = '';
        if (sources && sources.length > 0) {
            const listItems = sources.map(s => {
                const docName = s.document_name || "Document technique";
                const scorePct = s.relevance_score ? ` (Pertinence: ${Math.round(s.relevance_score * 100)}%)` : '';
                return `<li style="margin-bottom: 4px; font-size: 13px; color: var(--text-muted);">📄 ${docName}${scorePct}</li>`;
            }).join('');
            
            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'msg-sources';
            sourcesDiv.style.marginTop = '12px';
            sourcesDiv.style.paddingTop = '8px';
            sourcesDiv.style.borderTop = '1px dashed var(--border-color)';
            sourcesDiv.innerHTML = `
                <details style="cursor: pointer;">
                    <summary style="font-size: 13px; font-weight: 600; color: var(--primary); outline: none;">Sources consultées (${sources.length})</summary>
                    <ul style="margin-top: 6px; padding-left: 16px; list-style-type: none;">
                        ${listItems}
                    </ul>
                </details>
            `;
            bubble.querySelector('.msg-content').appendChild(sourcesDiv);
        }

        // Append actions block
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'msg-actions';
        const escapedResponse = fullResponseText.replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/\n/g, '\\n');
        actionsDiv.innerHTML = `
            <button class="action-icon-btn" onclick="copyMessageText('${escapedResponse}', this)">📋 Copier</button>
            <button class="action-icon-btn" onclick="regenerateLastResponse()">🔄 Régénérer</button>
        `;
        bubble.querySelector('.msg-content').appendChild(actionsDiv);
        scrollToBottom();

        // Update quota display
        updateQuotaUI();

        // Reload conversations to update names if connected
        if (state.isLoggedIn) {
            loadConversations();
        }

    } catch (e) {
        console.error("Send message error:", e);
        bubble.querySelector('.streaming-text').innerHTML = "⚠️ Connexion réseau impossible. Vérifiez votre connexion internet.";
    }
}

// Append Message Bubble into main container
function appendMessageBubble(role, content, imageSrc = null, sources = null) {
    const bubble = document.createElement('div');
    bubble.className = `message-bubble ${role}`;

    const avatarInitial = role === 'user' ? 'U' : 'A';
    
    let imageHtml = '';
    if (imageSrc) {
        imageHtml = `<img src="${imageSrc}" class="msg-image" alt="Chantier picture">`;
    }

    let actionsHtml = '';
    let sourcesHtml = '';
    if (role === 'assistant') {
        const escapedContent = content.replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/\n/g, '\\n');
        actionsHtml = `
            <div class="msg-actions">
                <button class="action-icon-btn" onclick="copyMessageText('${escapedContent}', this)">📋 Copier</button>
                <button class="action-icon-btn" onclick="regenerateLastResponse()">🔄 Régénérer</button>
            </div>
        `;
        
        if (sources && sources.length > 0) {
            const listItems = sources.map(s => {
                const docName = s.document_name || "Document technique";
                const scorePct = s.relevance_score ? ` (Pertinence: ${Math.round(s.relevance_score * 100)}%)` : '';
                return `<li style="margin-bottom: 4px; font-size: 13px; color: var(--text-muted);">📄 ${docName}${scorePct}</li>`;
            }).join('');
            
            sourcesHtml = `
                <div class="msg-sources" style="margin-top: 12px; padding-top: 8px; border-top: 1px dashed var(--border-color); width: 100%;">
                    <details style="cursor: pointer;">
                        <summary style="font-size: 13px; font-weight: 600; color: var(--primary); outline: none;">Sources consultées (${sources.length})</summary>
                        <ul style="margin-top: 6px; padding-left: 16px; list-style-type: none;">
                            ${listItems}
                        </ul>
                    </details>
                </div>
            `;
        }
    }

    bubble.innerHTML = `
        <div class="msg-avatar">${avatarInitial}</div>
        <div class="msg-content">
            ${imageHtml}
            <div class="bubble-text">${formatMarkdownText(content)}</div>
            ${sourcesHtml}
            ${actionsHtml}
        </div>
    `;

    messagesStream.appendChild(bubble);
}

// Format markdown elements using marked.js and highlight.js
function formatMarkdownText(text) {
    if (!text) return "";
    try {
        if (typeof marked !== 'undefined') {
            const options = {
                breaks: true,
                gfm: true
            };
            
            const parseFn = typeof marked.parse === 'function' ? marked.parse : marked;
            const parsedHtml = parseFn(text, options);
            
            // Highlight code blocks asynchronously
            setTimeout(() => {
                if (typeof hljs !== 'undefined') {
                    document.querySelectorAll('pre code').forEach((block) => {
                        hljs.highlightElement(block);
                    });
                }
            }, 0);
            
            return parsedHtml;
        }
    } catch (e) {
        console.warn("Marked parsing failed:", e);
    }
    
    // Fallback basic formatter
    let formatted = text.replace(/\n/g, '<br>');
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/(\d+)\.\s(.*?)(<br>|$)/g, '$1. $2$3');
    return formatted;
}

// Append Loading Bubble with 3 pulsing dots
function appendLoadingBubble() {
    const id = 'loading_' + Date.now();
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble assistant';
    bubble.id = id;

    bubble.innerHTML = `
        <div class="msg-avatar">A</div>
        <div class="msg-content">
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;

    messagesStream.appendChild(bubble);
    return id;
}

// Remove Loading Bubble
function removeLoadingBubble(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// Scroll chat panel to bottom
function scrollToBottom() {
    const chatWorkspace = document.getElementById('chat-workspace');
    chatWorkspace.scrollTop = chatWorkspace.scrollHeight;
}

// Copy message response helper
async function copyMessageText(text, btn) {
    try {
        await navigator.clipboard.writeText(text);
        const oldText = btn.textContent;
        btn.textContent = "Copié !";
        setTimeout(() => {
            btn.textContent = oldText;
        }, 2000);
    } catch (err) {
        showToast("Échec de la copie.");
    }
}

// Regenerate response helper
function regenerateLastResponse() {
    const bubbles = Array.from(messagesStream.querySelectorAll('.message-bubble'));
    let lastUserQuestion = "";
    
    for (let i = bubbles.length - 1; i >= 0; i--) {
        if (bubbles[i].classList.contains('user')) {
            const textContentEl = bubbles[i].querySelector('.bubble-text');
            if (textContentEl) {
                lastUserQuestion = textContentEl.textContent.trim();
            }
            break;
        }
    }
    
    if (lastUserQuestion) {
        chatInput.value = lastUserQuestion;
        
        let foundUser = false;
        while (messagesStream.lastChild) {
            const child = messagesStream.lastChild;
            if (child.classList && child.classList.contains('user')) {
                if (foundUser) break;
                foundUser = true;
            }
            messagesStream.removeChild(child);
        }
        sendMessage();
    } else {
        showToast("Aucun message à régénérer.");
    }
}

// Login Modal Management
function openLoginModal() {
    loginModal.classList.remove('hidden');
    switchAuthView('login');
}

// Close Login Modal
function closeLoginModal() {
    loginModal.classList.add('hidden');
}

// Switch between Register and Login views
function switchAuthView(view) {
    const loginForm = document.getElementById('auth-form-login');
    const registerForm = document.getElementById('auth-form-register');
    if (view === 'register') {
        loginForm.classList.add('hidden');
        registerForm.classList.remove('hidden');
    } else {
        loginForm.classList.remove('hidden');
        registerForm.classList.add('hidden');
    }
}

// Submit local email/password login
async function submitLogin() {
    const email = document.getElementById('login-email-input').value.trim();
    const password = document.getElementById('login-password-input').value;

    if (!email || !password) {
        showToast("Veuillez remplir tous les champs.");
        return;
    }

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        if (response.ok) {
            const data = await response.json();
            loginUser(data);
        } else {
            const err = await response.json();
            showToast(err.detail || "Identifiants incorrects.");
        }
    } catch (e) {
        console.error("Login error:", e);
        showToast("Erreur de connexion.");
    }
}

// Submit local registration
async function submitRegister() {
    const nom = document.getElementById('register-nom-input').value.trim();
    const email = document.getElementById('register-email-input').value.trim();
    const telephone = document.getElementById('register-phone-input').value.trim();
    const password = document.getElementById('register-password-input').value;

    if (!email || !password) {
        showToast("Adresse e-mail et mot de passe requis.");
        return;
    }

    try {
        const payload = { email, password };
        if (nom) payload.nom = nom;
        if (telephone) payload.telephone = telephone;

        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            showToast("Compte créé avec succès ! Connectez-vous maintenant.");
            switchAuthView('login');
            document.getElementById('login-email-input').value = email;
            document.getElementById('login-password-input').focus();
        } else {
            const err = await response.json();
            showToast(err.detail || "Erreur lors de l'inscription.");
        }
    } catch (e) {
        console.error("Registration error:", e);
        showToast("Erreur de connexion.");
    }
}

// Handle Google ID Token response from gsi client
async function handleGoogleCredentialResponse(googleResponse) {
    try {
        const res = await fetch('/api/auth/google', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential: googleResponse.credential })
        });
        if (res.ok) {
            const data = await res.json();
            loginUser(data);
        } else {
            const err = await res.json();
            showToast(`Connexion Google échouée: ${err.detail || "Erreur"}`);
        }
    } catch (e) {
        console.error("Google login error:", e);
        showToast("Erreur de connexion.");
    }
}

// Simulate Google Sign-In locally for dev/test
async function simulateGoogleOAuth() {
    const mockEmail = `artisan.google@example.com`;
    const response = {
        credential: `mock_google_${mockEmail}`
    };
    await handleGoogleCredentialResponse(response);
}

// Execute session login
function loginUser(data) {
    state.isLoggedIn = true;
    state.user = data.user;
    localStorage.setItem('prosartisan_user', JSON.stringify(data.user));
    localStorage.setItem('prosartisan_token', data.access_token);
    localStorage.setItem('prosartisan_refresh_token', data.refresh_token);
    
    closeLoginModal();
    updateAuthUI();
    showToast(`Bienvenue chef ! Connecté en tant que ${data.user.nom || data.user.email}`);
    
    startNewChat();
    loadConversations();
    updateQuotaUI();
}

// Logout session
function logout() {
    localStorage.removeItem('prosartisan_user');
    localStorage.removeItem('prosartisan_token');
    localStorage.removeItem('prosartisan_refresh_token');
    state.isLoggedIn = false;
    state.user = null;
    state.currentConversationId = null;
    
    updateAuthUI();
    startNewChat();
    showToast("Déconnexion réussie.");
    updateQuotaUI();
}

// Toast notification helper
function showToast(message) {
    const toast = document.getElementById('toast-notif');
    const toastText = document.getElementById('toast-text');
    if (!toast || !toastText) return;
    
    toastText.textContent = message;
    toast.classList.remove('hidden');
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}
