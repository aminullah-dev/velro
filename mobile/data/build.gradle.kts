plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

android {
    namespace = "af.velro.data"
    compileSdk = 35

    defaultConfig {
        minSdk = 24
        // Migration tests run on a device: MigrationTestHelper needs a real
        // SQLite, and a migration verified against a mock is not verified.
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // The base URL is a build setting, not a constant in code, so a staging
        // build is a flag rather than an edit.
        //
        // 10.0.2.2 is the emulator's alias for the host machine and means
        // nothing on a real handset -- so a debug build installed on a phone
        // could not reach the development API at all, which is most of what a
        // phone is for at this stage. `-Pvelro.apiHost=<lan-ip>` points it at
        // the machine running scripts/dev-api.sh instead. The default stays
        // the emulator, because that is the common case.
        // Two ways to say where the backend is, because there are two kinds
        // of answer. `velro.apiHost` is the development shorthand -- a bare
        // address that means "http, port 8000", which is what dev-api.sh
        // serves. `velro.apiUrl` is the whole truth and is used verbatim,
        // which production needs: https, no port, and a path.
        //
        // Deriving one from the other was tried and is wrong: a release
        // pointed at api.velro.linumic.com would have been built as
        // http://api.velro.linumic.com:8000/, which is neither the scheme
        // nor the port a real deployment answers on -- an APK that cannot
        // reach its own backend, discovered by whoever installed it.
        val apiHost = (project.findProperty("velro.apiHost") as String?) ?: "10.0.2.2"
        val apiUrl = (project.findProperty("velro.apiUrl") as String?)
            ?: "http://$apiHost:8000/api/v1/"
        require(apiUrl.endsWith("/api/v1/")) {
            "velro.apiUrl must end in /api/v1/ -- Retrofit resolves every " +
                "endpoint against it as a directory: $apiUrl"
        }
        buildConfigField("String", "API_BASE_URL", "\"$apiUrl\"")
    }
    buildFeatures { buildConfig = true }

    // Schemas are checked in so a migration can be written against the exact
    // shape that shipped, and so migration tests have something to migrate from.
    ksp { arg("room.schemaLocation", "$projectDir/schemas") }
    sourceSets["androidTest"].assets.srcDir("$projectDir/schemas")
    buildTypes {
        release {
            buildConfigField("String", "API_BASE_URL", "\"https://api.velro.linumic.com/api/v1/\"")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    api(project(":domain"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)

    implementation(libs.retrofit)
    implementation(libs.retrofit.serialization)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)

    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)

    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.hilt.android)
    implementation(libs.hilt.work)
    ksp(libs.hilt.compiler)
    // The second processor is not a duplicate: dagger's compiler ignores
    // @HiltWorker entirely, and a worker without its generated assisted
    // factory dies at instantiation -- silently FAILED in WorkManager's
    // ledger, which is why the sync worker never ran once since it was built.
    ksp(libs.androidx.hilt.compiler)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.androidx.room.testing)
    androidTestImplementation(libs.junit)
    androidTestImplementation(libs.androidx.room.testing)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
}
