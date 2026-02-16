"""Skill composer for automatic composition and chaining."""

from __future__ import annotations

from typing import Any

from loguru import logger


class SkillComposer:
    """
    Automatic skill composition and chaining.
    
    Features:
    - Analyzes task requirements
    - Finds matching skills from repository
    - Composes multi-step skill chains
    - Validates dependencies
    - Generates composite skills
    """
    
    def __init__(self, skill_manager):
        """
        Initialize composer.
        
        Args:
            skill_manager: Reference to SkillManager instance
        """
        self.manager = skill_manager
    
    def compose_for_task(
        self,
        task_description: str,
        max_skills: int = 5,
        skill_type_priority: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Compose a sequence of skills for a given task.
        
        Args:
            task_description: Natural language task description
            max_skills: Maximum number of skills in composition
            skill_type_priority: Priority order for skill types (e.g., ["meta", "composite", "basic"])
        
        Returns:
            List of skill dicts in execution order
        """
        if skill_type_priority is None:
            skill_type_priority = ["meta", "composite", "basic"]
        
        logger.info(f"Composing skills for task: {task_description}")
        
        # Search for relevant skills hierarchically
        composition = []
        seen_skills = set()
        
        for skill_type in skill_type_priority:
            results = self.manager.search_skills(
                task_description,
                limit=max_skills,
                skill_type=skill_type,
            )
            
            for result in results:
                skill_name = result["skill_name"]
                
                if skill_name in seen_skills:
                    continue
                
                # Get full skill info
                skill = self.manager.get_skill(skill_name)
                if skill:
                    composition.append({
                        "skill": skill,
                        "relevance_score": result["score"],
                        "reason": f"Matched for {skill_type} level",
                    })
                    seen_skills.add(skill_name)
                    
                    if len(composition) >= max_skills:
                        break
            
            if len(composition) >= max_skills:
                break
        
        # Resolve and order by dependencies
        ordered_composition = self._resolve_dependencies(composition)
        
        logger.info(f"Composed {len(ordered_composition)} skills: {[s['skill']['name'] for s in ordered_composition]}")
        return ordered_composition
    
    def _resolve_dependencies(self, skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Order skills based on dependencies (topological sort).
        
        Args:
            skills: List of skill dicts
        
        Returns:
            Ordered list of skills
        """
        # Build dependency graph
        skill_map = {s["skill"]["name"]: s for s in skills}
        graph: dict[str, list[str]] = {}
        in_degree: dict[str, int] = {}
        
        for s in skills:
            name = s["skill"]["name"]
            deps = s["skill"].get("dependencies", [])
            
            graph[name] = []
            if name not in in_degree:
                in_degree[name] = 0
            
            for dep in deps:
                if dep in skill_map:
                    graph[dep].append(name)
                    in_degree[name] = in_degree.get(name, 0) + 1
        
        # Topological sort (Kahn's algorithm)
        queue = [name for name in graph if in_degree[name] == 0]
        ordered = []
        
        while queue:
            current = queue.pop(0)
            ordered.append(skill_map[current])
            
            for neighbor in graph.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # If not all skills were ordered, there's a cycle or missing deps
        if len(ordered) < len(skills):
            logger.warning("Circular dependencies detected, using original order")
            return skills
        
        return ordered
    
    def validate_composition(self, composition: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Validate a skill composition.
        
        Args:
            composition: List of skill dicts
        
        Returns:
            Validation result with status and issues
        """
        issues = []
        warnings = []
        
        skill_names = {s["skill"]["name"] for s in composition}
        
        # Check dependencies
        for item in composition:
            skill = item["skill"]
            for dep in skill.get("dependencies", []):
                if dep not in skill_names:
                    # Check if dependency exists in repository
                    dep_skill = self.manager.get_skill(dep)
                    if not dep_skill:
                        issues.append(f"Skill '{skill['name']}' depends on missing skill '{dep}'")
                    else:
                        warnings.append(f"Skill '{skill['name']}' depends on '{dep}' which is not in composition")
        
        # Check for skill type consistency
        types = [s["skill"].get("skill_type", "basic") for s in composition]
        if "meta" in types and types.index("meta") != 0:
            warnings.append("Meta-skill should typically be first in composition")
        
        is_valid = len(issues) == 0
        
        return {
            "valid": is_valid,
            "issues": issues,
            "warnings": warnings,
            "skill_count": len(composition),
        }
    
    def create_composite_skill(
        self,
        name: str,
        description: str,
        component_skills: list[str],
        instructions: str | None = None,
    ) -> bool:
        """
        Create a new composite skill from existing skills.
        
        Args:
            name: Name for the composite skill
            description: Description of the composite skill
            component_skills: List of skill names to compose
            instructions: Optional additional instructions
        
        Returns:
            True if created successfully
        """
        # Validate all component skills exist
        components = []
        for skill_name in component_skills:
            skill = self.manager.get_skill(skill_name)
            if not skill:
                logger.error(f"Component skill '{skill_name}' not found")
                return False
            components.append(skill)
        
        # Generate composite skill content
        content_parts = [
            f"# {name}",
            "",
            description,
            "",
            "## Component Skills",
            "",
        ]
        
        for skill in components:
            content_parts.append(f"### {skill['name']}")
            content_parts.append(skill.get("description", "No description"))
            content_parts.append("")
        
        if instructions:
            content_parts.append("## Execution Instructions")
            content_parts.append(instructions)
            content_parts.append("")
        
        content_parts.append("## Workflow")
        content_parts.append("")
        for idx, skill in enumerate(components, 1):
            content_parts.append(f"{idx}. **{skill['name']}**: {skill.get('description', 'Execute this skill')}")
        
        content = "\n".join(content_parts)
        
        # Add to repository
        try:
            self.manager.add_skill(
                name=name,
                content=content,
                skill_type="composite",
                description=description,
                tags=["composite", "auto-generated"],
                dependencies=component_skills,
            )
            logger.info(f"Created composite skill '{name}' from {len(component_skills)} components")
            return True
        except Exception as e:
            logger.error(f"Failed to create composite skill: {e}")
            return False
    
    def suggest_compositions(
        self, query: str, num_suggestions: int = 3
    ) -> list[dict[str, Any]]:
        """
        Suggest possible skill compositions for a query.
        
        Args:
            query: Task query
            num_suggestions: Number of suggestions to generate
        
        Returns:
            List of suggested compositions
        """
        suggestions = []
        
        # Get top skills for each type
        for i in range(num_suggestions):
            # Vary the search approach for diversity
            if i == 0:
                # Meta-first approach
                priority = ["meta", "composite", "basic"]
            elif i == 1:
                # Composite-first approach
                priority = ["composite", "basic", "meta"]
            else:
                # Basic-first approach
                priority = ["basic", "composite", "meta"]
            
            composition = self.compose_for_task(
                query,
                max_skills=5,
                skill_type_priority=priority,
            )
            
            if composition:
                validation = self.validate_composition(composition)
                suggestions.append({
                    "composition": composition,
                    "validation": validation,
                    "approach": f"{priority[0]}-first",
                })
        
        return suggestions
    
    def analyze_skill_coverage(self, task_description: str) -> dict[str, Any]:
        """
        Analyze how well current skills cover a task.
        
        Args:
            task_description: Task to analyze
        
        Returns:
            Coverage analysis
        """
        # Search across all levels
        meta_skills = self.manager.search_skills(task_description, limit=3, skill_type="meta")
        composite_skills = self.manager.search_skills(task_description, limit=5, skill_type="composite")
        basic_skills = self.manager.search_skills(task_description, limit=10, skill_type="basic")
        
        # Calculate coverage scores
        avg_meta_score = sum(s["score"] for s in meta_skills) / len(meta_skills) if meta_skills else 0.0
        avg_composite_score = sum(s["score"] for s in composite_skills) / len(composite_skills) if composite_skills else 0.0
        avg_basic_score = sum(s["score"] for s in basic_skills) / len(basic_skills) if basic_skills else 0.0
        
        overall_score = (avg_meta_score * 0.4 + avg_composite_score * 0.3 + avg_basic_score * 0.3)
        
        return {
            "overall_coverage": overall_score,
            "meta_coverage": avg_meta_score,
            "composite_coverage": avg_composite_score,
            "basic_coverage": avg_basic_score,
            "meta_skills_found": len(meta_skills),
            "composite_skills_found": len(composite_skills),
            "basic_skills_found": len(basic_skills),
            "recommendation": self._get_recommendation(overall_score),
        }
    
    def _get_recommendation(self, coverage_score: float) -> str:
        """Get recommendation based on coverage score."""
        if coverage_score > 0.7:
            return "Good coverage - existing skills can handle this task"
        elif coverage_score > 0.4:
            return "Moderate coverage - consider creating composite skill"
        else:
            return "Low coverage - consider creating new skills"
