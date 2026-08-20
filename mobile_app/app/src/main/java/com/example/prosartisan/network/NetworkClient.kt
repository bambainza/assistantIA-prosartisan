package com.example.prosartisan.network

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

@Serializable
data class LoginResponse(
    val access_token: String,
    val refresh_token: String,
    val user: UserDto
)

@Serializable
data class UserDto(
    val id: String,
    val email: String,
    val nom: String,
    val type_abonnement: String
)

@Serializable
data class ConversationDto(
    val id: String,
    val title: String,
    val created_at: String,
    val updated_at: String
)

@Serializable
data class MessageDto(
    val id: String,
    val role: String,
    val content: String,
    val created_at: String
)

@Serializable
data class ConversationDetailDto(
    val id: String,
    val title: String,
    val messages: List<MessageDto> = emptyList()
)

@Serializable
data class QuotaInfoDto(
    val statut: String,
    val restantes: Int
)

@Serializable
data class ChatResponseDto(
    val reponse: String,
    val conversation_id: String,
    val quota_info: QuotaInfoDto,
    val sources: List<String> = emptyList()
)

class NetworkClient(private val context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("prosartisan_prefs", Context.MODE_PRIVATE)
    
    var baseUrl: String
        get() = prefs.getString("base_url", "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000"
        set(value) {
            prefs.edit().putString("base_url", value).apply()
        }

    var token: String?
        get() = prefs.getString("jwt_token", null)
        set(value) {
            prefs.edit().putString("jwt_token", value).apply()
        }

    var userEmail: String?
        get() = prefs.getString("user_email", null)
        set(value) {
            prefs.edit().putString("user_email", value).apply()
        }

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    private val json = Json { ignoreUnknownKeys = true }
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    fun logout() {
        token = null
        userEmail = null
    }

    suspend fun login(email: String, password: String): Result<LoginResponse> = kotlinx.coroutines.withContext(Dispatchers.IO) {
        try {
            val bodyJson = json.encodeToString(mapOf("email" to email, "password" to password))
            val request = Request.Builder()
                .url("$baseUrl/api/auth/login")
                .post(bodyJson.toRequestBody(jsonMediaType))
                .build()

            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    val bodyString = response.body?.string() ?: throw Exception("Empty body")
                    val loginRes = json.decodeFromString<LoginResponse>(bodyString)
                    token = loginRes.access_token
                    userEmail = loginRes.user.email
                    Result.success(loginRes)
                } else {
                    Result.failure(Exception("Login failed: ${response.code} ${response.message}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun register(email: String, password: String, nom: String, telephone: String): Result<UserDto> = kotlinx.coroutines.withContext(Dispatchers.IO) {
        try {
            val bodyJson = json.encodeToString(mapOf(
                "email" to email,
                "password" to password,
                "nom" to nom,
                "telephone" to telephone
            ))
            val request = Request.Builder()
                .url("$baseUrl/api/auth/register")
                .post(bodyJson.toRequestBody(jsonMediaType))
                .build()

            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    val bodyString = response.body?.string() ?: throw Exception("Empty body")
                    val user = json.decodeFromString<UserDto>(bodyString)
                    Result.success(user)
                } else {
                    Result.failure(Exception("Registration failed: ${response.code} ${response.message}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getConversations(query: String? = null): Result<List<ConversationDto>> = kotlinx.coroutines.withContext(Dispatchers.IO) {
        try {
            val url = if (query != null) "$baseUrl/api/conversations?q=$query" else "$baseUrl/api/conversations"
            val request = Request.Builder()
                .url(url)
                .get()
                .addHeader("Authorization", "Bearer ${token ?: ""}")
                .build()

            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    val bodyString = response.body?.string() ?: throw Exception("Empty body")
                    val conversations = json.decodeFromString<List<ConversationDto>>(bodyString)
                    Result.success(conversations)
                } else {
                    Result.failure(Exception("Failed to fetch conversations: ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getConversationDetail(convId: String): Result<ConversationDetailDto> = kotlinx.coroutines.withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("$baseUrl/api/conversations/$convId")
                .get()
                .addHeader("Authorization", "Bearer ${token ?: ""}")
                .build()

            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    val bodyString = response.body?.string() ?: throw Exception("Empty body")
                    val conversation = json.decodeFromString<ConversationDetailDto>(bodyString)
                    Result.success(conversation)
                } else {
                    Result.failure(Exception("Failed to fetch conversation: ${response.code}"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun sendMessageStream(
        question: String,
        conversationId: String?,
        metierId: Int?
    ): Flow<StreamEvent> = flow {
        val payload = mutableMapOf<String, Any?>("question" to question)
        if (conversationId != null) payload["conversation_id"] = conversationId
        if (metierId != null) payload["metier_id"] = metierId

        val bodyJson = json.encodeToString(payload)
        val request = Request.Builder()
            .url("$baseUrl/api/chat/stream")
            .post(bodyJson.toRequestBody(jsonMediaType))
            .addHeader("Accept", "text/event-stream")
            .addHeader("Authorization", "Bearer ${token ?: ""}")
            .build()

        try {
            val response = client.newCall(request).execute()
            if (response.code == 402) {
                emit(StreamEvent.QuotaExceeded)
                return@flow
            }
            if (!response.isSuccessful) {
                emit(StreamEvent.Error("HTTP error: ${response.code}"))
                return@flow
            }

            val byteStream = response.body?.byteStream() ?: throw Exception("Empty stream body")
            val reader = BufferedReader(InputStreamReader(byteStream))
            var line: String?
            var currentEvent = ""

            while (reader.readLine().also { line = it } != null) {
                val l = line?.trim() ?: continue
                if (l.isEmpty()) continue

                if (l.startsWith("event:")) {
                    currentEvent = l.substring("event:".length).trim()
                } else if (l.startsWith("data:")) {
                    val dataContent = l.substring("data:".length).trim()
                    when (currentEvent) {
                        "info" -> {
                            try {
                                val info = json.decodeFromString<StreamInfo>(dataContent)
                                emit(StreamEvent.Info(info.conversation_id, info.sources))
                            } catch (e: Exception) {
                                // Ignore malformed info
                            }
                        }
                        "chunk" -> {
                            try {
                                val chunk = json.decodeFromString<String>(dataContent)
                                emit(StreamEvent.Chunk(chunk))
                            } catch (e: Exception) {
                                // Ignore malformed chunk
                            }
                        }
                        "end" -> {
                            emit(StreamEvent.End)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            emit(StreamEvent.Error(e.message ?: "Unknown streaming error"))
        }
    }.flowOn(Dispatchers.IO)
}

@Serializable
data class StreamInfo(
    val conversation_id: String,
    val sources: List<String> = emptyList()
)

sealed class StreamEvent {
    data class Info(val conversationId: String, val sources: List<String>) : StreamEvent()
    data class Chunk(val chunk: String) : StreamEvent()
    object End : StreamEvent()
    object QuotaExceeded : StreamEvent()
    data class Error(val message: String) : StreamEvent()
}
