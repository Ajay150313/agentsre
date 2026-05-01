from langchain.agents import initialize_agent, load_tools
from langchain.agents import AgentType
from langchain.llms import OpenAI
from agentsre import AgentSLICollector, TaskRecord

# Setup your agent
llm = OpenAI(temperature=0, model="gpt-4")
tools = load_tools(["serpapi", "llm-math"], llm=llm)
agent = initialize_agent(
    tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True
)

# Add SRE instrumentation
collector = AgentSLICollector()

# Run the agent
response = agent.run("What is 2 + 2?")

# Record what happened for SLIs
collector.record(TaskRecord(
    task_id="t-001",
    task_class="math",
    tool_calls=2,
    required_escalation=False,
    pending_approval=False,
    decision_confidence=0.95,
    completed=True,
))

# See the metrics
for sli in collector.collect("math"):
    print(f"{sli.name}: {sli.value} {sli.status}")
