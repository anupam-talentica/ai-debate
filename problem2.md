
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