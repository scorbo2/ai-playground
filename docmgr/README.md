# docmgr - simple document manager in FastMCP

`docmgr` is a small Python project that serves a number of MCP tools that an LLM can use to view,
search, and optionally edit local documents.

MCP tools are potentially destructive, so use with caution.

This project is intended to be illustrative of what can be done with MCP.
It is an academic/hobby project, but it can actually be used for local document management.

## Requirements

Any recent version of Python.

- `pip install -r requirements.txt` gives you FastMCP (pinned to the 1.x line:
  `mcp` 2.x renamed FastMCP to `MCPServer` and changed the API, so docmgr targets 1.x)
- `pip install "mcp[cli]<2"` also gives you a dev server + inspector

## Usage

The `docmgr` script itself is executable Python code (`#!/usr/bin/env python3` + `chmod 744` on linux):

```shell
# Show help and usage info:
$ docmgr -h

# Serve documents from the given directory:
$ docmgr /path/to/docs/

# Serve + allow edits (docmgr is read-only by default):
$ docmgr --allow-edit /path/to/docs/

# Serve + allow edit + allow creation of new docs:
$ docmgr --allow-edit --allow-create /path/to/docs

# Serve + allow deletion of existing docs:
$ docmgr --allow-delete /path/to/docs

# You can use --allow-all as a synonym for allowing edit, creation, and deletion:
$ docmgr --allow-all /path/to/docs

# Exactly one path is required! Path must exist and be readable!
# If edit, creation, or deletion is allowed, path must also be writable!

# By default, docmgr uses stdio. You can optionally use streamable http:
$ docmgr --host 127.0.0.1 --port 8080 /path/to/docs
# `host` has no default, and streamable http is disabled if omitted.
# `port` defaults to 8080, but you can specify any valid port > 1024
# `port` is ignored if specified without --host
```

When using streamable http, clients must connect to the **`/mcp` endpoint**,
e.g. `http://127.0.0.1:8080/mcp` in the MCP Inspector. The root path `/` is
not an endpoint and returns 404. docmgr enables CORS on the HTTP endpoint so
browser-based clients (like the Inspector's direct-connect mode) can complete
their `OPTIONS` preflight.

## Supported file types

`docmgr` will serve all UTF-8 documents, recursively, in its given document path, regardless of file extension.
Files containing non-UTF8 characters are not served: they are invisible to `search_documents`,
`list_all_documents`, and `glob`, and will generate an error if given as a `rel_path` to any tool.

Note: hidden files are also served, if they are valid UTF-8 documents. Example: dotfiles in Linux.

## Containment to served directory

The script uses `Path.resolve()` to prevent the LLM from accidentally (or deliberately) escaping containment.
Any requested `rel_path` that somehow resolves to a location outside of the served directory is rejected with an error.
(This can actually happen with symlinks).

## Cross-platform paths

`rel_path` values are validated with the OS-native path flavour, so docmgr behaves
the same on Windows, macOS, and Linux:

- Absolute paths are rejected — including Windows drive paths (`C:\docs\file.txt`,
  `C:/docs/file.txt`) and UNC shares (`\\server\share\file.txt`).
- Paths containing `..` are rejected (`a/../b`); on Windows the backslash form (`a\..\b`) is rejected as well.
- Relative paths may use either separator on Windows (`docs/file.txt` and
  `docs\file.txt` are both fine); on Linux/macOS use forward slashes as usual.

## Tools list

- `search_documents(query: str, max_results: int = 20, case_sensitive: bool = false) -> list[dict]` : accepts a search string
  and an optional max results limit (defaulting to 20). Can be used to search documents for
  a given string. Returns a snippet of up to 50 characters on either side of the first search match
  in each matching document. Returns an empty list if no hits. Returns a dict with keys:
  `rel_path`, `snippet`, `snippet_offset`, and `offset`. (`snippet_offset` and `offset` might
  be equal, if the match is at the start of the document. Otherwise, `snippet_offset` is the start
  of the returned snippet, while `offset` is the start of the match).
  Search is always recursive from the top of the served directory. Searches cannot be constrained by directory.
  Note: only the *first* match in each document is returned! This tool doesn't tell you how many times the
  search term exists in each document.
- `list_all_documents()` - This is equivalent to `glob("**/*")`. The returned list is ordered by `rel_path`.
- `glob(path_str: str) -> list[str]` - accepts a wildcard path string like `*.txt` or `**/*.txt`
  and returns a list of relative paths that match that string. The returned list is ordered by `rel_path`.
- `get_document(rel_path: str) -> str` - retrieves the entire contents of the specified
  document (with `rel_path` being a path strictly relative to the served directory - absolute paths
  and paths with `..` in them are rejected with an error).
- `get_document_length(rel_path: str) -> int` - reports the file size, in characters, of the
  given document. Returns an error if no such document. `rel_path` is resolved as with `get_document`.
- `get_document_partial(rel_path: str, offset: int, length: int) -> str` - similar to
  `get_document`, but only retrieves the specified number of characters for the specified document,
  starting at the specified character offset. Returns an error if offset or length are invalid:
  `offset` must be greater than or equal to 0, and less than or equal to `get_document_length(rel_path)`.
  `length` must be less than or equal to `offset` + the remaining count of characters in the document.
- `edit_document(rel_path: str, to_replace: str, replace_with: str, int offset)` - requires
  document editing to be enabled. Accepts an exact string to be replaced in the document, and the
  text with which to replace it. You must specify the offset where `to_replace` begins. Returns
  an error if `to_replace` is not present at the given offset, or if the given offset is invalid.
  Note: `to_replace` can be empty to insert/append the `replace_with` text at the given offset.
- `create_document(rel_path: str, text: str)` - requires document creation to be enabled. Accepts
  text to be written to a new `rel_path` in the served directory. Returns an error if the given
  path already exists. Creates parent directories as needed.
- `delete_document(rel_path: str)` - requires document deletion to be enabled. Removes the document
  at the given relative path, or returns an error if no such document exists. Does not delete the
  containing directory.

The server also advertises its enabled write capabilities in its MCP `instructions`
(visible to the LLM client at connection), so the model knows in advance which write
tools it can use successfully on a given instance.

## Example usage

### Searching, reading, and summarizing

"Search my documents for any containing the term "fluffy bunny". Report how many documents use this term."

"Read the document at `docs/hello.txt` and summarize it for me."

"How big is my `good_ideas.txt` document?"

"Read the first thousand characters of my `new_project_idea.txt` document and tell me if you think I'm off to a good start."

### Editing and creating

"The `project1/README.md` document has a lot of spelling mistakes. Can you fix them for me?"

"Create a new `project2/README.md` document and initialize it with a simple Work in Progress message for now."

"Find all `*.md` files and append a LICENSE section to the end of each one with a link to the MIT License."

"Delete the `bad_project/README.md` document. I don't want it anymore."

## Development plan

A staged development plan will build the project in discrete steps:

1. Initial script creation. No tools. Use `argparse` to implement and validate command-line arguments.
   Return appropriate help text for each, and ensure arguments are valid (exactly one path is specified,
   no unrecognized arguments are accepted).
2. Implement read-only tools (searching and reading documents). The `--allow-*` flags are accepted
   but ignored at this stage.
3. Implement `allow-edit` and associated tools.
4. Implement `allow-create` and associated tools.
5. Implement `allow-delete` and associated tools.
6. Ensure `allow-all` enables all of: edit, create, and delete.

Each stage should include Pytest unit tests with a fabricated temporary directory of synthesized documents,
for both happy and unhappy paths (appropriate errors are returned for negative scenarios, correct results
are returned for positive scenarios).

## Tests

- `pytest` runs the unit test suite: happy and unhappy paths for every tool,
  against a fabricated temporary directory of synthesized documents.
- `python e2e_docmgr.py` spawns the real server over stdio and streamable
  HTTP and drives it with a live MCP client session.

Both need the venv: `python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`

## License and disclaimer

`docmgr` is licensed under the [MIT License](../LICENSE).

Use at your own risk! With all permissions enabled, your LLM will be able to modify and delete actual documents!
