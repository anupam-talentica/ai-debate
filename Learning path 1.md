Learning path - 

Goal: Understand what agents actually are (beyond LLM calls) - 4 days

Learn:
	•	What is an agent vs prompt vs workflow
	•	Concepts:
		•	Planning vs execution
		•	Tool use
		•	Memory (short-term vs long-term)
		•	Reflection / retries

Build:
	•	Simple agent:
	•	Input → decide → call tool → return result

Goal: Make an agent that can act, not just respond - 4 days

Learn:
	•	Function/tool calling
	•	Structured outputs
	•	Error handling + retries

Build:
	•	Tool-using agent:
	•	Calculator
	•	Web search
	•	Database query

Goal: True agentic behavior (coordination + roles) - 7 days

Learn:
	•	Agent roles (planner, executor, critic)
	•	Communication patterns:
	•	Sequential
	•	Hierarchical (supervisor)
	•	Collaborative

Build:
	•	Assignment 1: Supervised Multi-Agent System for Blog Generation

Goal: Make agents stateful and improving - 7 days

Learn:
	•	RAG (Retrieval-Augmented Generation)
	•	Vector databases
	•	When to use memory vs not

Build:
	•	Assignment 2: Real-Time Multi-Agent Debate Chatbot with Memory

Other Concepts and Framework:
	•	Agent frameworks (ADK, LangGraph)
	•	Agent evaluation (metrics, benchmarks)
    •	Debuggin+Monitoring (Langsmith)
	•	Advance agentic patterns (ReAct pattern, Tree-of-thought / multi-step reasonin, Retry + fallback)
	•	Guardrails and safety (content filtering, ethical considerations)
    •	MCP, A2A protocols

Resources:
Course from Langgraph - https://www.youtube.com/redirect?event=video_description&redir_token=QUFFLUhqa01FTzRpeS1PR3dhTHRsemtBSzNUNXh4ZG5IQXxBQ3Jtc0ttM1hjbjhhcDF5T1NCbDVtSGZFbDl1Q01hT2pLcU9hV0lSdDBLWVFSOXphN3JKdXdmTFRlVV9ubWFTbTVPT281MWdYTDF2U0hjREYyazhBMmozSk5YR1laSV9VOFZsWUlTUExIQkFGaFUtVENlYTRGSQ&q=https%3A%2F%2Facademy.langchain.com%2Fcourses%2Fintro-to-langgraph%2F%3Futm_medium%3Dsocial%26utm_source%3Dyoutube%26utm_campaign%3Dq4-2025_youtube-academy-links_aw&v=29XE10U6ooc

Langgraph Docs - https://www.youtube.com/redirect?event=video_description&redir_token=QUFFLUhqbGpnYUFEbUFuUXIwZzJad0RDcXFqb3c0VnhJUXxBQ3Jtc0ttSHJvSktpd0NhdGhKczd5ZzZQZGFscVZGU0NCdld6eUx2Rm1PUXVoSGMxaGowUlhWUUNWZVUta0tkSURXdF9nTlVsNnROYXk1eXJEZGllbWY5TnhrRTdXS0VYUzNHcTBqVC1Ra0tBWnpSUUhnVWQwcw&q=https%3A%2F%2Flangchain-ai.github.io%2Flanggraph%2Ftutorials%2Fintroduction%2F&v=29XE10U6ooc


------------------------------------------------------------------------------
Assignment 1: Supervised Multi-Agent System for Blog Generation

Objective
Design and implement a supervised multi-agent system that generates a blog on a given topic. The system should consist of multiple specialized agents coordinated by a central Supervisor Agent.

⸻

System Components
1. Supervisor Agent
	•	Orchestrates the overall workflow
	•	Assigns tasks to agents and manages execution order
	•	Reviews intermediate outputs and ensures quality of the final result

⸻

2. Researcher Agent
	•	Gathers relevant information and data on the given topic
	•	Produces structured notes for downstream processing

⸻

3. Analyst Agent
	•	Analyzes the researcher’s output
	•	Extracts key insights and organizes them into a logical structure or outline

⸻

4. Writer Agent
	•	Converts insights into a well-structured blog
	•	Ensures clarity, coherence, and readability

⸻

Guidelines
	•	The Supervisor should coordinate the flow: Researcher → Analyst → Writer
	•	Maintain state across agents where required
	•	Add any tools as needed based on your implementation approach

⸻

Final Deliverable
	•	A working supervised multi-agent system
	•	A generated blog (~500 words) on the topic:
“When to Use an Agent as a Tool vs. an Agent as a Sub-Agent”

------------------------------------------------------------------------------

Assignment 2: Real-Time Multi-Agent Debate Chatbot with Memory

Objective
Build a multi-agent chatbot that conducts a structured, real-time debate on a given topic. Agents should interact with each other, respond to opposing arguments, and produce a final outcome moderated by a Supervisor.

⸻

System Components
1. Moderator (Supervisor Agent)
	•	Controls the debate flow and timing
	•	Assigns turns to agents
	•	Ensures structured rounds
	•	Summarizes arguments and declares the winner
	•	Decides when to use memory

⸻

2. Pro Agent
	•	Argues in favor of the topic
	•	Responds to Con agent’s arguments

⸻

3. Con Agent
	•	Argues against the topic
	•	Counters Pro agent’s arguments

⸻

Debate Structure
	1.	Opening Round
	•	Pro Agent → ~200 words
	•	Con Agent → ~200 words
	2.	Rebuttal Round
	•	Pro Agent → ~100 words (must counter Con’s points)
	•	Con Agent → ~100 words (must counter Pro’s points)
	3.	Closing Remarks
	•	Pro Agent → ~50–100 words
	•	Con Agent → ~50–100 words
	4.	Moderator Decision
	•	Summarizes both sides
	•	Declares a winner with justification

⸻

Streaming Requirement
	•	The debate should feel live and conversational
	•	Output should be streamed step-by-step, for example:
	•	“Pro Agent is presenting opening arguments…”
	•	“Con Agent is responding…”
	•	“Pro Agent is rebutting…”
	•	“Moderator is evaluating…”

⸻

Memory Requirement
	•	Store past debates including:
	•	Topic
	•	Key arguments (pro/con)
	•	Final outcome
	•	Use a vector database to:
	•	Retrieve relevant past debates for internal context
	•	Avoid repeating identical arguments
	•	Improve argument quality and diversity over time

⸻

Why Memory is Needed (with Example)
Memory helps agents behave like experienced debaters, not stateless responders.

Example:
	•	First debate: “Should AI be used in hiring?”
	•	Pro argues: efficiency, scalability
	•	Con argues: bias, lack of transparency
	•	Later debate: “Should AI replace recruiters?”

Without memory:
	•	Agents may repeat the same generic points (efficiency vs bias)

With memory:
	•	Agents can evolve arguments:
	•	Pro: “Beyond efficiency discussed earlier, AI can enable data-driven candidate matching at scale…”
	•	Con: “While bias is known, a bigger concern is over-reliance leading to loss of human judgment…”

⸻

Guidelines
	•	Agents must read and respond to each other’s arguments
	•	Memory should enhance reasoning, not be explicitly referenced
	•	Moderator controls debate flow and memory usage
	•	Add tools and implementation details as needed

⸻

Final Deliverable
	•	A working chatbot that:
	•	Accepts a debate topic
	•	Runs a structured multi-agent debate
	•	Streams responses in real-time
	•	Declares a winner
	•	Demonstrate:
	•	Agent interaction (true debate)
	•	Structured flow
	•	Meaningful use of memory