plugins {
    java
    id("com.gradleup.shadow") version "8.3.6"
    id("xyz.jpenilla.run-paper") version "3.0.2"
}

group = "dev.flycraft"
version = "0.1.0"

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
}

dependencies {
    compileOnly("io.papermc.paper:paper-api:1.21.11-R0.1-SNAPSHOT")
    implementation("com.google.code.gson:gson:2.11.0")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("io.papermc.paper:paper-api:1.21.11-R0.1-SNAPSHOT")
    testImplementation("org.junit.jupiter:junit-jupiter")
}

java {
    toolchain.languageVersion = JavaLanguageVersion.of(21)
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release = 21
}

tasks.processResources {
    filesMatching("plugin.yml") {
        expand("version" to project.version)
    }
}

tasks.test {
    useJUnitPlatform()
}

tasks.shadowJar {
    archiveClassifier = ""
    relocate("com.google.gson", "dev.flycraft.plugin.lib.gson")
}

tasks.runServer {
    minecraftVersion("1.21.11")
}

tasks.build {
    dependsOn(tasks.shadowJar)
}
