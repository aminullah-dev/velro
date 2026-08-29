plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

android {
    namespace = "af.velro.driver"
    compileSdk = 35

    defaultConfig {
        applicationId = "af.velro.driver"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        // RTL is the default here, not an afterthought: Dari is the primary
        // language and English is the exception.
        resourceConfigurations += listOf("en", "fa", "ps")
    }

    buildFeatures { compose = true }

    buildTypes {
        debug { applicationIdSuffix = ".debug" }
        release {
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
    implementation(project(":feature:driver"))

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
}
