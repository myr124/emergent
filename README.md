# Emergent: AI-Powered Crisis Simulation Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

![ezgif-4c6a86316dd8fd](https://github.com/user-attachments/assets/7adb10a2-4517-4929-b0ae-9956b335c269)

Emergent is a web-based, AI-powered Tabletop Exercise (TTX) platform that allows emergency managers to simulate disaster scenarios and their impact on a community. It provides a safe, controlled, and highly detailed environment to practice, test, and refine emergency plans, with a focus on improving communication with vulnerable populations.

## The Problem

In a crisis, effective communication can save lives. However, testing communication strategies, especially for reaching diverse and vulnerable communities, is incredibly challenging. Traditional tabletop exercises are often static and resource-intensive. Emergent aims to solve this by providing a dynamic, AI-driven simulation environment that models complex human behaviors and communication patterns.

## Key Features

- **AI-Powered Scenario Generation:** Use Google's Gemini model to dynamically generate realistic disaster scenarios and narrative injects.
- **Interactive Simulation:** Run exercises on an interactive GIS map, with events unfolding over a structured timeline.
- **Persona-Based Modeling:** Simulate a diverse community with unique "personas" that react differently to events based on their demographics and roles using Google Gemini's ADK and Parallel Agents
- **AI Chat Interaction:** Engage with an Gemini AI-powered chatbot to get situational updates and test communication strategies by seeing how personas react.
- **Comprehensive After-Action Reporting:** Generate detailed reports after each simulation, including an executive summary, deep-dive analytics, and an interactive timeline replay.
- **Modern, Intuitive Interface:** A clean and responsive UI built with Next.js, Tailwind CSS, and shadcn/ui.

## Technology Stack

- **Framework:** [Next.js](https://nextjs.org/) 14+
- **Language:** [TypeScript](https://www.typescriptlang.org/)
- **AI:** [Google Gemini](https://ai.google.dev/) via `@google/generative-ai`
- **Styling:** [Tailwind CSS](https://tailwindcss.com/) with [shadcn/ui](https://ui.shadcn.com/)
- **Mapping:** [React Leaflet](https://react-leaflet.js.org/)
- **3D Visualization:** [React Three Fiber](https://docs.pmnd.rs/react-three-fiber/getting-started/introduction) & [Drei](https://github.com/pmndrs/drei)

## Getting Started

Follow these instructions to get a local copy of the project up and running for development and testing.

### Prerequisites

- Node.js (v20.x or later recommended)
- npm or yarn

### Installation

1.  **Clone the repository:**

    ```sh
    git clone https://github.com/your-username/your-repository-name.git
    cd your-repository-name
    ```

2.  **Install dependencies:**

    ```sh
    npm install
    ```

3.  **Set up environment variables:**

    This project requires an API key for the Google Gemini AI service.

    Create a file named `.env.local` in the root of the project and add your API key:

    ```
    GOOGLE_API_KEY="YOUR_API_KEY_HERE"
    ```

4.  **Run the development server:**

    ```sh
    npm run dev
    ```

    Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

### Running the simulation backend

The persona agents live in `backend/` (Python, Google ADK). Simulations run on a Redis queue drained by a worker pool, and the frontend talks to it at `NEXT_PUBLIC_SIM_BACKEND_URL`.

```sh
docker run -d --name emergent-redis -p 6379:6379 redis:7-alpine

cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
echo 'GOOGLE_API_KEY="YOUR_API_KEY_HERE"' > .env

.venv/bin/uvicorn main:app --port 8000      # API
.venv/bin/python -m simqueue.worker          # worker pool, in another terminal
```

Then add `NEXT_PUBLIC_SIM_BACKEND_URL=http://localhost:8000` to `.env.local`. Backend tests: `cd backend && .venv/bin/pip install pytest pytest-asyncio && .venv/bin/python -m pytest` (needs Redis).

### Other Scripts

- **Build for production:**

  ```sh
  npm run build
  ```

- **Run production server:**

  ```sh
  npm run start
  ```

- **Run linter:**
  ```sh
  npm run lint
  ```

## Project Structure

The codebase is organized to keep a clean separation of concerns.

- `app/`: Contains the core application logic, pages, and API routes, following the Next.js App Router structure.
  - `app/api/`: Backend API endpoints for AI generation, chat, etc.
  - `app/components/`: The majority of the React components that make up the UI.
  - `app/(pages)/`: Different top-level pages like `/editor`, `/simulation-v2`, etc.
- `components/ui/`: Core UI components from shadcn/ui.
- `lib/`: Contains utility functions, type definitions, and state management stores.
  - `lib/stores/`: State management logic (e.g., Zustand stores).
  - `lib/types/`: TypeScript type definitions for data structures like scenarios and personas.
- `public/`: Static assets like images and icons.

## Contributing

Contributions are welcome! If you have a suggestion or find a bug, please open an issue to discuss it.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
