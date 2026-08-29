package af.velro.data.di

import af.velro.data.BuildConfig
import af.velro.data.api.AuthInterceptor
import af.velro.data.api.RefreshRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.TokenRefreshAuthenticator
import af.velro.data.api.TokenStore
import af.velro.data.api.VelroApi
import af.velro.data.db.VelroDatabase
import android.content.Context
import androidx.room.Room
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import java.util.concurrent.TimeUnit
import javax.inject.Singleton
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * The composition root for the data layer.
 *
 * The only place a concrete class meets an interface. Nothing above this
 * constructs a Retrofit service, opens a database, or knows what the base URL
 * is.
 */
@Module
@InstallIn(SingletonComponent::class)
object DataModule {

    @Provides
    @Singleton
    fun json(): Json = Json {
        ignoreUnknownKeys = true      // a new server field must not crash an old app
        explicitNulls = false
        coerceInputValues = true
    }

    @Provides
    @Singleton
    fun tokenStore(@ApplicationContext context: Context): TokenStore = TokenStore(context)

    @Provides
    @Singleton
    fun responseMapper(json: Json): ResponseMapper = ResponseMapper(json)

    @Provides
    @Singleton
    fun okHttp(tokens: TokenStore, json: Json): OkHttpClient {
        // A bare OkHttp used only to refresh, so the authenticator cannot
        // recurse into itself through the main client.
        val refreshClient = OkHttpClient.Builder()
            .callTimeout(20, TimeUnit.SECONDS)
            .build()

        val authenticator = TokenRefreshAuthenticator(tokens, json) { refreshToken, deviceId ->
            val body = json.encodeToString(
                RefreshRequest.serializer(),
                RefreshRequest(refreshToken, deviceId),
            ).toRequestBody("application/json".toMediaType())
            refreshClient.newCall(
                okhttp3.Request.Builder()
                    .url(BuildConfig.API_BASE_URL + "auth/refresh")
                    .post(body)
                    .build()
            ).execute()
        }

        return OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokens))
            .authenticator(authenticator)
            // Generous timeouts: 2G in a valley is slow, not broken, and a
            // premature timeout turns a working request into a retry storm.
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(45, TimeUnit.SECONDS)
            .writeTimeout(45, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .apply {
                if (BuildConfig.DEBUG) {
                    addInterceptor(
                        HttpLoggingInterceptor().apply {
                            // Headers only: a body log would print OTP codes and
                            // booking verification codes.
                            level = HttpLoggingInterceptor.Level.HEADERS
                        }
                    )
                }
            }
            .build()
    }

    @Provides
    @Singleton
    fun api(client: OkHttpClient, json: Json): VelroApi =
        Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(VelroApi::class.java)

    @Provides
    @Singleton
    fun database(@ApplicationContext context: Context): VelroDatabase =
        Room.databaseBuilder(context, VelroDatabase::class.java, VelroDatabase.NAME)
            // No fallbackToDestructiveMigration: wiping a driver's offline
            // queue because a migration was not written is not an acceptable
            // upgrade path.
            .build()
}
