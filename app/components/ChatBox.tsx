'use client'
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import React, { useState } from "react";
import { ApiLoadingAnimation, type SimulationProgress } from "./ApiLoadingAnimation";
import { useRouter } from "next/navigation";
import type { EmergencyPlan } from "@/lib/utils/emergencyPlan";

const SIM_BACKEND_URL =
  process.env.NEXT_PUBLIC_SIM_BACKEND_URL ?? 'https://knighthacks2025backend.onrender.com';
const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

interface SimulationStatus {
  sim_id: string;
  status: 'running' | 'completed' | 'partial' | 'failed';
  total: number;
  completed: number;
  failed: number;
  cache_hits: number;
  errors?: Record<string, string>;
  list_sessions?: unknown[];
}

async function runQueuedSimulation(
  prompt: string,
  onProgress: (progress: SimulationProgress) => void
): Promise<SimulationStatus> {
  const report = (s: SimulationStatus) =>
    onProgress({ completed: s.completed, failed: s.failed, total: s.total, cacheHits: s.cache_hits });

  const created = await fetch(`${SIM_BACKEND_URL}/simulations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  if (!created.ok) {
    throw new Error(`API request failed with status: ${created.status}`);
  }

  let status: SimulationStatus = await created.json();
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  while (status.status === 'running') {
    report(status);
    if (Date.now() > deadline) {
      throw new Error('Simulation timed out');
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    const polled = await fetch(`${SIM_BACKEND_URL}/simulations/${status.sim_id}`);
    if (!polled.ok) {
      throw new Error(`API request failed with status: ${polled.status}`);
    }
    status = await polled.json();
  }
  report(status);
  return status;
}

const TTX_SCRIPT = `Hurricane Cronus – Tabletop Exercise (TTX)
A Test of Dynamic Response and Population-Centric Planning

1. Exercise Overview
Exercise Name: Hurricane Cronus TTX

Date:

Location: [Location of Exercise]

Scope: This is a tabletop exercise designed to test the emergency management team's strategic decision-making, public communication, and resource allocation capabilities during a hurricane threat. The exercise will be augmented by the Project Cassandra simulation platform, providing real-time insights into population behavior.

Mission Area(s): Preparedness, Response, Recovery

2. Exercise Objectives
Assess Population Behavior: Evaluate the team's ability to use simulated persona-based insights to understand and predict public reactions to emergency communications and orders.

Test Communication Strategies: Determine the effectiveness of different public messaging strategies by observing the reactions of diverse agent personas within the simulation.

Identify Emergent Crises: Use the simulation to identify and develop mitigation strategies for emergent social phenomena, such as the spread of misinformation, shadow evacuations, and behavioral "tipping points."

Optimize Resource Allocation: Refine plans for deploying resources (shelters, transportation, first responders) based on dynamic, behavior-driven predictions of public need.

3. Ground Rules
This is an open, low-stress, no-fault discussion. Responses should be based on current plans, policies, and authorities.

Decisions are not precedent-setting. The goal is to identify strengths and areas for improvement in a safe environment.

Do not fight the scenario; it is a tool to guide discussion. The simulation outputs are designed to challenge assumptions and provoke critical thinking.

Module 1: Initial Threat Assessment
Time: 120 to 96 Hours Before Landfall (5 to 4 Days Out)

Situation Update: A tropical storm, named Cronus, has formed in the Atlantic. The National Hurricane Center (NHC) projects a potential track toward the Florida peninsula. Early models show a significant chance of intensification, with a 5-day forecast cone covering much of Central Florida. The current forecast predicts it will be a Category 1 hurricane at this stage.

Facilitator: "You have just started your shift at the Emergency Operations Center. The initial forecast for Hurricane Cronus is on the screen. Let's begin by activating our simulation tool to get a baseline understanding of our community."

Inject #1.1 (For the Application Operator):

"Please initialize the simulation for Central Florida with the standard demographic and persona distribution. Query the system for the initial public sentiment regarding the 5-day forecast for a Category 1 storm."

(The Operator presents the initial dashboard to the participants, showing the geographical distribution of personas.)

System Response (to be read by Operator): "Initial sentiment analysis shows that 85% of the simulated population is showing low concern. 'Planner' personas are confirming their supply kits, while 'Skeptic' and 'Reluctant Homeowner' personas are showing no change in behavior. Social media monitoring shows low chatter, mostly focused on the storm potentially disrupting weekend plans."

Discussion Questions:

Based on this initial forecast and the public's low level of concern, what are the first three actions your team takes?

What should be the key message in your first public press conference and social media posts?

How does the knowledge that a significant portion of the population is predisposed to skepticism influence your initial communication strategy?

Module 2: Escalating Threat
Time: 72 to 48 Hours Before Landfall (3 to 2 Days Out)

Situation Update: Hurricane Cronus has rapidly intensified to a Category 3 hurricane. The NHC has issued a Hurricane Watch for all of Central Florida's coastal and inland counties. Forecasters now warn that Cronus is expected to become a major hurricane (Category 4) before landfall.

Facilitator: "The threat has become much more serious. Public attention is increasing, and people are beginning to make decisions. Let's test an initial public warning and see how our population reacts."

Inject #2.1 (For the Application Operator):

"Issue a voluntary evacuation recommendation for all coastal Evacuation Zones (Zone A). Broadcast the alert in English, Spanish, and Haitian Creole. Monitor the immediate behavioral response of all personas in that zone and identify any emergent social media narratives."

(The Operator presents the updated map, showing some agents beginning to move and highlighting social media activity.)

System Response (to be read by Operator): "The voluntary order has triggered an immediate 30% evacuation rate among 'Planner' personas in Zone A. However, 90% of 'Skeptic' and 'Reluctant Homeowner' personas are ignoring the voluntary order. A 'Social Media Influencer' persona has just posted: 'Here we go again, another over-hyped storm. I'm staying put. #FloridaStrong.' The simulation shows this post is being shared and liked primarily by other 'Skeptic' agents, reinforcing their decision to stay."

Discussion Questions:

Your voluntary evacuation is only partially effective. What is your next move? Do you escalate the messaging, or wait?

The simulation has identified a counter-narrative of skepticism spreading on social media. How do you address this specific piece of misinformation?

What resources do you begin to stage at this point, knowing that a significant portion of the population is delaying their decision?

Module 3: Imminent Threat & Critical Decisions
Time: 36 to 24 Hours Before Landfall (1.5 to 1 Day Out)

Situation Update: Cronus is now a powerful Category 4 hurricane. The NHC has upgraded the watch to a Hurricane Warning. A devastating storm surge is predicted for coastal areas. The governor has declared a state of emergency. The decision to issue mandatory evacuation orders now rests with you.

Facilitator: "This is the critical decision point. Your actions in the next few hours will determine the outcome for thousands. Let's use the simulation to test our primary evacuation plan."

Inject #3.1 (For the Application Operator):

"Issue a mandatory evacuation order for Zones A and B. Open three public shelters: 'Shelter 1' (Pet-Friendly), 'Shelter 2' (General), and 'Shelter 3' (General). What is the immediate evacuation uptake, the projected traffic congestion on I-4 and SR 528, and the projected fill rate for the shelters?"

(The Operator displays the map, which now shows heavy traffic on major arteries. The shelter capacity dashboard is also shown.)

System Response (to be read by Operator): "Evacuation uptake is now at 70% across all personas except 'Skeptics.' Traffic analysis predicts gridlock on I-4 eastbound within 90 minutes. SR 528 is also at 95% capacity. The 'Pet-Friendly' shelter is projected to be over capacity in 2 hours, while the other two shelters are only at 40% projected capacity. We are detecting that multiple 'Devoted Pet Owner' personas located in Zone A are refusing to leave because they cannot get to the single pet-friendly shelter."

Inject #3.2 (For the Application Operator):

"A 'Social Media Influencer' persona has just posted a false rumor: 'Police are closing all bridges to the beaches in one hour to stop looting!' What is the immediate impact on agent behavior?"

(The Operator updates the map to show the new, chaotic traffic patterns.)

System Response (to be read by Operator): "The rumor has caused a social 'tipping point.' A significant number of agents who were preparing to leave are now panicking and getting on the road immediately. This has caused a cascading traffic failure on secondary roads as agents attempt to find alternate routes, creating gridlock in areas that were previously clear."

Discussion Questions:

The pet-friendly shelter is full, and pet owners are refusing to leave. What is your decision?

The simulation shows a traffic nightmare unfolding due to a social media rumor. What immediate, concrete actions can you take to mitigate this?

Based on the predicted traffic jams, do you alter your advice to the public about evacuation routes? How?

Module 4: Final Hours & Non-Compliance
Time: 12 to 0 Hours Before Landfall

Situation Update: The outer bands of Hurricane Cronus are beginning to affect the region. Winds are gusting to tropical-storm force. Conditions are rapidly deteriorating. The window for safe evacuation is closing.

Facilitator: "Despite your best efforts, a number of people have remained in the mandatory evacuation zones. We need to understand who is left and why, to plan for rescue operations."

Inject #4.1 (For the Application Operator):

"Query all agent personas remaining in Zones A and B. Ask them for their primary reason for not evacuating. Categorize and display the results."

(The Operator presents a summary of the agent "interviews".)

System Response (to be read by Operator): "Analysis of the remaining 20% of agents shows:

45% are 'Skeptic' or 'Reluctant Homeowner' personas who now realize the danger but feel it is too late and unsafe to leave.

30% are 'Resource-Constrained' personas who report having no transportation or financial means to evacuate.

15% are 'Altruist' personas who are still attempting to help neighbors.

10% are 'Devoted Pet Owners' who could not find a suitable shelter for their animals."

Inject #4.2 (For the Application Operator):

"Simulate a power outage for the western half of Zone B, where a high concentration of 'Resource-Constrained' seniors are located."

System Response (to be read by Operator): "The power outage has put the 'Resource-Constrained' persona, who is dependent on an oxygen concentrator, into a 'Distress' state. They are now calling for emergency medical services."

Discussion Questions:

You now have a clear breakdown of why people have stayed. How does this intelligence shape your immediate search-and-rescue plans post-landfall?

The power has failed, and a medically vulnerable person is in immediate danger. Your team is stretched thin. How do you prioritize this rescue call against other incoming emergencies?

What message do you broadcast to those who have sheltered in place, knowing their various reasons for doing so?

5. End of Exercise & Hot Wash
Facilitator: "Hurricane Cronus has now made landfall. This concludes the exercise."

The facilitator should now lead a "hot wash," or an informal after-action review, to capture immediate feedback from the participants.

Hot Wash Discussion Points:

What was the most valuable insight you gained from interacting with the persona-based simulation?

How did the simulation change your decision-making process compared to a traditional TTX?

What was the biggest weakness in our current plan that the simulation exposed?

What is one concrete action we will take to improve our emergency operations plan based on what we learned today?`;

interface ChatBoxProps {
  selectedPlan: EmergencyPlan | null;
}

const ChatBox: React.FC<ChatBoxProps> = ({ selectedPlan }) => {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState<SimulationProgress | null>(null);
  const router = useRouter();

  const handleStart = async () => {
    if (!selectedPlan) {
      alert('Please select a session from the sidebar first.');
      return;
    }

    setIsLoading(true);
    setProgress(null);

    try {
      // Convert the selected plan to a formatted JSON string for the prompt
      const promptData = JSON.stringify(selectedPlan, null, 2);

      // Queue the run: the backend fans it out to one job per persona and a
      // worker pool runs them, so we poll for progress instead of holding a request open.
      const data = await runQueuedSimulation(promptData, setProgress);
      console.log('API Response:', data);

      if (data.status === 'failed') {
        const firstError = Object.values(data.errors ?? {})[0];
        throw new Error(`All personas failed${firstError ? `: ${firstError}` : ''}`);
      }
      if (data.status === 'partial') {
        console.warn(`${data.failed} of ${data.total} personas failed:`, data.errors);
      }

      // Store the response and navigate to simulation
      localStorage.setItem('scenarioData', JSON.stringify(data));

      // Navigate to simulation page
      router.push('/simulation-v2');
    } catch (error) {
      console.error('Error calling API:', error);
      alert('Failed to generate scenario. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {isLoading && <ApiLoadingAnimation progress={progress} />}
      <div className="absolute left-0 right-0 bottom-10 flex flex-col items-center gap-2 pointer-events-none">
        {!selectedPlan && (
          <p className="text-sm text-muted-foreground font-mono">
            ← Select a session to start
          </p>
        )}
        <Button
          onClick={handleStart}
          disabled={isLoading || !selectedPlan}
          className="text-sm px-4 py-3 rounded font-mono pointer-events-auto"
          variant="default"
        >
          {selectedPlan ? 'Start Simulation' : 'Start'}
        </Button>
      </div>
    </>
  );
};

export default ChatBox;
