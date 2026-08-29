# Kotlinx serialization keeps the generated serializers reachable.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class af.velro.** { *** Companion; }
-keepclasseswithmembers class af.velro.** { kotlinx.serialization.KSerializer serializer(...); }
