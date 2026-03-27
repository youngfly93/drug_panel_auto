"""
基因知识库模块

提供基因诊疗知识的加载和查询功能。
"""

from .gene_knowledge import GeneKnowledgeProvider
from .mutation_description import MutationDescriptionGenerator

__all__ = ["GeneKnowledgeProvider", "MutationDescriptionGenerator"]
