// ==========================================================================
// ProsArtisan Chat Application JS Logic
// State Management, Login Simulation, API calls, and UI Rendering.
// ==========================================================================

// Global state variables
let state = {
    isLoggedIn: false,
    user: null, // { email, user_id }
    currentConversationId: null,
    conversations: [],
    selectedImage: null, // base64 string or file URL
};

// Default Anonyme User UUID used by backend for sandbox/anonymous calls
const ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000001";

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
const modalEmailInput = document.getElementById('modal-email-input');

// Initialize App on DOM Loaded
document.addEventListener('DOMContentLoaded', () => {
    // 1. Check local storage for existing session
    const storedUser = localStorage.getItem('prosartisan_user');
    if (storedUser) {
        try {
            state.user = JSON.parse(storedUser);
            state.isLoggedIn = true;
            updateAuthUI();
            loadConversations();
        } catch (e) {
            console.error("Failed to parse stored session:", e);
            logout();
        }
    } else {
        updateAuthUI();
    }

    // Auto-expand textarea input
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight - 4) + 'px';
    });
});

// Update UI based on connection state
function updateAuthUI() {
    if (state.isLoggedIn) {
        // Logged-in view
        ctaSidebarLogin.classList.add('hidden');
        userProfileFooter.classList.remove('hidden');
        userEmailLbl.textContent = state.user.email;
        
        // Header profile
        authButtonsHeader.classList.add('hidden');
        userAvatarHeader.classList.remove('hidden');
        document.querySelector('.header-avatar').textContent = state.user.email.charAt(0).toUpperCase();
        document.getElementById('user-avatar-lbl').textContent = state.user.email.charAt(0).toUpperCase();
        historyEmpty.classList.add('hidden');
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
    }
}

// Fetch Conversations list for connected user
async function loadConversations() {
    if (!state.isLoggedIn) return;

    try {
        const response = await fetch(`/api/conversations?user_id=${state.user.user_id}`);
        if (response.ok) {
            state.conversations = await response.json();
            renderConversationsList();
        } else {
            showToast("Impossible de charger l'historique.");
        }
    } catch (e) {
        console.error("Failed to fetch conversations:", e);
        showToast("Erreur de connexion avec le serveur.");
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
            <button class="conv-item ${activeClass}" onclick="selectConversation('${conv.id}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                ${conv.title || "Discussions"}
            </button>
            <button class="delete-conv-btn" onclick="deleteConversation('${conv.id}', event)" title="Supprimer la discussion">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
        `;
        conversationsList.appendChild(li);
    });
}

// Select and load a conversation
async function selectConversation(id) {
    state.currentConversationId = id;
    renderConversationsList(); // Update active highlights

    try {
        const response = await fetch(`/api/conversations/${id}`);
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
        const response = await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
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

// Speech recognition simulation
function startSpeechRecognition() {
    showToast("🎤 Entrée vocale en cours d'écoute...");
    setTimeout(() => {
        fillInput("Quelles sont les étapes pour couler une dalle en béton armé ?");
    }, 2000);
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

    // 2. Add loading assistant bubble
    const loadingId = appendLoadingBubble();
    scrollToBottom();

    // 3. Prepare payload
    const userId = state.isLoggedIn ? state.user.user_id : ANONYMOUS_USER_ID;
    const payload = {
        user_id: userId,
        question: text,
        metier_id: 1, // Default Batiment
        image_url: image
    };

    // If connected, pass active conversation ID
    if (state.isLoggedIn && state.currentConversationId) {
        payload.conversation_id = state.currentConversationId;
    }

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        removeLoadingBubble(loadingId);

        if (response.ok) {
            const data = await response.json();
            
            // Add Assistant bubble
            appendMessageBubble('assistant', data.reponse);
            scrollToBottom();

            // If connected and conversation was newly created, save ID
            if (state.isLoggedIn) {
                if (data.conversation_id && state.currentConversationId !== data.conversation_id) {
                    state.currentConversationId = data.conversation_id;
                }
                loadConversations(); // Reload history list
            }
        } else {
            appendMessageBubble('assistant', "⚠️ Désolé chef, une erreur s'est produite lors de la connexion à l'assistant. Veuillez réessayer.");
        }
    } catch (e) {
        console.error("Send message error:", e);
        removeLoadingBubble(loadingId);
        appendMessageBubble('assistant', "⚠️ Connexion réseau impossible. Vérifiez votre connexion internet.");
    }
}

// Append Message Bubble into main container
function appendMessageBubble(role, content, imageSrc = null) {
    const bubble = document.createElement('div');
    bubble.className = `message-bubble ${role}`;

    const avatarInitial = role === 'user' ? 'U' : 'A';
    
    let imageHtml = '';
    if (imageSrc) {
        imageHtml = `<img src="${imageSrc}" class="msg-image" alt="Chantier picture">`;
    }

    bubble.innerHTML = `
        <div class="msg-avatar">${avatarInitial}</div>
        <div class="msg-content">
            ${imageHtml}
            <p>${formatMarkdownText(content)}</p>
        </div>
    `;

    messagesStream.appendChild(bubble);
}

// Format basic markdown elements
function formatMarkdownText(text) {
    if (!text) return "";
    
    // Replace newlines with <br>
    let formatted = text.replace(/\n/g, '<br>');
    
    // Simple bold markdown
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Ordered bullet items
    formatted = formatted.replace(/(\d+)\.\s(.*?)(<br>|$)/g, '$1. $2$3');

    return formatted;
}

// Append Loading Bubble
function appendLoadingBubble() {
    const id = 'loading_' + Date.now();
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble assistant';
    bubble.id = id;

    bubble.innerHTML = `
        <div class="msg-avatar">A</div>
        <div class="msg-content">
            <p> réfléchit... 👷‍♂️</p>
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

// Login Modal Management
function openLoginModal() {
    loginModal.classList.remove('hidden');
    modalEmailInput.focus();
}

function closeLoginModal() {
    loginModal.classList.add('hidden');
}

// Simulate Google / Apple Auth
function simulateOAuth(provider) {
    const mockEmail = `artisan.${provider.toLowerCase()}@example.com`;
    performMockLogin(mockEmail);
}

// Submit Email connection
function submitEmailLogin() {
    const email = modalEmailInput.value.trim();
    if (!email) {
        showToast("Veuillez saisir une adresse e-mail valide.");
        return;
    }
    performMockLogin(email);
}

// Execute Connection
function performMockLogin(email) {
    // Generate static UUID based on email for testing consistency
    const userId = "00000000-0000-0000-0000-000000000002"; 
    
    state.user = { email, user_id: userId };
    state.isLoggedIn = true;
    
    localStorage.setItem('prosartisan_user', JSON.stringify(state.user));
    
    closeLoginModal();
    updateAuthUI();
    showToast(`Bienvenue chef ! Connecté en tant que ${email}`);
    
    // Load conversations list
    startNewChat();
    loadConversations();
}

// Logout session
function logout() {
    localStorage.removeItem('prosartisan_user');
    state.isLoggedIn = false;
    state.user = null;
    state.currentConversationId = null;
    
    updateAuthUI();
    startNewChat();
    showToast("Déconnexion réussie.");
}

// Toast notification helper
function showToast(message) {
    const toast = document.getElementById('toast-notif');
    const toastText = document.getElementById('toast-text');
    
    toastText.textContent = message;
    toast.classList.remove('hidden');
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}
