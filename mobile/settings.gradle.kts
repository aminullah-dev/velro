pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "velro"

// :domain is a plain Kotlin module, not an Android library. That single choice
// makes the dependency rule impossible to violate by accident -- the compiler
// rejects an android.* import there.
include(":domain")
include(":data")
include(":core:ui")
include(":core:i18n")
include(":feature:auth")
include(":feature:booking")
include(":feature:trip")
include(":feature:driver")
include(":app-passenger")
include(":app-driver")
