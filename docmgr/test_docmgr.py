"""Pytest unit tests for the docmgr DocumentStore.

Tests the store directly (no MCP server involved) against a fabricated
temporary directory of synthesized documents, covering happy and unhappy
paths for each stage of the development plan: read-only tools, edit,
create, delete, and --allow-all.

Run:  .venv/bin/pytest test_docmgr.py
"""

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path, PureWindowsPath

import pytest

# The script is an extensionless executable, so load it explicitly as a module
# (spec_from_file_location wants a str path and an explicit loader without .py).
_MODULE_PATH = str(Path(__file__).resolve().parent / "docmgr")
_spec = importlib.util.spec_from_file_location(
    "docmgr_under_test", _MODULE_PATH,
    loader=SourceFileLoader("docmgr_under_test", _MODULE_PATH),
)
docmgr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(docmgr)

DocumentStore = docmgr.DocumentStore
DocumentError = docmgr.DocumentError

HELLO = "Hello, world!\nMy fluffy bunny likes carrots.\n"  # 45 chars
IDEAS = "Project ideas: a fluffy bunny app.\n"  # 33 chars


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    """Fabricate a small document tree, including the edge cases."""
    (docs := tmp_path / "docs").mkdir()
    (docs / "hello.txt").write_text(HELLO, encoding="utf-8")
    (docs / "notes").mkdir()
    (docs / "notes" / "ideas.txt").write_text(IDEAS, encoding="utf-8")
    (docs / ".hidden.txt").write_text("hidden but served\n", encoding="utf-8")
    (docs / "unicode.txt").write_text("café au lait\n", encoding="utf-8")  # 13 chars, 14 bytes
    (docs / "empty.txt").write_text("", encoding="utf-8")
    (docs / "binary.bin").write_bytes(b"\x00\xff\xfe not utf-8 \x00")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret data\n", encoding="utf-8")
    (docs / "escape.txt").symlink_to(outside / "secret.txt")
    return docs


def make_store(docs_dir: Path, edit: bool = False, create: bool = False, delete: bool = False) -> DocumentStore:
    return DocumentStore(docs_dir, edit, create, delete)


# -- path safety (applies to every stage) -------------------------------------


class TestPathSafety:
    def test_resolve_withAbsolutePath_raisesDocumentError(self, docs_dir):
        # GIVEN a store,
        # WHEN resolving an absolute path,
        # THEN a DocumentError is raised mentioning relativity:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="relative"):
            store.resolve("/etc/passwd")

    def test_resolve_withDotDotSegment_raisesDocumentError(self, docs_dir):
        # GIVEN a store,
        # WHEN resolving a path containing '..',
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match=r"\.\."):
            store.resolve("notes/../hello.txt")

    def test_resolve_withEmptyRelPath_raisesDocumentError(self, docs_dir):
        # GIVEN a store,
        # WHEN resolving an empty rel_path,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="empty"):
            store.resolve("")

    def test_resolve_withSymlinkEscapingRoot_raisesDocumentError(self, docs_dir):
        # GIVEN a symlink inside the served dir pointing outside it,
        # WHEN resolving that symlink,
        # THEN containment is rejected:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="outside the served directory"):
            store.resolve("escape.txt")


# -- path safety: Windows path flavours -----------------------------------------
#
# No Windows machine is available in CI, so these tests swap the module's
# PurePath for PureWindowsPath. pathlib's Windows flavour parses strings
# identically on every host, so this faithfully simulates Windows
# validation (issue #3: "Windows Paths not supported").


class TestPathSafetyWindowsPaths:
    @pytest.fixture
    def windows_flavour(self, monkeypatch):
        """Make the store validate rel_paths with Windows path semantics."""
        monkeypatch.setattr(docmgr, "PurePath", PureWindowsPath)

    def test_resolve_withWindowsDriveAbsolutePath_raisesDocumentError(self, docs_dir, windows_flavour):
        # GIVEN Windows path parsing is simulated,
        # WHEN resolving a drive-absolute path,
        # THEN it is rejected by the early 'must be relative' check:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="relative"):
            store.resolve(r"C:\Users\paul\docs\file.txt")

    def test_resolve_withWindowsForwardSlashDriveAbsolutePath_raisesDocumentError(self, docs_dir, windows_flavour):
        # GIVEN Windows path parsing is simulated,
        # WHEN resolving a drive-absolute path using forward slashes,
        # THEN it is rejected by the early 'must be relative' check:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="relative"):
            store.resolve("C:/Users/paul/docs/file.txt")

    def test_resolve_withWindowsUncAbsolutePath_raisesDocumentError(self, docs_dir, windows_flavour):
        # GIVEN Windows path parsing is simulated,
        # WHEN resolving a UNC path,
        # THEN it is rejected by the early 'must be relative' check:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="relative"):
            store.resolve(r"\\server\share\file.txt")

    def test_resolve_withWindowsBackslashDotDot_raisesDocumentError(self, docs_dir, windows_flavour):
        # GIVEN Windows path parsing is simulated,
        # WHEN resolving a backslash-separated '..' escape,
        # THEN it is rejected by the early 'must not contain ..' check:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match=r"\.\."):
            store.resolve(r"..\..\outside\secret.txt")

    def test_resolve_withWindowsBackslashRelativePath_passesEarlyValidation(self, docs_dir, windows_flavour):
        # GIVEN Windows path parsing is simulated and a document at docs/hello.txt,
        # WHEN resolving the backslash form of a relative path,
        # THEN early validation does not reject it (on real Windows the OS
        # treats the backslash as a separator, so this finds the document):
        store = make_store(docs_dir)
        candidate = store.resolve(r"docs\hello.txt")
        assert candidate.is_absolute()

    def test_glob_withWindowsDriveAbsolutePattern_raisesDocumentError(self, docs_dir, windows_flavour):
        # GIVEN Windows path parsing is simulated,
        # WHEN globbing a drive-absolute pattern,
        # THEN it is rejected by the early 'must be relative' check:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="relative"):
            store.glob(r"C:\*")

    def test_glob_withWindowsBackslashDotDotPattern_raisesDocumentError(self, docs_dir, windows_flavour):
        # GIVEN Windows path parsing is simulated,
        # WHEN globbing a backslash-separated '..' pattern,
        # THEN it is rejected by the early 'must not contain ..' check:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match=r"\.\."):
            store.glob(r"..\..\*.txt")


# -- stage 2: read-only tools --------------------------------------------------


class TestSearchDocuments:
    def test_search_documents_withPlainQuery_returnsOneHitPerDocument_sortedByRelPath(self, docs_dir):
        # GIVEN two documents containing "fluffy bunny",
        # WHEN searching for it,
        # THEN both are reported, at most once each, sorted by rel_path:
        store = make_store(docs_dir)
        hits = store.search("fluffy bunny", max_results=20, case_sensitive=False)
        assert [h["rel_path"] for h in hits] == ["hello.txt", "notes/ideas.txt"]

    def test_search_documents_withPlainQuery_reportsOffsetAndSnippet(self, docs_dir):
        # GIVEN hello.txt containing "fluffy bunny" at a known offset,
        # WHEN searching for it,
        # THEN the hit's offset is the match start and the snippet brackets it
        # by up to 50 chars each side (snapped to the document start here):
        store = make_store(docs_dir)
        offset = HELLO.find("fluffy bunny")
        (hit,) = [h for h in store.search("fluffy bunny", 20, False) if h["rel_path"] == "hello.txt"]
        assert hit["offset"] == offset
        assert hit["snippet_offset"] == max(0, offset - 50)
        assert hit["snippet"] == HELLO[max(0, offset - 50):offset + len("fluffy bunny") + 50]
        assert "fluffy bunny" in hit["snippet"]

    def test_search_documents_isCaseInsensitiveByDefault(self, docs_dir):
        # GIVEN lowercase document content,
        # WHEN searching with an uppercase query and case_sensitive=False,
        # THEN the match is found:
        store = make_store(docs_dir)
        assert len(store.search("FLUFFY BUNNY", 20, False)) == 2

    def test_search_documents_withCaseSensitiveTrue_andDifferentCase_returnsEmptyList(self, docs_dir):
        # GIVEN lowercase document content,
        # WHEN searching with an uppercase query and case_sensitive=True,
        # THEN no hits are found:
        store = make_store(docs_dir)
        assert store.search("FLUFFY BUNNY", 20, True) == []

    def test_search_documents_withNoHits_returnsEmptyList(self, docs_dir):
        # GIVEN documents that lack the query,
        # WHEN searching,
        # THEN an empty list is returned:
        store = make_store(docs_dir)
        assert store.search("zzz-no-such-term", 20, False) == []

    def test_search_documents_withMaxResultsOne_capsResultsToOne(self, docs_dir):
        # GIVEN two matching documents,
        # WHEN searching with max_results=1,
        # THEN only one hit is returned:
        store = make_store(docs_dir)
        assert len(store.search("fluffy", 1, False)) == 1

    def test_search_documents_withEmptyQuery_raisesDocumentError(self, docs_dir):
        # WHEN searching with an empty query,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="query"):
            store.search("", 20, False)

    def test_search_documents_withNonUTF8File_skipsIt(self, docs_dir):
        # GIVEN a non-UTF-8 file,
        # WHEN searching for a term it "contains" as bytes,
        # THEN it is invisible to search:
        store = make_store(docs_dir)
        assert all(h["rel_path"] != "binary.bin" for h in store.search("not utf-8", 20, False))

    def test_search_documents_withMatchAtDocumentStart_reportsEqualOffsets(self, docs_dir):
        # GIVEN a query matching at offset 0 of hello.txt,
        # WHEN searching,
        # THEN offset == snippet_offset == 0:
        store = make_store(docs_dir)
        (hit,) = [h for h in store.search("Hello", 20, False) if h["rel_path"] == "hello.txt"]
        assert hit["offset"] == 0
        assert hit["snippet_offset"] == 0


class TestListAndGlob:
    def test_list_all_documents_returnsSortedRelPaths_includesHidden_excludesNonUTF8AndEscapingSymlink(self, docs_dir):
        # GIVEN a tree with a hidden file, a non-UTF-8 file, and an escaping symlink,
        # WHEN listing all documents,
        # THEN only served documents are returned, sorted by rel_path:
        store = make_store(docs_dir)
        assert store.list_all() == [".hidden.txt", "empty.txt", "hello.txt", "notes/ideas.txt", "unicode.txt"]

    def test_glob_withTopLevelPattern_returnsOnlyTopLevelMatches_sorted(self, docs_dir):
        # WHEN globbing "*.txt",
        # THEN only top-level .txt documents match:
        store = make_store(docs_dir)
        assert store.glob("*.txt") == [".hidden.txt", "empty.txt", "hello.txt", "unicode.txt"]

    def test_glob_withRecursivePattern_findsNestedDocuments(self, docs_dir):
        # WHEN globbing "**/ideas.txt",
        # THEN the nested document matches:
        store = make_store(docs_dir)
        assert store.glob("**/ideas.txt") == ["notes/ideas.txt"]

    def test_glob_withNoMatches_returnsEmptyList(self, docs_dir):
        # WHEN globbing a pattern that matches nothing,
        # THEN an empty list is returned:
        store = make_store(docs_dir)
        assert store.glob("*.nope") == []

    def test_glob_withAbsolutePattern_raisesDocumentError(self, docs_dir):
        # WHEN globbing an absolute pattern,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="relative"):
            store.glob("/etc/*.conf")

    def test_glob_withDotDotPattern_raisesDocumentError(self, docs_dir):
        # WHEN globbing a pattern containing '..',
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match=r"\.\."):
            store.glob("notes/../hello.txt")


class TestGetDocument:
    def test_get_document_withValidRelPath_returnsFullContent(self, docs_dir):
        # WHEN reading hello.txt,
        # THEN its exact content is returned:
        store = make_store(docs_dir)
        assert store.get("hello.txt") == HELLO

    def test_get_document_withMissingFile_raisesDocumentError(self, docs_dir):
        # WHEN reading a nonexistent document,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="no such document"):
            store.get("nope.txt")

    def test_get_document_withDirectory_raisesDocumentError(self, docs_dir):
        # WHEN reading a directory,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="no such document"):
            store.get("notes")

    def test_get_document_withNonUTF8File_raisesDocumentError(self, docs_dir):
        # WHEN reading a non-UTF-8 file,
        # THEN a DocumentError identifying it as not valid UTF-8 is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="not a valid UTF-8"):
            store.get("binary.bin")

    def test_get_document_withEscapingSymlink_raisesDocumentError(self, docs_dir):
        # WHEN reading a symlink that escapes the served directory,
        # THEN containment is rejected:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="outside the served directory"):
            store.get("escape.txt")


class TestGetDocumentLength:
    def test_get_document_length_countsCharactersNotBytes(self, docs_dir):
        # GIVEN unicode.txt, which is 13 characters but 14 bytes,
        # WHEN reporting its length,
        # THEN the character count is returned:
        store = make_store(docs_dir)
        assert store.length("unicode.txt") == 13
        assert (docs_dir / "unicode.txt").stat().st_size == 14

    def test_get_document_length_withMissingFile_raisesDocumentError(self, docs_dir):
        # WHEN reporting the length of a missing document,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="no such document"):
            store.length("nope.txt")


class TestGetDocumentPartial:
    def test_get_document_partial_withValidRange_returnsExactSlice(self, docs_dir):
        # WHEN reading 5 chars from offset 0 of hello.txt,
        # THEN that exact slice is returned:
        store = make_store(docs_dir)
        assert store.partial("hello.txt", 0, 5) == "Hello"

    def test_get_document_partial_withOffsetAtEndAndLengthZero_returnsEmptyString(self, docs_dir):
        # GIVEN a document of length 45,
        # WHEN reading at offset 45 with length 0,
        # THEN the empty string is returned:
        store = make_store(docs_dir)
        assert store.partial("hello.txt", 45, 0) == ""

    def test_get_document_partial_withNegativeOffset_raisesDocumentError(self, docs_dir):
        # WHEN reading with offset -1,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="out of range"):
            store.partial("hello.txt", -1, 5)

    def test_get_document_partial_withOffsetBeyondLength_raisesDocumentError(self, docs_dir):
        # WHEN reading with offset 46 on a 45-char document,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="out of range"):
            store.partial("hello.txt", 46, 5)

    def test_get_document_partial_withLengthExceedingRemaining_raisesDocumentError(self, docs_dir):
        # WHEN reading more characters than remain,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="exceeds document length"):
            store.partial("hello.txt", 0, 46)

    def test_get_document_partial_withNegativeLength_raisesDocumentError(self, docs_dir):
        # WHEN reading with length -1,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="length must be >= 0"):
            store.partial("hello.txt", 0, -1)


# -- stage 3: edit ---------------------------------------------------------------


class TestEditDocument:
    def test_edit_document_withMatchAtOffset_replacesExactlyOneOccurrence(self, docs_dir):
        # GIVEN hello.txt containing "carrots" at a known offset,
        # WHEN replacing "carrots" with "peas" at that offset,
        # THEN the file contains the replacement and the rest is untouched:
        store = make_store(docs_dir, edit=True)
        offset = HELLO.find("carrots")
        store.edit("hello.txt", "carrots", "peas", offset)
        expected = HELLO[:offset] + "peas" + HELLO[offset + len("carrots"):]
        assert (docs_dir / "hello.txt").read_text(encoding="utf-8") == expected

    def test_edit_document_withEmptyToReplace_insertsAtOffset(self, docs_dir):
        # GIVEN an empty document,
        # WHEN editing with an empty to_replace at offset 0,
        # THEN replace_with is inserted:
        store = make_store(docs_dir, edit=True)
        store.edit("empty.txt", "", "fresh", 0)
        assert (docs_dir / "empty.txt").read_text(encoding="utf-8") == "fresh"

    def test_edit_document_withOffsetAtLengthAndEmptyToReplace_appendsToEnd(self, docs_dir):
        # GIVEN an empty document,
        # WHEN inserting at offset == document length,
        # THEN the text is appended:
        store = make_store(docs_dir, edit=True)
        store.edit("empty.txt", "", "a", 0)
        store.edit("empty.txt", "", "b", store.length("empty.txt"))
        assert (docs_dir / "empty.txt").read_text(encoding="utf-8") == "ab"

    def test_edit_document_withTextNotAtGivenOffset_raisesDocumentError(self, docs_dir):
        # GIVEN "peas" starting at offset 8 in hello.txt (after an edit),
        # WHEN editing with a shifted offset,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir, edit=True)
        offset = HELLO.find("carrots")
        store.edit("hello.txt", "carrots", "peas", offset)
        with pytest.raises(DocumentError, match="does not contain"):
            store.edit("hello.txt", "peas", "carrots", offset + 1)

    def test_edit_document_withOffsetBeyondLength_raisesDocumentError(self, docs_dir):
        # WHEN editing with offset beyond the document length,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir, edit=True)
        with pytest.raises(DocumentError, match="out of range"):
            store.edit("hello.txt", "x", "y", len(HELLO) + 1)

    def test_edit_document_withMissingFile_raisesDocumentError(self, docs_dir):
        # WHEN editing a missing document,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir, edit=True)
        with pytest.raises(DocumentError, match="no such document"):
            store.edit("nope.txt", "x", "y", 0)

    def test_edit_document_whenEditDisabled_raisesDocumentError(self, docs_dir):
        # GIVEN a read-only store,
        # WHEN calling edit,
        # THEN a DocumentError naming the missing flag is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="--allow-edit"):
            store.edit("hello.txt", "x", "y", 0)


# -- stage 4: create ---------------------------------------------------------------


class TestCreateDocument:
    def test_create_document_withNewNestedPath_createsParentsAndFile(self, docs_dir):
        # WHEN creating a document under a nonexistent nested directory,
        # THEN the parents are created and the file contains the text:
        store = make_store(docs_dir, create=True)
        store.create("new/dir/file.txt", "hello create")
        assert (docs_dir / "new/dir/file.txt").read_text(encoding="utf-8") == "hello create"

    def test_create_document_withExistingPath_raisesDocumentError(self, docs_dir):
        # GIVEN an existing document,
        # WHEN creating at the same path,
        # THEN a DocumentError is raised and the original content is intact:
        store = make_store(docs_dir, create=True)
        with pytest.raises(DocumentError, match="already exists"):
            store.create("hello.txt", "overwrite attempt")
        assert (docs_dir / "hello.txt").read_text(encoding="utf-8") == HELLO

    def test_create_document_withExistingDirectoryPath_raisesDocumentError(self, docs_dir):
        # GIVEN an existing directory,
        # WHEN creating at that path,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir, create=True)
        with pytest.raises(DocumentError, match="already exists"):
            store.create("notes", "not a file")

    def test_create_document_whenCreateDisabled_raisesDocumentError(self, docs_dir):
        # GIVEN a read-only store,
        # WHEN calling create,
        # THEN a DocumentError naming the missing flag is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="--allow-create"):
            store.create("nope.txt", "x")

    def test_create_document_withEscapingSymlinkPath_raisesDocumentError(self, docs_dir):
        # GIVEN a symlink escaping the served directory,
        # WHEN creating at that path,
        # THEN containment is rejected:
        store = make_store(docs_dir, create=True)
        with pytest.raises(DocumentError, match="outside the served directory"):
            store.create("escape.txt", "x")


# -- stage 5: delete ---------------------------------------------------------------


class TestDeleteDocument:
    def test_delete_document_withExistingFile_removesFileButKeepsDirectory(self, docs_dir):
        # GIVEN a document inside a directory,
        # WHEN deleting it,
        # THEN the file is gone and the directory remains:
        store = make_store(docs_dir, delete=True)
        store.delete("notes/ideas.txt")
        assert not (docs_dir / "notes/ideas.txt").exists()
        assert (docs_dir / "notes").is_dir()

    def test_delete_document_withMissingFile_raisesDocumentError(self, docs_dir):
        # WHEN deleting a missing document,
        # THEN a DocumentError is raised:
        store = make_store(docs_dir, delete=True)
        with pytest.raises(DocumentError, match="no such document"):
            store.delete("nope.txt")

    def test_delete_document_withDirectory_raisesDocumentError(self, docs_dir):
        # WHEN deleting a directory,
        # THEN a DocumentError is raised and the directory survives:
        store = make_store(docs_dir, delete=True)
        with pytest.raises(DocumentError, match="no such document"):
            store.delete("notes")
        assert (docs_dir / "notes").is_dir()

    def test_delete_document_whenDeleteDisabled_raisesDocumentError(self, docs_dir):
        # GIVEN a read-only store,
        # WHEN calling delete,
        # THEN a DocumentError naming the missing flag is raised:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="--allow-delete"):
            store.delete("hello.txt")


# -- stage 6: --allow-all -----------------------------------------------------------


class TestAllowAll:
    def test_allowAll_store_enablesEditCreateAndDelete(self, docs_dir):
        # GIVEN a store constructed with all permissions,
        # WHEN exercising each write tool,
        # THEN all three succeed:
        store = make_store(docs_dir, edit=True, create=True, delete=True)
        store.create("allow_all.txt", "created")
        store.edit("allow_all.txt", "created", "edited", 0)
        assert (docs_dir / "allow_all.txt").read_text(encoding="utf-8") == "edited"
        store.delete("allow_all.txt")
        assert not (docs_dir / "allow_all.txt").exists()

    def test_readOnly_store_refusesAllWriteTools(self, docs_dir):
        # GIVEN a read-only store,
        # WHEN calling edit, create, and delete,
        # THEN each is refused with the appropriate flag named:
        store = make_store(docs_dir)
        with pytest.raises(DocumentError, match="--allow-edit"):
            store.edit("hello.txt", "x", "y", 0)
        with pytest.raises(DocumentError, match="--allow-create"):
            store.create("nope.txt", "x")
        with pytest.raises(DocumentError, match="--allow-delete"):
            store.delete("hello.txt")


# -- server instructions: capability advertisement ----------------------------


class TestDescribeCapabilities:
    def test_describe_capabilities_withReadOnly_store_reportsAllWriteToolsDisabledWithFlags(self, docs_dir):
        # GIVEN a read-only store,
        # WHEN describing its capabilities,
        # THEN all three write tools are reported disabled, each with its enabling flag:
        text = docmgr.describe_capabilities(make_store(docs_dir))
        assert text.count("disabled") == 3
        for flag in ("--allow-edit", "--allow-create", "--allow-delete"):
            assert flag in text
        assert str(docs_dir.resolve()) in text

    def test_describe_capabilities_withAllowAll_store_reportsAllWriteToolsEnabled(self, docs_dir):
        # GIVEN a fully-permitted store,
        # WHEN describing its capabilities,
        # THEN all three write tools are reported enabled and no flag is mentioned:
        text = docmgr.describe_capabilities(make_store(docs_dir, edit=True, create=True, delete=True))
        assert text.count("enabled") == 3
        for flag in ("--allow-edit", "--allow-create", "--allow-delete"):
            assert flag not in text

    def test_describe_capabilities_withOnlyEditEnabled_reportsOnlyCreateAndDeleteDisabled(self, docs_dir):
        # GIVEN a store with only edit permission,
        # WHEN describing its capabilities,
        # THEN only create and delete are reported disabled:
        text = docmgr.describe_capabilities(make_store(docs_dir, edit=True))
        assert text.count("disabled") == 2
        assert "--allow-edit" not in text
        assert "--allow-create" in text
        assert "--allow-delete" in text
