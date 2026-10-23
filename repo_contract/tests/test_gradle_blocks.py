"""Brace-matched gradle blocks: suffix variants and manifest placeholders."""

from __future__ import annotations

from repo_contract import gradle_blocks as gb

KTS = """
// a { comment } with braces
android {
    namespace = "com.kuhy.demo" /* { block comment } */
    defaultConfig {
        applicationId = "com.kuhy.demo"
        manifestPlaceholders["appLabel"] = "Demo"
        versionName = "${flutter.versionName}"
    }
    flavorDimensions += "store"
    productFlavors {
        create("daily") {
            dimension = "store"
            manifestPlaceholders["appLabel"] =
                "Daily"
        }
        create("sandbox") {
            applicationIdSuffix = ".sandbox"
            manifestPlaceholders["appLabel"] = "Demo SANDBOX"
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
        getByName("debug") {
            applicationIdSuffix = ".debug"
        }
    }
}
"""

GROOVY = """
android {
    defaultConfig {
        manifestPlaceholders = [appLabel: 'Demo', other: "x"]
        applicationIdSuffix ".everything"
    }
    buildTypes {
        debug {
            applicationIdSuffix '.debug'
            manifestPlaceholders.appLabel = "Debug"
        }
        profile {
            manifestPlaceholders.put("appLabel", labelFor("profile"))
        }
    }
    productFlavors {
        beta {
            manifestPlaceholders += mapOf("appLabel" to "Beta")
        }
    }
}
"""


def test_comments_dropped_strings_kept() -> None:
    text = "a = \"// not a comment\" // gone\nb = '/* kept */' /* gone */ c"
    assert gb.strip_comments(text) == "a = \"// not a comment\" \nb = '/* kept */'  c"


def test_escaped_and_triple_quoted_strings() -> None:
    text = 'x = "a\\"{" \ny = """{ "quoted" }""" // c\nz { }'
    paths = [b.path for b in gb.blocks(text)]
    assert ("z",) in paths and len(paths) == 2


def test_block_paths() -> None:
    paths = {b.path for b in gb.blocks(KTS)}
    assert ("android", "productFlavors", "sandbox") in paths
    assert ("android", "buildTypes", "debug") in paths
    assert ("android", "buildTypes", "release") in paths
    assert ("android", "defaultConfig") in paths


def test_braces_inside_strings_ignored() -> None:
    blocks = gb.blocks('a { b = "${x}" }\n')
    assert [b.path for b in blocks] == [("a",), ()]


def test_unbalanced_braces_tolerated() -> None:
    assert [b.path for b in gb.blocks("}\na {\n b {\n")] == [
        ("a", "b"),
        ("a",),
        (),
    ]


def test_unnamed_header() -> None:
    assert gb.blocks("{ }")[0].path == ("?",)


def test_suffixed_variants_kts() -> None:
    assert gb.suffixed_variants(KTS) == ["debug", "sandbox"]


def test_suffixed_variants_groovy_ignores_default_config() -> None:
    assert gb.suffixed_variants(GROOVY) == ["debug"]


def test_placeholders_kts_every_block() -> None:
    assert gb.placeholder_values(KTS, "appLabel") == [
        ("defaultConfig", "Demo"),
        ("productFlavors.daily", "Daily"),
        ("productFlavors.sandbox", "Demo SANDBOX"),
    ]


def test_placeholders_groovy_forms() -> None:
    assert gb.placeholder_values(GROOVY, "appLabel") == [
        ("defaultConfig", "Demo"),
        ("buildTypes.debug", "Debug"),
        ("buildTypes.profile", None),
        ("productFlavors.beta", "Beta"),
    ]


def test_placeholder_templates_and_variables_are_not_literals() -> None:
    text = 'android {\n manifestPlaceholders["l"] = "A$b"\n}\nmanifestPlaceholders["l"] = name\n'
    assert gb.placeholder_values(text, "l") == [("top level", None), ("android", None)]


def test_placeholder_unterminated_string_is_not_literal() -> None:
    assert gb.placeholder_values('manifestPlaceholders["l"] = "abc', "l") == [
        ("top level", None)
    ]


def test_placeholder_absent() -> None:
    assert gb.placeholder_values(KTS, "missing") == []
