# Nanobot Persistent Memory — Full Architecture Analysis

## 1. Directory Structure

```
nanobot/memory/
├── __init__.py        # Public API (re-exports from db.py + crystallize.py)
├── db.py              # SQLite storage — facts, journal, conversations, reflections, token_usage
├── vector.py          # ChromaDB vector store — semantic search via embeddings
└── crystallize.py     # LLM-based fact extraction from dialogues

nanobot/agent/
├── memory.py          # MemoryStore — file-based memory (MEMORY.md + daily notes)
├── context.py         # ContextBuilder — assembles system prompt with memory enrichment
└── tools/
    └── memory.py      # MemorySearchTool — agent tool for semantic/filtered search

nanobot/session/
└── manager.py         # SessionManager — JSONL-based conversation persistence

src/core/
└── memory.py          # CrystalMemory — in-memory dialogue buffer (MVP/legacy)

Storage paths (all under ~/.nanobot/):
├── memory.db          # SQLite database
├── chroma/            # ChromaDB persistent directory
├── sessions/          # JSONL session files
└── workspace/
    └── memory/
        ├── MEMORY.md      # Long-term notes (agent-written)
        └── YYYY-MM-DD.md  # Daily notes
```

## 2. Storage Layers Overview

| Layer | Engine | Purpose | Path |
|-------|--------|---------|------|
| Structured facts | SQLite | Category/key/value facts, journal, conversations | `~/.nanobot/memory.db` |
| Vector index | ChromaDB (PersistentClient) | Semantic similarity search | `~/.nanobot/chroma/` |
| File-based memory | Markdown files | Agent-accessible notes | `~/.nanobot/workspace/memory/` |
| Session history | JSONL files | Per-chat conversation persistence | `~/.nanobot/sessions/` |
| In-memory buffer | Python dict | Fast session context (MVP) | RAM only |

## 3. Libraries Used

- **SQLite3** (stdlib) — structured data storage
- **ChromaDB** (`chromadb.PersistentClient`) — vector database
- **SentenceTransformers** via `chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction` — embeddings
- **Model**: `all-MiniLM-L6-v2` (384-dim, cosine similarity)
- **HNSW** index with cosine distance (`hnsw:space = cosine`)
- **Loguru** — logging
- **Pydantic / Pydantic-Settings** — config schema

## 4. Vector Format

- **Embedding model**: `all-MiniLM-L6-v2` (384 dimensions, float32)
- **Distance metric**: Cosine similarity (`hnsw:space: cosine`)
- **Collection name**: `nanobot_memory`
- **Storage**: ChromaDB PersistentClient at `~/.nanobot/chroma/`
- **Document format**: Each vector entry contains:
  - `id` — stable string like `fact::category::key`
  - `document` — text representation of the fact
  - `metadata` — dict with type, category, key, value, domain, sub_category, updated_at
- **Fallback**: If SentenceTransformers unavailable, ChromaDB uses its built-in default embedder

## 5. Dependencies for Memory

From `pyproject.toml` (main deps relevant to memory):

```
pydantic>=2.0.0
pydantic-settings>=2.0.0
loguru>=0.7.0
litellm>=1.0.0        # Used by crystallize (LLM calls)
```

Not in pyproject.toml but required at runtime:

```
chromadb              # Vector DB (imported dynamically)
sentence-transformers # For all-MiniLM-L6-v2 (optional, graceful fallback)
```

## 6. Save/Load Flow

### 6.1 Fact Save Flow

```
User message
    │
    ▼
crystallize_memories() ──► LLM extracts JSON facts
    │
    ▼
add_fact(category, key, value, domain, sub_category)
    │
    ├──► SQLite INSERT/UPSERT into `facts` table
    │
    └──► ChromaDB upsert (text + metadata)
         id = "fact::{category}::{key}"
         text = "Domain: ...\nКатегория: ...\nКлюч: ...\nЗначение: ..."
```

### 6.2 Fact Retrieval Flow

```
Agent receives message
    │
    ▼
ContextBuilder.build_messages()
    │
    ├──► semantic_search(current_message, limit=5)
    │       │
    │       ▼
    │    ChromaDB collection.query(query_texts=[...])
    │       │
    │       ▼
    │    Filter by distance < 0.7
    │       │
    │       ▼
    │    Inject as system message: "Relevant facts from your memory: ..."
    │
    └──► Agent can also call memory_search tool manually
            │
            ├── With domain/category filter → get_facts_filtered() (SQLite)
            └── Without filter → semantic_search() (ChromaDB)
```

### 6.3 Session Persistence

```
Message arrives
    │
    ├──► SessionManager.get_or_create(key)
    │       loads from ~/.nanobot/sessions/{key}.jsonl
    │
    ├──► session.add_message(role, content)
    │
    └──► SessionManager.save(session)
            writes metadata line + message lines as JSONL
```
