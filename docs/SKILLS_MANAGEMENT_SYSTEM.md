# Skills Management System

Comprehensive system for managing, organizing, and composing AI agent skills with semantic search, versioning, and automatic composition.

## 🏗️ Architecture

### Core Components

#### 1. SkillRepository
SQLite-based storage with full versioning support.

**Features:**
- Version control for skill evolution
- Dependency tracking
- Tag-based organization
- Usage statistics (execution count, success rate)
- JSONL execution history
- Metadata management

**Schema:**
- `skills` - Main skill storage
- `skill_versions` - Version history
- `skill_dependencies` - Skill relationships
- `skill_tags` - Tag indexing
- `skill_metadata` - Extended metadata and stats

#### 2. SkillVectorSearch
HNSW-based semantic search using sentence embeddings.

**Features:**
- Fast approximate nearest neighbor search
- Persistent index storage
- SentenceTransformer embeddings (all-MiniLM-L6-v2)
- Hierarchical search support
- Automatic index synchronization

**Configuration:**
- Embedding dimension: 384 (all-MiniLM-L6-v2)
- Space: Cosine similarity
- Max elements: 10,000 (configurable)
- ef_construction: 200 (quality parameter)
- M: 16 (connections per element)

#### 3. SkillComposer
Automatic skill composition and chaining.

**Features:**
- Task-based skill composition
- Dependency resolution (topological sort)
- Validation of compositions
- Coverage analysis
- Automatic composite skill generation
- Multiple composition strategies

#### 4. SkillManager
Main interface integrating all components.

**Features:**
- Unified API for all operations
- Automatic synchronization
- Import/export functionality
- System-wide statistics
- Hierarchical search

## 🎯 Skill Types

### Basic Skills
Atomic, single-purpose skills.

**Example:**
```markdown
---
description: "Read and parse JSON files"
---

# Read JSON File

## Prerequisites
- File path must be known
- File must be valid JSON

## Steps
1. Use `read_file` tool to load content
2. Parse JSON with error handling
3. Return parsed data
```

### Composite Skills
Combinations of multiple basic or composite skills.

**Example:**
```markdown
---
description: "Analyze project structure and generate report"
---

# Project Analysis

## Component Skills
- list_directory
- read_file
- analyze_code
- write_report

## Workflow
1. List all files in project
2. Read configuration files
3. Analyze code structure
4. Generate summary report
```

### Meta Skills
High-level orchestration skills.

**Example:**
```markdown
---
description: "Full project setup and configuration"
---

# Project Setup

## Orchestrates
- Environment setup
- Dependency installation
- Configuration generation
- Initial testing

## Strategy
Use adaptive approach based on project type detection
```

## 🔍 Hierarchical Search

Search operates at three levels with different priorities:

1. **Meta Level** - High-level task orchestration
2. **Composite Level** - Multi-step workflows
3. **Basic Level** - Atomic operations

**Example Query:**
```python
results = manager.hierarchical_search("Deploy web application")

# Returns:
# {
#   "meta": [{"skill_name": "full_deployment", "score": 0.92, ...}],
#   "composite": [{"skill_name": "build_and_test", "score": 0.88, ...}],
#   "basic": [{"skill_name": "run_npm_build", "score": 0.75, ...}]
# }
```

## 💾 Storage Structure

```
storage_dir/
├── skills.db              # SQLite database
├── history/              # JSONL execution logs
│   ├── skill_name.jsonl
│   └── ...
└── index/                # Vector search index
    ├── skills.index      # HNSW index
    └── skills_mapping.pkl # ID mappings
```

## 📊 Usage Statistics

Tracked metrics:
- **Usage count** - Total executions
- **Success count** - Successful executions
- **Success rate** - success_count / usage_count
- **Average execution time** - Exponential moving average
- **Last execution** - Timestamp

## 🔄 Version Control

Each skill update creates a new version:

```python
# Initial version
manager.add_skill("my_skill", content="v1")  # version=1

# Update
manager.update_skill("my_skill", content="v2", 
                    change_description="Added error handling")  # version=2
```

Version history is preserved in `skill_versions` table.

## 🎼 Automatic Composition

The composer can automatically create skill sequences:

```python
composition = manager.compose_for_task(
    "Set up Python project with testing",
    max_skills=5
)

# Returns ordered list of skills with dependencies resolved
# Example: [create_virtualenv, install_pytest, create_test_files, run_tests]
```

### Composition Validation

```python
validation = manager.composer.validate_composition(composition)

# Returns:
# {
#   "valid": True,
#   "issues": [],
#   "warnings": ["Skill X depends on Y which is not in composition"],
#   "skill_count": 5
# }
```

### Coverage Analysis

```python
coverage = manager.analyze_coverage("Build React application")

# Returns:
# {
#   "overall_coverage": 0.78,
#   "meta_coverage": 0.85,
#   "composite_coverage": 0.82,
#   "basic_coverage": 0.68,
#   "recommendation": "Good coverage - existing skills can handle this task"
# }
```

## 📚 API Reference

### SkillManager

#### Core Operations
```python
# Initialize
manager = SkillManager("/path/to/storage", auto_sync=True)

# Add skill
skill_id = manager.add_skill(
    name="my_skill",
    content="# Skill content...",
    skill_type="basic",  # basic, composite, meta
    description="Short description",
    tags=["python", "web"],
    dependencies=["other_skill"]
)

# Get skill
skill = manager.get_skill("my_skill")

# Update skill
manager.update_skill("my_skill", new_content, "Change description")

# Delete skill
manager.delete_skill("my_skill")
```

#### Search Operations
```python
# Simple search
results = manager.search_skills("web scraping", limit=5)

# Type-filtered search
results = manager.search_skills("data processing", 
                               limit=10, 
                               skill_type="composite")

# Hierarchical search
results = manager.hierarchical_search("deploy application", 
                                     max_per_level=3)
```

#### Composition
```python
# Compose for task
composition = manager.compose_for_task("Build and deploy app", max_skills=5)

# Create composite skill
success = manager.create_composite_skill(
    name="full_workflow",
    description="Complete workflow",
    component_skills=["skill1", "skill2", "skill3"],
    instructions="Execute in sequence with validation"
)

# Get suggestions
suggestions = manager.suggest_compositions("migrate database", 
                                          num_suggestions=3)
```

#### Statistics
```python
# Skill stats
stats = manager.get_skill_stats("my_skill")
# Returns: {usage_count, success_count, success_rate, avg_execution_time_ms}

# System stats
system_stats = manager.get_system_stats()
# Returns: {total_skills, skills_by_type, total_executions, success_rate}

# Execution history
history = manager.get_skill_history("my_skill", limit=100)
```

#### Import/Export
```python
# Export
manager.export_skill("my_skill", "/path/to/export.md")

# Import
manager.import_skill_from_file("/path/to/skill.md")
```

#### Maintenance
```python
# Rebuild vector index
manager.rebuild_index()

# List all skills
all_skills = manager.list_skills()

# List by type
basic_skills = manager.list_skills(skill_type="basic")

# List by tags
web_skills = manager.list_skills(tags=["web", "python"])
```

## 🚀 Integration Example

```python
from pathlib import Path
from nanobot.agent.skill_manager import SkillManager

# Initialize
storage = Path.home() / ".nanobot" / "skills"
manager = SkillManager(storage, auto_sync=True)

# Add some skills
manager.add_skill(
    name="setup_python_env",
    content="""
# Setup Python Environment

## Steps
1. Check Python version
2. Create virtual environment
3. Install dependencies from requirements.txt
4. Verify installation
""",
    skill_type="basic",
    description="Set up Python development environment",
    tags=["python", "setup", "environment"]
)

manager.add_skill(
    name="run_tests",
    content="""
# Run Python Tests

## Steps
1. Activate virtual environment
2. Run pytest with coverage
3. Generate coverage report
4. Check for failures
""",
    skill_type="basic",
    description="Run Python test suite",
    tags=["python", "testing"]
)

# Create composite skill
manager.create_composite_skill(
    name="python_ci_workflow",
    description="Complete Python CI workflow",
    component_skills=["setup_python_env", "run_tests"],
    instructions="Set up environment, then run full test suite"
)

# Search for relevant skills
results = manager.search_skills("python testing", limit=5)
for result in results:
    print(f"{result['skill_name']}: {result['score']:.2f}")

# Compose workflow for task
composition = manager.compose_for_task(
    "Set up and test Python project",
    max_skills=5
)

# Execute skills and track
for item in composition:
    skill = item["skill"]
    print(f"Executing: {skill['name']}")
    
    # ... execute skill ...
    
    # Record execution
    manager.record_execution(
        skill['name'],
        success=True,
        execution_time_ms=123.45,
        context={"user": "dev", "project": "myapp"}
    )

# Analyze system
stats = manager.get_system_stats()
print(f"Total skills: {stats['total_skills']}")
print(f"Success rate: {stats['overall_success_rate']:.2%}")
```

## 🔧 Configuration

### Vector Search Parameters

```python
from nanobot.agent.skill_vector_search import SkillVectorSearch

search = SkillVectorSearch(
    index_dir="/path/to/index",
    embedding_dim=384,      # Match embedder dimension
    max_elements=50000,     # Increase for large skill sets
    ef_construction=200,    # Higher = better quality, slower build
    m=16                    # Higher = better quality, more memory
)

# Adjust search quality
search._get_index().set_ef(100)  # Higher = better accuracy, slower
```

### Repository Configuration

```python
from nanobot.agent.skill_repository import SkillRepository

repository = SkillRepository("/path/to/skills.db")

# Custom operations
conn = repository._get_connection()
# ... custom SQL queries ...
conn.close()
```

## 🧪 Testing

Run the test suite:

```bash
pytest tests/test_skill_management.py -v
```

Tests cover:
- Repository operations
- Versioning
- Dependencies
- Search (if hnswlib available)
- Composition
- Import/export
- Statistics

## 📈 Performance

### Benchmarks (approximate)

- **Skill addition**: ~10ms (with auto_sync)
- **Simple search**: ~5ms (10K skills)
- **Hierarchical search**: ~15ms (10K skills)
- **Composition**: ~50ms (complex dependencies)
- **Index rebuild**: ~30s (10K skills)

### Optimization Tips

1. **Disable auto_sync** during bulk operations
2. **Batch index updates** with `rebuild_index()`
3. **Use appropriate max_elements** for your use case
4. **Adjust ef and M** based on speed/quality tradeoff
5. **Regular index maintenance** with `rebuild_index()`

## 🔒 Thread Safety

- **Repository**: SQLite with default isolation
- **Vector Search**: Not thread-safe (use locks if needed)
- **SkillManager**: Inherit from components

For multi-threaded access, implement locking:

```python
import threading

class ThreadSafeSkillManager:
    def __init__(self, *args, **kwargs):
        self.manager = SkillManager(*args, **kwargs)
        self.lock = threading.Lock()
    
    def add_skill(self, *args, **kwargs):
        with self.lock:
            return self.manager.add_skill(*args, **kwargs)
    
    # ... wrap other methods ...
```

## 🐛 Troubleshooting

### Vector search not working
```python
# Check if dependencies are installed
try:
    import hnswlib
    import sentence_transformers
    print("Dependencies OK")
except ImportError as e:
    print(f"Missing: {e}")
    print("Install: pip install hnswlib sentence-transformers")
```

### Index corruption
```python
# Rebuild from scratch
manager.rebuild_index()
```

### Missing skills in search
```python
# Sync repository to index
manager._sync_vector_index()
```

### Database locked
```python
# Increase timeout or use WAL mode
import sqlite3
conn = sqlite3.connect("skills.db", timeout=30.0)
conn.execute("PRAGMA journal_mode=WAL")
```

## 📝 Best Practices

1. **Skill Organization**
   - Use clear, descriptive names
   - Add comprehensive descriptions
   - Tag appropriately (3-5 tags per skill)
   - Document prerequisites and limitations

2. **Dependencies**
   - Keep dependency chains shallow
   - Avoid circular dependencies
   - Version compatibility in descriptions

3. **Versioning**
   - Include change descriptions
   - Test before deploying updates
   - Keep backward compatibility when possible

4. **Performance**
   - Regular index maintenance
   - Prune unused skills
   - Monitor execution stats
   - Archive rarely-used skills

5. **Composition**
   - Validate before execution
   - Handle missing dependencies gracefully
   - Use coverage analysis for gaps
   - Test composite skills independently

## 🎯 Future Enhancements

Potential additions:
- Skill templates
- Automatic skill generation from trajectories
- Skill recommendation engine
- A/B testing for skill variants
- Distributed skill repository
- Real-time collaboration
- Skill marketplace
- Performance profiling
- Automatic optimization

## 📄 License

Part of nanobot-ai project (MIT License)
