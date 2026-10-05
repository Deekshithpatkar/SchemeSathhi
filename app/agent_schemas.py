"""
Pydantic Schemas for Checkpoint 14: AI Agent Orchestration.
Defines structured schemas for:
- Agent action requests (tool calling or completion)
- Step-by-step execution traces
- Agent state tracking
- Evaluation metrics
- Master agent execution results
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AgentAction(BaseModel):
    """Structured decision produced by the orchestrating LLM."""
    thought: str = Field(default="", description="Chain-of-thought rationale for this step")
    action: str = Field(description="Name of the tool to execute or 'finish'")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to the tool")
    final_answer: Optional[str] = Field(default=None, description="Final answer or conclusion if action is 'finish'")


class AgentTraceStep(BaseModel):
    """Execution trace entry for a single step in the agent loop."""
    step_number: int = Field(description="1-based step index")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    thought: str = Field(default="", description="Agent's reasoning at this step")
    tool_name: str = Field(description="Tool called at this step")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool")
    success: bool = Field(default=True, description="Whether tool execution succeeded")
    execution_time_ms: float = Field(default=0.0, description="Duration of tool execution in milliseconds")
    result_summary: str = Field(description="Concise summary of tool output")
    error: Optional[str] = Field(default=None, description="Error message if tool execution failed")


class AgentState(BaseModel):
    """
    Structured working memory maintained by the agent throughout execution.
    Tracks documents, hashes, extractions, comparisons, and database states.
    """
    scheme_key: Optional[str] = Field(default=None, description="Stable identifier of the target scheme")
    scheme_name: Optional[str] = Field(default=None, description="Official scheme name")
    department: Optional[str] = Field(default=None, description="Government department")
    source_url: Optional[str] = Field(default=None, description="URL of the official source portal")
    
    current_document_url: Optional[str] = Field(default=None, description="URL of the discovered document")
    current_document_path: Optional[str] = Field(default=None, description="Local path to downloaded PDF")
    current_document_hash: Optional[str] = Field(default=None, description="SHA-256 hash of the downloaded PDF")
    
    previous_version_hash: Optional[str] = Field(default=None, description="SHA-256 hash of previous version if known")
    is_unchanged_document: bool = Field(default=False, description="True if hash matches existing active version")
    
    processed_document_path: Optional[str] = Field(default=None, description="Path to Step 9 structured document JSON")
    current_extraction: Optional[Dict[str, Any]] = Field(default=None, description="CP10 extracted semantic rules")
    
    document_comparison: Optional[Dict[str, Any]] = Field(default=None, description="CP11 document comparison output")
    rule_comparison: Optional[Dict[str, Any]] = Field(default=None, description="CP12 rule comparison output")
    
    knowledge_base_update: Optional[Dict[str, Any]] = Field(default=None, description="CP13 database persistence output")
    
    review_required: bool = Field(default=False, description="Flag indicating human review is needed")
    review_reasons: List[str] = Field(default_factory=list, description="All reasons triggering human review")
    completed: bool = Field(default=False, description="True when agent finishes its objective")
    final_answer: Optional[str] = Field(default=None, description="Summary answer reported by the agent")


class AgentExecutionMetrics(BaseModel):
    """Evaluation metrics for the agent orchestration run."""
    total_steps: int = Field(default=0, description="Total steps taken in loop")
    successful_tool_calls: int = Field(default=0, description="Number of successful tool invocations")
    failed_tool_calls: int = Field(default=0, description="Number of failed tool invocations")
    unnecessary_tool_calls: int = Field(default=0, description="Number of redundant calls avoided or made")
    tool_call_rate: float = Field(default=1.0, description="Ratio of successful tool calls to total attempts")
    end_to_end_success: bool = Field(default=True, description="True if agent reached valid completion")
    review_required: bool = Field(default=False, description="True if run ended with review required")


class AgentResult(BaseModel):
    """Master output of the Checkpoint 14 AI Agent run."""
    task: str = Field(description="The user instruction or objective given to the agent")
    status: str = Field(description="'completed', 'review_required', 'failed', 'max_steps_exceeded'")
    final_answer: str = Field(description="Human-readable final outcome summary")
    review_required: bool = Field(default=False)
    review_reasons: List[str] = Field(default_factory=list)
    state: AgentState = Field(description="Final state reached by the agent")
    metrics: AgentExecutionMetrics = Field(description="Execution and performance statistics")
    trace: List[AgentTraceStep] = Field(default_factory=list, description="Chronological execution trace")
