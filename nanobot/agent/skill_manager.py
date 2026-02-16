"""Main skill management interface integrating all components."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.skill_composer import SkillComposer
from nanobot.agent.skill_repository import SkillRepository
from nanobot.agent.skill_vector_search import SkillVectorSearch


class SkillManager:
    """
    Main interface for the Skills Management System.
    
    Integrates:
    - SkillRepository: SQLite storage with versioning
    - SkillVectorSearch: HNSW-based semantic search
    - SkillComposer: Automatic skill composition
    
    Features:
    - Hierarchical skill organization (meta/composite/basic)
    - Semantic search with vector embeddings
    - Automatic composition and chaining
    - Version control and history tracking
    - Usage statistics and optimization
    """
    
    def __init__(
        self,
        storage_dir: Path | str,
        auto_sync: bool = True,
    ):
        """
        Initialize skill manager.
        
        Args:
            storage_dir: Directory for all skill data
            auto_sync: Automatically sync repository changes to vector index
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.repository = SkillRepository(self.storage_dir / "skills.db")
        self.vector_search = SkillVectorSearch(self.storage_dir / "index")
        self.composer = SkillComposer(self)
        
        self.auto_sync = auto_sync
        
        logger.info(f"SkillManager initialized at {self.storage_dir}")
        
        # Sync if needed
        if auto_sync:
            self._sync_vector_index()
    
    def add_skill(
        self,
        name: str,
        content: str,
        skill_type: str = "basic",
        description: str | None = None,
        tags: list[str] | None = None,
        dependencies: list[str] | None = None,
    ) -> int:
        """
        Add a new skill.
        
        Args:
            name: Unique skill name
            content: Skill content (markdown)
            skill_type: Type (basic, composite, meta)
            description: Short description
            tags: List of tags
            dependencies: List of required skills
        
        Returns:
            Skill ID
        """
        # Add to repository
        skill_id = self.repository.add_skill(
            name=name,
            content=content,
            skill_type=skill_type,
            description=description,
            tags=tags,
            dependencies=dependencies,
        )
        
        # Add to vector index
        if self.auto_sync:
            self.vector_search.add_skill(name, content, skill_type)
            self.vector_search.save()
        
        logger.info(f"Added skill '{name}' (type: {skill_type})")
        return skill_id
    
    def update_skill(
        self, name: str, content: str, change_description: str | None = None
    ) -> bool:
        """
        Update skill content (creates new version).
        
        Args:
            name: Skill name
            content: New content
            change_description: Description of changes
        
        Returns:
            True if updated successfully
        """
        success = self.repository.update_skill(name, content, change_description)
        
        if success and self.auto_sync:
            skill = self.repository.get_skill(name)
            if skill:
                self.vector_search.add_skill(
                    name, content, skill.get("skill_type", "basic")
                )
                self.vector_search.save()
        
        return success
    
    def get_skill(self, name: str) -> dict[str, Any] | None:
        """
        Get skill by name.
        
        Args:
            name: Skill name
        
        Returns:
            Skill dict or None
        """
        return self.repository.get_skill(name)
    
    def list_skills(
        self, skill_type: str | None = None, tags: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        List skills with optional filtering.
        
        Args:
            skill_type: Filter by type
            tags: Filter by tags
        
        Returns:
            List of skill dicts
        """
        return self.repository.list_skills(skill_type=skill_type, tags=tags)
    
    def search_skills(
        self,
        query: str,
        limit: int = 5,
        skill_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search for skills.
        
        Args:
            query: Natural language query
            limit: Maximum results
            skill_type: Optional type filter
        
        Returns:
            List of results with skill_name, score, distance
        """
        results = self.vector_search.search(query, limit=limit, skill_type=skill_type)
        
        # Enrich with repository data
        enriched = []
        for result in results:
            skill = self.repository.get_skill(result["skill_name"])
            if skill:
                # Filter by type if specified
                if skill_type and skill.get("skill_type") != skill_type:
                    continue
                
                result["skill_type"] = skill.get("skill_type", "basic")
                result["description"] = skill.get("description", "")
                result["tags"] = skill.get("tags", [])
                enriched.append(result)
        
        return enriched
    
    def hierarchical_search(
        self, query: str, max_per_level: int = 3
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Search across all skill levels hierarchically.
        
        Args:
            query: Search query
            max_per_level: Maximum results per level
        
        Returns:
            Dict with meta, composite, and basic results
        """
        meta_results = self.search_skills(query, limit=max_per_level, skill_type="meta")
        composite_results = self.search_skills(query, limit=max_per_level, skill_type="composite")
        basic_results = self.search_skills(query, limit=max_per_level, skill_type="basic")
        
        return {
            "meta": meta_results,
            "composite": composite_results,
            "basic": basic_results,
        }
    
    def compose_for_task(
        self, task_description: str, max_skills: int = 5
    ) -> list[dict[str, Any]]:
        """
        Compose skills for a task.
        
        Args:
            task_description: Task description
            max_skills: Maximum skills in composition
        
        Returns:
            Ordered list of skills
        """
        return self.composer.compose_for_task(task_description, max_skills)
    
    def create_composite_skill(
        self,
        name: str,
        description: str,
        component_skills: list[str],
        instructions: str | None = None,
    ) -> bool:
        """
        Create composite skill from existing skills.
        
        Args:
            name: Composite skill name
            description: Description
            component_skills: List of component skill names
            instructions: Optional instructions
        
        Returns:
            True if created successfully
        """
        return self.composer.create_composite_skill(
            name, description, component_skills, instructions
        )
    
    def record_execution(
        self,
        skill_name: str,
        success: bool,
        execution_time_ms: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """
        Record skill execution for statistics.
        
        Args:
            skill_name: Skill name
            success: Whether execution succeeded
            execution_time_ms: Execution time
            context: Additional context
        """
        self.repository.record_execution(
            skill_name, success, execution_time_ms, context
        )
    
    def get_skill_stats(self, name: str) -> dict[str, Any] | None:
        """
        Get statistics for a skill.
        
        Args:
            name: Skill name
        
        Returns:
            Statistics dict or None
        """
        return self.repository.get_skill_stats(name)
    
    def get_skill_history(self, name: str, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get execution history for a skill.
        
        Args:
            name: Skill name
            limit: Maximum records
        
        Returns:
            List of execution records
        """
        return self.repository.get_skill_history(name, limit)
    
    def analyze_coverage(self, task_description: str) -> dict[str, Any]:
        """
        Analyze how well skills cover a task.
        
        Args:
            task_description: Task to analyze
        
        Returns:
            Coverage analysis
        """
        return self.composer.analyze_skill_coverage(task_description)
    
    def suggest_compositions(
        self, query: str, num_suggestions: int = 3
    ) -> list[dict[str, Any]]:
        """
        Suggest skill compositions for a query.
        
        Args:
            query: Task query
            num_suggestions: Number of suggestions
        
        Returns:
            List of suggested compositions
        """
        return self.composer.suggest_compositions(query, num_suggestions)
    
    def delete_skill(self, name: str) -> bool:
        """
        Delete a skill.
        
        Args:
            name: Skill name
        
        Returns:
            True if deleted successfully
        """
        success = self.repository.delete_skill(name)
        
        if success and self.auto_sync:
            self.vector_search.remove_skill(name)
            self.vector_search.save()
        
        return success
    
    def rebuild_index(self) -> None:
        """Rebuild vector index from repository."""
        logger.info("Rebuilding vector index from repository")
        
        all_skills = self.repository.list_skills()
        skills_data = []
        
        for skill_info in all_skills:
            skill = self.repository.get_skill(skill_info["name"])
            if skill:
                skills_data.append((skill["name"], skill["content"]))
        
        self.vector_search.rebuild_index(skills_data)
        logger.info(f"Index rebuilt with {len(skills_data)} skills")
    
    def _sync_vector_index(self) -> None:
        """Sync vector index with repository if needed."""
        repo_skills = set(s["name"] for s in self.repository.list_skills())
        index_skills = set(self.vector_search._skill_mapping.values())
        
        if repo_skills != index_skills:
            logger.info("Syncing vector index with repository")
            self.rebuild_index()
    
    def get_system_stats(self) -> dict[str, Any]:
        """
        Get overall system statistics.
        
        Returns:
            System stats dict
        """
        skills = self.repository.list_skills()
        
        total_skills = len(skills)
        by_type = {}
        total_usage = 0
        total_success = 0
        
        for skill in skills:
            skill_type = skill.get("skill_type", "basic")
            by_type[skill_type] = by_type.get(skill_type, 0) + 1
            total_usage += skill.get("usage_count", 0)
            total_success += skill.get("success_count", 0)
        
        success_rate = total_success / total_usage if total_usage > 0 else 0.0
        
        return {
            "total_skills": total_skills,
            "skills_by_type": by_type,
            "total_executions": total_usage,
            "overall_success_rate": success_rate,
            "storage_dir": str(self.storage_dir),
            "vector_index_stats": self.vector_search.get_stats(),
        }
    
    def export_skill(self, name: str, output_path: Path | str) -> bool:
        """
        Export a skill to a file.
        
        Args:
            name: Skill name
            output_path: Output file path
        
        Returns:
            True if exported successfully
        """
        skill = self.get_skill(name)
        if not skill:
            return False
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create formatted export
        content_parts = [
            f"# {skill['name']}",
            "",
            f"**Type:** {skill.get('skill_type', 'basic')}",
            f"**Description:** {skill.get('description', 'No description')}",
            f"**Version:** {skill.get('version', 1)}",
            "",
        ]
        
        if skill.get("tags"):
            content_parts.append(f"**Tags:** {', '.join(skill['tags'])}")
            content_parts.append("")
        
        if skill.get("dependencies"):
            content_parts.append(f"**Dependencies:** {', '.join(skill['dependencies'])}")
            content_parts.append("")
        
        content_parts.append("## Content")
        content_parts.append("")
        content_parts.append(skill.get("content", ""))
        
        output_file.write_text("\n".join(content_parts), encoding="utf-8")
        logger.info(f"Exported skill '{name}' to {output_path}")
        return True
    
    def import_skill_from_file(self, file_path: Path | str) -> bool:
        """
        Import a skill from a file.
        
        Args:
            file_path: Path to skill file
        
        Returns:
            True if imported successfully
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return False
        
        content = file_path.read_text(encoding="utf-8")
        
        # Extract metadata (simplified parser)
        lines = content.split("\n")
        name = file_path.stem
        description = ""
        skill_type = "basic"
        
        for line in lines:
            if line.startswith("**Type:**"):
                skill_type = line.split(":", 1)[1].strip()
            elif line.startswith("**Description:**"):
                description = line.split(":", 1)[1].strip()
        
        try:
            self.add_skill(
                name=name,
                content=content,
                skill_type=skill_type,
                description=description,
            )
            logger.info(f"Imported skill '{name}' from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to import skill: {e}")
            return False
