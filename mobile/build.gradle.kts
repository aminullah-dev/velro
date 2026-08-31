plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.hilt) apply false
    // Declared here, like every other AGP plugin, so the version is resolved
    // once for the whole build. A module that names a version again conflicts
    // with the classpath this establishes.
    alias(libs.plugins.android.test) apply false
    alias(libs.plugins.baselineprofile) apply false
}
