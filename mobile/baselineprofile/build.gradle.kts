plugins {
    alias(libs.plugins.android.test)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.baselineprofile)
}

/**
 * Generates the baseline profiles the two apps ship.
 *
 * Its own module, and a `com.android.test` one, because the generator is an
 * instrumented run against a real installed app rather than a unit test: it
 * launches the app, drives it, records which classes and methods the run
 * touched, and writes them out. Nothing here is compiled into a release.
 */
android {
    namespace = "af.velro.baselineprofile"
    compileSdk = 35

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    // The benchmark variant is what StartupBenchmark runs in; the generator
    // keeps its own. Kept non-minified and non-debuggable, because a
    // debuggable build is not what anyone installs and its timings say nothing.
    buildTypes {
        create("benchmark") {
            isDebuggable = false
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
        }
    }

    defaultConfig {
        // 28 is the floor for the profile tooling. The apps themselves still
        // go back to 24 -- a device below 28 simply gets no profile, which is
        // exactly the behaviour before this module existed.
        minSdk = 28
        targetSdk = 35
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    targetProjectPath = ":app-passenger"
}

// The generator needs a debuggable, non-minified build to read class names
// from, and it must not be the debug variant the developer is running.
baselineProfile {
    useConnectedDevices = true
}

dependencies {
    implementation(libs.androidx.test.junit)
    implementation(libs.androidx.test.uiautomator)
    implementation(libs.androidx.benchmark.macro.junit4)
}
