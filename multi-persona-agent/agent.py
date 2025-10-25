import json
import hashlib
import random
from typing import Any, Dict, List

from pydantic import Field, BaseModel
from google.adk.agents import Agent, LlmAgent, ParallelAgent, SequentialAgent
from .utils import load_instructions


# Steps
# 1. Generate 50 personas of varying archetypes
# 2. Produce one timeline LlmAgent per persona (50 agents total)
# 3. Each persona agent returns a condensed timeline (periodHistory) covering all periods
# 4. Run all persona agents in a single ParallelAgent, then a merger agent
# 5. Keep module-level root_agent exported at bottom (no wrapper functions)


# Demographics schema (matching API spec)
class Demographics(BaseModel):
    age: int
    race: str  # white | black | hispanic | asian | other
    socialStatus: str  # low_income | middle_income | high_income
    politicalLeaning: str  # liberal | moderate | conservative
    trustInGovernment: str  # low | medium | high
    educationLevel: str  # high_school | some_college | bachelors | graduate
    householdSize: int
    hasChildren: bool
    hasVehicle: bool
    homeOwnership: str  # rent | own


# Timeline entry for a single period
class PersonaPeriodEntry(BaseModel):
    periodNumber: int
    decision: str  # stay_home | evacuate | shelter_in_place | help_neighbors | gather_info | wait_and_see | evacuating | sheltered
    sentiment: str  # calm | concerned | anxious | panicked | skeptical | defiant
    reasoning: str
    actions: List[str]
    concerns: List[str]
    needsAssistance: bool
    location: str  # home | evacuating | shelter | with_family | helping_others


# Persona timeline schema (one per persona, covers all periods)
class PersonaTimelineSchema(BaseModel):
    personaId: str
    personaType: str
    personaName: str
    demographics: Demographics
    periodHistory: List[PersonaPeriodEntry]


# Persona type counts and labels (per API spec)
PERSONA_TYPE_COUNTS = {
    "the_planner": 5,
    "the_skeptic": 5,
    "the_altruist": 4,
    "resource_constrained": 4,
    "the_elderly": 4,
    "family_first": 4,
    "information_seeker": 4,
    "community_leader": 4,
    "tech_savvy": 4,
    "the_traditional": 4,
    "the_optimist": 4,
    "the_anxious": 4,
}  # total 50

PERSONA_TYPE_LABELS = {
    "the_planner": "The Planner",
    "the_skeptic": "The Skeptic",
    "the_altruist": "The Altruist",
    "resource_constrained": "Resource Constrained",
    "the_elderly": "The Elderly",
    "family_first": "Family First",
    "information_seeker": "Information Seeker",
    "community_leader": "Community Leader",
    "tech_savvy": "Tech Savvy",
    "the_traditional": "The Traditional",
    "the_optimist": "The Optimist",
    "the_anxious": "The Anxious",
}


# Deterministic helper to make demographics repeatable per persona id
def _rand_for(persona_id: str) -> random.Random:
    h = hashlib.sha256(persona_id.encode("utf-8")).hexdigest()
    seed = int(h[:16], 16)
    return random.Random(seed)


# Build roster (module-level)
roster: List[Dict[str, Any]] = []
for ptype, count in PERSONA_TYPE_COUNTS.items():
    for i in range(1, count + 1):
        persona_id = f"{ptype}_{i}"
        persona_name = f"{PERSONA_TYPE_LABELS.get(ptype, ptype)} #{i}"
        rnd = _rand_for(persona_id)

        race = rnd.choices(
            ["hispanic", "white", "black", "asian", "other"],
            weights=[40, 30, 20, 8, 2],
            k=1,
        )[0]

        social = rnd.choices(
            ["low_income", "middle_income", "high_income"], weights=[30, 50, 20], k=1
        )[0]

        political = rnd.choice(["liberal", "moderate", "conservative"])
        trust = rnd.choices(["low", "medium", "high"], weights=[30, 40, 30], k=1)[0]

        education = rnd.choices(
            ["high_school", "some_college", "bachelors", "graduate"],
            weights=[30, 30, 30, 10],
            k=1,
        )[0]
        household = rnd.randint(1, 6)
        has_children = household >= 3 and rnd.random() < 0.7

        if social == "low_income":
            has_vehicle = rnd.random() < 0.66
            home_ownership = "rent"
        elif social == "middle_income":
            has_vehicle = rnd.random() < 0.9
            home_ownership = rnd.choices(["rent", "own"], weights=[30, 70], k=1)[0]
        else:
            has_vehicle = True
            home_ownership = "own"

        # Adjust for persona type expectations
        if ptype == "the_planner":
            age = rnd.randint(35, 60)
            trust = "high"
            education = rnd.choice(["bachelors", "graduate"])
        elif ptype == "the_skeptic":
            age = rnd.randint(40, 70)
            trust = "low"
        elif ptype == "resource_constrained":
            age = rnd.randint(25, 65)
            social = "low_income"
            has_vehicle = rnd.random() < 0.33
            home_ownership = "rent"
            education = rnd.choice(["high_school", "some_college"])
        elif ptype == "the_elderly":
            age = rnd.randint(65, 85)
            has_vehicle = rnd.random() < 0.5
            trust = "high"
        elif ptype == "family_first":
            age = rnd.randint(28, 50)
            has_children = True
            household = rnd.randint(3, 6)
            has_vehicle = True
        elif ptype == "information_seeker":
            age = rnd.randint(25, 55)
            education = rnd.choice(["some_college", "bachelors", "graduate"])
        elif ptype == "the_anxious":
            age = rnd.randint(20, 60)
        elif ptype == "the_optimist":
            age = rnd.randint(18, 60)
        else:
            age = rnd.randint(18, 75)

        roster.append(
            {
                "personaId": persona_id,
                "personaType": PERSONA_TYPE_LABELS.get(ptype, ptype),
                "personaName": persona_name,
                "demographics": {
                    "age": age,
                    "race": race,
                    "socialStatus": social,
                    "politicalLeaning": political,
                    "trustInGovernment": trust,
                    "educationLevel": education,
                    "householdSize": household,
                    "hasChildren": has_children,
                    "hasVehicle": has_vehicle,
                    "homeOwnership": home_ownership,
                },
            }
        )


# Load prompts
_persona_timeline_template = load_instructions(
    "instructions/persona_timeline_prompt.txt"
)
_summarizer_instructions = load_instructions("instructions/summarizer_instructions.txt")
# keep archetype template for reference (not used here)
_archetype_template = load_instructions("instructions/archetype_template.txt")


# Build 12-period actionPlan using API spec example data (module-level)
periods: List[Dict[str, Any]] = [
    {
        "periodNumber": 1,
        "startTime": "T-120h",
        "endTime": "T-108h",
        "phase": "planning",
        "injects": [
            {
                "id": "inject-1-1",
                "time": "T-115h",
                "type": "weather_update",
                "title": "NWS Issues Tropical Storm Watch",
                "description": "National Weather Service issues tropical storm watch for South Florida. System currently at 50 mph winds, expected to strengthen.",
                "severity": "medium",
            }
        ],
        "eocActions": [
            {
                "id": "action-1-1",
                "time": "T-118h",
                "actionType": "public_announcement",
                "details": "EOC activates Level 1. Public advised to monitor weather and review emergency plans.",
                "targetPopulation": "All residents",
            }
        ],
    },
    {
        "periodNumber": 2,
        "startTime": "T-108h",
        "endTime": "T-96h",
        "phase": "planning",
        "injects": [],
        "eocActions": [],
    },
    {
        "periodNumber": 3,
        "startTime": "T-96h",
        "endTime": "T-84h",
        "phase": "planning",
        "injects": [],
        "eocActions": [],
    },
    {
        "periodNumber": 4,
        "startTime": "T-84h",
        "endTime": "T-72h",
        "phase": "planning",
        "injects": [
            {
                "id": "inject-4-1",
                "time": "T-85h",
                "type": "forecast_change",
                "title": "Hurricane Upgraded to Category 3",
                "description": "NWS upgrades storm to Category 3 hurricane with 125 mph winds. Landfall expected in 72-84 hours.",
                "severity": "high",
            },
            {
                "id": "inject-4-2",
                "time": "T-80h",
                "type": "infrastructure",
                "title": "Gas Stations Report Increased Demand",
                "description": "Gas stations across county reporting 30% increase in fuel sales. Some stations experiencing temporary shortages.",
                "severity": "medium",
            },
        ],
        "eocActions": [
            {
                "id": "action-4-1",
                "time": "T-85h",
                "actionType": "evacuation_order",
                "zone": "Zone A",
                "urgency": "voluntary",
                "details": "Issue voluntary evacuation order for coastal Zone A (mobile homes, low-lying areas)",
                "targetPopulation": "Coastal residents, mobile homes",
            }
        ],
    },
    {
        "periodNumber": 5,
        "startTime": "T-72h",
        "endTime": "T-60h",
        "phase": "preparation",
        "injects": [],
        "eocActions": [],
    },
    {
        "periodNumber": 6,
        "startTime": "T-60h",
        "endTime": "T-48h",
        "phase": "preparation",
        "injects": [
            {
                "id": "inject-6-1",
                "time": "T-60h",
                "type": "weather_update",
                "title": "Hurricane Forecast Updated",
                "description": "Confidence in landfall location increases. Direct hit on Miami-Dade now most likely scenario.",
                "severity": "high",
            }
        ],
        "eocActions": [
            {
                "id": "action-6-1",
                "time": "T-60h",
                "actionType": "shelter",
                "details": "Open primary emergency shelter at County High School (capacity: 500)",
                "targetPopulation": "General public",
            },
            {
                "id": "action-6-2",
                "time": "T-55h",
                "actionType": "evacuation_order",
                "zone": "Zone B",
                "urgency": "voluntary",
                "details": "Expand voluntary evacuation to Zone B (flood-prone areas)",
                "targetPopulation": "Flood-prone neighborhoods",
            },
        ],
    },
    {
        "periodNumber": 7,
        "startTime": "T-48h",
        "endTime": "T-36h",
        "phase": "preparation",
        "injects": [],
        "eocActions": [],
    },
    {
        "periodNumber": 8,
        "startTime": "T-36h",
        "endTime": "T-24h",
        "phase": "preparation",
        "injects": [
            {
                "id": "inject-8-1",
                "time": "T-38h",
                "type": "weather_update",
                "title": "Hurricane Maintains Category 4 Strength",
                "description": "Storm now Category 4 with 145 mph winds. Storm surge 12-15 feet predicted for coastal areas.",
                "severity": "critical",
            },
            {
                "id": "inject-8-2",
                "time": "T-30h",
                "type": "public_behavior",
                "title": "Traffic Congestion on Evacuation Routes",
                "description": "I-95 Northbound experiencing heavy delays. Travel time to Broward County increased to 3+ hours.",
                "severity": "high",
            },
        ],
        "eocActions": [
            {
                "id": "action-8-1",
                "time": "T-38h",
                "actionType": "evacuation_order",
                "zone": "Zones A, B, and C",
                "urgency": "mandatory",
                "details": "Mandatory evacuation order for Zones A, B, and C. All residents must evacuate immediately.",
                "targetPopulation": "Zones A, B, C - approximately 150,000 residents",
            },
            {
                "id": "action-8-2",
                "time": "T-36h",
                "actionType": "contraflow",
                "details": "Activate contraflow on I-95 Northbound. All lanes now outbound from Miami-Dade.",
                "targetPopulation": "Evacuating residents",
            },
            {
                "id": "action-8-3",
                "time": "T-32h",
                "actionType": "shelter",
                "details": "Open secondary shelters: West High School (300), North Community Center (200)",
                "targetPopulation": "General public",
            },
        ],
    },
    {
        "periodNumber": 9,
        "startTime": "T-24h",
        "endTime": "T-12h",
        "phase": "response",
        "injects": [],
        "eocActions": [],
    },
    {
        "periodNumber": 10,
        "startTime": "T-12h",
        "endTime": "T-6h",
        "phase": "response",
        "injects": [],
        "eocActions": [],
    },
    {
        "periodNumber": 11,
        "startTime": "T-6h",
        "endTime": "T+6h",
        "phase": "response",
        "injects": [],
        "eocActions": [],
    },
    {
        "periodNumber": 12,
        "startTime": "T+6h",
        "endTime": "T+18h",
        "phase": "recovery",
        "injects": [],
        "eocActions": [],
    },
]


# Build persona-level agents (one agent per persona that returns a periodHistory)
sub_agents: List[LlmAgent] = []
all_periods_json = json.dumps(periods, ensure_ascii=False)

for persona in roster:
    demographics_json = json.dumps(persona["demographics"], ensure_ascii=False)
    rendered = _persona_timeline_template.replace("{PERSONA_ID}", persona["personaId"])
    rendered = rendered.replace("{PERSONA_TYPE}", persona["personaType"])
    rendered = rendered.replace("{PERSONA_NAME}", persona["personaName"])
    rendered = rendered.replace("{DEMOGRAPHICS_JSON}", demographics_json)
    rendered = rendered.replace("{ALL_PERIODS_JSON}", all_periods_json)
    # Optionally provide a time hint (use period 4 startTime as a mid-scenario hint)
    rendered = rendered.replace("{TIME_HINT}", periods[3].get("startTime", ""))

    pid = persona["personaId"]
    agent_name = f"{pid}_timeline"
    llm_agent = LlmAgent(
        name=agent_name,
        model="gemini-2.0-flash-lite",
        instruction=rendered,
        description=f"{persona['personaType']} timeline across all periods",
        output_key=f"{agent_name}_output",
        output_schema=PersonaTimelineSchema,
    )
    sub_agents.append(llm_agent)


# Run all persona timeline agents in a single ParallelAgent
all_personas_parallel = ParallelAgent(
    name="all_personas_timeline_parallel",
    sub_agents=sub_agents,
    description=f"All persona timeline agents (size={len(sub_agents)})",
)


# Final merger/summarizer agent
class FinalSummarySchema(BaseModel):
    scenarioId: str
    generationTime: float
    status: str  # "completed" or "error"
    error: str | None = None
    periodResults: List[Dict[str, Any]] = []


merger_agent = LlmAgent(
    name="merger_agent",
    model="gemini-2.5-flash-lite",
    instruction=_summarizer_instructions,
    description="Summarizes persona timelines across all personas",
    output_schema=FinalSummarySchema,
    output_key="final_summary",
)


# Sequential pipeline: run the single parallel then merger
sequential_pipeline_agent = SequentialAgent(
    name="scenario_pipeline_timeline",
    sub_agents=[
        all_personas_parallel,
        merger_agent,
    ],
    description="Condensed 12-period timeline pipeline (one agent per persona)",
)


root_agent = sequential_pipeline_agent
