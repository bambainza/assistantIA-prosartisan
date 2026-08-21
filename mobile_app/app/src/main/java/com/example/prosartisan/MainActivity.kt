package com.example.prosartisan

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.*
import kotlin.OptIn
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.prosartisan.network.ConversationDto
import com.example.prosartisan.network.MessageDto
import com.example.prosartisan.network.NetworkClient
import com.example.prosartisan.theme.ProsArtisanTheme
import com.example.prosartisan.viewmodel.ChatUiState
import com.example.prosartisan.viewmodel.ChatViewModel
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val client = NetworkClient(applicationContext)

        setContent {
            ProsArtisanTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val chatViewModel: ChatViewModel = viewModel { ChatViewModel(client) }
                    AppContent(chatViewModel)
                }
            }
        }
    }
}

@Composable
fun AppContent(viewModel: ChatViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(
                        Color(0xFF1E1E2C),
                        Color(0xFF0F0F17)
                    )
                )
            )
    ) {
        when (val uiState = state) {
            is ChatUiState.Config -> ServerConfigScreen(uiState, viewModel)
            is ChatUiState.Auth -> LoginRegisterScreen(uiState, viewModel)
            is ChatUiState.Main -> MainChatScreen(uiState, viewModel)
        }
    }
}

@Composable
fun ServerConfigScreen(state: ChatUiState.Config, viewModel: ChatViewModel) {
    var urlText by remember { mutableStateOf(state.baseUrl) }

    // Mettre à jour le champ texte lorsque l'URL est auto-détectée
    LaunchedEffect(state.baseUrl) {
        urlText = state.baseUrl
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .safeContentPadding(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            imageVector = Icons.Default.Settings,
            contentDescription = "Config",
            tint = Color(0xFFE2A000),
            modifier = Modifier.size(72.dp)
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = "Configuration du Serveur",
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            color = Color.White
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Entrez l'URL de l'API backend de ProsArtisan",
            fontSize = 14.sp,
            color = Color.LightGray
        )
        Spacer(modifier = Modifier.height(24.dp))

        OutlinedTextField(
            value = urlText,
            onValueChange = { urlText = it },
            label = { Text("URL de l'API", color = Color.Gray) },
            singleLine = true,
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Color(0xFFE2A000),
                unfocusedBorderColor = Color.DarkGray,
                focusedTextColor = Color.White,
                unfocusedTextColor = Color.White
            ),
            modifier = Modifier.fillMaxWidth()
        )

        state.error?.let {
            Spacer(modifier = Modifier.height(8.dp))
            val isSuccess = it.startsWith("Serveur détecté")
            Text(
                text = it,
                color = if (isSuccess) Color(0xFF4CAF50) else if (it.contains("cours")) Color(0xFFE2A000) else Color.Red,
                fontSize = 13.sp
            )
        }

        Spacer(modifier = Modifier.height(24.dp))
        Button(
            onClick = { viewModel.saveBaseUrl(urlText) },
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE2A000)),
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp)
        ) {
            Text("Enregistrer et Continuer", color = Color.Black, fontWeight = FontWeight.Bold)
        }

        Spacer(modifier = Modifier.height(12.dp))
        OutlinedButton(
            onClick = { viewModel.detectServerUrl() },
            colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFE2A000)),
            border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE2A000)),
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp)
        ) {
            Text("Auto-détecter le serveur", fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
fun LoginRegisterScreen(state: ChatUiState.Auth, viewModel: ChatViewModel) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var nom by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .safeContentPadding(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            imageVector = Icons.Default.AccountCircle,
            contentDescription = "Auth",
            tint = Color(0xFFE2A000),
            modifier = Modifier.size(80.dp)
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = if (state.isLogin) "Connexion ProsArtisan" else "Créer un Compte",
            fontSize = 26.sp,
            fontWeight = FontWeight.Bold,
            color = Color.White
        )
        Spacer(modifier = Modifier.height(24.dp))

        if (!state.isLogin) {
            OutlinedTextField(
                value = nom,
                onValueChange = { nom = it },
                label = { Text("Nom complet", color = Color.Gray) },
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFFE2A000),
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White
                ),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(12.dp))
            OutlinedTextField(
                value = phone,
                onValueChange = { phone = it },
                label = { Text("Téléphone (ex: +225...)", color = Color.Gray) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFFE2A000),
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White
                ),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(12.dp))
        }

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Adresse email", color = Color.Gray) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Color(0xFFE2A000),
                focusedTextColor = Color.White,
                unfocusedTextColor = Color.White
            ),
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(12.dp))

        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Mot de passe", color = Color.Gray) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Color(0xFFE2A000),
                focusedTextColor = Color.White,
                unfocusedTextColor = Color.White
            ),
            modifier = Modifier.fillMaxWidth()
        )

        state.error?.let {
            Spacer(modifier = Modifier.height(8.dp))
            Text(text = it, color = Color.Red, fontSize = 13.sp)
        }

        Spacer(modifier = Modifier.height(24.dp))

        if (state.isLoading) {
            CircularProgressIndicator(color = Color(0xFFE2A000))
        } else {
            Button(
                onClick = {
                    if (state.isLogin) {
                        viewModel.login(email, password)
                    } else {
                        viewModel.register(email, password, nom, phone)
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE2A000)),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp)
            ) {
                Text(
                    text = if (state.isLogin) "Se connecter" else "S'inscrire",
                    color = Color.Black,
                    fontWeight = FontWeight.Bold,
                    fontSize = 16.sp
                )
            }
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = if (state.isLogin) "Pas de compte ? Inscrivez-vous" else "Déjà inscrit ? Connectez-vous",
                color = Color.LightGray,
                fontSize = 14.sp,
                modifier = Modifier
                    .clickable { viewModel.toggleAuthMode() }
                    .padding(8.dp)
            )
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                text = "Modifier l'adresse serveur",
                color = Color(0xFFE2A000),
                fontSize = 13.sp,
                modifier = Modifier
                    .clickable { viewModel.showConfigScreen() }
                    .padding(8.dp)
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainChatScreen(state: ChatUiState.Main, viewModel: ChatViewModel) {
    val coroutineScope = rememberCoroutineScope()
    val scrollState = rememberLazyListState()

    // Effet pour faire défiler vers le bas lors de la réception de nouveaux messages/chunks
    LaunchedEffect(state.messages.size, state.currentStreamText) {
        if (state.messages.isNotEmpty() || state.currentStreamText.isNotEmpty()) {
            scrollState.animateScrollToItem(
                if (state.currentStreamText.isNotEmpty()) state.messages.size else state.messages.size - 1
            )
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            "ProsArtisan IA",
                            fontWeight = FontWeight.Bold,
                            color = Color.White,
                            fontSize = 18.sp
                        )
                        Text(
                            text = "Abonnement: ${if (state.quotaRestant != null && state.quotaRestant > 10) "Pro Illimité" else "Gratuit"}",
                            fontSize = 12.sp,
                            color = Color.LightGray
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = { viewModel.setSidebarOpen(true) }) {
                        Icon(Icons.Default.Menu, contentDescription = "Menu", tint = Color.White)
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.createConversation() }) {
                        Icon(Icons.Default.Add, contentDescription = "New", tint = Color(0xFFE2A000))
                    }
                    IconButton(onClick = { viewModel.logout() }) {
                        Icon(Icons.Default.ExitToApp, contentDescription = "Logout", tint = Color.LightGray)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF171721))
            )
        },
        containerColor = Color.Transparent
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                // Barre de Sélection de Métier (Horizontal choice chips)
                MetierSelectorRow(
                    selectedId = state.activeMetierId,
                    onSelect = { viewModel.selectMetier(it) }
                )

                // Fenêtre principale de messages
                LazyColumn(
                    state = scrollState,
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp)
                ) {
                    items(state.messages) { msg ->
                        MessageBubble(msg)
                    }
                    if (state.isStreaming && state.currentStreamText.isNotEmpty()) {
                        item {
                            StreamingBubble(state.currentStreamText)
                        }
                    }
                }

                // Pied de page / Zone de saisie
                ChatInputArea(
                    text = state.inputMessage,
                    isStreaming = state.isStreaming,
                    onTextChange = { viewModel.updateInput(it) },
                    onSend = { viewModel.sendMessage() }
                )
            }

            // Tiroir latéral personnalisé (Custom Sidebar Drawer)
            if (state.isSidebarOpen) {
                CustomSidebar(
                    conversations = state.conversations,
                    activeConvId = state.activeConversationId,
                    onSelectConv = { viewModel.selectConversation(it) },
                    onClose = { viewModel.setSidebarOpen(false) }
                )
            }

            // Pop-up du Paywall Mobile Money
            if (state.showPaywall) {
                PaywallDialog(
                    onDismiss = { viewModel.dismissPaywall() },
                    onPaymentSuccess = { viewModel.triggerFakePaymentWebhookSuccess() }
                )
            }

            // Notification d'erreur éphémère
            state.error?.let {
                Snackbar(
                    action = {
                        TextButton(onClick = { viewModel.dismissError() }) {
                            Text("OK", color = Color(0xFFE2A000))
                        }
                    },
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(16.dp)
                ) {
                    Text(it)
                }
            }
        }
    }
}

@Composable
fun MetierSelectorRow(selectedId: Int?, onSelect: (Int?) -> Unit) {
    val metiers = listOf(
        1 to "🧱 Maçonnerie",
        2 to "⚡ Électricité",
        3 to "🚰 Plomberie",
        4 to "🪵 Menuiserie"
    )

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFF171721))
            .padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        metiers.forEach { (id, label) ->
            val isSelected = selectedId == id
            Box(
                modifier = Modifier
                    .background(
                        color = if (isSelected) Color(0xFFE2A000) else Color(0xFF232333),
                        shape = RoundedCornerShape(16.dp)
                    )
                    .clickable { onSelect(id) }
                    .padding(horizontal = 12.dp, vertical = 6.dp)
            ) {
                Text(
                    text = label,
                    color = if (isSelected) Color.Black else Color.White,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp
                )
            }
        }
    }
}

@Composable
fun MessageBubble(msg: MessageDto) {
    val isUser = msg.role == "user"
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        Card(
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 16.dp,
                bottomStart = if (isUser) 16.dp else 2.dp,
                bottomEnd = if (isUser) 2.dp else 16.dp
            ),
            colors = CardDefaults.cardColors(
                containerColor = if (isUser) Color(0xFF0F5A47) else Color(0xFF2C2C3C)
            ),
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = msg.content,
                    color = Color.White,
                    fontSize = 15.sp
                )
            }
        }
    }
}

@Composable
fun StreamingBubble(text: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.Start
    ) {
        Card(
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 16.dp,
                bottomStart = 2.dp,
                bottomEnd = 16.dp
            ),
            colors = CardDefaults.cardColors(
                containerColor = Color(0xFF232333)
            ),
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = text,
                    color = Color.LightGray,
                    fontSize = 15.sp
                )
            }
        }
    }
}

@Composable
fun ChatInputArea(
    text: String,
    isStreaming: Boolean,
    onTextChange: (String) -> Unit,
    onSend: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFF171721))
            .padding(12.dp)
            .navigationBarsPadding()
            .imePadding(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        OutlinedTextField(
            value = text,
            onValueChange = onTextChange,
            placeholder = { Text("Posez votre question chantier...", color = Color.Gray) },
            maxLines = 4,
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Color(0xFFE2A000),
                unfocusedBorderColor = Color.DarkGray,
                focusedTextColor = Color.White,
                unfocusedTextColor = Color.White
            ),
            modifier = Modifier.weight(1f)
        )
        Spacer(modifier = Modifier.width(12.dp))
        IconButton(
            onClick = onSend,
            enabled = !isStreaming && text.isNotBlank(),
            modifier = Modifier
                .background(
                    color = if (text.isNotBlank() && !isStreaming) Color(0xFFE2A000) else Color.DarkGray,
                    shape = RoundedCornerShape(50)
                )
                .size(48.dp)
        ) {
            if (isStreaming) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp), color = Color.Black)
            } else {
                Icon(
                    imageVector = Icons.Default.Send,
                    contentDescription = "Send",
                    tint = Color.Black
                )
            }
        }
    }
}

@Composable
fun CustomSidebar(
    conversations: List<ConversationDto>,
    activeConvId: String?,
    onSelectConv: (String) -> Unit,
    onClose: () -> Unit
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.5f))
            .clickable { onClose() }
    ) {
        Column(
            modifier = Modifier
                .fillMaxHeight()
                .width(280.dp)
                .background(Color(0xFF171721))
                .clickable(enabled = false) {}
                .padding(16.dp)
                .safeContentPadding()
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Discussions",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
                IconButton(onClick = onClose) {
                    Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                }
            }
            Spacer(modifier = Modifier.height(16.dp))

            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(conversations) { conv ->
                    val isActive = conv.id == activeConvId
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = if (isActive) Color(0xFFE2A000) else Color(0xFF232333)
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onSelectConv(conv.id) }
                    ) {
                        Text(
                            text = conv.title,
                            color = if (isActive) Color.Black else Color.White,
                            fontSize = 14.sp,
                            maxLines = 1,
                            modifier = Modifier.padding(12.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun PaywallDialog(onDismiss: () -> Unit, onPaymentSuccess: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = "⚡ Quota de discussion épuisé",
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp,
                color = Color.White
            )
        },
        text = {
            Column {
                Text(
                    text = "Pour continuer à poser des questions techniques en illimité sur le chantier, activez un Pass d'Accès instantané.",
                    color = Color.LightGray,
                    fontSize = 14.sp
                )
                Spacer(modifier = Modifier.height(20.dp))
                
                // Option 1 : Wave (Orange/Bleu)
                Button(
                    onClick = onPaymentSuccess,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1E90FF)),
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Row(
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "Payer par Wave (500 F CFA)",
                            color = Color.White,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
                
                Spacer(modifier = Modifier.height(10.dp))

                // Option 2 : Orange Money
                Button(
                    onClick = onPaymentSuccess,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFF4500)),
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Row(
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            "Orange Money (500 F CFA)",
                            color = Color.White,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("Plus tard", color = Color.Gray)
            }
        },
        containerColor = Color(0xFF1E1E2C)
    )
}
