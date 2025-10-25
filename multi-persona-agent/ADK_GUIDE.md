LLM‑Facing Implementation Guide for google/adk-python
======================================================

Drop this whole document into your other LLM as system or developer instructions. It
teaches the model the ADK concepts and constrains its output to clean, runnable code.

0) Output Rules (very important)
Return only code blocks and minimal comments unless explicitly asked for prose.
Python ≥ 3.9 code only.
Prefer standard library + google-adk APIs. Avoid extra deps unless requested.
Use type hints and small, pure functions. Keep files short and readable.
When adding tools, define them as plain Python functions with clear docstrings and typed params/returns.
For multi‑file projects, include a minimal tree, then provide file contents in order.
If environment variables are needed, write them to .env (do not hardcode secrets).
If a command must be run, show it in a single fenced bash block.
Pass mypy/ruff/flake8 by default (PEP8, no unused imports, no wildcard imports).

1) Quick Mental Model of ADK
Agent: A unit that receives a request, thinks (LLM or workflow), and optionally uses tools.
Tools : Plain Python callables (or OpenAPI, 3rd‑party integrations) that an agent may invoke.
Models: Configure model name (e.g., "gemini-2.5-flash") and auth (e.g., GOOGLE_API_KEY).
Workflows: Compose agents via Sequential, Parallel, or Loop workflow agents.
Sessions, Memory & State: Built‑in primitives for longer interactions.
Run Surfaces: CLI (adk run) and web UI (adk web).
Eval: Built‑in evaluation harness (adk eval)
You can build a single agent, multi‑agent trees, or use LLM‑driven routing (an LlmAgent coordinating sub‑agents).

2) Project Bootstrap (scaffold)
When asked to create a new agent project, do the following:
# Create project
adkcreatemy_agent

# Install deps (inside virtualenv)
pipinstallgoogle-adk
# Add API key (Gemini by default)
echo'GOOGLE_API_KEY="YOUR_API_KEY"'> my_agent/.env
Project structure to assume: 
my_agent/
  agent.py      # main agent definition (root_agent is required)
  __init__.py
  .env          # API keys
Run surfaces: 
# CLI chat
adkrunmy_agent
# Web dev UI
adkweb--port8000my_agent

3) Canonical Single‑Agent Template
Use this as your default starting point.
# my_agent/agent.py
fromgoogle.adk.agentsimportAgent
fromtypingimportDict
# Example tool (define plain function tools with types and docstrings)
defget_current_time(city: str) -> Dict[str, str]:
    """Return the current time for a given city.
    NOTE: In real apps, call a time API. For demos, return a stubbed value.
    """
    return{"status":"success","city": city,"time":"10:30 AM"}
root_agent= Agent(
    name="time_helper",
    model="gemini-2.5-flash",# change if needed
    description="Tells the current time for a requested city.",
    instruction=(
        "You are a precise assistant. Use the get_current_time tool whenever the user "
        "asks about time in a specific city."
    ),
    tools=[get_current_time],
)
When asked to add more tools, just define more functions and include them in tools=[...].

4) Multi‑Agent (Coordinator + Specialists)
Use LlmAgent to coordinate sub‑agents. Keep agent responsibilities small.
# my_agent/agent.py
fromgoogle.adk.agentsimportLlmAgent, Agent
# Specialist 1
search_agent= Agent(
    name="search_agent",
    model="gemini-2.5-flash",
    description="Searches the web and summarizes findings.",
    instruction="Search and return concise facts with sources.",
)
# Specialist 2
writer_agent= Agent(
    name="writer_agent",
    model="gemini-2.5-flash",
    description="Writes polished paragraphs using given facts.",
    instruction="Write clear, concise paragraphs; cite inputs.",
)
# Coordinator routes tasks and aggregates responses
root_agent= LlmAgent(
    name="coordinator",
    model="gemini-2.5-flash",
    description="Coordinates research and writing tasks.",
    instruction=(
        "Decide which specialist to call based on the user request. "
        "If the request needs facts, ask search_agent. If drafting prose, ask writer_agent. "
        "Summarize final results cleanly."
    ),
    sub_agents=[search_agent, writer_agent],
)

5) Tool Patterns (Function Tools)
Follow these conventions:
- Keep parameters primitive (str/int/float/bool) or small dicts/lists.
- Add docstrings describing inputs/outputs succinctly.
- Return JSON‑serializable objects.

defweather(city: str, units: str="metric") -> dict:
    """Get weather for a city.
    Args:
        city: City name.
        units: "metric" or "imperial".
    Returns:
        dict with keys: status, city, temp, description.
    """
    # Placeholder implementation
    return{"status":"success","city": city,"temp": 21.5,"description": "clear"}

Add to an agent: 
root_agent= Agent(
    name="weather_bot",
    model="gemini-2.5-flash",
    instruction="Always call weather(city) when asked for weather.",
    tools=[weather],
)

6) Workflow Agents (Sequential / Parallel / Loop)
Use workflow agents when you need predictable pipelines.

Sequential example
fromgoogle.adk.agents.workflowimportSequential
fromgoogle.adk.agentsimportAgent
extract= Agent(name="extract", model="gemini-2.5-flash", instruction="Extract key points.")
expand= Agent(name="expand",  model="gemini-2.5-flash", instruction="Expand into a paragraph.")
polish= Agent(name="polish",  model="gemini-2.5-flash", instruction="Polish for clarity.")
root_agent= Sequential(name="pipeline", sub_agents=[extract, expand, polish])

Parallel example
fromgoogle.adk.agents.workflowimportParallel
fromgoogle.adk.agentsimportAgent
style_a= Agent(name="style_a", model="gemini-2.5-flash", instruction="Write in formal style.")
style_b= Agent(name="style_b", model="gemini-2.5-flash", instruction="Write in casual style.")
root_agent= Parallel(name="styles", sub_agents=[style_a, style_b])

Loop example
fromgoogle.adk.agents.workflowimportLoop
fromgoogle.adk.agentsimportAgent
refine= Agent(name="refine", model="gemini-2.5-flash", instruction="Improve the draft.")
root_agent= Loop(name="iterative_refine", sub_agents=[refine])

7) Runtime & Dev UI
Run locally via CLI or Web UI:
adkrunmy_agent
adkweb--port8000my_agent

Web UI tips:
- Select your agent in the top‑right dropdown.
- Inspect messages, tool calls, and intermediate steps.

8) Sessions, Memory, and State (use when asked)
Prefer stateless tools by default; opt‑in to memory for long tasks.
Store only minimal, relevant state.
If the user requests memory, use ADK session APIs (keep code minimal and documented).

9) Evaluation (smoke tests)
Provide a quick eval scaffold when asked.
# Evaluate an agent using sample cases in a folder
adkevalsamples_for_testing/hello_world
Or propose a tiny custom eval set (YAML/JSON) with expected outputs.

10) Common Recipes
A) Add a confirmation step before tool execution (HITL)
When a tool has side‑effects, gate it with a confirmation flow. Document the intent and the user‑visible prompt. Keep code minimal and use ADK’s built‑in patterns if available.
B) Use built‑in tools (e.g., Google Search)
Reference tools by import path when possible (e.g., from google.adk.tools import google_search) and add them to tools=[...].
C) Bring your own model/provider
Expose a MODEL_NAME env var and use ADK’s model configuration guidance. Keep provider‑specific code isolated.

11) Deployment
When requested, provide a minimal Dockerfile and instructions for Cloud Run. Avoid complex infra unless asked.

# Dockerfile
FROMpython:3.11-slim
WORKDIR/app
COPYmy_agent/app/my_agent
RUNpipinstall--no-cache-dirgoogle-adk
ENVPORT=8080
CMD["bash","-lc","adk web --port $PORT my_agent"]

12) Troubleshooting & Quality Bar
If a tool returns non‑JSON, normalize it before returning to the agent.
Avoid long chains of thought; keep calls short and explain failures succinctly.
Always validate parameters inside tools; raise clear exceptions.
Prefer deterministic behaviors; add docstrings that the agent can learn from.

13) Handy Snippets (ready to paste)
Environment / .env writing
echo'GOOGLE_API_KEY="YOUR_API_KEY"'> .env

Agent + two tools
fromgoogle.adk.agentsimportAgent
fromtypingimportDict
defcalc_bmi(weight_kg: float, height_m: float) -> Dict[str, float]:
    """Compute BMI = weight / height^2."""
    bmi= weight_kg/ (height_m** 2)
    return{"bmi": round(bmi, 2)}
defunit_convert(value: float, from_unit: str, to_unit: str) -> Dict[str, float]:
    """Very small unit converter demo (kg↔lb only)."""
    iffrom_unit=="kg"andto_unit=="lb":
        return{"result": value* 2.20462}
    iffrom_unit=="lb"andto_unit=="kg":
        return{"result": value/ 2.20462}
    raiseValueError("unsupported units")
root_agent= Agent(
    name="health_calc",
    model="gemini-2.5-flash",
    instruction=(
        "You can compute BMI (calc_bmi) and convert units (unit_convert). "
        "Always explain numbers briefly."
    ),
    tools=[calc_bmi, unit_convert],
)

Sequential workflow wrapper
fromgoogle.adk.agents.workflowimportSequential
fromgoogle.adk.agentsimportAgent
summarize= Agent(name="summarize", model="gemini-2.5-flash", instruction="Summarize text in 3 bullets.")
flesh_out= Agent(name="flesh_out", model="gemini-2.5-flash", instruction="Turn bullets into a paragraph.")
root_agent= Sequential(name="sum_to_paragraph", sub_agents=[summarize, flesh_out])

14) When Unsure
Prefer the simplest viable agent + tool(s).
Show the exact bash commands to run.
Keep code self‑documenting with concise docstrings and types.
Don’t invent APIs—adhere to constructs shown above.

15) Interfacing ADK (Python) with a Next.js Frontend
This section gives you concrete, copy‑paste patterns to connect a Python ADK backend to a Next.js (App Router) frontend.

Overview
Backend (Python/ADK): expose your root_agent through a small HTTP API (FastAPI recommended).
Frontend (Next.js): call the backend from server actions or /app/api routes; optionally stream tokens to the UI.
Alternatives: Use AG‑UI protocol bridges (e.g., CopilotKit) for richer agent↔UI interactions.

A) Minimal FastAPI wrapper for ADK
Create an HTTP surface that Next.js can call.

# server/main.py
fromfastapiimportFastAPI
fromfastapi.middleware.corsimportCORSMiddleware
frompydanticimportBaseModel
fromgoogle.adk.agentsimportAgent
fromtypingimportOptional, Dict, Any
# --- define or import your ADK agent ---
frommy_agent.agentimportroot_agent
# ensure this exposes an Agent-compatible entrypoint
app= FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],# lock down to your Vercel domain in prod
    allow_methods=["*"],
    allow_headers=["*"],
)
classChatRequest(BaseModel):
    input: str
    session_id: Optional[str] =None
    metadata: Optional[Dict[str, Any]] =None
@app.post("/chat")
asyncdefchat(req: ChatRequest):
    # Call the agent synchronously; for long tasks, you can make this background or streaming
    result= root_agent.run(req.input, session_id=req.session_id, metadata=req.metadataor{})
    # Standardize a JSON response schema
    return{
        "output": getattr(result,"text", str(result)),
        "raw": getattr(result,"__dict__", {}),
        "session_id": req.session_id,
    }
Run locally
uvicornserver.main:app--reload--port8080

B) Streaming tokens from ADK to Next.js
For chat UIs, expose SSE (Server‑Sent Events) to stream tokens.

# server/stream.py
fromfastapiimportFastAPI
fromfastapi.responsesimportStreamingResponse
fromgoogle.adk.agentsimportAgent
frommy_agent.agentimportroot_agent
app= FastAPI()
@app.get("/stream")
asyncdefstream(q: str):
    deftoken_gen():
        fortokeninroot_agent.stream(q):
            yieldf"data: {token}\n"
        yield"event: end\n"
    returnStreamingResponse(token_gen(),media_type="text/event-stream")

C) Next.js (App Router) calling the Python backend
Use a route handler to proxy requests (keeps secrets server-side) or call directly from a Server Action.

// app/api/chat/route.ts
import{ NextResponse}from"next/server";
exportasyncfunctionPOST(req:Request) {
    constbody=awaitreq.json();
    constr =awaitfetch(process.env.ADK_BACKEND_URL+"/chat", {
        method:"POST",
        headers: {"Content-Type":"application/json"},
        body:JSON.stringify(body),
    });
    constdata=awaitr.json();
    returnNextResponse.json(data);
}

app/page.tsx (client)
'use client';
import{ useState}from'react';
exportdefaultfunctionHome() {
    const[input, setInput] = useState("");
    const[output, setOutput] = useState("");
    return(
        <mainclassName="p-6 max-w-2xl mx-auto">
            <h1 className="text-2xl font-semibold mb-3">ADKChat</h1>
            <textareaclassName="w-full border p-2 rounded"value={input}
                onChange={e=>setInput(e.target.value)} />
            <buttonclassName="mt-3 px-4 py-2 rounded bg-black text-white"
                onClick={async() => {
                    constres=awaitfetch('/api/chat', {
                        method:'POST',
                        headers: {'Content-Type':'application/json'},
                        body:JSON.stringify({ input}),
                    });
                    constjson=awaitres.json();
                    setOutput(json.output);
                }}
            >Ask</button>
            <preclassName="mt-4 whitespace-pre-wrap">{output}</pre>
        </main>
    );
}

Streaming in Next.js (SSE client example): 
// app/stream/page.tsx
'use client';
import{ useEffect, useState}from'react';
exportdefaultfunctionStream() {
    const[buf, setBuf] = useState('');
    useEffect(()=> {
        constes =newEventSource(process.env.NEXT_PUBLIC_ADK_STREAM_URL+'/stream?q=hello');
        es.onmessage= (e) => setBuf(prev=> prev+ e.data);
        es.addEventListener('end', () => es.close());
        return() => es.close();
    }, []);
    return<preclassName="p-6">{buf}</pre>;
}

D) Authentication patterns
Put your model/API keys in the Python backend (.env), never in the Next.js client.
If you need user auth, protect /api/chat with your NextAuth middleware or signed JWTs, and validate them in the Python FastAPI app (e.g., an Authorization: Bearer header).

E) Deployment recipe (Cloud Run + Vercel)
1) Build & deploy ADK backend to Cloud Run
# Dockerfile
FROMpython:3.11-slim
WORKDIR/app
COPY. /app
RUNpipinstall--no-cache-dirgoogle-adkfastapiuvicorn[standard]
ENVPORT=8080
CMD["bash","-lc","uvicorn server.main:app --host 0.0.0.0 --port $PORT"]

Provision Cloud Run with minimal CPU/mem and set ADK_BACKEND_URL on Vercel to the HTTPS service URL.
2) Deploy Next.js to Vercel and set env vars:
- ADK_BACKEND_URL=https://<cloud-run-service-url>
- (optional) NEXT_PUBLIC_ADK_STREAM_URL if you expose /stream.

F) Using AG‑UI / CopilotKit with ADK
If you want a richer, eventful protocol between UI and agents, integrate an AG‑UI compatible bridge. A typical setup:
- Backend: keep ADK Python agents; add an AG‑UI bridge endpoint translating between UI events and agent calls.
- Frontend: Next.js + CopilotKit (or your own client) speaking the AG‑UI protocol to render thoughts, tool calls, citations, etc.

G) Testing and Evals from Next.js
Add a hidden route /api/smoke to trigger adk eval smoke tests or health checks.
Use Playwright to assert streaming renders and tool‑call UI states.

H) Gotchas
CORS : Restrict origins to your Vercel domain in prod.
Streaming over Vercel: prefer Edge-disabled route handlers for SSE (Node runtime).
Timeouts: Keep requests short or chunk work; use background jobs for long workflows.
Version drift: Pin google-adk version; check breaking changes before deploys.

I) One‑file quickstart (dev only)
If you just need a demo, run both in dev:
- Python: uvicorn server.main:app --port 8080
- Next.js: npm run dev
- Set ADK_BACKEND_URL=http://localhost:8080

J) Checklist for Production
- [ ] Auth in front of /chat
- [ ] Rate limiting & logging
- [ ] Observability (request IDs, timing, tool call traces)
- [ ] Structured responses (JSON schema)
- [ ] Evals: golden prompts, tool stubs, regression suite

K) Example: Structured JSON contract
Have the agent always respond with a strict schema; validate in Next.js.

# agent enforces schema via instruction
root_agent= Agent(
    name="planner",
    model="gemini-2.5-flash",
    instruction=(
        "Reply with JSON only: {\"summary\": str, \"actions\": [str]}"
    ),
)
# runtime check in Next.js
import{ z }from'zod';
constResp= z.object({ summary:z.string(),actions:z.array(z.string())});
# after fetch:
constparsed= Resp.parse(json.output? JSON.parse(json.output) : json);

L) Folder Layout (suggested)
backend/               # Python ADK service
  my_agent/agent.py
  server/main.py
  pyproject.toml
  Dockerfile
frontend/              # Next.js app
  app/api/chat/route.ts
  app/page.tsx
  next.config.ts

M) Security Notes
Never expose tool tokens or provider keys to the browser.
Sanitize tool inputs in Python; validate user params in Next.js API route.
Consider a per‑user session store if you enable memory.

N) References (for you, not the model)
ADK docs (Python quickstart, agents, web UI)
Community samples & frontend guides (FastAPI, AG‑UI, CopilotKit)

End of Guide
