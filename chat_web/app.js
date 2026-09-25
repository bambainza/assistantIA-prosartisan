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

// Historique local des visiteurs non connectés : le serveur ne conserve
// aucune discussion anonyme (plus de compte partagé lisible par tous). Stocké
// dans ce navigateur uniquement, borné, sans les photos (quota localStorage).
const LOCAL_HISTORY_KEY = 'prosartisan_local_history';
const LOCAL_HISTORY_MAX_CONVERSATIONS = 20;
const LOCAL_HISTORY_MAX_MESSAGES = 60;

const localHistory = {
    _read() {
        try {
            const value = JSON.parse(localStorage.getItem(LOCAL_HISTORY_KEY) || '[]');
            return Array.isArray(value) ? value : [];
        } catch (e) {
            return [];
        }
    },
    _write(conversations) {
        try {
            localStorage.setItem(LOCAL_HISTORY_KEY, JSON.stringify(conversations));
        } catch (e) {
            // Stockage plein : on sacrifie la discussion la plus ancienne.
            if (conversations.length > 1) this._write(conversations.slice(0, -1));
        }
    },
    list(query = null) {
        const q = (query || '').toLowerCase();
        return this._read()
            .filter(c => !q || (c.title || '').toLowerCase().includes(q))
            .map(c => ({ id: c.id, title: c.title }));
    },
    get(id) {
        return this._read().find(c => c.id === id) || null;
    },
    addExchange(id, question, answer) {
        const conversations = this._read();
        let conv = conversations.find(c => c.id === id);
        if (!conv) {
            conv = {
                id: `local-${Date.now()}`,
                title: question.length > 30 ? question.slice(0, 30) + '...' : question,
                messages: []
            };
        }
        conv.messages.push({ role: 'user', content: question }, { role: 'assistant', content: answer });
        conv.messages = conv.messages.slice(-LOCAL_HISTORY_MAX_MESSAGES);
        const others = conversations.filter(c => c.id !== conv.id);
        this._write([conv, ...others].slice(0, LOCAL_HISTORY_MAX_CONVERSATIONS));
        return conv.id;
    },
    rename(id, title) {
        this._write(this._read().map(c => (c.id === id ? { ...c, title } : c)));
    },
    remove(id) {
        this._write(this._read().filter(c => c.id !== id));
    }
};

function isLocalConversation(id) {
    return typeof id === 'string' && id.startsWith('local-');
}

// Dom Elements
const sidebar= document.getElementById('sidebar');
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
const srLiveRegion = document.getElementById('sr-live-region');

// Annonce un message aux lecteurs d'écran via la zone aria-live dédiée,
// sans toucher à l'affichage visuel (déjà géré par les bulles de messages).
function announceToScreenReader(text) {
    if (!srLiveRegion) return;
    srLiveRegion.textContent = text;
}

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

    loadActualitesBanner();
    handlePaymentReturn();

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
    setTimeout(async () => {
        if (window.google && window.google.accounts) {
            try {
                const configResponse = await fetch('/api/auth/google/config');
                const googleConfig = await configResponse.json();
                if (!googleConfig.enabled || !googleConfig.client_id) return;
                google.accounts.id.initialize({
                    client_id: googleConfig.client_id,
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
                // Quota gratuit du jour (jauge sur 5) + crédits achetés (Pack 50) affichés à part.
                const total = 5;
                const rest = data.gratuites_restantes_jour ?? Math.min(data.restantes, total);
                const credits = data.credits || 0;
                quotaText.textContent = credits > 0
                    ? `${rest} / ${total} + ${credits} crédits`
                    : `${rest} / ${total}`;
                
                const percent = Math.min(100, (rest / total) * 100);
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
    // Lien vers la console : réservé aux administrateurs (l'accès reste contrôlé côté serveur).
    const adminLink = document.getElementById('admin-console-link');
    if (adminLink) adminLink.classList.toggle('hidden', !(state.isLoggedIn && state.user && state.user.is_admin));

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
        // Historique local (ce navigateur uniquement)
        state.conversations = localHistory.list();
        renderConversationsList();

        const searchBar = document.getElementById('sidebar-search-container');
        if (searchBar) searchBar.classList.toggle('hidden', state.conversations.length === 0);
    }
}

// Fetch Conversations list for connected user
async function loadConversations(q = null) {
    if (!state.isLoggedIn) {
        state.conversations = localHistory.list(q);
        renderConversationsList();
        return;
    }

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
        // Titre issu de la question de l'utilisateur : toujours encodé.
        const convId = escapeHtml(conv.id);
        const convTitle = escapeHtml(conv.title || "Discussions");
        
        li.innerHTML = `
            <button class="conv-item ${activeClass}" onclick="selectConversation('${convId}')" id="conv-btn-${convId}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px; flex-shrink: 0;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                <span class="conv-title-text" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%; display: block;">${convTitle}</span>
            </button>
            <button class="edit-conv-btn" onclick="startRenameConversation('${convId}', event)" title="Renommer">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            </button>
            <button class="delete-conv-btn" onclick="deleteConversation('${convId}', event)" title="Supprimer la discussion">
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
        if (isLocalConversation(id)) {
            localHistory.rename(id, newTitle);
            titleSpan.textContent = newTitle;
            input.replaceWith(titleSpan);
            loadConversations();
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

    if (isLocalConversation(id)) {
        const conv = localHistory.get(id);
        if (!conv) {
            showToast("Discussion introuvable sur cet appareil.");
            return;
        }
        landingContainer.classList.add('hidden');
        messagesStream.classList.remove('hidden');
        messagesStream.innerHTML = '';
        conv.messages.forEach(msg => appendMessageBubble(msg.role, msg.content));
        scrollToBottom();
        return;
    }

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

    if (isLocalConversation(id)) {
        localHistory.remove(id);
        if (state.currentConversationId === id) startNewChat();
        loadConversations();
        showToast("Discussion supprimée.");
        return;
    }

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
// Photos réencodées en JPEG côté navigateur avant l'envoi : le serveur n'accepte
// que PNG/JPEG/WebP/GIF (une photo HEIC d'iPhone est convertie par les navigateurs
// qui savent la lire), et une photo réduite part bien plus vite en 3G.
const IMAGE_MAX_DIMENSION = 1600;
const IMAGE_JPEG_QUALITY = 0.85;

function encodeImageAsJpeg(file) {
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
            const scale = Math.min(1, IMAGE_MAX_DIMENSION / Math.max(img.naturalWidth, img.naturalHeight));
            const canvas = document.createElement('canvas');
            canvas.width = Math.round(img.naturalWidth * scale);
            canvas.height = Math.round(img.naturalHeight * scale);
            canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
            URL.revokeObjectURL(url);
            resolve(canvas.toDataURL('image/jpeg', IMAGE_JPEG_QUALITY));
        };
        img.onerror = () => {
            URL.revokeObjectURL(url);
            reject(new Error('image illisible'));
        };
        img.src = url;
    });
}

async function handleImageSelection() {
    const input = document.getElementById('image-upload');
    const file = input.files[0];
    if (!file) return;

    try {
        state.selectedImage = await encodeImageAsJpeg(file);
    } catch (e) {
        input.value = '';
        showToast("Format de photo non lu par ce navigateur (HEIC ?). Envoyez une photo JPEG ou PNG.");
        return;
    }
    previewImgName.textContent = file.name;
    imagePreviewBox.classList.remove('hidden');
    sendBtn.classList.remove('disabled');
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

// --- Speech-to-Text & Audio Recording via Mistral Voxtral ---
let mediaRecorder = null;
let audioChunks = [];
let isVoiceRecording = false;

async function toggleVoiceRecording() {
    if (isVoiceRecording) {
        stopVoiceRecording();
        return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        // Fallback Web Speech API
        startSpeechRecognitionFallback();
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioChunks = [];
        const options = (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported('audio/webm'))
            ? { mimeType: 'audio/webm' }
            : {};
        mediaRecorder = new MediaRecorder(stream, options);

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());
            if (audioChunks.length === 0) return;

            const mimeType = mediaRecorder.mimeType || 'audio/webm';
            const extension = mimeType.includes('webm') ? 'webm' : (mimeType.includes('ogg') ? 'ogg' : 'wav');
            const audioBlob = new Blob(audioChunks, { type: mimeType });
            
            showToast("⏳ Transcription en cours...");
            try {
                const formData = new FormData();
                formData.append('file', audioBlob, `vocal_${Date.now()}.${extension}`);

                const headers = {};
                if (state.token) {
                    headers['Authorization'] = `Bearer ${state.token}`;
                }

                const response = await fetch('/api/chat/transcribe', {
                    method: 'POST',
                    headers: headers,
                    body: formData,
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                if (data && data.text) {
                    fillInput(data.text);
                    showToast("✅ Note vocale transcrite avec succès !");
                }
            } catch (err) {
                console.error("Erreur transcription :", err);
                showToast("⚠️ Échec de la transcription.");
            }
        };

        mediaRecorder.start();
        isVoiceRecording = true;
        setMicButtonRecordingState(true);
        showToast("🎙️ Enregistrement en cours... Cliquez à nouveau pour transcrire.");
    } catch (err) {
        console.warn("Accès micro refusé ou indisponible, tentative Web Speech API:", err);
        startSpeechRecognitionFallback();
    }
}

function stopVoiceRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isVoiceRecording = false;
    setMicButtonRecordingState(false);
}

// Reflète l'état d'enregistrement du micro à la fois visuellement (classe CSS)
// et pour les technologies d'assistance (aria-pressed + libellé dynamique) —
// jusqu'ici seul un changement de couleur signalait l'état à l'utilisateur.
function setMicButtonRecordingState(recording) {
    const micBtn = document.getElementById('mic-btn');
    if (!micBtn) return;
    micBtn.classList.toggle('recording', recording);
    micBtn.setAttribute('aria-pressed', recording ? 'true' : 'false');
    const label = recording ? "Arrêter l'enregistrement" : "Entrée vocale";
    micBtn.setAttribute('aria-label', label);
    micBtn.title = recording ? "Arrêter l'enregistrement" : "Entrée Vocale";
}

function startSpeechRecognitionFallback() {
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
    announceToScreenReader("L'assistant rédige une réponse…");

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
        // Pas de filtre métier : chat_web n'a pas de sélecteur, et un identifiant
        // codé en dur (ex. 1, absent de la base) écartait tous les documents.
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
            const messagesParStatut = {
                402: "Vos questions gratuites du jour sont épuisées. Passez au Pass 24H ou au Pass Mensuel pour continuer.",
                413: "Photo ou note vocale trop volumineuse.",
                422: "Question trop longue ou photo trop volumineuse.",
                429: "Trop de requêtes. Patientez une minute avant de réessayer.",
                503: "Service momentanément indisponible. Réessayez dans un instant.",
            };
            const errorText = messagesParStatut[response.status]
                || "Désolé chef, une erreur s'est produite lors de la connexion à l'assistant. Veuillez réessayer.";
            bubble.querySelector('.streaming-text').textContent = `⚠️ ${errorText}`;
            announceToScreenReader(errorText);
            if (response.status === 402) {
                updateQuotaUI();
                openPaywallModal();
            }
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let fullResponseText = "";
        let buffer = "";
        let sources = [];
        // Type SSE courant : un `event: error` porte un message d'erreur, jamais
        // une réponse (ni affichée comme telle, ni enregistrée dans l'historique).
        let currentEvent = "message";
        let streamError = null;

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

                if (cleanLine.startsWith("event:")) {
                    currentEvent = cleanLine.substring(6).trim();
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
                        } else if (typeof parsed === 'string' && currentEvent === 'error') {
                            streamError = parsed;
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

        if (streamError && !fullResponseText.trim()) {
            // Échec côté serveur (ex. modèle indisponible) : message d'erreur seul,
            // sans actions (copier, écouter...) ni enregistrement de l'échange.
            bubble.querySelector('.streaming-text').textContent = streamError;
            announceToScreenReader(streamError);
            updateQuotaUI();
            return;
        }

        // Remove cursor when finished
        bubble.querySelector('.streaming-text').innerHTML = formatMarkdownText(fullResponseText);
        announceToScreenReader(fullResponseText ? `Réponse de l'assistant : ${fullResponseText}` : "L'assistant n'a pas pu générer de réponse.");

        // Append sources block if any
        let sourcesHtml = '';
        if (sources && sources.length > 0) {
            const listItems = sources.map(s => {
                const docName = escapeHtml(s.document_name || "Document technique");
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
            <button class="action-icon-btn speak-btn" onclick="toggleSpeakMessage('${escapedResponse}', this)">🔊 Écouter</button>
            <button class="action-icon-btn" onclick="regenerateLastResponse()">🔄 Régénérer</button>
            <button class="action-icon-btn feedback-btn" onclick="sendAssistantFeedback(1, '${assistantBubbleId}', this)" title="Réponse utile">👍 Utile</button>
            <button class="action-icon-btn feedback-btn" onclick="sendAssistantFeedback(-1, '${assistantBubbleId}', this)" title="Réponse imprécise">👎 Inexact</button>
        `;
        bubble.querySelector('.msg-content').appendChild(actionsDiv);
        scrollToBottom();

        // Update quota display
        updateQuotaUI();

        // Connecté : historique serveur. Anonyme : historique local uniquement.
        if (!state.isLoggedIn && fullResponseText.trim()) {
            state.currentConversationId = localHistory.addExchange(
                state.currentConversationId, text, fullResponseText
            );
        }
        loadConversations();

    } catch (e) {
        console.error("Send message error:", e);
        const networkErrorText = "Connexion réseau impossible. Vérifiez votre connexion internet.";
        bubble.querySelector('.streaming-text').innerHTML = `⚠️ ${networkErrorText}`;
        announceToScreenReader(networkErrorText);
    }
}

// Append Message Bubble into main container
// Encode une valeur avant insertion dans du HTML (texte ou attribut entre guillemets).
function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function appendMessageBubble(role, content, imageSrc = null, sources = null) {
    const bubble = document.createElement('div');
    bubble.className = `message-bubble ${role}`;

    const avatarInitial = role === 'user' ? 'U' : 'A';
    
    let imageHtml = '';
    if (imageSrc) {
        imageHtml = `<img src="${escapeHtml(imageSrc)}" class="msg-image" alt="Photo de chantier envoyée par l'utilisateur">`;
    }

    let actionsHtml = '';
    let sourcesHtml = '';
    if (role === 'assistant') {
        const escapedContent = content.replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/\n/g, '\\n');
        const bubbleMsgId = 'history_' + Math.random().toString(36).substring(2, 9);
        actionsHtml = `
            <div class="msg-actions">
                <button class="action-icon-btn" onclick="copyMessageText('${escapedContent}', this)">📋 Copier</button>
                <button class="action-icon-btn speak-btn" onclick="toggleSpeakMessage('${escapedContent}', this)">🔊 Écouter</button>
                <button class="action-icon-btn" onclick="regenerateLastResponse()">🔄 Régénérer</button>
                <button class="action-icon-btn" onclick="exportMessageAsPdf('${escapedContent}')" title="Exporter en PDF (impression navigateur)">🖨️ Exporter</button>
                <button class="action-icon-btn" onclick="shareMessage('${escapedContent}')" title="Partager">📤 Partager</button>
                <button class="action-icon-btn feedback-btn" onclick="sendAssistantFeedback(1, '${bubbleMsgId}', this)" title="Réponse utile">👍 Utile</button>
                <button class="action-icon-btn feedback-btn" onclick="sendAssistantFeedback(-1, '${bubbleMsgId}', this)" title="Réponse imprécise">👎 Inexact</button>
            </div>
        `;
        
        if (sources && sources.length > 0) {
            const listItems = sources.map(s => {
                const docName = escapeHtml(s.document_name || "Document technique");
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

// Envoyer un feedback sur une réponse (pouce haut / pouce bas)
async function sendAssistantFeedback(rating, messageId, btn) {
    try {
        const payload = {
            rating: rating,
            message_id: messageId,
            conversation_id: state.currentConversationId || null,
        };
        const headers = { 'Content-Type': 'application/json' };
        if (state.isLoggedIn) {
            const token = localStorage.getItem('prosartisan_token');
            if (token) headers['Authorization'] = `Bearer ${token}`;
        }
        const res = await fetch('/api/chat/feedback', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const parent = btn.parentElement;
            if (parent) {
                parent.querySelectorAll('.feedback-btn').forEach(b => {
                    b.disabled = true;
                    b.style.opacity = '0.5';
                    b.style.cursor = 'default';
                });
            }
            btn.style.opacity = '1';
            btn.style.fontWeight = 'bold';
            btn.style.color = rating === 1 ? '#4CAF50' : '#F44336';
            showToast(rating === 1 ? 'Merci pour votre retour positif ! 👍' : 'Merci, nous allons améliorer cette réponse ! 🛠️');
        } else {
            showToast('⚠️ Impossible d\'enregistrer le feedback.');
        }
    } catch (e) {
        console.error('Feedback error:', e);
        showToast('⚠️ Erreur réseau lors de l\'envoi du feedback.');
    }
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
            <div class="typing-indicator" role="status" aria-label="L'assistant rédige une réponse">
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

// Export d'une réponse en PDF via l'impression navigateur (pas de dépendance
// externe : l'artisan choisit "Enregistrer en PDF" dans la boîte de dialogue
// d'impression, disponible nativement sur desktop comme sur mobile).
function exportMessageAsPdf(text) {
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
        showToast("Autorisez les pop-ups pour exporter en PDF.");
        return;
    }
    const safeHtml = formatMarkdownText(text);
    printWindow.document.write(`
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <title>Fiche technique ProsArtisan IA</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.5; padding: 24px; color: #1a1a1a; }
                h1 { font-size: 18px; border-bottom: 2px solid #FF9800; padding-bottom: 8px; }
                pre { background: #f5f5f5; padding: 10px; border-radius: 6px; overflow-x: auto; }
                code { font-family: monospace; }
            </style>
        </head>
        <body>
            <h1>ProsArtisan IA — Fiche technique</h1>
            <div>${safeHtml}</div>
        </body>
        </html>
    `);
    printWindow.document.close();
    printWindow.onload = () => printWindow.print();
}

// Partage d'une réponse : Web Share API native si disponible (mobile),
// repli sur un lien WhatsApp pré-rempli sinon.
async function shareMessage(text) {
    const shareText = `ProsArtisan IA — ${text}`.slice(0, 1000);
    if (navigator.share) {
        try {
            await navigator.share({ title: 'ProsArtisan IA', text: shareText });
            return;
        } catch (_) {
            // Partage annulé par l'utilisateur ou API indisponible : repli WhatsApp.
        }
    }
    const waUrl = `https://wa.me/?text=${encodeURIComponent(shareText)}`;
    window.open(waUrl, '_blank', 'noopener,noreferrer');
}

// Global Audio Player for TTS
let currentAudioPlayer = null;
let currentSpeakingBtn = null;

async function toggleSpeakMessage(text, btnElement) {
    if (!text) return;

    // Si on clique sur le bouton en cours de lecture, on arrête
    if (currentSpeakingBtn === btnElement && (currentAudioPlayer || (window.speechSynthesis && window.speechSynthesis.speaking))) {
        stopSpeech();
        return;
    }

    // Arrêter toute lecture précédente
    stopSpeech();

    currentSpeakingBtn = btnElement;
    if (btnElement) {
        btnElement.innerHTML = '⏳ Chargement...';
        btnElement.classList.add('speaking');
    }

    try {
        const headers = { 'Content-Type': 'application/json' };
        if (state.token) {
            headers['Authorization'] = `Bearer ${state.token}`;
        }

        const response = await fetch('/api/chat/synthesize', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ text: text })
        });

        if (response.ok) {
            const blob = await response.blob();
            const audioUrl = URL.createObjectURL(blob);
            currentAudioPlayer = new Audio(audioUrl);
            
            currentAudioPlayer.onplay = () => {
                if (btnElement) btnElement.innerHTML = '⏹️ Arrêter';
            };

            currentAudioPlayer.onended = () => {
                stopSpeech();
            };

            currentAudioPlayer.onerror = () => {
                fallbackBrowserTts(text, btnElement);
            };

            await currentAudioPlayer.play();
            return;
        } else {
            fallbackBrowserTts(text, btnElement);
        }
    } catch (err) {
        console.warn("Échec de synthèse serveur, repli Web Speech API:", err);
        fallbackBrowserTts(text, btnElement);
    }
}

function fallbackBrowserTts(text, btnElement) {
    if (!window.speechSynthesis) {
        showToast("🔊 Synthèse vocale non supportée par votre navigateur.");
        stopSpeech();
        return;
    }

    // Nettoyer les balises Markdown basiques
    const cleanText = text.replace(/[*#`_]/g, '').replace(/\[(.*?)\]\(.*?\)/g, '$1');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'fr-FR';
    utterance.rate = 0.95;

    utterance.onstart = () => {
        if (btnElement) btnElement.innerHTML = '⏹️ Arrêter';
    };

    utterance.onend = () => {
        stopSpeech();
    };

    utterance.onerror = () => {
        stopSpeech();
    };

    window.speechSynthesis.speak(utterance);
}

function stopSpeech() {
    if (currentAudioPlayer) {
        currentAudioPlayer.pause();
        currentAudioPlayer.currentTime = 0;
        currentAudioPlayer = null;
    }
    if (window.speechSynthesis && window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
    }
    if (currentSpeakingBtn) {
        currentSpeakingBtn.innerHTML = '🔊 Écouter';
        currentSpeakingBtn.classList.remove('speaking');
        currentSpeakingBtn = null;
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
let loginModalTrigger = null;

function getModalFocusableElements() {
    const card = loginModal.querySelector('.modal-card');
    if (!card) return [];
    return Array.from(card.querySelectorAll('button, [href], input, select, textarea'))
        .filter(el => !el.disabled && el.offsetParent !== null);
}

function handleLoginModalKeydown(e) {
    if (e.key === 'Escape') {
        e.preventDefault();
        closeLoginModal();
        return;
    }
    // Entrée dans un champ valide le formulaire affiché (connexion ou inscription).
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
        e.preventDefault();
        if (e.target.id.startsWith('login-')) submitLogin();
        else if (e.target.id.startsWith('register-')) submitRegister();
        return;
    }
    if (e.key !== 'Tab') return;

    // Piège à focus : empêche Tab/Shift+Tab de sortir de la modale tant
    // qu'elle est ouverte (WAI-ARIA Dialog pattern).
    const focusable = getModalFocusableElements();
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
    }
}

function openLoginModal() {
    loginModalTrigger = document.activeElement;
    loginModal.classList.remove('hidden');
    switchAuthView('login');
    document.addEventListener('keydown', handleLoginModalKeydown);
    // Laisse le navigateur terminer le rendu (retrait de .hidden) avant de
    // déplacer le focus, sinon l'élément n'est pas encore focusable.
    setTimeout(() => {
        const focusable = getModalFocusableElements();
        (focusable[0] || loginModal).focus();
    }, 0);
}

// Close Login Modal
function closeLoginModal() {
    loginModal.classList.add('hidden');
    document.removeEventListener('keydown', handleLoginModalKeydown);
    if (loginModalTrigger && typeof loginModalTrigger.focus === 'function') {
        loginModalTrigger.focus();
    }
    loginModalTrigger = null;
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

// ==========================================================================
// Bandeau Actualités (annonces/conseils publiés par l'équipe)
// ==========================================================================

async function loadActualitesBanner() {
    try {
        const headers = {};
        if (state.isLoggedIn) {
            const token = localStorage.getItem('prosartisan_token');
            if (token) headers['Authorization'] = `Bearer ${token}`;
        }
        const res = await fetch('/api/actualites', { headers });
        if (!res.ok) return;
        const actualites = await res.json();
        if (!actualites || actualites.length === 0) return;

        const latest = actualites[0];
        if (sessionStorage.getItem(`prosartisan_actu_dismissed_${latest.id}`)) return;

        const banner = document.getElementById('actualites-banner');
        const bannerText = document.getElementById('actualites-banner-text');
        if (!banner || !bannerText) return;

        bannerText.textContent = `📣 ${latest.titre}`;
        banner.dataset.actualiteId = latest.id;
        banner.classList.remove('hidden');
    } catch (e) {
        // Silencieux : le bandeau est un plus, jamais bloquant pour le chat.
    }
}

// ==========================================================================
// Web Push (abonnement navigateur, protocole VAPID)
// ==========================================================================

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

async function toggleWebPushSubscription() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        showToast("Les notifications push ne sont pas supportées par ce navigateur.");
        return;
    }
    if (!state.isLoggedIn) {
        showToast("Connectez-vous pour activer les notifications.");
        openLoginModal();
        return;
    }

    try {
        const registration = await navigator.serviceWorker.ready;
        const existing = await registration.pushManager.getSubscription();

        if (existing) {
            await unsubscribeWebPush(existing);
            return;
        }

        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            showToast("Autorisation refusée pour les notifications.");
            return;
        }

        const keyRes = await fetch('/api/notifications/vapid-public-key');
        const { public_key } = await keyRes.json();

        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(public_key),
        });

        const token = localStorage.getItem('prosartisan_token');
        await fetch('/api/notifications/web-push/subscribe', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify(subscription.toJSON()),
        });

        updatePushNotifButtonState(true);
        showToast("Notifications activées !");
    } catch (e) {
        console.error('Web Push subscribe error:', e);
        showToast("Impossible d'activer les notifications.");
    }
}

async function unsubscribeWebPush(subscription) {
    try {
        const endpoint = subscription.endpoint;
        await subscription.unsubscribe();
        const token = localStorage.getItem('prosartisan_token');
        await fetch('/api/notifications/web-push/unsubscribe', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ endpoint }),
        });
        updatePushNotifButtonState(false);
        showToast("Notifications désactivées.");
    } catch (e) {
        console.error('Web Push unsubscribe error:', e);
    }
}

function updatePushNotifButtonState(active) {
    const btn = document.getElementById('push-notif-btn');
    if (!btn) return;
    btn.title = active ? "Désactiver les notifications" : "Activer les notifications";
    btn.setAttribute('aria-label', btn.title);
    btn.classList.toggle('active-push', active);
}

async function initWebPushButtonState() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
    try {
        const registration = await navigator.serviceWorker.ready;
        const existing = await registration.pushManager.getSubscription();
        updatePushNotifButtonState(!!existing);
    } catch (_) {
        /* Pas grave : le bouton reste dans son état par défaut. */
    }
}

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        setTimeout(initWebPushButtonState, 1500);
    });
}

function dismissActualitesBanner() {
    const banner = document.getElementById('actualites-banner');
    if (!banner) return;
    if (banner.dataset.actualiteId) {
        sessionStorage.setItem(`prosartisan_actu_dismissed_${banner.dataset.actualiteId}`, '1');
    }
    banner.classList.add('hidden');
}

// ==========================================================================
// 🧮 CALCULATEURS MÉTIER DÉTERMINISTES
// ==========================================================================

let lastCalcResult = "";

function openCalculatorsModal() {
    const modal = document.getElementById('calculators-modal');
    if (modal) modal.classList.remove('hidden');
}

function closeCalculatorsModal() {
    const modal = document.getElementById('calculators-modal');
    if (modal) modal.classList.add('hidden');
}

function switchCalcTab(tab) {
    const tabs = ['beton', 'cable', 'plomberie', 'carrelage', 'clim'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-btn-${t}`);
        const content = document.getElementById(`tab-content-${t}`);
        if (btn) btn.classList.toggle('active', t === tab);
        if (content) content.classList.toggle('hidden', t !== tab);
    });
}

async function executeCalculator(toolName, parameters) {
    try {
        const res = await fetch('/api/chat/calculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool_name: toolName, parameters })
        });
        const data = await res.json();
        const resultBox = document.getElementById('calc-result-box');
        const resultText = document.getElementById('calc-result-text');
        if (resultBox && resultText) {
            resultBox.classList.remove('hidden');
            lastCalcResult = data.result_text || JSON.stringify(data.data, null, 2);
            resultText.textContent = lastCalcResult;
            resultBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    } catch (e) {
        console.error("Calcul error:", e);
        showToast("Erreur lors de l'exécution du calcul.");
    }
}

function submitCalcBeton() {
    const type_dosage = document.getElementById('calc-beton-type').value;
    const volume_m3 = parseFloat(document.getElementById('calc-beton-vol').value) || 1.0;
    executeCalculator('calculer_dosage_beton_mortier', { type_dosage, volume_m3 });
}

function submitCalcCable() {
    const puissance_watts = parseFloat(document.getElementById('calc-cable-power').value) || 3500;
    const tension_volts = parseInt(document.getElementById('calc-cable-voltage').value, 10) || 230;
    const longueur_metres = parseFloat(document.getElementById('calc-cable-length').value) || 25;
    executeCalculator('calculer_section_cable_nfc15100', { puissance_watts, tension_volts, longueur_metres });
}

function submitCalcPlomb() {
    const type_appareil = document.getElementById('calc-plomb-app').value;
    const longueur_metres = parseFloat(document.getElementById('calc-plomb-length').value) || 4.0;
    executeCalculator('calculer_pente_evacuation_dtu60', { type_appareil, longueur_metres });
}

function submitCalcCarrelage() {
    const surface_m2 = parseFloat(document.getElementById('calc-carr-surf').value) || 25;
    const format_carreau = document.getElementById('calc-carr-dim').value;
    const pourcentage_chute = parseFloat(document.getElementById('calc-carr-waste').value) || 10;
    executeCalculator('calculer_surface_carrelage_colle', { surface_m2, format_carreau, pourcentage_chute });
}

function submitCalcClim() {
    const surface_m2 = parseFloat(document.getElementById('calc-clim-surf').value) || 20;
    const hauteur_sous_plafond = parseFloat(document.getElementById('calc-clim-height').value) || 2.8;
    const exposition_soleil = document.getElementById('calc-clim-sun').value;
    const nombre_personnes = parseInt(document.getElementById('calc-clim-pers').value, 10) || 2;
    executeCalculator('calculer_bilan_thermique_climatisation', {
        surface_m2, hauteur_sous_plafond, exposition_soleil, nombre_personnes
    });
}

function copyCalcResult() {
    if (!lastCalcResult) return;
    navigator.clipboard.writeText(lastCalcResult);
    showToast("Résultat copié dans le presse-papier !");
}

function injectCalcResultToChat() {
    if (!lastCalcResult) return;
    closeCalculatorsModal();
    if (chatInput) {
        chatInput.value = `Voici le résultat du calcul normé que j'ai obtenu :\n\n${lastCalcResult}\n\nPeux-tu me donner des conseils de mise en œuvre ?`;
        handleInputKeyPress();
        chatInput.focus();
    }
}

// ==========================================================================
// 📄 GÉNÉRATEUR DE DEVIS & FACTURES PRO-FORMA
// ==========================================================================

let currentQuoteData = {
    id: null,
    items: []
};

function openQuotesModal() {
    const modal = document.getElementById('quotes-modal');
    if (modal) {
        modal.classList.remove('hidden');
        if (currentQuoteData.items.length === 0) {
            addQuoteItemRow({ description: "Prestation principale", quantite: 1, unite: "u", prix_unitaire: 25000 });
        }
    }
}

function closeQuotesModal() {
    const modal = document.getElementById('quotes-modal');
    if (modal) modal.classList.add('hidden');
}

async function extractQuoteFromText() {
    const promptInput = document.getElementById('quote-prompt-input');
    if (!promptInput || !promptInput.value.trim()) {
        showToast("Veuillez saisir ou dicter vos notes de chantier.");
        return;
    }

    const btn = document.getElementById('btn-extract-quote');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "⏳ Analyse IA en cours...";

    try {
        const token = localStorage.getItem('prosartisan_token');
        const res = await fetch('/api/quotes/extract', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            },
            body: JSON.stringify({ prompt: promptInput.value.trim() })
        });

        if (res.ok) {
            const data = await res.json();
            document.getElementById('quote-client-name').value = data.client_nom || "";
            document.getElementById('quote-client-phone').value = data.client_telephone || "";
            document.getElementById('quote-client-address').value = data.client_adresse || "";
            
            const tbody = document.getElementById('quote-items-tbody');
            tbody.innerHTML = '';
            currentQuoteData.items = [];

            (data.items || []).forEach(item => addQuoteItemRow(item));
            recalculateQuoteTotals();
            showToast("Devis extrait et structuré avec succès !");
        } else {
            showToast("Erreur lors de l'analyse du devis.");
        }
    } catch (e) {
        console.error("Extraction quote error:", e);
        showToast("Erreur de connexion avec le serveur.");
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

function addQuoteItemRow(item = { description: "", quantite: 1, unite: "u", prix_unitaire: 0 }) {
    const tbody = document.getElementById('quote-items-tbody');
    if (!tbody) return;

    const row = document.createElement('tr');
    row.className = "quote-item-row";
    row.innerHTML = `
        <td><input type="text" class="item-desc" value="${escapeHtml(item.description || '')}" placeholder="Désignation"></td>
        <td><input type="number" class="item-qty" value="${item.quantite || 1}" min="0.1" step="any" oninput="recalculateQuoteTotals()"></td>
        <td><input type="text" class="item-unit" value="${escapeHtml(item.unite || 'u')}"></td>
        <td><input type="number" class="item-price" value="${item.prix_unitaire || 0}" min="0" step="100" oninput="recalculateQuoteTotals()"></td>
        <td class="item-total-cell">${Math.round((item.quantite || 1) * (item.prix_unitaire || 0)).toLocaleString('fr-FR')} F</td>
        <td><button class="remove-item-btn" onclick="removeQuoteItemRow(this)" title="Supprimer" aria-label="Supprimer la ligne">✕</button></td>
    `;
    tbody.appendChild(row);
    recalculateQuoteTotals();
}

function removeQuoteItemRow(btn) {
    const row = btn.closest('tr');
    if (row) {
        row.remove();
        recalculateQuoteTotals();
    }
}

function recalculateQuoteTotals() {
    const rows = document.querySelectorAll('.quote-item-row');
    let totalHT = 0;

    rows.forEach(row => {
        const qty = parseFloat(row.querySelector('.item-qty')?.value) || 0;
        const price = parseFloat(row.querySelector('.item-price')?.value) || 0;
        const lineTotal = qty * price;
        const totalCell = row.querySelector('.item-total-cell');
        if (totalCell) totalCell.textContent = `${Math.round(lineTotal).toLocaleString('fr-FR')} F`;
        totalHT += lineTotal;
    });

    const totalTVA = Math.round(totalHT * 0.18);
    const totalTTC = totalHT + totalTVA;

    const elHT = document.getElementById('quote-total-ht');
    const elTVA = document.getElementById('quote-total-tva');
    const elTTC = document.getElementById('quote-total-ttc');

    if (elHT) elHT.textContent = `${Math.round(totalHT).toLocaleString('fr-FR')} FCFA`;
    if (elTVA) elTVA.textContent = `${totalTVA.toLocaleString('fr-FR')} FCFA`;
    if (elTTC) elTTC.textContent = `${Math.round(totalTTC).toLocaleString('fr-FR')} FCFA`;
}

function gatherQuoteFormData() {
    const rows = document.querySelectorAll('.quote-item-row');
    const items = [];
    rows.forEach(row => {
        const desc = row.querySelector('.item-desc')?.value.trim();
        if (desc) {
            const qty = parseFloat(row.querySelector('.item-qty')?.value) || 1;
            const unit = row.querySelector('.item-unit')?.value.trim() || 'u';
            const price = parseFloat(row.querySelector('.item-price')?.value) || 0;
            items.push({ description: desc, quantite: qty, unite: unit, prix_unitaire: price });
        }
    });

    return {
        titre: "Devis travaux",
        type_document: document.getElementById('quote-type')?.value || "devis",
        client_nom: document.getElementById('quote-client-name')?.value.trim() || "Client",
        client_telephone: document.getElementById('quote-client-phone')?.value.trim() || "",
        client_adresse: document.getElementById('quote-client-address')?.value.trim() || "",
        taux_tva: 18.0,
        items: items
    };
}

async function saveQuoteToServer() {
    const payload = gatherQuoteFormData();
    if (payload.items.length === 0) {
        showToast("Ajoutez au moins une ligne de prestation.");
        return;
    }

    const token = localStorage.getItem('prosartisan_token');
    if (!token) {
        showToast("Connectez-vous pour enregistrer vos devis dans votre compte.");
        openLoginModal();
        return;
    }

    try {
        const res = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const data = await res.json();
            currentQuoteData.id = data.id;
            showToast(`Devis ${data.numero_devis} enregistré !`);
        } else {
            showToast("Erreur lors de l'enregistrement du devis.");
        }
    } catch (e) {
        console.error("Save quote error:", e);
        showToast("Erreur de connexion.");
    }
}

function exportQuoteWhatsApp() {
    const data = gatherQuoteFormData();
    if (data.items.length === 0) {
        showToast("Veuillez remplir votre devis.");
        return;
    }

    let text = `🛠️ *${data.type_document.toUpperCase()} PROSARTISAN*\n`;
    text += `👤 *Client :* ${data.client_nom} ${data.client_telephone ? '(' + data.client_telephone + ')' : ''}\n`;
    if (data.client_adresse) text += `📍 *Lieu :* ${data.client_adresse}\n`;
    text += `\n*DÉTAILS DES PRESTATIONS :*\n`;

    let totalHT = 0;
    data.items.forEach((it, idx) => {
        const lineTotal = it.quantite * it.prix_unitaire;
        totalHT += lineTotal;
        text += `${idx + 1}. ${it.description} - ${it.quantite} ${it.unite} × ${it.prix_unitaire.toLocaleString('fr-FR')} = *${Math.round(lineTotal).toLocaleString('fr-FR')} FCFA*\n`;
    });

    const totalTTC = Math.round(totalHT * 1.18);
    text += `\n💰 *Total HT :* ${Math.round(totalHT).toLocaleString('fr-FR')} FCFA\n`;
    text += `💵 *Total TTC (TVA 18%) :* *${totalTTC.toLocaleString('fr-FR')} FCFA*\n\n`;
    text += `_Devis généré avec l'Assistant ProsArtisan IA Expert_`;

    const encoded = encodeURIComponent(text);
    const phone = data.client_telephone.replace(/[^0-9]/g, '');
    const waUrl = phone ? `https://wa.me/${phone}?text=${encoded}` : `https://wa.me/?text=${encoded}`;
    window.open(waUrl, '_blank');
}

async function previewQuoteHtml() {
    const data = gatherQuoteFormData();
    if (data.items.length === 0) {
        showToast("Veuillez remplir votre devis.");
        return;
    }

    const token = localStorage.getItem('prosartisan_token');
    if (currentQuoteData.id && token) {
        window.open(`/api/quotes/${currentQuoteData.id}/html`, '_blank');
    } else {
        // Envoi pour sauvegarde ou preview directe
        if (token) {
            await saveQuoteToServer();
            if (currentQuoteData.id) {
                window.open(`/api/quotes/${currentQuoteData.id}/html`, '_blank');
                return;
            }
        }
        showToast("Enregistrez le devis pour ouvrir la version imprimable.");
    }
}

// ==========================================================================
// 🎙️ MODE VOCAL MAINS-LIBRES & WEBSOCKET AUDIO DUPLEX
// ==========================================================================

let liveVoiceWs = null;
let liveMediaRecorder = null;
let liveAudioStream = null;
let isLiveVoiceActive = false;
let currentVoiceAssistantBubble = null;

async function toggleLiveVoiceSession() {
    const micBtn = document.getElementById('mic-btn');
    if (isLiveVoiceActive) {
        stopLiveVoiceSession();
    } else {
        startLiveVoiceSession();
    }
}

async function startLiveVoiceSession() {
    const micBtn = document.getElementById('mic-btn');
    try {
        liveAudioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        liveMediaRecorder = new MediaRecorder(liveAudioStream);

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/api/chat/ws`;
        liveVoiceWs = new WebSocket(wsUrl);

        liveVoiceWs.onopen = () => {
            const token = localStorage.getItem('prosartisan_token');
            liveVoiceWs.send(JSON.stringify({
                action: 'auth',
                token: token || null,
                conversation_id: state.currentConversationId
            }));

            isLiveVoiceActive = true;
            if (micBtn) {
                micBtn.classList.add('recording-active');
                micBtn.setAttribute('aria-pressed', 'true');
            }
            showToast("🎙️ Écoute en cours... Parlez à l'assistant !");
            announceToScreenReader("Microphone activé, écoute en cours");

            const audioChunks = [];
            liveMediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };

            liveMediaRecorder.onstop = async () => {
                if (audioChunks.length > 0 && liveVoiceWs && liveVoiceWs.readyState === WebSocket.OPEN) {
                    const blob = new Blob(audioChunks, { type: 'audio/webm' });
                    const reader = new FileReader();
                    reader.onloadend = () => {
                        const base64Audio = reader.result.split(',')[1];
                        liveVoiceWs.send(JSON.stringify({
                            action: 'audio_chunk',
                            audio: base64Audio,
                            audio_format: 'audio/webm'
                        }));
                    };
                    reader.readAsDataURL(blob);
                }
            };

            liveMediaRecorder.start();
        };

        liveVoiceWs.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleVoiceWebSocketMessage(msg);
            } catch (e) {
                console.error("WS Parse error:", e);
            }
        };

        liveVoiceWs.onerror = (err) => {
            console.error("Voice WS Error:", err);
            stopLiveVoiceSession();
            showToast("Erreur de connexion vocale WebSocket.");
        };

        liveVoiceWs.onclose = () => {
            stopLiveVoiceSession();
        };

    } catch (err) {
        console.error("Audio Access Denied:", err);
        showToast("Accès au microphone refusé ou non supporté.");
    }
}

function stopLiveVoiceSession() {
    isLiveVoiceActive = false;
    const micBtn = document.getElementById('mic-btn');
    if (micBtn) {
        micBtn.classList.remove('recording-active');
        micBtn.setAttribute('aria-pressed', 'false');
    }

    if (liveMediaRecorder && liveMediaRecorder.state !== 'inactive') {
        liveMediaRecorder.stop();
    }
    if (liveAudioStream) {
        liveAudioStream.getTracks().forEach(t => t.stop());
        liveAudioStream = null;
    }
}

function handleVoiceWebSocketMessage(msg) {
    if (msg.type === 'user_transcription' && msg.text) {
        landingContainer.classList.add('hidden');
        messagesStream.classList.remove('hidden');
        appendMessage('user', msg.text);
    } else if (msg.type === 'stream') {
        if (!currentVoiceAssistantBubble) {
            currentVoiceAssistantBubble = appendAssistantStreamingBubble();
        }
        if (msg.chunk) {
            currentVoiceAssistantBubble.appendChunk(msg.chunk);
        }
    } else if (msg.type === 'audio_response' && msg.audio) {
        try {
            const audioMime = msg.audio_format || 'audio/mp3';
            const snd = new Audio(`data:${audioMime};base64,${msg.audio}`);
            snd.play().catch(e => console.warn("Autoplay blocked:", e));
        } catch (e) {
            console.error("Audio playback error:", e);
        }
    } else if (msg.type === 'stream_end') {
        if (currentVoiceAssistantBubble) {
            currentVoiceAssistantBubble.finalize();
            currentVoiceAssistantBubble = null;
        }
        updateQuotaUI();
    } else if (msg.type === 'payment_required') {
        showToast(msg.message || "Quota gratuit épuisé. Passez à la version Pro.");
        updateQuotaUI();
        openPaywallModal();
    } else if (msg.type === 'error') {
        showToast(msg.message || "Erreur lors du traitement vocal.");
    }
}

function appendAssistantStreamingBubble() {
    const bubble = document.createElement('div');
    bubble.className = "message assistant-message";
    bubble.innerHTML = `
        <div class="msg-avatar">⚡</div>
        <div class="msg-content-wrapper">
            <div class="msg-author">ProsArtisan IA</div>
            <div class="msg-text"></div>
        </div>
    `;
    messagesStream.appendChild(bubble);
    messagesStream.scrollTop = messagesStream.scrollHeight;

    const textEl = bubble.querySelector('.msg-text');
    let fullText = "";

    return {
        appendChunk: (chunk) => {
            fullText += chunk;
            textEl.innerHTML = marked.parse(fullText);
            messagesStream.scrollTop = messagesStream.scrollHeight;
        },
        finalize: () => {
            textEl.innerHTML = marked.parse(fullText);
            hljs.highlightAll();
        }
    };
}
// PWA : enregistrement depuis un fichier externe, compatible avec la CSP.
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/chat/sw.js').catch(() => {});
    });
}

// ── Paiement Mobile Money (Wave / Orange Money) ──
// Parcours : POST /api/payment/init → redirection vers l'URL de l'opérateur
// (simulateur en mode démo) → retour sur /chat/?transaction=…&paiement=… →
// suivi de GET /api/payment/transactions/{id} jusqu'à la confirmation, qui
// arrive par le webhook opérateur indépendamment du retour navigateur.
let paywallTrigger = null;

async function openPaywallModal() {
    const modal = document.getElementById('paywall-modal');
    if (!modal) return;
    paywallTrigger = document.activeElement;
    modal.classList.remove('hidden');
    const hint = document.getElementById('paywall-mode-hint');
    if (hint) {
        hint.textContent = state.isLoggedIn ? '' : "Connexion requise pour activer un Pass.";
        try {
            const response = await fetch('/api/payment/tarifs');
            if (response.ok) {
                const tarifs = await response.json();
                if (!tarifs.disponible) {
                    hint.textContent = "Paiement Mobile Money bientôt disponible.";
                } else if (tarifs.mode === 'demo') {
                    hint.textContent += " Mode démonstration : aucun montant ne sera débité.";
                }
            }
        } catch (e) {
            // Indication facultative : la modale reste utilisable hors ligne.
        }
    }
    setTimeout(() => modal.querySelector('input[name="paywall-offre"]:checked')?.focus(), 0);
}

function closePaywallModal() {
    document.getElementById('paywall-modal')?.classList.add('hidden');
    if (paywallTrigger && typeof paywallTrigger.focus === 'function') {
        paywallTrigger.focus();
    }
    paywallTrigger = null;
}

async function startPayment(operateur) {
    const typePass = document.querySelector('input[name="paywall-offre"]:checked')?.value || 'pass_24h';
    if (!state.isLoggedIn) {
        closePaywallModal();
        showToast("Connectez-vous pour activer un Pass.");
        openLoginModal();
        return;
    }
    const buttons = document.querySelectorAll('.paywall-pay-btn');
    buttons.forEach(b => { b.disabled = true; });
    try {
        const response = await fetch('/api/payment/init', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('prosartisan_token')}`
            },
            body: JSON.stringify({ type_pass: typePass, operateur })
        });
        if (response.status === 401) {
            logout();
            closePaywallModal();
            openLoginModal();
            return;
        }
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            showToast(err.detail || "Paiement momentanément indisponible.");
            return;
        }
        const data = await response.json();
        window.location.assign(data.payment_url);
    } catch (e) {
        showToast("Erreur de connexion : paiement non initialisé.");
    } finally {
        buttons.forEach(b => { b.disabled = false; });
    }
}

async function handlePaymentReturn() {
    const params = new URLSearchParams(window.location.search);
    const transactionId = params.get('transaction');
    const issue = params.get('paiement');
    if (!transactionId) return;
    // Nettoie l'URL : un rechargement ne relance pas le suivi.
    history.replaceState(null, '', window.location.pathname);

    if (issue !== 'succes') {
        showToast("Paiement annulé ou refusé : aucun montant n'a été débité.");
        return;
    }
    const token = localStorage.getItem('prosartisan_token');
    if (!token) return;
    showToast("Paiement en cours de confirmation…");
    for (let tentative = 0; tentative < 15; tentative++) {
        try {
            const response = await fetch(`/api/payment/transactions/${encodeURIComponent(transactionId)}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const txn = await response.json();
                if (txn.statut === 'ACCEPTED') {
                    showToast("✅ Paiement confirmé : votre Pass est actif !");
                    announceToScreenReader("Paiement confirmé, votre Pass est actif.");
                    updateQuotaUI();
                    return;
                }
                if (txn.statut === 'FAILED' || txn.statut === 'EXPIRED') {
                    showToast("Paiement refusé ou expiré : aucun montant n'a été débité.");
                    return;
                }
            }
        } catch (e) {
            // Réseau instable : nouvelle tentative.
        }
        await new Promise(resolve => setTimeout(resolve, 2000));
    }
    showToast("Confirmation en attente : votre Pass sera activé dès la confirmation de l'opérateur.");
}
