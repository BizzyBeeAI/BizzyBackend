from __future__ import annotations

from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from backend.agents.specialists import customer_bee, finance_bee, inventory_bee, sales_bee
from backend.models.agent import AgentResponse, AgentStatus, Evidence, RecommendedAction, RiskLevel


AGENT_REGISTRY = {
    "sales": sales_bee,
    "customer": customer_bee,
    "finance": finance_bee,
    "inventory": inventory_bee,
}

# Selects which agents to run based on the question
def intent_classifier(question: str) -> List[str]:
    """Uses LLM (or fallback heuristic) to determine which specialist agents are needed."""
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the Queen Bee Orchestrator for BizzyBee AI. 
Analyze the user's business query and identify which specialist agents are required to answer it thoroughly.

Available Agents:
- 'sales': Sales trends, revenue drops, product performance, unit pricing.
- 'customer': Customer complaints, defect feedback, support enquiries, unanswered messages.
- 'finance': Cash flow, unpaid/overdue invoices, receivables.
- 'inventory': Stock levels, reorder thresholds, inventory valuation, stockouts.

Return ONLY a comma-separated list of required agent names (e.g. 'customer,sales')."""),
            ("user", "{question}")
        ])
        
        chain = prompt | llm
        result = chain.invoke({"question": question}).content.strip()
        selected = [a.strip().lower() for a in result.split(",") if a.strip().lower() in AGENT_REGISTRY]
        return selected or ["sales"]
    except Exception:
        # Fallback keyword-based matching if LLM call fails or API key is missing
        text = question.lower()
        selected = []
        if any(k in text for k in ("sale", "revenue", "decline")): selected.append("sales")
        if any(k in text for k in ("customer", "complaint", "feedback", "enquiry", "review")): selected.append("customer")
        if any(k in text for k in ("invoice", "cash", "finance", "overdue")): selected.append("finance")
        if any(k in text for k in ("stock", "inventory", "product", "shortage")): selected.append("inventory")
        return selected or ["customer"]

# Runs the selected specialist agents and returns their results
def run_specialists(question: str) -> tuple[list[str], list[AgentResponse]]:
    # 1. Intent understanding & routing
    selected_agents = intent_classifier(question)
    
    # 2. Parallel or sequential execution of chosen specialist bees
    results = []
    for name in selected_agents:
        agent_fn = AGENT_REGISTRY[name]
        results.append(agent_fn())
        
    return selected_agents, results