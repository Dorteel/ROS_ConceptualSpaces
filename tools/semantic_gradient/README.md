# WordNet Semantic Gradient Editor

A standalone local browser tool for constructing human-defined gradients between
English WordNet antonyms. It has no ROS imports, nodes, topics, services, or GUI
dependencies. Python serves a plain HTML/CSS/JavaScript interface on loopback.

## Install and launch

From the repository root, on Linux or macOS with Python 3.10 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r tools/semantic_gradient/requirements.txt
python -m nltk.downloader wordnet
./semantic-gradient.sh
```

Open **http://127.0.0.1:8765**. Stop with Ctrl+C. First sampling indexes WordNet
and may take several seconds; subsequent sampling uses the in-memory index.
The tool does not automatically download corpora. If WordNet is missing, the
editor displays installation instructions; saved gradients remain accessible.
NLTK 3.9 is used for its stable corpus-loading behavior.

Optional settings:

```bash
./semantic-gradient.sh --port 9000 --data-dir /path/to/ObsidianVault/Gradients
PYTHON=/path/to/venv/bin/python ./semantic-gradient.sh
```

For a custom corpus directory, download with `python -m nltk.downloader -d
/path/to/nltk_data wordnet` and launch with `NLTK_DATA=/path/to/nltk_data`.
The server is a local single-user development tool, bound to `127.0.0.1`.
No Node.js installation, build step, CDN, or internet connection is needed after
installing dependencies and the corpus. Persistence uses POSIX file locking;
Windows is not currently supported.

## Editing

- The toolbar initially samples five pairs. Set a count from 1 to 50 and select
  **Resample** for another collection. Unsaved axes require explicit discard
  confirmation. A failed request preserves the current editor.
- Click anywhere in an axis area, enter a word or phrase, and apply. Intermediate
  positions are normalized numbers strictly between 0 and 1. Endpoints remain
  fixed at 0 and 1. Click a label to edit its text, set an exact position, or delete
  it; drag a label horizontally to reposition it.
- Labels occupy separate measured lanes when they would overlap. Vertical
  connector lines point to their positions; lane height has no semantic meaning.
- **Suggest Concepts** queries each endpoint's exact WordNet sense. Select a
  candidate and click the axis, or drag the candidate onto that same axis.
  Candidates are never inserted automatically. The interface marks candidates
  as unplaced or accepted. Selecting a candidate again cancels placement.
- Keyboard users can focus an axis and press Enter to open a concept dialog at
  0.5, or to accept the selected candidate there. Click that concept to set its
  precise position. All editing controls are keyboard accessible.
- **Save** saves one axis. **Save All** saves each modified axis sequentially;
  it is not a multi-axis transaction. Earlier successes remain saved if a later
  save fails, and remaining axes retain their unsaved state.
- **Saved Gradients** lists saved axes and searches endpoint/concept text without
  regard to case. **Load** restores exact positions, sense identifiers, provenance,
  and creation time. Other axes remain in the editor. Replacing a modified copy
  asks for confirmation. Navigation between the two views does not discard edits.
- Closing or refreshing the page triggers the browser's unsaved-change warning.
  Unsaved work lives in memory, not local storage; save before leaving. Browser
  or OS crashes cannot be protected by the navigation warning.

Renaming an accepted candidate turns it into a manual concept, since the new
text is no longer the WordNet lemma. Its previous candidate and provenance are
retained under `origin`. Moving it without renaming preserves WordNet provenance.

## Sampling and linguistic limits

The backend enumerates direct lemma-level `antonyms()` links across all English
WordNet parts of speech. Each endpoint retains its synset name, lemma name, and
lemma sense key. Canonically sorted sense identities deduplicate reversed links.
Each displayed collection also deduplicates identical lexical label pairs across
senses. Labels replace underscores with spaces; self-pairs and non-word artifacts
are excluded.

Sampling is weighted without replacement: attested lemma counts, adjective senses,
and short phrases receive preference. This favors familiar scalar pairs without
claiming to eliminate obscure terms. Resampling excludes the current sense IDs
when the corpus has enough alternatives; otherwise reuse is possible. If fewer
unique labels exist than requested, the editor reports the smaller sample.

Suggestions use actual lemmas in endpoint synsets (`synonym`), and, for adjective
senses, `similar_tos()` (`similar_to`) and `also_sees()` (`also_see`). They are
case-insensitively deduplicated, retaining all observed provenance paths, and
limited to 60 alphabetically ordered candidates per axis. Hover over a candidate
for its target sense and lemma key. An empty result is explicitly reported.

**WordNet does not encode numerical semantic gradients.** Synonyms and similar
adjectives may be near an endpoint, outside the intended axis, or irrelevant to
a user's context. Some antonyms are categorical rather than scalar. All candidate
acceptance, ordering, and positions are human judgments. No numerical position
is inferred from WordNet, and no relation is fabricated. This tool does not use
embeddings, language models, or automatic semantic ranking of intermediate terms.

## Files and schema

By default, output goes into `tools/semantic_gradient/saved_gradients/`, which is
ignored by Git. Set `--data-dir` to use a dedicated folder in an Obsidian vault.
Each pair produces matching UTF-8 files:

```text
cold-hot--<20-character-sense-id>.json
cold-hot--<20-character-sense-id>.md
```

The suffix is always present: the first 20 hexadecimal characters of SHA-256 of
the sorted `(synset, lemma_key)` endpoint identities. Thus save order does not
change filenames, reversed pairs share an identity, and identical words with
different senses have different files. One gradient is stored per sense pair.
A newly sampled pair cannot overwrite an existing save: load the existing
version from Saved Gradients first. Timestamps provide optimistic concurrency
protection when another tab or process has saved a newer version.

JSON is the source of truth. Schema version 1 contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `id` | Stable sense-pair identifier |
| `antonyms.left`, `antonyms.right` | Human-readable endpoint words |
| `endpoints.left`, `endpoints.right` | Objects with `word`, `synset`, `lemma`, `lemma_key` |
| `gradient` | Position-sorted array of intermediate concepts |
| `gradient[].concept` | Word or short phrase, 1–120 characters |
| `gradient[].position` | Finite numeric value, `0 < position < 1` |
| `gradient[].source` | `manual` or `wordnet` |
| `gradient[].provenance` | Required for `wordnet`: array of lexical relation records |
| `gradient[].origin` | Original candidate/provenance if an accepted word was renamed |
| `created_at`, `modified_at` | UTC ISO 8601 timestamps set by the server on save |

Each provenance record has `endpoint` (`left`/`right`), `from_synset`, `relation`
(`synonym`/`similar_to`/`also_see`), target `synset`, `lemma`, and `lemma_key`.
Unsaved API documents have null timestamps. Endpoints are represented separately
from the intermediate array. Position precision is retained in JSON; Markdown
shows up to six significant digits in a position-sorted table, with metadata
and provenance. Markdown is readable in Obsidian without additional plugins.

Each file is written through a flushed temporary file and atomic replacement.
A directory lock serializes saves across processes. Markdown is prepared first,
then JSON commits the revision; write failures attempt to restore the previous
Markdown. On startup, Markdown mirrors are regenerated from validated JSON if
missing or inconsistent. The two files cannot be atomically replaced together:
an abrupt interruption may temporarily leave an inconsistent mirror (or an
orphan Markdown file on a first save). Restart repairs mirrors with committed
JSON; an orphan Markdown file is not considered a saved gradient. Keep backups
for filesystem or hardware failure. Editing Markdown does not update JSON, and
startup will restore the generated mirror. Invalid JSON is reported rather than
silently skipped or overwritten.

## Tests

```bash
source .venv/bin/activate
python -m pip install -r tools/semantic_gradient/requirements-test.txt
python -m playwright install chromium
./test.sh
```

On a minimal Linux image, Playwright may also require system libraries; follow
its installation diagnostic or use `python -m playwright install --with-deps
chromium`. Focused commands are `./test.sh backend`, `./test.sh integration`, and
`./test.sh browser`. The integration tests require the downloaded WordNet corpus;
the full suite deliberately fails rather than silently skipping missing setup.

Backend tests use a small deterministic lexical fixture for extraction,
deduplication, resampling, provenance, schema validation, search, collisions,
concurrent-edit conflicts, failed writes, mirror recovery, and HTTP responses.
Real-corpus tests verify sampled antonyms and suggestion relations against NLTK.
Chromium tests run the real HTTP server with isolated temporary storage and a
predictable corpus, exercising clicking, dragging, editing, deletion, independent
axes, candidate acceptance, exact position round trips, save/search/reload,
unsaved protection, failed resampling, and dense labels at mobile widths.
