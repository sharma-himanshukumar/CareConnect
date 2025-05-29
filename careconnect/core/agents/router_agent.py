from typing import TypedDict, List, Annotated, Union, Dict, Optional
import operator

# Define a type for a single step in our dynamic plan
class PlanStep(TypedDict, total=False):
    agent_to_call: str  # Name of the agent node (e.g., "drug_agent")
    goal_for_agent: str # Specific instruction for this agent in this step
    # We might add other fields later if needed, e.g., specific inputs derived by the planner

class OrchestratorState(TypedDict):
    original_query: str
    current_task_description: str # Overall task or current step's goal

    # Results from individual agents
    hospital_info: Annotated[Optional[str], operator.add]
    lab_summary_info: Annotated[Optional[str], operator.add]
    nearby_labs_info: Annotated[Optional[str], operator.add]
    drug_advice_info: Annotated[Optional[str], operator.add]

    # For dynamic complex flows
    # The `operator.add` here might not be ideal for a list that gets replaced.
    # We'll manage its update carefully in the nodes.
    # Using a simple assignment in the nodes might be cleaner for 'generated_plan'.
    generated_plan: Optional[List[PlanStep]]
    # We'll pop from generated_plan, so no explicit index needed if we manage it carefully.

    # Intermediate data that might be passed/used between plan steps
    extracted_location: Optional[str]
    extracted_symptoms: Optional[str]
    suggested_tests: Annotated[Optional[List[str]], operator.add]

    final_response: str
    error_message: Optional[str]


def hospital_agent_executor(query: str, location: str = None) -> str:
    print(f"🏥 Hospital Agent called with query: '{query}', location: '{location or 'not specified'}'")
    if "delhi" in query.lower() or (location and "delhi" in location.lower()):
        return "Found Apollo Hospital, Max Hospital, and Fortis Hospital near Delhi. They all have excellent facilities."
    if "heart" in query.lower():
        return "Identified Escorts Heart Institute and Max Hospital Saket as specialized heart hospitals."
    return "Could not find specific hospital data for your query."

def lab_data_summarizer_agent_executor(pdf_path: str) -> str:
    print(f"📄 Lab Summarizer Agent called with PDF: '{pdf_path}'")
    # In reality, this would process the PDF
    return f"Summary of lab report '{pdf_path}': Key indicators are normal. Slight elevation in WBC."

def pathology_lab_finder_agent_executor(location: str, test_types: List[str] = None) -> str:
    tests_str = f" for tests: {', '.join(test_types)}" if test_types else ""
    print(f"🔬 Lab Finder Agent called for location: '{location}'{tests_str}")
    if "delhi" in location.lower():
        return f"Nearby labs in Delhi: Dr. Lal PathLabs, SRL Diagnostics {tests_str}."
    return f"Could not find labs for {location}{tests_str}."

def drug_agent_executor(symptom_or_query: str) -> str:
    print(f"💊 Drug Agent called with: '{symptom_or_query}'")
    if "fever" in symptom_or_query.lower():
        return "For fever, consider Paracetamol. Consult a doctor if it persists."
    if "heart heaviness" in symptom_or_query.lower():
        return "For heart heaviness, it's crucial to see a doctor. Possible preliminary tests include ECG, Echocardiogram, and Troponin levels. Do not self-medicate for this."
    return "I can provide general information about drugs. For specific medical advice, please consult a doctor."

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers.openai_functions import PydanticOutputFunctionsParser # or .json if preferred

# Initialize LLM (as before)
llm = ChatOpenAI(model="gpt-4o", temperature=0) # Or your preferred model

class OrchestratorDecision(BaseModel):
    """
    Decision model for the orchestrator.
    Determines the next single agent to call OR outlines a multi-step plan.
    If a plan is generated, 'next_agent_direct_call' should be null.
    If a direct call is made, 'plan_steps' should be null.
    """
    next_agent_direct_call: Optional[str] = Field(
        default=None,
        description="The single agent to call directly: 'hospital_agent', 'lab_summarizer_agent', 'lab_finder_agent', 'drug_agent', or 'generate_response'."
    )
    plan_steps: Optional[List[PlanStep]] = Field(
        default=None,
        description="A list of sequential steps (agent and its goal) if a multi-step process is required. Example: [{'agent_to_call': 'drug_agent', 'goal_for_agent': 'Suggest tests for symptoms X.'}, {'agent_to_call': 'lab_finder_agent', 'goal_for_agent': 'Find labs for suggested tests.'}]"
    )
    extracted_location: Optional[str] = Field(description="Any location explicitly mentioned or implied by the user query (e.g., 'delhi').")
    extracted_symptoms: Optional[str] = Field(description="Any symptoms mentioned by the user (e.g., 'fever', 'heart heaviness').")
    requires_pdf_summary: bool = Field(default=False, description="True if the user provided a PDF path and wants it summarized.")
    pdf_path: Optional[str] = Field(description="Path to the PDF if requires_pdf_summary is True.")
    reasoning: str = Field(description="Brief reasoning for the decision or plan.")


# Updated Router Prompt to guide the LLM for planning
# (Keep your agent mocks from the previous response)
# hospital_agent_executor, lab_data_summarizer_agent_executor, etc.

router_prompt_template_str = """
You are an expert medical query orchestrator and planner.
Your goal is to understand the user's request and decide the best course of action.
This might involve:
1. Calling a single specialized agent directly.
2. Devising a multi-step plan involving several agents if the query is complex and requires sequential information gathering.
3. Deciding to generate a final response if enough information is gathered or the query cannot be handled further.

Available agents and their functions:
- 'hospital_agent': Finds hospitals, details, or uses vector DB for brochures. Useful for: "Find hospital near X", "Tell me about Y hospital".
- 'lab_summarizer_agent': Summarizes PDF lab reports. User must provide a PDF path. Useful for: "Summarize this report.pdf".
- 'lab_finder_agent': Finds pathology labs near a location, optionally for specific tests. Useful for: "Find labs in Y", "Labs for blood test near Z".
- 'drug_agent': Answers medicine-related questions, symptom queries. Can suggest preliminary tests if appropriate for symptoms. Useful for: "What medicine for fever?", "I have symptom X, what could it be?", "What tests for symptom Y?".
- 'generate_response': Use this when all necessary information is gathered, or the query is too general/cannot be handled by other agents.

User's query: "{original_query}"
Current context/task: "{current_task_description}"

Current state of collected information (use this to avoid redundant steps):
- Hospital Info: {hospital_info}
- Lab Summary: {lab_summary_info}
- Nearby Labs: {nearby_labs_info}
- Drug Advice (may include test suggestions): {drug_advice_info}
- Suggested Tests (extracted explicitly): {suggested_tests}
- Extracted Location: {extracted_location}
- Extracted Symptoms: {extracted_symptoms}

Decision Process:
- Analyze the user's query and the current state.
- If the query is simple and can be handled by one agent: set 'next_agent_direct_call'.
- If the query is complex and requires a sequence (e.g., symptoms -> suggest tests -> find labs -> find specialized hospitals):
    - Define a 'plan_steps' list. Each step is a dictionary: {{"agent_to_call": "AGENT_NAME", "goal_for_agent": "SPECIFIC_TASK_FOR_AGENT"}}.
    - Ensure the plan is logical and builds upon previous steps. For example, don't try to find labs for tests before tests have been suggested.
- If enough information is gathered, or if the query cannot be processed further by the available agents, set 'next_agent_direct_call' to 'generate_response'.
- Extract 'extracted_location' and 'extracted_symptoms' if newly identified or relevant.
- If PDF summarization is clearly requested with a path, set 'requires_pdf_summary' and 'pdf_path'.
- Provide brief 'reasoning'.

IMPORTANT:
- If you create 'plan_steps', 'next_agent_direct_call' MUST be null/None.
- If you set 'next_agent_direct_call', 'plan_steps' MUST be null/None.
"""

router_prompt = ChatPromptTemplate.from_template(router_prompt_template_str)
# Bind the Pydantic model to the LLM (using function calling or with_structured_output)
# structured_llm_router = llm.with_structured_output(OrchestratorDecision) # Newer Langchain
# OR for older/more control:
parser = PydanticOutputFunctionsParser(pydantic_schema=OrchestratorDecision)
llm_with_tools = llm.bind_tools([OrchestratorDecision], tool_choice="OrchestratorDecision")
planner_chain = router_prompt | llm_with_tools | parser

def route_query_node(state: OrchestratorState):
    print(f"\n--- Router Node --- Current Task: {state.get('current_task_description', 'Initial Call')}")

    # Part 1: Execute next step if a plan is active
    active_plan = state.get("generated_plan")
    if active_plan and len(active_plan) > 0:
        next_step_details = active_plan.pop(0) # Get and remove the first step from the plan
        agent_for_step = next_step_details["agent_to_call"]
        goal_for_step = next_step_details["goal_for_agent"]

        print(f"Executing plan step: Agent='{agent_for_step}', Goal='{goal_for_step}'")
        print(f"Remaining plan steps: {len(active_plan)}")

        # Return instructions to call the agent for this step
        # The 'generated_plan' in the returned dict is the REMAINING plan.
        return {
            "generated_plan": active_plan if active_plan else None, # Pass on the modified plan
            "next_agent": agent_for_step,
            "current_task_description": goal_for_step, # This becomes the specific task for the agent
            # Carry over existing extracted entities, they might be needed by the agent
            "extracted_location": state.get("extracted_location"),
            "extracted_symptoms": state.get("extracted_symptoms"),
            "suggested_tests": state.get("suggested_tests"),
            # Ensure other agent results are also carried forward implicitly by TypedDict
        }

    # Part 2: If no active plan, call the LLM to decide/plan
    print("No active plan, calling LLM planner...")
    prompt_input = {
        "original_query": state["original_query"],
        "current_task_description": state.get("current_task_description", "Initial user query. Decide next single agent or create a plan."),
        "hospital_info": state.get("hospital_info"),
        "lab_summary_info": state.get("lab_summary_info"),
        "nearby_labs_info": state.get("nearby_labs_info"),
        "drug_advice_info": state.get("drug_advice_info"),
        "suggested_tests": state.get("suggested_tests"),
        "extracted_location": state.get("extracted_location"),
        "extracted_symptoms": state.get("extracted_symptoms"),
    }

    # decision = structured_llm_router.invoke(prompt_input) # if using with_structured_output
    decision_tool_call = planner_chain.invoke(prompt_input)
    if not isinstance(decision_tool_call, OrchestratorDecision): # when using bind_tools
        decision = OrchestratorDecision(**decision_tool_call.tool_calls[0]['args'])
    else: # when using with_structured_output
        decision = decision_tool_call

    print(f"LLM Planner Decision: Reasoning: '{decision.reasoning}'")
    print(f"  Next direct call: {decision.next_agent_direct_call}, Plan steps: {decision.plan_steps}")
    print(f"  Extracted Location: {decision.extracted_location}, Symptoms: {decision.extracted_symptoms}")

    # Prepare updates for the state based on planner's decision
    updates_to_state = {
        "extracted_location": decision.extracted_location or state.get("extracted_location"), # Prioritize new extraction
        "extracted_symptoms": decision.extracted_symptoms or state.get("extracted_symptoms"),
        "requires_pdf_summary": decision.requires_pdf_summary,
        "pdf_path": decision.pdf_path,
    }

    if decision.plan_steps and len(decision.plan_steps) > 0:
        print(f"LLM generated a new plan with {len(decision.plan_steps)} steps.")
        updates_to_state["generated_plan"] = decision.plan_steps
        # The first step of the plan will be executed in the next iteration of this router node
        updates_to_state["next_agent"] = "router" # Signal to loop back to router to start plan execution
        updates_to_state["current_task_description"] = "Starting execution of a newly generated plan."
        return updates_to_state

    elif decision.next_agent_direct_call:
        print(f"LLM decided direct call to: {decision.next_agent_direct_call}")
        updates_to_state["next_agent"] = decision.next_agent_direct_call
        updates_to_state["generated_plan"] = None # Clear any old plan
        updates_to_state["current_task_description"] = f"LLM directed call to {decision.next_agent_direct_call} for query: {state['original_query']}."
        return updates_to_state
    else:
        # Should ideally not happen if prompt is good, but as a fallback:
        print("LLM planner did not specify a next agent or a plan. Defaulting to generate_response.")
        updates_to_state["next_agent"] = "generate_response"
        updates_to_state["generated_plan"] = None
        updates_to_state["current_task_description"] = "Preparing to generate final response due to unclear next step from planner."
        return updates_to_state
    

def call_drug_agent_node(state: OrchestratorState):
    print("\n--- Drug Agent Node ---")
    # The 'current_task_description' will be the 'goal_for_agent' from the plan, or a general desc.
    task_goal = state.get("current_task_description", state["original_query"])
    
    # If the goal specifically mentions symptoms, prioritize those for the drug agent
    symptoms_for_agent = state.get("extracted_symptoms")
    query_for_drug_agent = task_goal # Start with the goal

    if symptoms_for_agent and symptoms_for_agent.lower() in task_goal.lower(): # if symptoms are part of task goal
        query_for_drug_agent = f"{task_goal} (Symptoms: {symptoms_for_agent})" # Make it more explicit if needed
    elif symptoms_for_agent and "suggest tests" in task_goal.lower(): # If goal is to suggest tests for known symptoms
        query_for_drug_agent = f"What preliminary tests are advisable for symptoms: {symptoms_for_agent}?"
    elif not symptoms_for_agent and "suggest tests" in task_goal.lower() and "symptoms" in task_goal.lower():
        # If goal is to suggest tests but symptoms aren't in state, the goal itself might contain them.
        # This relies on the planner LLM creating good goals.
        pass # query_for_drug_agent is already task_goal
    elif symptoms_for_agent: # General case if symptoms are known but not explicitly in goal
         query_for_drug_agent = f"{state.get('extracted_symptoms')}, {task_goal}" # Combine
    else: # Fallback to original query if nothing more specific
        query_for_drug_agent = state["original_query"]


    print(f"Drug agent to be called with: '{query_for_drug_agent}' based on goal: '{task_goal}'")
    result = drug_agent_executor(symptom_or_query=query_for_drug_agent)
    
    updates = {"drug_advice_info": result} # Add to existing advice potentially
    
    # Extract suggested tests if the goal was to suggest tests
    # And if the drug agent's output indicates tests were suggested
    if "suggest tests" in task_goal.lower() and \
       ("tests include" in result.lower() or "consider tests like" in result.lower() or "preliminary tests" in result.lower()):
        try:
            tests_part = ""
            patterns = ["tests include ", "consider tests like ", "preliminary tests are ", "suggest tests such as "]
            for p in patterns:
                if p in result.lower():
                    tests_part = result.lower().split(p, 1)[1].split(".")[0].strip()
                    break
            
            if tests_part:
                # Basic parsing, can be improved with regex or another LLM call for robust extraction
                raw_tests = [test.strip() for test in tests_part.split(', and')]
                raw_tests = [t for sublist in [s.split(',') for s in raw_tests] for t in sublist]
                suggested_tests_list = [t.strip().capitalize() for t in raw_tests if t.strip()]
                
                if suggested_tests_list:
                    # Combine with any previously suggested tests and ensure uniqueness
                    current_suggested_tests = state.get("suggested_tests") or []
                    updated_tests = list(set(current_suggested_tests + suggested_tests_list))
                    updates["suggested_tests"] = updated_tests
                    print(f"Extracted/Updated suggested tests: {updated_tests}")
        except Exception as e:
            print(f"Error parsing suggested tests from drug agent output: {e}")
            # Fallback or keep existing if parsing fails and tests already exist
            if not state.get("suggested_tests") and "ecg" in result.lower(): # crude fallback
                 updates["suggested_tests"] = ["ECG", "Blood test (general)"]


    updates["current_task_description"] = f"Completed drug agent task: {task_goal}"
    return updates

# Similar considerations for call_lab_finder_node (it needs location and suggested_tests from state)
# and call_hospital_agent_node (it needs location and potentially symptoms/test context).
def call_lab_finder_node(state: OrchestratorState):
    print("\n--- Lab Finder Node ---")
    task_goal = state.get("current_task_description", "Find nearby labs.")
    location = state.get("extracted_location")
    tests_to_find = state.get("suggested_tests")

    if not location:
        # Attempt to extract location from original query if not already found
        # This is a fallback, ideally planner or earlier steps should get it.
        # For a robust solution, you might have a dedicated "clarify_location" step/agent.
        # query_for_location_llm = f"Extract the location from this user query: {state['original_query']}. If no location, respond with 'None'."
        # extracted_loc = llm.invoke(query_for_location_llm).content
        # if extracted_loc.lower() != "none": location = extracted_loc
        print("Warning: Location not found in state for lab finder. Lab results might be inaccurate.")
        # Use a default or make it part of the query to the lab finder if it can handle ambiguity
        location = "user's general area" # Placeholder

    print(f"Lab Finder Agent called for location: '{location}', tests: {tests_to_find} (Goal: {task_goal})")
    result = pathology_lab_finder_agent_executor(location=location, test_types=tests_to_find)
    return {"nearby_labs_info": result, "current_task_description": f"Completed lab finding: {task_goal}"}


def call_hospital_agent_node(state: OrchestratorState):
    print("\n--- Hospital Agent Node ---")
    task_goal = state.get("current_task_description", state["original_query"])
    location = state.get("extracted_location")
    symptoms = state.get("extracted_symptoms") # Might be useful for finding specialized hospitals

    query_for_hospital_agent = task_goal
    if location and location.lower() not in query_for_hospital_agent.lower():
        query_for_hospital_agent += f" near {location}"
    if symptoms and "specialized" in task_goal.lower() and symptoms.lower() not in query_for_hospital_agent.lower():
         query_for_hospital_agent += f" for {symptoms}"


    print(f"Hospital Agent called with query: '{query_for_hospital_agent}' (Goal: {task_goal})")
    result = hospital_agent_executor(query=query_for_hospital_agent, location=location) # Pass location explicitly if your agent supports it
    return {"hospital_info": result, "current_task_description": f"Completed hospital search: {task_goal}"}

# call_lab_summarizer_node remains largely the same, as it's usually a direct request.
def call_lab_summarizer_node(state: OrchestratorState):
    print("\n--- Lab Summarizer Node ---")
    if not state.get("requires_pdf_summary") or not state.get("pdf_path"):
        return {"error_message": "PDF path not provided for summarization.", "current_task_description": "Error in lab summarizer."}
    result = lab_data_summarizer_agent_executor(pdf_path=state["pdf_path"])
    return {"lab_summary_info": result, "current_task_description": "Completed lab summary."}


def should_continue_routing(state: OrchestratorState):
    if state.get("error_message"):
        print("Error detected, routing to generate_response.")
        return "generate_response"

    next_node = state.get("next_agent")
    
    if next_node == "router": # If planner created a plan, or plan is ongoing
        print("Routing back to 'router' to process/continue plan.")
        return "router"
    elif next_node and next_node != "generate_response":
        print(f"Routing to '{next_node}'.")
        return next_node
    else: # Default to generate_response if no other specific next step
        print("No specific next agent, routing to 'generate_response'.")
        return "generate_response"
    
from langgraph.graph import StateGraph, END

# (Keep your mock agent executor functions)

# Create the graph
workflow = StateGraph(OrchestratorState)

# Add nodes
workflow.add_node("router", route_query_node)
workflow.add_node("hospital_agent", call_hospital_agent_node)
workflow.add_node("lab_summarizer_agent", call_lab_summarizer_node)
workflow.add_node("lab_finder_agent", call_lab_finder_node)
workflow.add_node("drug_agent", call_drug_agent_node)
workflow.add_node("generate_response", generate_response_node) # generate_response_node from previous example is fine

# Set entry point
workflow.set_entry_point("router")

# Conditional edges from the router
workflow.add_conditional_edges(
    "router",
    should_continue_routing,
    {
        "router": "router", # Loop back to router to process plan or re-plan
        "hospital_agent": "hospital_agent",
        "lab_summarizer_agent": "lab_summarizer_agent",
        "lab_finder_agent": "lab_finder_agent",
        "drug_agent": "drug_agent",
        "generate_response": "generate_response",
    }
)

# Edges from agent nodes BACK TO THE ROUTER
# After an agent completes its task, the router decides what's next (continue plan, re-plan, or finish)
workflow.add_edge("hospital_agent", "router")
workflow.add_edge("lab_summarizer_agent", "router")
workflow.add_edge("lab_finder_agent", "router")
workflow.add_edge("drug_agent", "router")

# Edge from generate_response to END
workflow.add_node("END", END) # Define END node for clarity if not implicitly handled
workflow.add_edge("generate_response", END)

# Compile the graph
app = workflow.compile()


def generate_response_node(state: OrchestratorState):
    print("\n--- Response Generation Node ---")
    if state.get("error_message"):
        final_response = f"An error occurred: {state['error_message']}"
    else:
        responses = []
        # Initial query context
        responses.append(f"Regarding your query: \"{state['original_query']}\"")

        # Order of information can be important for readability
        if state.get("extracted_symptoms"):
            responses.append(f"Identified symptoms: {state['extracted_symptoms']}.")
        if state.get("extracted_location"):
            responses.append(f"For location: {state['extracted_location']}.")

        if state.get("drug_advice_info"):
            # Check if test suggestions are already covered by suggested_tests to avoid redundancy
            advice = state["drug_advice_info"]
            if state.get("suggested_tests"):
                # Basic attempt to remove explicit test list from drug advice if already in suggested_tests
                for test_item in state["suggested_tests"]:
                    if test_item.lower() in advice.lower():
                        advice = advice.replace(test_item, "", 1) # Replace first occurrence
                        advice = advice.replace(test_item.capitalize(), "", 1)
                advice = advice.replace("tests include : ,", "tests include:").replace("tests include ,", "tests include:")
                advice = " ".join(advice.split()) # Clean up extra spaces
            responses.append(f"Medical & Drug Information:\n{advice}")

        if state.get("suggested_tests"):
            responses.append(f"Suggested Diagnostic Tests: {', '.join(state['suggested_tests'])}.")
        
        if state.get("nearby_labs_info"):
            responses.append(f"Nearby Labs Information:\n{state['nearby_labs_info']}")
        
        if state.get("hospital_info"):
            responses.append(f"Hospital Information:\n{state['hospital_info']}")
        
        if state.get("lab_summary_info"):
            responses.append(f"Lab Report Summary:\n{state['lab_summary_info']}")

        if len(responses) <= 1 : # Only original query
            final_response = "I'm sorry, I couldn't fully process your request with the available information or agents. Please try rephrasing or providing more details."
        else:
            final_response = "\n\n".join(responses)
            
    return {"final_response": final_response, "current_task_description": "Final response generated."}



# Test Cases

# 1. Simple hospital request (should be a direct call, no plan)
print("\n--- Test Case 1: Simple Hospital Request ---")
inputs1 = {"original_query": "I need hospital details near Delhi.", "current_task_description": "Initial user query."}
for event in app.stream(inputs1, {"recursion_limit": 25}):
    # print(event) # For full event details
    for k, v_dict in event.items():
        if k != "__end__":
            print(f"State after node '{k}':")
            # print(f"  Full state: {v_dict}") # For debugging full state
            print(f"    Current Task: {v_dict.get('current_task_description')}")
            if v_dict.get('generated_plan') is not None: # Check if None explicitly
                 print(f"    Active Plan: {v_dict.get('generated_plan')}")
            if v_dict.get('final_response'):
                 print(f"    Final Response Preview: {v_dict.get('final_response')[:100]}...")

print(f"\nFinal Output for Test Case 1:\n{event['__end__']['final_response']}")


# 2. Complex query that should generate a plan
print("\n\n--- Test Case 2: Complex Symptom Query (expecting a plan) ---")
inputs2 = {
    "original_query": "I'm feeling heaviness in my chest and shortness of breath. I live in Mumbai. What should I do?",
    "current_task_description": "Initial user query."
}
for event in app.stream(inputs2, {"recursion_limit": 25}):
    for k, v_dict in event.items():
        if k != "__end__":
            print(f"State after node '{k}':")
            print(f"    Current Task: {v_dict.get('current_task_description')}")
            if v_dict.get('generated_plan') is not None:
                 print(f"    Active Plan: {v_dict.get('generated_plan')}")
            if v_dict.get('suggested_tests'):
                 print(f"    Suggested Tests: {v_dict.get('suggested_tests')}")
            if v_dict.get('final_response'):
                 print(f"    Final Response Preview: {v_dict.get('final_response')[:100]}...")
print(f"\nFinal Output for Test Case 2:\n{event['__end__']['final_response']}")


# 3. Drug query only
print("\n\n--- Test Case 3: Simple Drug Query ---")
inputs3 = {
    "original_query": "What medicine can I take for a headache?",
    "current_task_description": "Initial user query."
}
for event in app.stream(inputs3, {"recursion_limit": 25}):
    for k, v_dict in event.items():
        if k != "__end__":
            print(f"State after node '{k}':")
            print(f"    Current Task: {v_dict.get('current_task_description')}")
            if v_dict.get('final_response'):
                 print(f"    Final Response Preview: {v_dict.get('final_response')[:100]}...")
print(f"\nFinal Output for Test Case 3:\n{event['__end__']['final_response']}")

# To visualize (optional, requires graphviz and other dependencies)
# from IPython.display import Image, display
# try:
#     img_bytes = app.get_graph().draw_mermaid_png()
#     with open("orchestrator_graph.png", "wb") as f:
#         f.write(img_bytes)
#     print("\nGraph saved to orchestrator_graph.png")
#     # display(Image(img_bytes)) # if in Jupyter
# except Exception as e:
#     print(f"Could not draw graph: {e}")