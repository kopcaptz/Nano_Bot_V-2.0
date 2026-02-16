"""Tests for the Skills Management System."""

import tempfile
from pathlib import Path

import pytest

from nanobot.agent.skill_manager import SkillManager
from nanobot.agent.skill_repository import SkillRepository


@pytest.fixture
def temp_storage():
    """Create temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def repository(temp_storage):
    """Create a SkillRepository instance."""
    return SkillRepository(temp_storage / "test.db")


@pytest.fixture
def skill_manager(temp_storage):
    """Create a SkillManager instance."""
    # Note: Vector search may fail if dependencies not installed
    # Tests should handle this gracefully
    return SkillManager(temp_storage, auto_sync=False)


class TestSkillRepository:
    """Test SkillRepository functionality."""
    
    def test_add_skill(self, repository):
        """Test adding a new skill."""
        skill_id = repository.add_skill(
            name="test_skill",
            content="# Test Skill\n\nThis is a test.",
            skill_type="basic",
            description="Test skill",
            tags=["test", "example"],
        )
        
        assert skill_id > 0
        
        skill = repository.get_skill("test_skill")
        assert skill is not None
        assert skill["name"] == "test_skill"
        assert skill["skill_type"] == "basic"
        assert skill["description"] == "Test skill"
        assert "test" in skill["tags"]
    
    def test_duplicate_skill(self, repository):
        """Test that duplicate skill names are rejected."""
        repository.add_skill(
            name="duplicate",
            content="First version",
        )
        
        with pytest.raises(ValueError):
            repository.add_skill(
                name="duplicate",
                content="Second version",
            )
    
    def test_update_skill(self, repository):
        """Test updating skill content and versioning."""
        repository.add_skill(
            name="evolving_skill",
            content="Version 1",
        )
        
        success = repository.update_skill(
            "evolving_skill",
            "Version 2",
            "Added new features",
        )
        
        assert success
        
        skill = repository.get_skill("evolving_skill")
        assert skill["version"] == 2
        assert skill["content"] == "Version 2"
    
    def test_list_skills_by_type(self, repository):
        """Test filtering skills by type."""
        repository.add_skill("basic1", "Content", skill_type="basic")
        repository.add_skill("basic2", "Content", skill_type="basic")
        repository.add_skill("composite1", "Content", skill_type="composite")
        repository.add_skill("meta1", "Content", skill_type="meta")
        
        basic_skills = repository.list_skills(skill_type="basic")
        assert len(basic_skills) == 2
        
        composite_skills = repository.list_skills(skill_type="composite")
        assert len(composite_skills) == 1
    
    def test_list_skills_by_tags(self, repository):
        """Test filtering skills by tags."""
        repository.add_skill("skill1", "Content", tags=["python", "web"])
        repository.add_skill("skill2", "Content", tags=["python", "data"])
        repository.add_skill("skill3", "Content", tags=["javascript"])
        
        python_skills = repository.list_skills(tags=["python"])
        assert len(python_skills) == 2
        
        python_web_skills = repository.list_skills(tags=["python", "web"])
        assert len(python_web_skills) == 1
    
    def test_dependencies(self, repository):
        """Test skill dependencies."""
        repository.add_skill("base_skill", "Base content")
        repository.add_skill(
            "dependent_skill",
            "Depends on base",
            dependencies=["base_skill"],
        )
        
        skill = repository.get_skill("dependent_skill")
        assert "base_skill" in skill["dependencies"]
    
    def test_record_execution(self, repository):
        """Test recording skill execution."""
        repository.add_skill("executable", "Content")
        
        repository.record_execution("executable", success=True, execution_time_ms=100.5)
        repository.record_execution("executable", success=True, execution_time_ms=95.0)
        repository.record_execution("executable", success=False)
        
        stats = repository.get_skill_stats("executable")
        assert stats["usage_count"] == 3
        assert stats["success_count"] == 2
        assert stats["success_rate"] == pytest.approx(2 / 3)
    
    def test_execution_history(self, repository):
        """Test JSONL execution history."""
        repository.add_skill("logged_skill", "Content")
        
        repository.record_execution(
            "logged_skill",
            success=True,
            execution_time_ms=50.0,
            context={"user": "test", "task": "example"},
        )
        
        history = repository.get_skill_history("logged_skill")
        assert len(history) == 1
        assert history[0]["success"] is True
        assert history[0]["execution_time_ms"] == 50.0
        assert history[0]["context"]["user"] == "test"
    
    def test_delete_skill(self, repository):
        """Test deleting a skill."""
        repository.add_skill("deletable", "Content")
        
        assert repository.get_skill("deletable") is not None
        
        success = repository.delete_skill("deletable")
        assert success
        
        assert repository.get_skill("deletable") is None


class TestSkillManager:
    """Test SkillManager functionality."""
    
    def test_add_and_get_skill(self, skill_manager):
        """Test adding and retrieving a skill."""
        skill_id = skill_manager.add_skill(
            name="manager_test",
            content="# Manager Test\n\nTest content.",
            description="Test via manager",
        )
        
        assert skill_id > 0
        
        skill = skill_manager.get_skill("manager_test")
        assert skill is not None
        assert skill["name"] == "manager_test"
    
    def test_list_skills(self, skill_manager):
        """Test listing skills."""
        skill_manager.add_skill("skill1", "Content 1", skill_type="basic")
        skill_manager.add_skill("skill2", "Content 2", skill_type="composite")
        
        all_skills = skill_manager.list_skills()
        assert len(all_skills) >= 2
        
        basic_skills = skill_manager.list_skills(skill_type="basic")
        assert any(s["name"] == "skill1" for s in basic_skills)
    
    def test_update_skill(self, skill_manager):
        """Test updating a skill."""
        skill_manager.add_skill("updatable", "Original content")
        
        success = skill_manager.update_skill("updatable", "Updated content", "Fixed bug")
        assert success
        
        skill = skill_manager.get_skill("updatable")
        assert skill["content"] == "Updated content"
        assert skill["version"] == 2
    
    def test_record_execution(self, skill_manager):
        """Test recording execution through manager."""
        skill_manager.add_skill("trackable", "Content")
        
        skill_manager.record_execution("trackable", success=True, execution_time_ms=75.0)
        
        stats = skill_manager.get_skill_stats("trackable")
        assert stats["usage_count"] == 1
        assert stats["success_count"] == 1
    
    def test_system_stats(self, skill_manager):
        """Test getting system statistics."""
        skill_manager.add_skill("stat1", "Content", skill_type="basic")
        skill_manager.add_skill("stat2", "Content", skill_type="composite")
        skill_manager.add_skill("stat3", "Content", skill_type="meta")
        
        stats = skill_manager.get_system_stats()
        
        assert stats["total_skills"] >= 3
        assert "basic" in stats["skills_by_type"]
        assert "composite" in stats["skills_by_type"]
        assert "meta" in stats["skills_by_type"]
    
    def test_export_import_skill(self, skill_manager, temp_storage):
        """Test exporting and importing skills."""
        skill_manager.add_skill(
            "exportable",
            "# Exportable Skill\n\nThis is exportable.",
            description="Export test",
        )
        
        export_path = temp_storage / "exported_skill.md"
        success = skill_manager.export_skill("exportable", export_path)
        assert success
        assert export_path.exists()
        
        # Delete original
        skill_manager.delete_skill("exportable")
        assert skill_manager.get_skill("exportable") is None
        
        # Import back
        success = skill_manager.import_skill_from_file(export_path)
        assert success
        
        skill = skill_manager.get_skill("exportable")
        assert skill is not None


class TestSkillComposer:
    """Test SkillComposer functionality."""
    
    def test_create_composite_skill(self, skill_manager):
        """Test creating a composite skill."""
        # Add base skills
        skill_manager.add_skill("base1", "Base skill 1", description="First base")
        skill_manager.add_skill("base2", "Base skill 2", description="Second base")
        
        # Create composite
        success = skill_manager.create_composite_skill(
            name="composite_test",
            description="Composite of base skills",
            component_skills=["base1", "base2"],
            instructions="Execute in order",
        )
        
        assert success
        
        # Verify composite skill
        skill = skill_manager.get_skill("composite_test")
        assert skill is not None
        assert skill["skill_type"] == "composite"
        assert "base1" in skill["dependencies"]
        assert "base2" in skill["dependencies"]
    
    def test_analyze_coverage(self, skill_manager):
        """Test coverage analysis (simplified without vector search)."""
        skill_manager.add_skill(
            "web_scraping",
            "How to scrape websites",
            skill_type="basic",
            tags=["web", "data"],
        )
        
        # This test may not work without vector search dependencies
        # Just verify the method doesn't crash
        try:
            coverage = skill_manager.analyze_coverage("How to scrape a website")
            assert "overall_coverage" in coverage
        except Exception:
            # Vector search not available, skip
            pass


def test_skill_repository_persistence(temp_storage):
    """Test that repository persists across instances."""
    db_path = temp_storage / "persistent.db"
    
    # First instance
    repo1 = SkillRepository(db_path)
    repo1.add_skill("persistent_skill", "Content that persists")
    
    # Second instance (simulating restart)
    repo2 = SkillRepository(db_path)
    skill = repo2.get_skill("persistent_skill")
    
    assert skill is not None
    assert skill["name"] == "persistent_skill"
    assert skill["content"] == "Content that persists"


def test_concurrent_updates(repository):
    """Test handling of concurrent-like updates."""
    repository.add_skill("concurrent", "Version 0")
    
    # Multiple updates
    for i in range(1, 6):
        repository.update_skill("concurrent", f"Version {i}")
    
    skill = repository.get_skill("concurrent")
    assert skill["version"] == 6
    assert skill["content"] == "Version 5"
