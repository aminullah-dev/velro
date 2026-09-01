# VELRO mobile

Two apps, one codebase: `app-passenger` and `app-driver`.

## Opening it in Android Studio

Open the **`mobile` folder**, not the repository root — that is where
`settings.gradle.kts` lives, and Studio needs to see it to know this is one
project with eleven modules.

Studio writes `local.properties` with the path to your SDK the first time it
syncs; that file is git-ignored on purpose, because it is a path on your
machine and nobody else's. Nothing else is needed: the Gradle wrapper pins
the exact Gradle version (`gradle/wrapper/gradle-wrapper.properties`), so
Studio, the terminal and CI all build with the same one.

Run either app from the toolbar's configuration menu. Both point at
`http://10.0.2.2:8000` by default, which is how the Android emulator reaches
a backend running on the same machine. For a real handset on the same wifi,
build from a terminal with your Mac's LAN address:

    ./gradlew :app-passenger:installDebug -Pvelro.apiHost=10.0.0.109

## Signing

**Debug builds** — everything you run from Studio's green ▶ button, and
every `installDebug` — are signed automatically with the debug key Android
generates for your user account (`~/.android/debug.keystore`). It requires
no setup, and it is not a real identity: Google, and anyone else, treats a
debug-signed APK as untrusted. It is fine for testing on your own handsets
and for handing an APK to a tester.

**Release builds** need a key that belongs to VELRO, and only you can create
it — a signing key is a credential, so it is not something to hand to anyone
else, me included:

    keytool -genkeypair -v -keystore ~/velro-release.jks \
      -alias velro -keyalg RSA -keysize 2048 -validity 10000

It asks for a password twice and for a name; the name can be `VELRO`.

Then tell the build where it is. From a terminal, the environment:

    export VELRO_KEYSTORE=~/velro-release.jks
    export VELRO_KEYSTORE_PASSWORD='the password you chose'

For Android Studio, which inherits nothing from your shell, write
`mobile/keystore.properties` (git-ignored):

    storeFile=/Users/you/velro-release.jks
    storePassword=the password you chose
    keyAlias=velro
    keyPassword=the password you chose

With neither, a release build still succeeds and produces
`app-passenger-release-**unsigned**.apk`, which Android refuses to install.
That is deliberate: the alternative is silently shipping something signed
with a debug key that anyone in the world can also produce.

### The one thing that cannot be replaced

Back the `.jks` file up somewhere that is not this laptop, twice. Every
future update to an installed app must be signed with the same key: Android
checks, and refuses an update signed by a different one. Lose it and every
user has to uninstall and lose their local data before they can install
again. The password is equally irreplaceable — there is no reset.

## Tests

    ./gradlew test

125 unit tests across the modules: 101 Android, 24 in `:domain`.
