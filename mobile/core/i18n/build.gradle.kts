plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "af.velro.core.i18n"
    compileSdk = 35

    defaultConfig {
        minSdk = 24   // Android 7. Below this is a vanishing share of the market
                      // and costs more in workarounds than it wins in reach.
        consumerProguardFiles("consumer-rules.pro")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

// The locale files are the backend's. Copying them at build time rather than
// keeping a second copy is what makes "one key set, three surfaces" true rather
// than aspirational -- a key added on the server cannot go missing here.
val syncLocales by tasks.registering(Copy::class) {
    from(rootProject.layout.projectDirectory.dir("../backend/resources/locales")) {
        include("*.json")
    }
    into(layout.buildDirectory.dir("generated/assets/locales"))
}

android.sourceSets.named("main") {
    assets.srcDir(layout.buildDirectory.dir("generated/assets"))
}

tasks.named("preBuild") { dependsOn(syncLocales) }

dependencies {
    implementation(project(":domain"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.serialization.json)
    testImplementation(libs.junit)
}
