plugins {
    alias(libs.plugins.kotlin.jvm)
}

// Deliberately a kotlin("jvm") module rather than an Android library: there is
// no android.* on the compile classpath at all, so the dependency rule from
// platform-core is enforced by the compiler instead of by review.
kotlin {
    jvmToolchain(17)
}

dependencies {
    testImplementation(libs.junit)
    // Test-only: the shared specification is JSON. `main` keeps no dependency
    // at all, which is the property that makes this module's purity checkable.
    testImplementation(libs.kotlinx.serialization.json)
}
