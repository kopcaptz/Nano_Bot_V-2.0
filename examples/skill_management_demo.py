"""
Skills Management System Demo

Demonstrates the complete workflow of the Skills Management System.
"""

import asyncio
import time
from pathlib import Path

from loguru import logger

from nanobot.agent.skill_manager import SkillManager


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def main():
    """Run the skills management demo."""
    
    print_section("Skills Management System Demo")
    
    # Initialize manager
    storage_dir = Path.home() / ".nanobot" / "skills_demo"
    manager = SkillManager(storage_dir, auto_sync=True)
    
    print(f"Storage directory: {storage_dir}")
    print(f"Initial system stats: {manager.get_system_stats()}")
    
    # ========================================
    # 1. Create Basic Skills
    # ========================================
    print_section("1. Creating Basic Skills")
    
    basic_skills = [
        {
            "name": "read_config_file",
            "content": """# Read Configuration File

## Purpose
Read and parse a configuration file (JSON, YAML, or INI format).

## Prerequisites
- File path must be provided
- File must exist and be readable
- Format must be valid

## Steps
1. Check if file exists
2. Detect file format from extension
3. Read file content
4. Parse according to format
5. Return parsed configuration

## Error Handling
- File not found: Return error with clear message
- Parse error: Return error with line number if possible
- Permission denied: Suggest checking file permissions
""",
            "description": "Read and parse configuration files",
            "tags": ["config", "file", "parsing"],
        },
        {
            "name": "setup_virtualenv",
            "content": """# Setup Python Virtual Environment

## Purpose
Create and activate a Python virtual environment.

## Prerequisites
- Python 3.6+ installed
- pip available

## Steps
1. Check Python version
2. Create virtual environment: `python -m venv .venv`
3. Activate environment:
   - Linux/Mac: `source .venv/bin/activate`
   - Windows: `.venv\\Scripts\\activate.bat`
4. Upgrade pip: `pip install --upgrade pip`
5. Verify activation

## Verification
Run `which python` (Linux/Mac) or `where python` (Windows) to confirm.
""",
            "description": "Create Python virtual environment",
            "tags": ["python", "environment", "setup"],
        },
        {
            "name": "install_dependencies",
            "content": """# Install Python Dependencies

## Purpose
Install project dependencies from requirements file.

## Prerequisites
- Virtual environment activated
- requirements.txt exists

## Steps
1. Verify requirements.txt exists
2. Check current pip version
3. Install dependencies: `pip install -r requirements.txt`
4. Verify installations
5. Generate dependency tree (optional)

## Common Issues
- Compilation errors: Install build tools
- Version conflicts: Review requirements.txt
- Network errors: Retry or use mirror
""",
            "description": "Install Python project dependencies",
            "tags": ["python", "dependencies", "pip"],
            "dependencies": ["setup_virtualenv"],
        },
        {
            "name": "run_pytest",
            "content": """# Run Python Tests with Pytest

## Purpose
Execute Python test suite using pytest.

## Prerequisites
- pytest installed
- Tests written in test_*.py or *_test.py

## Steps
1. Activate virtual environment
2. Run pytest: `pytest -v --cov=.`
3. Generate coverage report
4. Check exit code
5. Parse test results

## Options
- `-v`: Verbose output
- `--cov`: Coverage analysis
- `--maxfail=1`: Stop after first failure
- `-k pattern`: Run specific tests
""",
            "description": "Run Python test suite with pytest",
            "tags": ["python", "testing", "pytest"],
            "dependencies": ["install_dependencies"],
        },
    ]
    
    for skill_data in basic_skills:
        try:
            skill_id = manager.add_skill(**skill_data)
            print(f"✓ Created skill: {skill_data['name']} (ID: {skill_id})")
        except ValueError as e:
            print(f"⚠ Skill already exists: {skill_data['name']}")
    
    # ========================================
    # 2. Create Composite Skill
    # ========================================
    print_section("2. Creating Composite Skill")
    
    success = manager.create_composite_skill(
        name="python_project_setup",
        description="Complete Python project setup workflow",
        component_skills=[
            "setup_virtualenv",
            "install_dependencies",
            "run_pytest",
        ],
        instructions="""
Execute the following steps in order:
1. Create and activate virtual environment
2. Install all project dependencies
3. Run test suite to verify setup

If any step fails, provide clear error message and troubleshooting steps.
""",
    )
    
    if success:
        print("✓ Created composite skill: python_project_setup")
    
    # ========================================
    # 3. Create Meta Skill
    # ========================================
    print_section("3. Creating Meta Skill")
    
    meta_skill_id = manager.add_skill(
        name="full_project_initialization",
        content="""# Full Project Initialization

## Purpose
Complete project initialization from scratch, adapting to project type.

## Strategy
1. Detect project type (Python, Node.js, Rust, etc.)
2. Create appropriate directory structure
3. Initialize version control (git)
4. Set up development environment
5. Install dependencies
6. Run initial tests
7. Generate documentation

## Adaptive Behavior
- Python: Use virtualenv + pip/poetry
- Node.js: Use npm/yarn
- Rust: Use cargo
- Other: Provide guidance

## Success Criteria
- All dependencies installed
- Tests passing
- Documentation generated
- Ready for development
""",
        skill_type="meta",
        description="Complete project initialization with type detection",
        tags=["meta", "initialization", "project"],
        dependencies=["python_project_setup", "read_config_file"],
    )
    
    print(f"✓ Created meta skill: full_project_initialization (ID: {meta_skill_id})")
    
    # ========================================
    # 4. Semantic Search
    # ========================================
    print_section("4. Semantic Search")
    
    queries = [
        "How to set up Python environment",
        "Run tests for my project",
        "Initialize a new project",
    ]
    
    for query in queries:
        print(f"\nQuery: '{query}'")
        results = manager.search_skills(query, limit=3)
        
        if results:
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result['skill_name']}")
                print(f"     Score: {result['score']:.3f} | Type: {result.get('skill_type', 'N/A')}")
                print(f"     {result.get('description', 'No description')[:80]}")
        else:
            print("  No results (vector search may not be available)")
    
    # ========================================
    # 5. Hierarchical Search
    # ========================================
    print_section("5. Hierarchical Search")
    
    query = "Set up Python project with testing"
    print(f"Query: '{query}'\n")
    
    hierarchical_results = manager.hierarchical_search(query, max_per_level=2)
    
    for level, results in hierarchical_results.items():
        print(f"\n{level.upper()} LEVEL:")
        if results:
            for result in results:
                print(f"  - {result['skill_name']} (score: {result['score']:.3f})")
        else:
            print("  (no results)")
    
    # ========================================
    # 6. Skill Composition
    # ========================================
    print_section("6. Automatic Skill Composition")
    
    task = "Prepare Python project for testing"
    print(f"Task: '{task}'\n")
    
    composition = manager.compose_for_task(task, max_skills=4)
    
    if composition:
        print("Composed workflow:")
        for i, item in enumerate(composition, 1):
            skill = item["skill"]
            print(f"  {i}. {skill['name']}")
            print(f"     Type: {skill.get('skill_type', 'basic')}")
            print(f"     Relevance: {item.get('relevance_score', 0):.3f}")
            
            if skill.get("dependencies"):
                print(f"     Requires: {', '.join(skill['dependencies'])}")
    else:
        print("No composition generated (vector search may not be available)")
    
    # ========================================
    # 7. Coverage Analysis
    # ========================================
    print_section("7. Coverage Analysis")
    
    task = "Deploy web application to cloud"
    print(f"Task: '{task}'\n")
    
    try:
        coverage = manager.analyze_coverage(task)
        
        print(f"Overall Coverage: {coverage['overall_coverage']:.2%}")
        print(f"Meta Coverage: {coverage['meta_coverage']:.2%}")
        print(f"Composite Coverage: {coverage['composite_coverage']:.2%}")
        print(f"Basic Coverage: {coverage['basic_coverage']:.2%}")
        print(f"\nRecommendation: {coverage['recommendation']}")
    except Exception as e:
        print(f"Coverage analysis not available: {e}")
    
    # ========================================
    # 8. Execution Tracking
    # ========================================
    print_section("8. Execution Tracking")
    
    test_skill = "run_pytest"
    print(f"Simulating executions for: {test_skill}\n")
    
    # Simulate some executions
    executions = [
        (True, 156.3, {"test_count": 42, "passed": 42}),
        (True, 142.7, {"test_count": 42, "passed": 42}),
        (False, 89.1, {"test_count": 42, "passed": 40, "failed": 2}),
        (True, 151.0, {"test_count": 43, "passed": 43}),
    ]
    
    for success, exec_time, context in executions:
        manager.record_execution(test_skill, success, exec_time, context)
        status = "✓" if success else "✗"
        print(f"  {status} Execution: {exec_time:.1f}ms - {context}")
    
    # Get statistics
    stats = manager.get_skill_stats(test_skill)
    if stats:
        print(f"\nStatistics for '{test_skill}':")
        print(f"  Total executions: {stats['usage_count']}")
        print(f"  Successful: {stats['success_count']}")
        print(f"  Success rate: {stats['success_rate']:.2%}")
        print(f"  Avg execution time: {stats.get('average_execution_time_ms', 0):.1f}ms")
    
    # Get execution history
    print(f"\nRecent history:")
    history = manager.get_skill_history(test_skill, limit=3)
    for i, record in enumerate(history[-3:], 1):
        status = "✓" if record['success'] else "✗"
        print(f"  {i}. {status} {record['timestamp']}: {record.get('execution_time_ms', 0):.1f}ms")
    
    # ========================================
    # 9. Version Control
    # ========================================
    print_section("9. Version Control")
    
    skill_name = "run_pytest"
    print(f"Updating skill: {skill_name}\n")
    
    updated_content = """# Run Python Tests with Pytest (Enhanced)

## Purpose
Execute Python test suite using pytest with enhanced reporting.

## Prerequisites
- pytest installed
- pytest-cov installed
- Tests written in test_*.py or *_test.py

## Steps
1. Activate virtual environment
2. Run pytest: `pytest -v --cov=. --cov-report=html`
3. Generate HTML coverage report
4. Check exit code
5. Parse test results
6. Generate summary statistics

## Options
- `-v`: Verbose output
- `--cov`: Coverage analysis
- `--cov-report=html`: HTML coverage report
- `--maxfail=1`: Stop after first failure
- `-k pattern`: Run specific tests
- `--lf`: Run last failed tests only

## Improvements
- Added HTML coverage reports
- Added test filtering options
- Enhanced error messages
"""
    
    success = manager.update_skill(
        skill_name,
        updated_content,
        "Added HTML coverage and test filtering options"
    )
    
    if success:
        skill = manager.get_skill(skill_name)
        print(f"✓ Updated to version {skill['version']}")
        print(f"  Change: Added HTML coverage and filtering")
    
    # ========================================
    # 10. System Statistics
    # ========================================
    print_section("10. System Statistics")
    
    system_stats = manager.get_system_stats()
    
    print(f"Total Skills: {system_stats['total_skills']}")
    print(f"\nSkills by Type:")
    for skill_type, count in system_stats['skills_by_type'].items():
        print(f"  {skill_type}: {count}")
    
    print(f"\nExecution Statistics:")
    print(f"  Total executions: {system_stats['total_executions']}")
    print(f"  Overall success rate: {system_stats['overall_success_rate']:.2%}")
    
    print(f"\nVector Index:")
    vec_stats = system_stats['vector_index_stats']
    print(f"  Indexed skills: {vec_stats['total_skills']}")
    print(f"  Embedding dimension: {vec_stats['embedding_dim']}")
    
    # ========================================
    # 11. Export/Import
    # ========================================
    print_section("11. Export and Import")
    
    export_dir = storage_dir / "exports"
    export_dir.mkdir(exist_ok=True)
    
    export_skill = "setup_virtualenv"
    export_path = export_dir / f"{export_skill}.md"
    
    if manager.export_skill(export_skill, export_path):
        print(f"✓ Exported '{export_skill}' to {export_path}")
        print(f"  File size: {export_path.stat().st_size} bytes")
    
    # ========================================
    # Summary
    # ========================================
    print_section("Demo Complete!")
    
    print("The Skills Management System provides:")
    print("  ✓ Hierarchical skill organization (basic, composite, meta)")
    print("  ✓ Semantic search with vector embeddings")
    print("  ✓ Automatic skill composition and dependency resolution")
    print("  ✓ Version control with full history")
    print("  ✓ Execution tracking and statistics")
    print("  ✓ Import/export functionality")
    print("  ✓ Coverage analysis for task planning")
    
    print(f"\nStorage location: {storage_dir}")
    print(f"Total skills created: {system_stats['total_skills']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        logger.exception("Demo failed")
        print(f"\nError: {e}")
        print("\nNote: Vector search features require 'hnswlib' and 'sentence-transformers'")
        print("Install with: pip install hnswlib sentence-transformers")
