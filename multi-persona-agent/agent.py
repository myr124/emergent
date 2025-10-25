from pydantic import Field
from google.adk.agents import Agent, LlmAgent, ParallelAgent, SequentialAgent
from pydantic import BaseModel
from typing import List
from .utils import load_instructions


# Steps
# 1. Generate 50 personas of varying archetypes
# 2. Each of these personas should have some opinion on the state of the hurricane
#
class PersonaMiniSchema(BaseModel):
    race: str
    age: int
    sex: str
    response: str


sub_agents: List[LlmAgent] = []


personality_archetypes = {
    "lowincome": "low-income, high risk, socially connected",
    "middleclass": "middle-class, low risk, socially average",
    "retired": "retired, high risk, socially limited",
    "underemployed": "under-employed, medium risk, socially connected",
    "highincome": "high-income, medium risk, socially active",
    "student": "student, low risk, socially connected",
}

# Load the archetype template once and render per-archetype by replacing {ARCHETYPE_DESC}
_archetype_template = load_instructions("instructions/archetype_template.txt")

for archetype in personality_archetypes:
    arche_desc = personality_archetypes[archetype]
    instruction_text = _archetype_template.replace("{ARCHETYPE_DESC}", arche_desc)

    agent = LlmAgent(
        name=archetype,
        model="gemini-2.0-flash-lite",
        instruction=instruction_text,
        description=f"{archetype} population subset description",
        output_key=f"{archetype}_key",
        # 👇 Enforce tiny persona output (prevents giant blobs)
        output_schema=PersonaMiniSchema,
    )
    sub_agents.append(agent)

    # ---------------------------------------------


# 2) Batch fan-out into small ParallelAgent "waves"
#    (keeps stock ADK; reduces 429s & blast radius)
# ---------------------------------------------
def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


WAVE_SIZE = 6  # tune: 6–8 is a good start
review_waves = []
for i, wave_agents in enumerate(chunk(sub_agents, WAVE_SIZE), start=1):
    review_waves.append(
        ParallelAgent(
            name=f"subset_wave_{i}",
            sub_agents=wave_agents,
            description=f"subset wave #{i} (size={len(wave_agents)})",
        )
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
    instruction=load_instructions("instructions/summarizer_instructions.txt"),
    description="Summarizes the entire sentiment of all population subsets",
    output_schema=outputSchema,
    output_key="final_summary",
)

# --- Sequential Pipeline (unchanged pattern) ---
# Just insert the waves instead of one massive parallel.
sequential_pipeline_agent = SequentialAgent(
    name="FinalAnalysisAgent",
    sub_agents=[
        *review_waves,  # Phase 2: multiple small ParallelAgent batches
        merger_agent,  # Phase 3
    ],
    description="Coordinates the creation of agents and summarization of reactions to hurricane",
)


root_agent = sequential_pipeline_agent
