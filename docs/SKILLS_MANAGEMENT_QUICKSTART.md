# Skills Management System - Quick Start

Get started with the Skills Management System in 5 minutes.

## Installation

### 1. Install Dependencies

```bash
pip install -e .
pip install hnswlib sentence-transformers
```

Or add to your requirements:
```
hnswlib>=0.8.0
sentence-transformers>=2.0.0
```

### 2. Basic Setup

```python
from pathlib import Path
from nanobot.agent.skill_manager import SkillManager

# Initialize manager
storage = Path.home() / ".nanobot" / "skills"
manager = SkillManager(storage, auto_sync=True)
```

## Quick Example

### Add a Skill

```python
manager.add_skill(
    name="hello_world",
    content="""
# Hello World Skill

## Purpose
Print a greeting message.

## Steps
1. Get user name
2. Format greeting
3. Print message
""",
    skill_type="basic",
    description="Simple greeting skill",
    tags=["example", "greeting"]
)
```

### Search for Skills

```python
# Semantic search
results = manager.search_skills("greeting user", limit=5)

for result in results:
    print(f"{result['skill_name']}: {result['score']:.2f}")
```

### Create Composite Skill

```python
# Add component skills first
manager.add_skill("validate_input", "Validate user input", skill_type="basic")
manager.add_skill("process_data", "Process validated data", skill_type="basic")

# Create composite
manager.create_composite_skill(
    name="full_workflow",
    description="Complete data processing workflow",
    component_skills=["validate_input", "process_data"]
)
```

### Track Execution

```python
# Record execution
manager.record_execution(
    "hello_world",
    success=True,
    execution_time_ms=45.2,
    context={"user": "Alice"}
)

# Get statistics
stats = manager.get_skill_stats("hello_world")
print(f"Success rate: {stats['success_rate']:.2%}")
```

## Core Features

### 1. Hierarchical Organization

Three skill levels:
- **Basic**: Atomic operations
- **Composite**: Multi-step workflows
- **Meta**: High-level orchestration

```python
# Search all levels
results = manager.hierarchical_search("deploy application")
# Returns: {"meta": [...], "composite": [...], "basic": [...]}
```

### 2. Automatic Composition

```python
composition = manager.compose_for_task(
    "Set up Python project",
    max_skills=5
)

# Execute in order
for item in composition:
    skill = item["skill"]
    print(f"Step: {skill['name']}")
```

### 3. Version Control

```python
# Update skill (creates new version)
manager.update_skill(
    "hello_world",
    "Updated content...",
    "Added error handling"
)

# Check version
skill = manager.get_skill("hello_world")
print(f"Version: {skill['version']}")
```

### 4. Coverage Analysis

```python
coverage = manager.analyze_coverage("Build web app")
print(coverage["recommendation"])
# "Good coverage - existing skills can handle this task"
```

## Run the Demo

```bash
cd /workspace
python examples/skill_management_demo.py
```

This demo shows:
- Creating skills (basic, composite, meta)
- Semantic search
- Hierarchical search
- Automatic composition
- Execution tracking
- Version control
- Import/export
- Statistics

## Common Patterns

### Pattern 1: Task-Based Workflow

```python
# 1. Analyze what skills are available
coverage = manager.analyze_coverage("Your task here")

# 2. Get suggestions
suggestions = manager.suggest_compositions("Your task here")

# 3. Choose composition
composition = suggestions[0]["composition"]

# 4. Execute
for item in composition:
    # ... execute skill ...
    manager.record_execution(item["skill"]["name"], success=True)
```

### Pattern 2: Progressive Skill Building

```python
# Start with basic skills
basic_skills = ["read_file", "parse_json", "validate_schema"]

for name in basic_skills:
    manager.add_skill(name, content, skill_type="basic")

# Build composite skills
manager.create_composite_skill(
    "validate_config",
    "Read and validate configuration",
    basic_skills
)

# Create meta skill for orchestration
manager.add_skill(
    "setup_project",
    meta_content,
    skill_type="meta",
    dependencies=["validate_config"]
)
```

### Pattern 3: Skill Evolution

```python
# v1: Basic implementation
manager.add_skill("process_data", "Basic processing")

# Collect metrics
manager.record_execution("process_data", success=True)

# v2: Enhanced version
manager.update_skill(
    "process_data",
    "Enhanced with error handling",
    "Added retry logic and validation"
)

# Track improvement
stats_before = manager.get_skill_stats("process_data")
# ... use skill ...
stats_after = manager.get_skill_stats("process_data")
```

## Integration with Agent Loop

```python
class EnhancedAgent:
    def __init__(self):
        self.skill_manager = SkillManager("~/.nanobot/skills")
    
    async def handle_task(self, task: str):
        # 1. Find relevant skills
        composition = self.skill_manager.compose_for_task(task)
        
        # 2. Execute workflow
        for item in composition:
            skill = item["skill"]
            
            try:
                result = await self.execute_skill(skill)
                self.skill_manager.record_execution(
                    skill["name"],
                    success=True,
                    execution_time_ms=result.duration
                )
            except Exception as e:
                self.skill_manager.record_execution(
                    skill["name"],
                    success=False,
                    context={"error": str(e)}
                )
                raise
    
    async def execute_skill(self, skill):
        # Your skill execution logic
        pass
```

## Best Practices

1. **Descriptive Names**: Use clear, action-oriented names
   - Good: `parse_json_config`, `validate_user_input`
   - Bad: `helper1`, `utils`

2. **Rich Descriptions**: Include prerequisites, steps, and error handling
   
3. **Appropriate Tags**: 3-5 relevant tags per skill

4. **Track Everything**: Record all executions for insights

5. **Regular Maintenance**:
   ```python
   # Rebuild index periodically
   manager.rebuild_index()
   
   # Review low-performing skills
   stats = manager.get_system_stats()
   ```

## Troubleshooting

### Vector search not working

```bash
pip install hnswlib sentence-transformers
```

### Slow search

```python
# Reduce ef parameter (trade accuracy for speed)
manager.vector_search._get_index().set_ef(20)
```

### Index out of sync

```python
manager.rebuild_index()
```

## Next Steps

1. Read the [full documentation](SKILLS_MANAGEMENT_SYSTEM.md)
2. Run the demo: `python examples/skill_management_demo.py`
3. Explore tests: `pytest tests/test_skill_management.py -v`
4. Integrate with your agent
5. Build your skill library!

## Resources

- **Documentation**: `docs/SKILLS_MANAGEMENT_SYSTEM.md`
- **Demo**: `examples/skill_management_demo.py`
- **Tests**: `tests/test_skill_management.py`
- **Code**: `nanobot/agent/skill_*.py`

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review the test cases for examples
3. Run the demo to verify setup
4. Check logs for detailed error messages
