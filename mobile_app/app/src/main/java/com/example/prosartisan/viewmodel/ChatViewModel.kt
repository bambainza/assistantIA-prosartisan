package com.example.prosartisan.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.prosartisan.network.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

sealed class ChatUiState {
    data class Config(val baseUrl: String, val error: String? = null) : ChatUiState()
    
    data class Auth(
        val isLogin: Boolean = true,
        val email: String = "",
        val nom: String = "",
        val phone: String = "",
        val error: String? = null,
        val isLoading: Boolean = false
    ) : ChatUiState()

    data class Main(
        val email: String,
        val conversations: List<ConversationDto> = emptyList(),
        val activeConversationId: String? = null,
        val messages: List<MessageDto> = emptyList(),
        val inputMessage: String = "",
        val activeMetierId: Int? = 1, // Par défaut 1 (Maçonnerie / Bâtiment)
        val isStreaming: Boolean = false,
        val currentStreamText: String = "",
        val quotaRestant: Int? = null,
        val showPaywall: Boolean = false,
        val error: String? = null,
        val isSidebarOpen: Boolean = false
    ) : ChatUiState()
}

class ChatViewModel(private val client: NetworkClient) : ViewModel() {
    private val _uiState = MutableStateFlow<ChatUiState>(ChatUiState.Config(client.baseUrl))
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private val _isDarkTheme = MutableStateFlow(true)
    val isDarkTheme: StateFlow<Boolean> = _isDarkTheme.asStateFlow()

    fun toggleTheme() {
        _isDarkTheme.value = !_isDarkTheme.value
    }

    init {
        viewModelScope.launch {
            // Détection automatique de l'URL du serveur en arrière-plan au démarrage
            client.autoDetectBaseUrl()
            
            val savedToken = client.token
            val savedEmail = client.userEmail
            if (savedToken != null && savedEmail != null) {
                loadMainState(savedEmail)
            } else {
                _uiState.value = ChatUiState.Auth(isLogin = true)
            }
        }
    }

    fun saveBaseUrl(url: String) {
        if (url.isBlank()) {
            _uiState.update { 
                if (it is ChatUiState.Config) it.copy(error = "L'adresse URL ne peut pas être vide") else it
            }
            return
        }
        client.baseUrl = url
        _uiState.value = ChatUiState.Auth(isLogin = true)
    }

    fun toggleAuthMode() {
        val current = _uiState.value
        if (current is ChatUiState.Auth) {
            _uiState.value = current.copy(
                isLogin = !current.isLogin,
                error = null,
                isLoading = false
            )
        }
    }

    fun login(email: String, authKey: String) {
        val current = _uiState.value
        if (current !is ChatUiState.Auth) return

        _uiState.value = current.copy(isLoading = true, error = null)
        viewModelScope.launch {
            client.login(email, authKey).fold(
                onSuccess = { res ->
                    loadMainState(res.user.email)
                },
                onFailure = { err ->
                    _uiState.value = current.copy(
                        isLoading = false,
                        error = err.message ?: "Échec de la connexion"
                    )
                }
            )
        }
    }

    fun register(email: String, authKey: String, nom: String, phone: String) {
        val current = _uiState.value
        if (current !is ChatUiState.Auth) return

        _uiState.value = current.copy(isLoading = true, error = null)
        viewModelScope.launch {
            client.register(email, authKey, nom, phone).fold(
                onSuccess = {
                    // Connexion automatique après inscription réussie
                    client.login(email, authKey).fold(
                        onSuccess = { res ->
                            loadMainState(res.user.email)
                        },
                        onFailure = { err ->
                            _uiState.value = current.copy(
                                isLoading = false,
                                error = "Compte créé mais connexion automatique échouée: ${err.message}"
                            )
                        }
                    )
                },
                onFailure = { err ->
                    _uiState.value = current.copy(
                        isLoading = false,
                        error = err.message ?: "Échec de l'inscription"
                    )
                }
            )
        }
    }

    fun logout() {
        client.logout()
        _uiState.value = ChatUiState.Auth(isLogin = true)
    }

    fun showConfigScreen() {
        _uiState.value = ChatUiState.Config(client.baseUrl)
    }

    fun detectServerUrl() {
        viewModelScope.launch {
            _uiState.update {
                if (it is ChatUiState.Config) it.copy(error = "Détection en cours...") else it
            }
            val detected = client.autoDetectBaseUrl()
            _uiState.value = ChatUiState.Config(detected, error = "Serveur détecté : $detected")
        }
    }

    fun setSidebarOpen(open: Boolean) {
        val current = _uiState.value
        if (current is ChatUiState.Main) {
            _uiState.value = current.copy(isSidebarOpen = open)
        }
    }

    fun selectMetier(metierId: Int?) {
        val current = _uiState.value
        if (current is ChatUiState.Main) {
            _uiState.value = current.copy(activeMetierId = metierId)
        }
    }

    fun updateInput(text: String) {
        val current = _uiState.value
        if (current is ChatUiState.Main) {
            _uiState.value = current.copy(inputMessage = text)
        }
    }

    fun createConversation() {
        val current = _uiState.value
        if (current !is ChatUiState.Main) return

        _uiState.value = current.copy(
            activeConversationId = null,
            messages = emptyList(),
            inputMessage = "",
            isSidebarOpen = false
        )
    }

    fun selectConversation(convId: String) {
        val current = _uiState.value
        if (current !is ChatUiState.Main) return

        _uiState.value = current.copy(isSidebarOpen = false)
        viewModelScope.launch {
            client.getConversationDetail(convId).fold(
                onSuccess = { detail ->
                    _uiState.update { state ->
                        if (state is ChatUiState.Main) {
                            state.copy(
                                activeConversationId = detail.id,
                                messages = detail.messages
                            )
                        } else state
                    }
                },
                onFailure = { err ->
                    _uiState.update { state ->
                        if (state is ChatUiState.Main) {
                            state.copy(error = "Erreur de chargement: ${err.message}")
                        } else state
                    }
                }
            )
        }
    }

    fun dismissError() {
        _uiState.update { state ->
            when (state) {
                is ChatUiState.Main -> state.copy(error = null)
                is ChatUiState.Auth -> state.copy(error = null)
                is ChatUiState.Config -> state.copy(error = null)
            }
        }
    }

    fun dismissPaywall() {
        val current = _uiState.value
        if (current is ChatUiState.Main) {
            _uiState.value = current.copy(showPaywall = false)
        }
    }

    fun triggerFakePaymentWebhookSuccess() {
        // Méthode de simulation pour rafraîchir le quota après un clic sur le paywall
        val current = _uiState.value
        if (current is ChatUiState.Main) {
            _uiState.value = current.copy(
                showPaywall = false,
                quotaRestant = 100 // Simulation d'activation d'abonnement
            )
            refreshConversations()
        }
    }

    fun sendMessage() {
        val current = _uiState.value
        if (current !is ChatUiState.Main || current.isStreaming) return
        val question = current.inputMessage.trim()
        if (question.isEmpty()) return

        // Créer un message temporaire de l'utilisateur
        val userTempMsg = MessageDto(
            id = java.util.UUID.randomUUID().toString(),
            role = "user",
            content = question,
            created_at = ""
        )

        // Effacer l'input et activer le mode streaming
        _uiState.value = current.copy(
            messages = current.messages + userTempMsg,
            inputMessage = "",
            isStreaming = true,
            currentStreamText = "..."
        )

        viewModelScope.launch {
            var activeConvId = current.activeConversationId
            var fullResponseText = ""
            
            client.sendMessageStream(question, activeConvId, current.activeMetierId).collect { event ->
                when (event) {
                    is StreamEvent.Info -> {
                        activeConvId = event.conversationId
                        _uiState.update { state ->
                            if (state is ChatUiState.Main) {
                                state.copy(activeConversationId = activeConvId)
                            } else state
                        }
                    }
                    is StreamEvent.Chunk -> {
                        if (fullResponseText.isEmpty()) {
                            fullResponseText = event.chunk
                        } else {
                            fullResponseText += event.chunk
                        }
                        _uiState.update { state ->
                            if (state is ChatUiState.Main) {
                                state.copy(currentStreamText = fullResponseText)
                            } else state
                        }
                    }
                    is StreamEvent.End -> {
                        val assistantFinalMsg = MessageDto(
                            id = java.util.UUID.randomUUID().toString(),
                            role = "assistant",
                            content = fullResponseText,
                            created_at = ""
                        )
                        _uiState.update { state ->
                            if (state is ChatUiState.Main) {
                                state.copy(
                                    messages = state.messages + assistantFinalMsg,
                                    isStreaming = false,
                                    currentStreamText = ""
                                )
                            } else state
                        }
                        refreshConversations()
                    }
                    is StreamEvent.QuotaExceeded -> {
                        _uiState.update { state ->
                            if (state is ChatUiState.Main) {
                                state.copy(
                                    isStreaming = false,
                                    currentStreamText = "",
                                    showPaywall = true
                                )
                            } else state
                        }
                    }
                    is StreamEvent.Error -> {
                        _uiState.update { state ->
                            if (state is ChatUiState.Main) {
                                state.copy(
                                    isStreaming = false,
                                    currentStreamText = "",
                                    error = "Erreur: ${event.message}"
                                )
                            } else state
                        }
                    }
                }
            }
        }
    }

    private fun loadMainState(email: String) {
        _uiState.value = ChatUiState.Main(email = email)
        refreshConversations()
    }

    private fun refreshConversations() {
        val current = _uiState.value
        if (current !is ChatUiState.Main) return

        viewModelScope.launch {
            client.getConversations().fold(
                onSuccess = { list ->
                    _uiState.update { state ->
                        if (state is ChatUiState.Main) {
                            state.copy(conversations = list)
                        } else state
                    }
                },
                onFailure = { err ->
                    _uiState.update { state ->
                        if (state is ChatUiState.Main) {
                            state.copy(error = "Erreur liste: ${err.message}")
                        } else state
                    }
                }
            )
        }
    }
}
