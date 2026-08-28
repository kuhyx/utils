"""`go.mod` parsing: the block form, the single-line form, and `// indirect`."""

from __future__ import annotations

from dep_freshness.parsers.golang import parse
from dep_freshness.tests.conftest import write

GO_MOD = """\
module github.com/kuhyx/demo

go 1.25

require (
\tgithub.com/spf13/cobra v1.10.1
\tgithub.com/stretchr/testify v1.11.1 // indirect
)

require golang.org/x/sync v0.18.0

replace example.com/x => ./x
"""


def test_direct_requirements_are_read(tmp_path):
    deps = {d.name: d for d in parse(write(tmp_path, "go.mod", GO_MOD))}
    assert deps["github.com/spf13/cobra"].pinned == "1.10.1"
    assert deps["golang.org/x/sync"].pinned == "0.18.0"


def test_indirect_requirements_are_owned_by_the_module_graph_not_this_repo(tmp_path):
    deps = {d.name: d for d in parse(write(tmp_path, "go.mod", GO_MOD))}
    assert "github.com/stretchr/testify" not in deps


def test_the_go_directive_is_a_toolchain_declaration(tmp_path):
    deps = {d.name: d for d in parse(write(tmp_path, "go.mod", GO_MOD))}
    assert deps["go"].ecosystem == "toolchain"
    assert deps["go"].constraint == "1.25"


def test_replace_directives_are_not_requirements(tmp_path):
    deps = {d.name: d for d in parse(write(tmp_path, "go.mod", GO_MOD))}
    assert "example.com/x" not in deps


def test_an_unreadable_file_yields_nothing(tmp_path):
    assert parse(tmp_path / "missing.mod") == []
