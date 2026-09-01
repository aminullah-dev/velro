import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
    alias(libs.plugins.baselineprofile)
}

android {
    namespace = "af.velro.passenger"
    compileSdk = 35

    defaultConfig {
        applicationId = "af.velro.passenger"
        minSdk = 24
        targetSdk = 35
        // From gradle.properties, so the two apps cannot drift apart.
        versionCode = (project.findProperty("velro.versionCode") as String).toInt()
        versionName = project.findProperty("velro.versionName") as String
        // RTL is the default here, not an afterthought: Dari is the primary
        // language and English is the exception.
        resourceConfigurations += listOf("en", "fa", "ps")
    }

    buildFeatures { compose = true }

    // Never from a file in the repository: a keystore or its password
    // committed here would be one `git push` away from letting anyone ship an
    // update that Android accepts as VELRO. Absent, the release build is
    // simply unsigned and says so, rather than silently signing with the
    // debug key -- and an unsigned release APK cannot be installed at all.
    //
    // Two ways in, because there are two ways to build. The environment is
    // what a terminal and a CI runner have; keystore.properties is what
    // Android Studio can use, since a GUI launched from the Dock inherits
    // none of a shell's exported variables. The file lives beside this build
    // script, is git-ignored, and is read only for its path and password.
    val secrets = rootProject.file("keystore.properties").takeIf { it.isFile }?.let {
        Properties().apply { it.inputStream().use(::load) }
    }
    fun secret(env: String, key: String): String? =
        System.getenv(env) ?: secrets?.getProperty(key)

    val keystorePath: String? = secret("VELRO_KEYSTORE", "storeFile")
    val keystorePassword: String? = secret("VELRO_KEYSTORE_PASSWORD", "storePassword")

    signingConfigs {
        if (keystorePath != null && keystorePassword != null) {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = keystorePassword
                keyAlias = secret("VELRO_KEY_ALIAS", "keyAlias") ?: "velro"
                keyPassword = secret("VELRO_KEY_PASSWORD", "keyPassword") ?: keystorePassword
            }
        }
    }

    buildTypes {
        debug { applicationIdSuffix = ".debug" }
        release {
            signingConfig = signingConfigs.findByName("release")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
        // ModalBottomSheet is still marked experimental in Material3. Declared
        // once per module rather than annotated at every call site, which
        // otherwise walks all the way up to MainActivity and makes the opt-in
        // look like a property of the screen rather than of the library.
        freeCompilerArgs += "-opt-in=androidx.compose.material3.ExperimentalMaterial3Api"
    }
}

dependencies {
    implementation(project(":domain"))
    implementation(project(":data"))
    implementation(project(":core:ui"))
    implementation(project(":core:i18n"))
    implementation(project(":feature:auth"))
    implementation(project(":feature:booking"))
    implementation(project(":feature:trip"))
    implementation(project(":feature:safety"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.hilt.android)
    implementation(libs.hilt.navigation.compose)
    implementation(libs.hilt.work)
    ksp(libs.hilt.compiler)

    testImplementation(libs.junit)

    // Without this the profile ships in the APK and nothing reads it. It is
    // the piece that installs the compiled trace on devices where Play did not
    // already do it -- which is most of them here, since sideloaded and
    // third-party-store installs are common in this market.
    implementation(libs.androidx.profileinstaller)

    // The generator that records this app's profile.
    //
    // A profile is per-APK: it is a list of methods baked into this artifact,
    // not something shared between the two apps even though they share most of
    // their code. The driver app therefore needs its own generator module
    // pointed at it -- see :baselineprofile-driver.
    baselineProfile(project(":baselineprofile"))
}
