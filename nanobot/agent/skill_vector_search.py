"""Vector search for skills using HNSW indexing."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

from loguru import logger


class SkillVectorSearch:
    """
    HNSW-based vector search for skills.
    
    Features:
    - Fast approximate nearest neighbor search
    - Persistent index storage
    - Integration with SentenceTransformer embeddings
    - Hierarchical search support (meta/composite/basic)
    """
    
    def __init__(
        self,
        index_dir: Path | str,
        embedding_dim: int = 384,  # all-MiniLM-L6-v2 dimension
        max_elements: int = 10000,
        ef_construction: int = 200,
        m: int = 16,
    ):
        """
        Initialize vector search.
        
        Args:
            index_dir: Directory for index storage
            embedding_dim: Dimension of embeddings
            max_elements: Maximum number of skills to index
            ef_construction: HNSW construction parameter (higher = better quality, slower)
            m: HNSW M parameter (number of connections, higher = better quality, more memory)
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        self.embedding_dim = embedding_dim
        self.max_elements = max_elements
        
        # Index files
        self.index_file = self.index_dir / "skills.index"
        self.mapping_file = self.index_dir / "skills_mapping.pkl"
        
        # Lazy loading
        self._index = None
        self._embedder = None
        self._skill_mapping: dict[int, str] = {}
        self._reverse_mapping: dict[str, int] = {}
        self._ef_construction = ef_construction
        self._m = m
        
        # Load existing index if available
        if self.index_file.exists() and self.mapping_file.exists():
            self._load_index()
    
    def _get_embedder(self):
        """Get or create embedder (SentenceTransformer)."""
        if self._embedder is not None:
            return self._embedder
        
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Loaded SentenceTransformer embedder")
            return self._embedder
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer: {e}")
            raise RuntimeError("SentenceTransformer not available") from e
    
    def _get_index(self):
        """Get or create HNSW index."""
        if self._index is not None:
            return self._index
        
        try:
            import hnswlib
        except ImportError as e:
            raise RuntimeError(
                "hnswlib not installed. Install with: pip install hnswlib"
            ) from e
        
        self._index = hnswlib.Index(space="cosine", dim=self.embedding_dim)
        
        if self.index_file.exists():
            try:
                self._index.load_index(str(self.index_file), max_elements=self.max_elements)
                logger.info(f"Loaded HNSW index from {self.index_file}")
            except Exception as e:
                logger.warning(f"Failed to load index: {e}. Creating new index.")
                self._index.init_index(
                    max_elements=self.max_elements,
                    ef_construction=self._ef_construction,
                    M=self._m,
                )
        else:
            self._index.init_index(
                max_elements=self.max_elements,
                ef_construction=self._ef_construction,
                M=self._m,
            )
            logger.info("Created new HNSW index")
        
        # Set ef for search (higher = better quality, slower)
        self._index.set_ef(50)
        
        return self._index
    
    def _load_index(self) -> None:
        """Load index and mappings from disk."""
        try:
            with open(self.mapping_file, "rb") as f:
                data = pickle.load(f)
                self._skill_mapping = data.get("skill_mapping", {})
                self._reverse_mapping = data.get("reverse_mapping", {})
            
            # Index will be lazy loaded when needed
            logger.info(f"Loaded mappings for {len(self._skill_mapping)} skills")
        except Exception as e:
            logger.error(f"Failed to load mappings: {e}")
            self._skill_mapping = {}
            self._reverse_mapping = {}
    
    def _save_index(self) -> None:
        """Save index and mappings to disk."""
        try:
            index = self._get_index()
            index.save_index(str(self.index_file))
            
            with open(self.mapping_file, "wb") as f:
                pickle.dump(
                    {
                        "skill_mapping": self._skill_mapping,
                        "reverse_mapping": self._reverse_mapping,
                    },
                    f,
                )
            logger.info(f"Saved index with {len(self._skill_mapping)} skills")
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    def add_skill(self, skill_name: str, content: str, skill_type: str = "basic") -> None:
        """
        Add or update a skill in the index.
        
        Args:
            skill_name: Unique skill name
            content: Skill content to embed
            skill_type: Type of skill (for hierarchical search)
        """
        embedder = self._get_embedder()
        index = self._get_index()
        
        # Create embedding from content
        embedding = embedder.encode(content, convert_to_numpy=True)
        
        # Get or assign ID
        if skill_name in self._reverse_mapping:
            skill_id = self._reverse_mapping[skill_name]
            # Update existing
            index.mark_deleted(skill_id)
        else:
            skill_id = len(self._skill_mapping)
            self._skill_mapping[skill_id] = skill_name
            self._reverse_mapping[skill_name] = skill_id
        
        # Add to index
        index.add_items([embedding], [skill_id])
        
        logger.debug(f"Added skill '{skill_name}' to vector index (ID: {skill_id})")
    
    def remove_skill(self, skill_name: str) -> bool:
        """
        Remove a skill from the index.
        
        Args:
            skill_name: Skill name
        
        Returns:
            True if removed successfully
        """
        if skill_name not in self._reverse_mapping:
            return False
        
        skill_id = self._reverse_mapping[skill_name]
        index = self._get_index()
        
        try:
            index.mark_deleted(skill_id)
            del self._skill_mapping[skill_id]
            del self._reverse_mapping[skill_name]
            logger.info(f"Removed skill '{skill_name}' from vector index")
            return True
        except Exception as e:
            logger.error(f"Failed to remove skill '{skill_name}': {e}")
            return False
    
    def search(
        self,
        query: str,
        limit: int = 5,
        skill_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar skills.
        
        Args:
            query: Search query (natural language)
            limit: Maximum number of results
            skill_type: Optional filter by skill type
        
        Returns:
            List of results with skill_name, score, and distance
        """
        if not self._skill_mapping:
            return []
        
        embedder = self._get_embedder()
        index = self._get_index()
        
        # Embed query
        query_embedding = embedder.encode(query, convert_to_numpy=True)
        
        # Search
        try:
            # Request more results if filtering by type
            search_k = limit * 3 if skill_type else limit
            labels, distances = index.knn_query([query_embedding], k=min(search_k, len(self._skill_mapping)))
            
            results = []
            for idx, (label, distance) in enumerate(zip(labels[0], distances[0])):
                if label in self._skill_mapping:
                    skill_name = self._skill_mapping[label]
                    
                    # Convert distance to similarity score (1 - cosine_distance)
                    score = 1.0 - distance
                    
                    results.append({
                        "skill_name": skill_name,
                        "score": float(score),
                        "distance": float(distance),
                        "rank": idx + 1,
                    })
            
            return results[:limit]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def hierarchical_search(
        self,
        query: str,
        max_per_level: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Hierarchical search across skill levels.
        
        Args:
            query: Search query
            max_per_level: Maximum results per level
        
        Returns:
            Dict with meta, composite, and basic skill results
        """
        # Search across all skills first
        all_results = self.search(query, limit=max_per_level * 3)
        
        # This is a simplified version - in practice, you'd query the repository
        # to get skill types and organize results hierarchically
        
        # For now, return a structure that can be populated by the manager
        return {
            "meta": [],
            "composite": [],
            "basic": all_results[:max_per_level],
        }
    
    def rebuild_index(self, skills: list[tuple[str, str]]) -> None:
        """
        Rebuild entire index from scratch.
        
        Args:
            skills: List of (skill_name, content) tuples
        """
        logger.info(f"Rebuilding index with {len(skills)} skills")
        
        # Clear existing
        self._skill_mapping.clear()
        self._reverse_mapping.clear()
        self._index = None
        
        # Recreate index
        index = self._get_index()
        embedder = self._get_embedder()
        
        # Batch encode for efficiency
        contents = [content for _, content in skills]
        embeddings = embedder.encode(contents, convert_to_numpy=True, show_progress_bar=True)
        
        # Add all skills
        for idx, (skill_name, _) in enumerate(skills):
            self._skill_mapping[idx] = skill_name
            self._reverse_mapping[skill_name] = idx
        
        # Add to index in batch
        index.add_items(embeddings, list(range(len(skills))))
        
        # Save
        self._save_index()
        logger.info("Index rebuild complete")
    
    def save(self) -> None:
        """Save index and mappings to disk."""
        self._save_index()
    
    def get_stats(self) -> dict[str, Any]:
        """
        Get index statistics.
        
        Returns:
            Stats dict
        """
        return {
            "total_skills": len(self._skill_mapping),
            "index_file": str(self.index_file),
            "embedding_dim": self.embedding_dim,
            "max_elements": self.max_elements,
        }
