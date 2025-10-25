from pydantic import Field
from google.adk.agents import Agent, LlmAgent, ParallelAgent, SequentialAgent
from pydantic import BaseModel
from typing import List, Dict, Literal
import os
from .utils import load_instructions, format_phases_for_prompt, load_text


# Steps
# 1. Generate 50 personas of varying archetypes
# 2. Each of these personas should have some opinion on the state of the hurricane
#
class PhaseResponse(BaseModel):
    decision: Literal[
        "stay_home",
        "evacuate",
        "shelter_in_place",
        "help_neighbors",
        "gather_info",
        "wait_and_see",
    ]
    sentiment: Literal[
        "calm", "concerned", "anxious", "panicked", "skeptical", "defiant"
    ]
    location: Literal["home", "evacuating", "shelter", "with_family", "helping_others"]
    actions_taken: List[str] = Field(
        description="Bullet points of actions taken during this phase"
    )
    personality_reasoning: str = Field(
        description="1-2 sentences explaining why this persona made these decisions"
    )


class PersonaDetailedSchema(BaseModel):
    race: str
    age: int
    sex: str
    bio: str = Field(
        description="Detailed biography including occupation, family, housing, resources"
    )
    representation: float = Field(
        description="Estimated % of population this persona represents (0-100)"
    )
    response: List[PhaseResponse] = Field(
        description="Array of phase responses in chronological order (index 0 = phase 1, index 1 = phase 2, etc.)"
    )


sub_agents: List[LlmAgent] = []


# Total number of agents to generate
TOTAL_AGENTS = 20

# Archetype proportions (percentages as decimals: 0.30 = 30%, 0.05 = 5%)
# Note: These should sum to approximately 1.0 (100%)
ARCHETYPE_PROPORTIONS = {
    "lowincome": 0.30,  # 30% of population
    "middleclass": 0.24,  # 24% of population
    "retired": 0.20,  # 20% of population
    "underemployed": 0.16,  # 16% of population
    "highincome": 0.06,  # 6% of population
    "student": 0.04,  # 4% of population
}

# Archetype descriptions
ARCHETYPE_DESCRIPTIONS = {
    "lowincome": "low-income, high risk, socially connected",
    "middleclass": "middle-class, low risk, socially average",
    "retired": "retired, high risk, socially limited",
    "underemployed": "under-employed, medium risk, socially connected",
    "highincome": "high-income, medium risk, socially active",
    "student": "student, low risk, socially connected",
}

# Load the archetype template once and render per-archetype by replacing {ARCHETYPE_DESC} and {EMERGENCY_PHASES}
_archetype_template = load_instructions("prompts/archetype_template.txt")
# Allow overriding the emergency phases via an environment variable so the FASTAPI wrapper
# (main.py) can pass user-defined emergency plan text at runtime by setting
# EMERGENCY_PHASES in the process environment (or multi-persona-agent/.env).
_emergency_phases = os.environ.get("EMERGENCY_PHASES")
if not _emergency_phases:
    # Fallback to the on-disk template if no env override is present.
    _emergency_phases = load_text("prompts/emergency_plan.txt")

# Calculate actual counts from proportions
archetype_counts = {}
agents_allocated = 0

# First pass: calculate counts using floor
for archetype, proportion in ARCHETYPE_PROPORTIONS.items():
    count = int(TOTAL_AGENTS * proportion)
    archetype_counts[archetype] = count
    agents_allocated += count

# Second pass: distribute remaining agents to archetypes with largest remainders
remaining = TOTAL_AGENTS - agents_allocated
if remaining > 0:
    remainders = [
        (archetype, (TOTAL_AGENTS * proportion) - archetype_counts[archetype])
        for archetype, proportion in ARCHETYPE_PROPORTIONS.items()
    ]
    remainders.sort(key=lambda x: x[1], reverse=True)

    for i in range(remaining):
        archetype = remainders[i][0]
        archetype_counts[archetype] += 1

# Generate agents based on calculated archetype counts
agent_counter = 0
for archetype, count in archetype_counts.items():
    arche_desc = ARCHETYPE_DESCRIPTIONS[archetype]
    instruction_text = _archetype_template.replace(
        "{ARCHETYPE_DESC}", arche_desc
    ).replace("{EMERGENCY_PHASES}", _emergency_phases)

    for i in range(count):
        agent_counter += 1
        agent = LlmAgent(
            name=f"{archetype}_{i + 1}",
            model="gemini-2.0-flash",
            instruction=instruction_text,
            description=f"{archetype} population subset description",
            output_key=f"{archetype}_{i + 1}_key",
            # 👇 Enforce detailed persona output with phase responses
            output_schema=PersonaDetailedSchema,
        )
        sub_agents.append(agent)

# Total agents: sum of all archetype counts
print(f"Generated {agent_counter} persona agents from {TOTAL_AGENTS} requested")
print(f"Distribution: {archetype_counts}")


# Single ParallelAgent for all personas (FASTER than waves)
all_personas_agent = ParallelAgent(
    name="all_personas",
    sub_agents=sub_agents,
    description=f"All {len(sub_agents)} persona agents running in parallel",
)


# --- Output schema for the merger (the big final object you already use) ---
class outputSchema(BaseModel):
    output: str = Field(description="test")


# --- Merger Agent ---
# TIP in your synthesis_prompt.txt:
# - Read only persona keys that end with "_review".
# - Ignore any missing keys (some personas may fail).
# - Produce exactly ONE final JSON into output_key="final_summary".
merger_agent = LlmAgent(
    name="merger_agent",
    model="gemini-2.5-flash-lite",
    instruction=load_instructions("prompts/summarizer_instructions.txt"),
    description="Summarizes the entire sentiment of all population subsets",
    output_schema=outputSchema,
    output_key="final_summary",
)

# --- Sequential Pipeline (optimized for speed) ---
# Single parallel execution of all personas, then merger
sequential_pipeline_agent = SequentialAgent(
    name="FinalAnalysisAgent",
    sub_agents=[
        all_personas_agent,  # Phase 1: All personas in parallel (faster!)
        merger_agent,  # Phase 2: Merge all responses
    ],
    description="Coordinates the creation of agents and summarization of reactions to hurricane",
)


root_agent = sequential_pipeline_agent
