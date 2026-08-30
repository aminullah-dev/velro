import org.gradle.api.tasks.PathSensitivity

plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "af.velro.core.ui"
    compileSdk = 35
    defaultConfig { minSdk = 24 }
    buildFeatures { compose = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
        freeCompilerArgs += "-opt-in=androidx.compose.material3.ExperimentalMaterial3Api"
    }
}

dependencies {
    api(project(":domain"))
    api(project(":core:i18n"))

    implementation(libs.androidx.core.ktx)
    api(platform(libs.androidx.compose.bom))
    api(libs.androidx.compose.ui)
    api(libs.androidx.compose.ui.graphics)
    api(libs.androidx.compose.material3)
    api(libs.androidx.compose.material.icons)
    // BackHandler lives here, and every screen frame needs it.
    api(libs.androidx.activity.compose)
    api(libs.androidx.compose.ui.tooling.preview)
    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
}

// The font test reads res/font and assets at runtime, which Gradle cannot infer
// from the source set -- without this it would be considered up to date after a
// font is swapped, and the guard would pass on a font it never opened.
tasks.withType<Test>().configureEach {
    inputs.dir("src/main/res/font").withPathSensitivity(PathSensitivity.RELATIVE)
    inputs.dir("src/main/assets/licences").withPathSensitivity(PathSensitivity.RELATIVE)
}
